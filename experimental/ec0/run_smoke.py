"""Explicit local EC-0 smoke test. Never imported by the production MCP server."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from uuid import uuid4

from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import read_json, write_json
from astra_video_studio.media.ffmpeg import inspect_binary

REVISION = 'a41ff5015c6687db15a6f074a47b870b8f09fece'
ROOT = Path(__file__).resolve().parent


def parse_receipt(raw, job):
    if len(raw) > 8192: raise ValueError('EC0 stdout exceeds receipt budget')
    def pairs(items):
        result = {}
        for key,value in items:
            if key in result: raise ValueError('Duplicate receipt key')
            result[key] = value
        return result
    def invalid_constant(value): raise ValueError('Non-finite receipt value')
    data = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)
    expected = {'protocol':'astra-ec0-v1','job_id':job,'status':'succeeded',
        'upstream_revision':REVISION,'backend':'effectcraft-cpu','width':160,'height':90,'fps':30,'frame_count':6}
    if not isinstance(data,dict) or any(data.get(k)!=v for k,v in expected.items()):
        raise ValueError('EC0 receipt identity/status/fixture mismatch')
    if data.get('project_roundtrip_equal') is not True or data.get('pixel_probes_passed') is not True:
        raise ValueError('EC0 verification missing')
    return data


def main():
    settings = Settings.from_env()
    executable = settings.contained_path('ec0/target/debug/astra-ec0-probe.exe')
    if not executable.is_file(): raise ValueError('Build the pinned EC0 probe first')
    base = settings.contained_path('ec0'); runs = settings.contained_path('ec0/runs'); runs.mkdir(exist_ok=True)
    if list(base.glob('smoke-*/pending.json')): raise ValueError('Retained EC0 pending run: inspect before continuing')
    attempt = settings.contained_path('ec0/smoke-'+uuid4().hex); attempt.mkdir()
    shutil.copyfile(ROOT/'acceptance-plan.json',attempt/'acceptance-plan.json')
    assert digest(ROOT/'acceptance-plan.json')==digest(attempt/'acceptance-plan.json')
    binary_sha = digest(executable)
    reference=read_json(base/'dependencies-current.json')
    closure_path=settings.contained_path(reference['closure_path'])
    metadata_path=settings.contained_path(reference['metadata_path'])
    assert digest(closure_path)==reference['closure_sha256']
    closure=read_json(closure_path)
    assert closure['gui_packages']==[]
    assert closure['metadata_sha256']==digest(metadata_path)
    assert closure['cargo_lock_sha256']==digest(ROOT/'worker/Cargo.lock')
    shutil.copyfile(closure_path,attempt/'dependency-closure.json')
    shutil.copyfile(metadata_path,attempt/'cargo-metadata.json')
    baseline = {str(p):digest(p) for p in settings.contained_path('projects').rglob('*.aep')}
    write_json(attempt/'aep-baseline.json',baseline)
    ffmpeg = inspect_binary('ffmpeg',settings.ffmpeg); ffprobe = inspect_binary('ffprobe',settings.ffprobe)
    if not ffmpeg.available or not ffprobe.available: raise ValueError('FFmpeg/FFprobe missing')
    reports = []
    for threads in (1,2,1):
        job = uuid4().hex
        stdout,stderr = attempt/(job+'-stdout.json'),attempt/(job+'-stderr.log')
        env = dict(os.environ,RAYON_NUM_THREADS=str(threads))
        env['TEMP']=str(settings.contained_path('ec0/temp')); env['TMP']=env['TEMP']
        assert digest(executable)==binary_sha
        with stdout.open('xb') as out,stderr.open('xb') as err:
            start=time.monotonic()
            write_json(attempt/'pending.json',{'job_id':job,'phase':'dispatch_intent','executable_sha256':binary_sha,'stdout':str(stdout)})
            process=subprocess.Popen([str(executable),'--root',str(runs),'--job',job],env=env,stdout=out,stderr=err,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            write_json(attempt/'pending.json',{'job_id':job,'pid':process.pid,'executable_sha256':binary_sha,'stdout':str(stdout)})
            # wait() leaves an uncertain child running on timeout. No kill or replay.
            code=process.wait(timeout=30)
        elapsed=time.monotonic()-start
        write_json(attempt/(job+'-exit.json'),{'job_id':job,'exit_code':code,'seconds':elapsed})
        if code: raise ValueError('EC0 worker failed; retained attempt/pending and logs, inspect before retry')
        receipt=parse_receipt(stdout.read_bytes() if stdout.stat().st_size<=8192 else b'x'*8193,job)
        directory=settings.contained_path('ec0/runs/'+job)
        if read_json(directory/'result.json')!=receipt: raise ValueError('EC0 file/stdout evidence mismatch')
        paths=[directory/'project.ecproj',directory/'result.json',*[directory/f'frame-{i:04}.png' for i in range(6)]]
        for path in paths:
            if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):raise ValueError('EC0 output escaped job')
            if not path.is_file() or path.stat().st_size>16*1024*1024:raise ValueError('EC0 missing/oversized output')
        frames=[digest(directory/f'frame-{i:04}.png') for i in range(6)]
        if len(set(frames))!=1: raise ValueError('Static EC0 fixture changed across frames')
        # Preserve the exact pending bytes before clearing this proven completed slot.
        shutil.copyfile(attempt/'pending.json',attempt/(job+'-completed-pending.json'))
        (attempt/'pending.json').unlink()
        reports.append({'job_id':job,'threads':threads,'seconds':elapsed,'receipt':receipt,
            'files':[{ 'name':p.name,'sha256':digest(p),'bytes':p.stat().st_size} for p in paths]})
    frame_sets=[[f['sha256'] for f in row['files'] if f['name'].endswith('.png')] for row in reports]
    if not all(row==frame_sets[0] for row in frame_sets):raise ValueError('CPU/thread determinism failed')
    source = settings.contained_path('ec0/runs/'+reports[0]['job_id'])
    video = attempt/'smoke.mp4'
    subprocess.run([ffmpeg.path,'-v','error','-framerate','30','-start_number','0','-i',str(source/'frame-%04d.png'),
        '-frames:v','6','-c:v','libx264','-pix_fmt','yuv420p',str(video)],check=True,capture_output=True,timeout=30,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    probe=subprocess.run([ffprobe.path,'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(video)],
        check=True,capture_output=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    metadata=json.loads(probe.stdout); stream=metadata['streams'][0]
    assert stream['codec_name']=='h264' and stream['width']==160 and stream['height']==90
    assert stream['avg_frame_rate']=='30/1' and int(stream['nb_read_frames'])==6
    assert abs(float(metadata['format']['duration'])-.2)<=1/30
    subprocess.run([ffmpeg.path,'-v','error','-xerror','-i',str(video),'-f','null','-'],check=True,capture_output=True,
        timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert digest(executable)==binary_sha
    assert all(digest(Path(path))==sha for path,sha in baseline.items())
    record={'scope':'EC0 first milestone: fixed opaque solids, not full EC0 acceptance','directory':str(attempt),
        'upstream_revision':REVISION,'binary_sha256':binary_sha,'cargo_lock_sha256':digest(ROOT/'worker/Cargo.lock'),
        'plan_sha256':digest(attempt/'acceptance-plan.json'),'runs':reports,'cpu_png_deterministic':True,
        'reachable_packages':closure['reachable_package_count'],'gui_packages':closure['gui_packages'],
        'dependency_closure_sha256':digest(attempt/'dependency-closure.json'),
        'prior_aep_files_verified':len(baseline),'video_sha256':digest(video),'video_path':str(video),
        'full_decode_passed':True,'probe':metadata,'remaining_gates':read_json(ROOT/'acceptance-plan.json')['remaining_ec0_scope']}
    write_json(attempt/'verification.json',record)
    write_json(base/'smoke-current.json',{'directory':str(attempt),'verification_sha256':digest(attempt/'verification.json')})
    print(json.dumps({'directory':str(attempt),'cpu_png_deterministic':True,'full_decode_passed':True,
        'prior_aep_files_verified':len(baseline),'ec0_status':'in_progress'}))


if __name__=='__main__':main()
