"""Opt-in second EC-0 milestone; fixed fixtures, no AE commands or engine switch."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from uuid import uuid4
from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import read_json,write_json
from astra_video_studio.media.ffmpeg import inspect_binary
from text_curves_oracles import verify_curves,raster_text_bounds

ROOT=Path(__file__).resolve().parent
REV='a41ff5015c6687db15a6f074a47b870b8f09fece'
FONT_SHA='40d692fce188e4471e2b3cba937be967878f631ad3ebbbdcd587687c7ebe0c82'


def receipt(raw,job,case):
    if len(raw)>8192:raise ValueError('Receipt exceeds 8KiB')
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:raise ValueError('Duplicate JSON key')
            result[k]=v
        return result
    def invalid(value):raise ValueError('Non-finite JSON')
    data=json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)
    if not isinstance(data,dict) or any(data.get(k)!=v for k,v in {'protocol':'astra-ec0-text-curves-v1','job_id':job,'case':case,'system_fonts_scanned':False}.items()):raise ValueError('Receipt identity mismatch')
    if data.get('system_fonts_scanned') is not False:raise ValueError('System font scan occurred')
    if case=='text-curves':
        expected={'status':'succeeded','upstream_revision':REV,'width':640,'height':360,'fps':30,'frame_count':61,'font_postscript':'Inter-Regular','font_sha256':FONT_SHA}
        if any(data.get(k)!=v for k,v in expected.items()) or data.get('font_preflight_passed') is not True or data.get('project_roundtrip_equal') is not True:raise ValueError('Success verification mismatch')
    else:
        errors={'missing-font':'FONT_MISSING:','unsupported-glyph':'GLYPH_UNSUPPORTED:','wrong-font-hash':'FONT_HASH_MISMATCH'}
        if case not in errors or data.get('status')!='failed' or not data.get('error','').startswith(errors[case]):raise ValueError('Expected negative refusal absent')
    return data


def main():
    s=Settings.from_env();base=s.contained_path('ec0');runs=s.contained_path('ec0/text-curves-runs');runs.mkdir(exist_ok=True)
    if list(base.glob('*/pending.json')):raise ValueError('Pending EC0 attempt requires inspection')
    exe=s.contained_path('ec0/target/debug/astra-ec0-text-curves.exe');binary=digest(exe)
    attempt=s.contained_path('ec0/text-curves-'+uuid4().hex);attempt.mkdir()
    for name in ('text-curves-plan.json','text-curves-layout-amendment-01.json'):
        shutil.copyfile(ROOT/name,attempt/name);assert digest(ROOT/name)==digest(attempt/name)
    plan=read_json(attempt/'text-curves-plan.json')
    reference=read_json(base/'dependencies-current.json');closure_path=s.contained_path(reference['closure_path']);meta_path=s.contained_path(reference['metadata_path'])
    assert digest(closure_path)==reference['closure_sha256'];closure=read_json(closure_path)
    assert not closure['gui_packages'] and closure['cargo_lock_sha256']==digest(ROOT/'worker/Cargo.lock') and closure['metadata_sha256']==digest(meta_path)
    shutil.copyfile(closure_path,attempt/'dependency-closure.json');shutil.copyfile(meta_path,attempt/'cargo-metadata.json')
    baseline={str(p):digest(p) for p in s.contained_path('projects').rglob('*.aep')};write_json(attempt/'aep-baseline.json',baseline)
    ffmpeg=inspect_binary('ffmpeg',s.ffmpeg);ffprobe=inspect_binary('ffprobe',s.ffprobe)
    if not ffmpeg.available or not ffprobe.available:raise ValueError('FFmpeg/FFprobe missing')
    reports=[]
    cases=[(case,1) for case in plan['negative_cases']]+[('text-curves',threads) for threads in (1,2,1)]
    for case,threads in cases:
        job=uuid4().hex;out=attempt/(job+'-stdout.json');err=attempt/(job+'-stderr.log');directory=s.contained_path('ec0/text-curves-runs/'+job)
        env=dict(os.environ,RAYON_NUM_THREADS=str(threads),TEMP=str(base/'temp'),TMP=str(base/'temp'))
        assert digest(exe)==binary
        write_json(attempt/'pending.json',{'phase':'dispatch_intent','job_id':job,'case':case,'binary_sha256':binary,'stdout':str(out)})
        with out.open('xb') as stdout,err.open('xb') as stderr:
            start=time.monotonic();child=subprocess.Popen([str(exe),'--root',str(runs),'--job',job,'--case',case],env=env,stdout=stdout,stderr=stderr,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            write_json(attempt/'pending.json',{'phase':'running','job_id':job,'pid':child.pid,'case':case,'binary_sha256':binary})
            code=child.wait(timeout=180)
        write_json(attempt/(job+'-exit.json'),{'job_id':job,'exit_code':code,'seconds':time.monotonic()-start})
        data=receipt(out.read_bytes() if out.stat().st_size<=8192 else b'x'*8193,job,case)
        row={'case':case,'threads':threads,'job_id':job,'receipt':data}
        if case!='text-curves':
            if code==0 or directory.exists():raise ValueError('Negative case wrote an output slot or succeeded')
            row['refused_before_output']=True
        else:
            if code!=0:raise ValueError('Worker failed')
            expected=['project.ecproj','result.json','curves.json','text.json']+[f'frame-{i:04}.png' for i in range(61)]
            if sorted(p.name for p in directory.iterdir())!=sorted(expected):raise ValueError('Unexpected or missing job outputs')
            for name in expected:
                path=directory/name
                if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()) or path.stat().st_size>16777216:raise ValueError('Output containment/size error')
            if read_json(directory/'result.json')!=data:raise ValueError('Receipt/file mismatch')
            row['curves']=verify_curves(read_json(directory/'curves.json'))
            text=read_json(directory/'text.json')
            for key in ('point','box'):
                if text[key]['font']!='Inter-Regular' or text[key]['missing_font'] or text[key]['all_glyph_faces_exact'] is not True:raise ValueError('Text substitution')
            if text['point']['byte_of_char'][4]!=len('AÇÃO'.encode('utf-8')) or text['box']['lines']!=2:raise ValueError('Unicode range/paragraph mismatch')
            raw=subprocess.run([ffmpeg.path,'-v','error','-i',str(directory/'frame-0030.png'),'-f','rawvideo','-pix_fmt','rgba','-'],capture_output=True,check=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)).stdout
            row['text_bounds']=raster_text_bounds(raw,640,360,text)
            row['files']=[{'name':name,'bytes':(directory/name).stat().st_size,'sha256':digest(directory/name)} for name in expected]
            row['frame_hashes']=[digest(directory/f'frame-{i:04}.png') for i in range(61)]
            if len(set(row['frame_hashes']))<30:raise ValueError('Motion raster is static or lost')
        reports.append(row)
        shutil.copyfile(attempt/'pending.json',attempt/(job+'-completed-pending.json'));(attempt/'pending.json').unlink()
    positive=[r for r in reports if r['case']=='text-curves']
    assert all(row['frame_hashes']==positive[0]['frame_hashes'] for row in positive)
    source=runs/positive[0]['job_id'];video=attempt/'text-curves.mp4'
    subprocess.run([ffmpeg.path,'-v','error','-framerate','30','-i',str(source/'frame-%04d.png'),'-frames:v','61','-c:v','libx264','-pix_fmt','yuv420p',str(video)],capture_output=True,check=True,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    probe=json.loads(subprocess.run([ffprobe.path,'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(video)],capture_output=True,check=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)).stdout)
    stream=probe['streams'][0]
    assert stream['width']==640 and stream['height']==360 and stream['codec_name']=='h264' and stream['avg_frame_rate']=='30/1' and int(stream['nb_read_frames'])==61
    assert abs(float(probe['format']['duration'])-61/30)<=1/30
    subprocess.run([ffmpeg.path,'-v','error','-xerror','-i',str(video),'-f','null','-'],capture_output=True,check=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert digest(exe)==binary and all(digest(Path(path))==sha for path,sha in baseline.items())
    record={'scope':'EC0 second milestone, fixed text and manual curves, no AE parity','directory':str(attempt),'upstream_revision':REV,'binary_sha256':binary,
        'cargo_lock_sha256':digest(ROOT/'worker/Cargo.lock'),'plan_sha256':digest(attempt/'text-curves-plan.json'),'amendment_sha256':digest(attempt/'text-curves-layout-amendment-01.json'),
        'dependency_closure_sha256':digest(attempt/'dependency-closure.json'),'reachable_packages':closure['reachable_package_count'],'gui_packages':closure['gui_packages'],
        'runs':reports,'cpu_png_deterministic':True,'prior_aep_files_verified':len(baseline),'full_decode_passed':True,'video_path':str(video),'video_sha256':digest(video),'probe':probe,
        'limits':['No AE parity or artistic approval','Manual fixed curves only; no general auto/continuous/roving edits','Point/box and one code-point color range; text animators pending','No AEP/effects/GPU/stress/full license acceptance']}
    write_json(attempt/'verification.json',record);write_json(base/'text-curves-current.json',{'directory':str(attempt),'verification_sha256':digest(attempt/'verification.json')})
    print(json.dumps({'directory':str(attempt),'positive_runs':3,'negative_refusals':3,'cpu_png_deterministic':True,'full_decode_passed':True,'prior_aep_files_verified':len(baseline),'metrics':positive[0]['curves']}))


if __name__=='__main__':main()
