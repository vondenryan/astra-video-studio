"""Explicit final-render contracts. Shares the guarded preview worker, not its limits."""
import json
import math
from pathlib import Path, PureWindowsPath
import shutil
import subprocess

from pydantic import Field, model_validator
from typing import Literal

from astra_video_studio.config import _containment_key
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import Job
from astra_video_studio.media.audio import binaries
from astra_video_studio.media.preview import PreviewService, frame_sequence
from astra_video_studio.motion_engine.schemas import StrictModel
from astra_video_studio.motion_engine.timeline import frame
from astra_video_studio.scene_editing import ID
from astra_video_studio.schemas import OperationResult
from astra_video_studio.audio import SHA


def destination_path(settings, value, require_new=True):
    if Path(value).is_absolute() or PureWindowsPath(value).drive:
        raise ValueError('Destination must be workspace-relative')
    path = settings.contained_path(value)
    if _containment_key(path) == _containment_key(settings.workspace.resolve()):
        raise ValueError('Destination cannot be the workspace root')
    if require_new and path.exists(): raise ValueError('Destination already exists; outputs are never overwritten')
    return path


class FinalRenderRequest(StrictModel):
    project_id: ID
    composition_id: ID
    base_aep_sha256: SHA
    audio_state_sha256: SHA | None = None
    preset: Literal['h264_aac', 'tiff_rgba8'] = 'h264_aac'
    start_time: float = Field(default=0, ge=0, le=300)
    duration: float = Field(default=30, ge=0.1, le=300)
    width: int = Field(default=1920, ge=64, le=3840)
    height: int = Field(default=1080, ge=64, le=2160)
    fps: float = Field(gt=0, le=120)
    destination: str = Field(min_length=1, max_length=240)
    color_policy: Literal['interpret_native_rgb_as_srgb']

    @model_validator(mode='after')
    def contract(self):
        if self.width % 2 or self.height % 2: raise ValueError('Final resolution must be even')
        if self.preset == 'h264_aac' and not self.audio_state_sha256:
            raise ValueError('Distribution preset requires an explicit audio state')
        return self


def final_plan(request, comp, settings):
    if request.duration > settings.final_max_seconds: raise ValueError('Final duration exceeds configured budget')
    if not math.isclose(request.fps, comp['fps'], abs_tol=1e-6, rel_tol=0):
        raise ValueError('FPS conversion/retiming is not supported; choose saved composition FPS')
    first, last = frame(request.start_time, comp['fps']), frame(request.start_time+request.duration, comp['fps'])
    count = last-first
    if count < 1 or count > settings.final_max_frames or last/comp['fps'] > comp['duration']+1e-6:
        raise ValueError('Final interval/frame count exceeds composition or configured budget')
    if comp['width'] > 3840 or comp['height'] > 2160:
        raise ValueError('Final native source exceeds 4K')
    if request.width > comp['width'] or request.height > comp['height']:
        raise ValueError('Final upscaling is not supported')
    if request.preset == 'tiff_rgba8' and (request.width != comp['width'] or request.height != comp['height']):
        raise ValueError('Native TIFF intermediate preserves source resolution; no implicit resampling')
    # Source native sequence + encoded/PNG/alpha intermediates, conservatively bounded.
    estimate = (comp['width']*comp['height']*16 + request.width*request.height*8)*count
    return {'purpose':'final', 'preset':request.preset, 'start_time':first/comp['fps'], 'duration':count/comp['fps'],
        'fps':comp['fps'], 'frame_count':count, 'width':request.width, 'height':request.height,
        'source_width':comp['width'], 'source_height':comp['height'], 'estimated_bytes':estimate,
        'color_policy':request.color_policy, 'output_depth_bits':8, 'alpha':request.preset=='tiff_rgba8',
        'alpha_association':'preserve native TIFF bytes/association' if request.preset=='tiff_rgba8' else 'native matted RGB; alpha discarded'}


