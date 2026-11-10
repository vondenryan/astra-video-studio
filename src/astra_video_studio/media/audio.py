"""Bounded owned FFmpeg audio jobs. No AE, shell, arbitrary filters or paths."""
from array import array
import json
import math
from pathlib import Path
import subprocess
import sys
import wave

from astra_video_studio.media.ffmpeg import inspect_binary

RATE = 48000
CHANNELS = 2
MAX_SECONDS = 300


def binaries(settings):
    values = [inspect_binary(n, getattr(settings, n)) for n in ('ffmpeg', 'ffprobe')]
    if any(not v.available or v.error for v in values):
        raise ValueError('; '.join(v.error or 'Media executable unavailable' for v in values if not v.available or v.error))
    return values[0].path, values[1].path


def run(command, log, timeout=120):
    with Path(log).open('x', encoding='utf-8') as output:
        completed = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
            timeout=timeout, shell=False, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if completed.returncode:
        raise ValueError(f'Audio stage failed (exit {completed.returncode}); see {log}')


def probe(binary, source, log):
    run([binary, '-v', 'error', '-protocol_whitelist', 'file,pipe', '-show_streams', '-show_format', '-of', 'json', str(source)], log, 30)
    if Path(log).stat().st_size > 1024*1024:
        raise ValueError('Audio probe metadata exceeds limit')
    return json.loads(Path(log).read_text(encoding='utf-8-sig'))


def decode(binary, source, target, log):
    run([binary, '-nostdin', '-v', 'error', '-xerror', '-n', '-protocol_whitelist', 'file,pipe',
        '-i', str(source), '-map', '0:a:0', '-vn', '-sn', '-dn', '-t', str(MAX_SECONDS+1),
        '-ac', str(CHANNELS), '-ar', str(RATE), '-c:a', 'pcm_s16le', str(target)], log)


def analyze_pcm(path):
    """Sample peak/RMS and conservative 20ms energy-rise candidates, not true peak/beats."""
    peak = total = samples = 0
    candidates = []
    previous = 0.0
    last_onset = -RATE
    with wave.open(str(path), 'rb') as stream:
        if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate()) != (CHANNELS, 2, RATE):
            raise ValueError('Expected owned 48kHz stereo PCM16 analysis file')
        frames = stream.getnframes()
        if not 0 < frames <= MAX_SECONDS*RATE:
            raise ValueError('Audio must span more than zero and at most 300 seconds')
        offset = 0
        while raw := stream.readframes(960):
            values = array('h', raw)
            if sys.byteorder != 'little': values.byteswap()
            energy = sum(v*v for v in values)
            level = math.sqrt(energy/len(values))/32768
            peak = max(peak, max(abs(v) for v in values))
            total += energy
            samples += len(values)
            if level >= 10**(-24/20) and level >= max(previous*2.82, 0.001) and offset-last_onset >= RATE*0.12:
                if len(candidates) < 256:
                    candidates.append({'sample': offset, 'confidence': min(0.95, 1-previous/max(level, 1e-9)),
                        'method': '20ms_energy_rise', 'uncertainty_samples': 960})
                last_onset = offset
            previous = level
            offset += len(values)//CHANNELS
    def db(value): return 20*math.log10(value) if value > 0 else None
    return {'sample_rate': RATE, 'channels': CHANNELS, 'sample_count': frames, 'duration': frames/RATE,
        'peak_dbfs': db(peak/32768), 'rms_dbfs': db(math.sqrt(total/samples)/32768),
        'peak_linear': peak/32768, 'energy_onsets': candidates,
        'analysis': 'decoded PCM16 sample peak/RMS; no true-peak, LUFS or semantic beat claim'}


def sample_at_frame(value, fps):
    return int(math.floor(value*RATE/fps+0.5))


def mix_command(binary, state, assets, start_frame, count, target):
    fps = state['fps']
    full_samples = sample_at_frame(state['duration_frames'], fps)
    first = sample_at_frame(start_frame, fps)
    length = sample_at_frame(start_frame+count, fps)-first
    command = [binary, '-nostdin', '-v', 'error', '-n', '-filter_complex_threads', '1',
        '-f', 'lavfi', '-i', f'anullsrc=r={RATE}:cl=stereo']
    filters = [f'[0:a]atrim=end_sample={full_samples},asetpts=PTS-STARTPTS[base]']
    names = ['[base]']
    for i, clip in enumerate(state['audio_clips'], 1):
        command += ['-protocol_whitelist', 'file,pipe', '-i', str(assets[clip['asset_id']]['pcm_path'])]
        duration = sample_at_frame(clip['duration_frames'], fps)
        fade_in = sample_at_frame(clip['fade_in_frames'], fps)
        fade_out = sample_at_frame(clip['fade_out_frames'], fps)
        chain = (f'[{i}:a]atrim=start_sample={clip["source_start_sample"]}:end_sample={clip["source_start_sample"]+duration},'
            f'asetpts=PTS-STARTPTS,volume={clip["gain_db"]}dB')
        if fade_in: chain += f',afade=t=in:ss=0:ns={fade_in}'
        if fade_out: chain += f',afade=t=out:ss={duration-fade_out}:ns={fade_out}'
        chain += f',adelay={sample_at_frame(clip["start_frame"], fps)}S:all=1[c{i}]'
        filters.append(chain)
        names.append(f'[c{i}]')
    filters.append(''.join(names)+f'amix=inputs={len(names)}:duration=first:dropout_transition=0:normalize=0,'
        f'atrim=start_sample={first}:end_sample={first+length},asetpts=PTS-STARTPTS,'
        f'apad=whole_len={length},atrim=end_sample={length}[mix]')
    return command + ['-filter_complex', ';'.join(filters), '-map', '[mix]', '-ar', str(RATE),
        '-ac', str(CHANNELS), '-c:a', 'pcm_s16le', str(target)]


def verify_audio_probe(probed, duration, fps):
    streams = [s for s in probed.get('streams', []) if s.get('codec_type') == 'audio']
    if len(streams) != 1: raise ValueError('Expected exactly one preview audio stream')
    audio = streams[0]
    actual = float(audio.get('duration', 'nan'))
    if audio.get('codec_name') != 'aac' or int(audio.get('sample_rate', 0)) != RATE or audio.get('channels') != CHANNELS:
        raise ValueError('Preview audio must be AAC/48kHz/stereo')
    if not math.isfinite(actual) or abs(actual-duration) > 1/fps:
        raise ValueError('Preview audio duration differs by more than one frame')
    video = [s for s in probed.get('streams', []) if s.get('codec_type') == 'video']
    if len(video) != 1: raise ValueError('Expected one video stream alongside audio')
    delta = abs(float(audio.get('start_time', 0))-float(video[0].get('start_time', 0)))
    if not math.isfinite(delta) or delta > 1/fps:
        raise ValueError('Audio/video stream starts differ by more than one frame')
    return {'codec': 'aac', 'sample_rate': RATE, 'channels': CHANNELS,
        'duration': actual, 'stream_start_delta': delta, 'event_sync_measured': False}