def discover_presets(settings):
    ffmpeg, ffprobe = binaries(settings)
    output = subprocess.run([ffmpeg, '-hide_banner', '-encoders'], capture_output=True, text=True,
        encoding='utf-8', errors='replace', timeout=10, shell=False,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if output.returncode or len(output.stdout) > 1024*1024: raise ValueError('Encoder discovery failed')
    names = {line.split()[1] for line in output.stdout.splitlines() if len(line.split()) >= 2 and line.lstrip().startswith(('V','A'))}
    return {'ffmpeg_path':ffmpeg, 'ffprobe_path':ffprobe, 'native_validation':'per render acknowledgement and decoded output; not implied by discovery',
        'render_presets':[
            {'preset':'h264_aac','available':{'libx264','aac'}.issubset(names),'audio':True,'alpha':False,'depth':8,
             'rgb_interpretation':'sRGB explicit','matrix':'BT.709','range':'limited'},
            {'preset':'tiff_rgba8','available':'tiff' in names,
             'audio':'separate WAV if requested','alpha':True,'depth':8,'rgb_interpretation':'sRGB explicit',
             'alpha_association':'native TIFF, copied without reencoding; verify output module per render'}],
        'final_max_seconds':settings.final_max_seconds,'final_max_frames':settings.final_max_frames}


class RenderService(PreviewService):
    def presets(self):
        job = Job(self.settings, 'render_presets_list')
        try:
            data = discover_presets(self.settings)
            result = OperationResult(operation_id=job.id, status='succeeded', data=data)
        except Exception as exc:
            result = OperationResult(operation_id=job.id, status='failed', error=f'{type(exc).__name__}: {exc}')
        job.record(result.status, result=result.model_dump(mode='json'))
        return result

    def make_plan(self, request, comp):
        destination_path(self.settings, request.destination)
        plan = final_plan(request, comp, self.settings)
        if shutil.disk_usage(self.settings.workspace).free < plan['estimated_bytes']+256*1024*1024:
            raise ValueError('Insufficient disk for declared final frame budget')
        presets = discover_presets(self.settings)
        if not next(p for p in presets['render_presets'] if p['preset']==request.preset)['available']:
            raise ValueError('Requested final encoder preset unavailable')
        return plan

    def output_directory(self, job, request):
        path = destination_path(self.settings, request.destination)
        path.mkdir(parents=True, exist_ok=False)
        job.record('running', destination_path=str(path), purpose='final')
        return path

    @staticmethod
    def check_color(info):
        color = info.get('source_color', {})
        if color.get('bits_per_channel') != 8 or color.get('linearized') is not False:
            raise ValueError('Final preset supports non-linear 8-bit native output only; no implicit HDR/linear conversion')
        if color.get('working_space') not in ('', 'None', 'sRGB IEC61966-2.1'):
            raise ValueError('Native working space is outside the declared sRGB interpretation')

    def finish_sequence(self, job, request, source, source_hash, render_copy, plan, prepared,
                        first, pattern, output, ffmpeg, ffprobe, audio_mix, audio_measurement):
        self._process(job, [ffprobe,'-v','error','-show_streams','-of','json',pattern.replace('%05d',f'{first:05d}')], 'source_pixel_format',30)
        probe = json.loads((job.directory/'source_pixel_format.log').read_text(encoding='utf-8-sig'))
        pixel = probe['streams'][0].get('pix_fmt','')
        if pixel != 'rgba':
            raise ValueError('Native TIFF sequence is not 8-bit RGBA; refusing implicit depth/alpha conversion')
        if plan['width'] != plan['source_width'] or plan['height'] != plan['source_height']:
            raise ValueError('Native TIFF intermediate preserves source resolution; resizing needs a separate conversion contract')
        images=output/'frames';images.mkdir()
        native_frames=sorted((job.directory/'frames').iterdir())
        for index,path in enumerate(native_frames):
            self._check_cancel(job)
            target=images/f'frame_{index:05d}.tif'
            sha=digest(path);shutil.copyfile(path,target)
            if digest(path)!=sha or digest(target)!=sha: raise ValueError('Native TIFF copy changed bytes')
        output_first, output_pattern = frame_sequence(images, plan['frame_count'])
        self._process(job,[ffmpeg,'-nostdin','-v','error','-xerror','-framerate',str(plan['fps']),'-start_number',str(output_first),
            '-i',output_pattern,'-f','null','-'],'rgba_decode',120)
        raw=job.directory/'alpha.raw'
        self._process(job,[ffmpeg,'-nostdin','-v','error','-n','-framerate',str(plan['fps']),'-start_number',str(output_first),
            '-i',output_pattern,'-vf','alphaextract','-pix_fmt','gray','-f','rawvideo',str(raw)],'alpha_decode',120)
        if raw.stat().st_size != plan['width']*plan['height']*plan['frame_count']:
            raise ValueError('Alpha decoded frame/size mismatch')
        low,high=255,0
        with raw.open('rb') as stream:
            while block:=stream.read(1024*1024): low=min(low,min(block));high=max(high,max(block))
        from astra_video_studio.jobs import write_json
        sequence = {'schema_version':1,'frame_count':plan['frame_count'],'fps':plan['fps'],'width':plan['width'],'height':plan['height'],
            'frames':[{'path':p.name,'sha256':digest(p),'bytes':p.stat().st_size} for p in sorted(images.iterdir())],
            'alpha_verified':True,'alpha_min':low,'alpha_max':high,'transparency_exercised':low<255,'depth_bits':8,
            'source_pixel_format':pixel,'color_policy':request.color_policy,'source_color':prepared.data.get('source_color'),
            'alpha_association':prepared.data.get('output_settings',{}).get('Color'),
            'composition_background':prepared.data.get('composition_background'),
            'native_bytes_preserved':True,'native_output_settings':prepared.data.get('output_settings')}
        write_json(output/'sequence.json',sequence)
        mix_sha = None
        if audio_mix:
            mix_sha = digest(audio_mix)
            shutil.copyfile(audio_mix,output/'audio-mix.wav')
            if digest(audio_mix)!=mix_sha or digest(output/'audio-mix.wav')!=mix_sha:
                raise ValueError('Intermediate audio copy integrity mismatch')
        if digest(source)!=source_hash: raise ValueError('Source changed during intermediate encoding')
        if audio_mix:
            from astra_video_studio.audio import AudioService,AudioTarget
            target=AudioTarget.model_validate(request.model_dump(include={'project_id','composition_id','base_aep_sha256','audio_state_sha256'}))
            _,_,state=AudioService(self.settings).state(target);AudioService(self.settings).assets(state)
        raw.unlink()  # Exact job-owned decoded intermediate, after successful verification.
        return OperationResult(operation_id=job.id,status='succeeded',project_id=request.project_id,project_path=str(source),
            data={'purpose':'final','preset':'tiff_rgba8','source_sha256':source_hash,'audio_state_sha256':request.audio_state_sha256,
                'destination_path':str(output),'sequence_manifest_path':str(output/'sequence.json'),
                'sequence_manifest_sha256':digest(output/'sequence.json'),'verification':sequence | {'frames':'see sequence manifest'},
                'plan':plan,'ae_preparation':prepared.data,'audio_verification':audio_measurement,'audio_mix_sha256':mix_sha},
            artifacts=[str(output/'sequence.json'),str(render_copy),str(images),*([str(output/'audio-mix.wav')] if audio_mix else [])])
