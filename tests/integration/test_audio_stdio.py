"""Real MCP + FFmpeg acceptance, with explicitly fake AEP metadata; no AE calls."""
import asyncio
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
from uuid import uuid4

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest

from astra_video_studio.audio import AudioService, AudioTarget, AudioInspect, AudioClipSet
from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import write_json
from astra_video_studio.media import audio as media
from astra_video_studio.media.preview import verify_probe
from astra_video_studio.responses import encoded, COMPACT_BYTES

F = runpy.run_path('tests/fixtures/audio_scene.py')


async def exercise(workspace):
    workspace.mkdir(parents=True, exist_ok=True)
    source, comp = F['fake_project'](workspace)
    original = source.read_bytes()
    F['write_tone'](workspace/'bed.wav',20,1000)
    F['write_tone'](workspace/'hit.wav',0.5,10000,True)
    target={'project_id':F['PID'],'composition_id':F['CID'],'base_aep_sha256':digest(source)}
    params=StdioServerParameters(command=sys.executable,args=['-m','astra_video_studio.mcp_server'],
        env=dict(os.environ,ASTRA_WORKSPACE=str(workspace.resolve())))
    sizes=[]
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as client:
            await client.initialize()
            listing=await client.list_tools()
            assert len(listing.tools)==77
            async def call(name,request):
                response=await client.call_tool(name,{'request':request})
                assert not response.isError,response.content
                assert response.structuredContent.get('status')=='succeeded',response.content
                assert len(encoded(response.model_dump(mode='json',exclude_none=True)))<=COMPACT_BYTES
                sizes.append(len(encoded(response.model_dump(mode='json',exclude_none=True))))
                ref=response.structuredContent['evidence']
                raw=json.loads(Path(ref['path']).read_text(encoding='utf-8'))['result']
                assert digest(Path(ref['path']))==ref['sha256']
                return raw['data']
            bed=await call('audio_inspect',{'source_path':str((workspace/'bed.wav').resolve())})
            hit=await call('audio_inspect',{'source_path':str((workspace/'hit.wav').resolve())})
            assert bed['sample_count']==960000 and bed['source_sample_rate']==48000
            cues=await call('audio_markers_create',{'asset_id':hit['asset_id'],'markers':[{'sample':0,'label':'hit'}]})
            energy=await call('audio_markers_create',{'asset_id':hit['asset_id'],'method':'energy'})
            assert energy['audio_markers'] and energy['audio_markers'][0]['uncertainty_samples']==960
            state=await call('audio_clip_set',target|{'clip':{'asset_id':bed['asset_id'],'duration_frames':480,
                'gain_db':-6,'fade_in_frames':24,'fade_out_frames':48}})
            clips=[]
            for _ in range(2):
                state=await call('audio_clip_set',target|{'audio_state_sha256':state['audio_state_sha256'],
                    'clip':{'asset_id':hit['asset_id'],'duration_frames':12,'gain_db':-6,'fade_out_frames':2}})
                clips.append(state['clip_id'])
            state=await call('timeline_markers_set',target|{'audio_state_sha256':state['audio_state_sha256'],
                'markers':[{'marker_id':f'{i+8:032x}','frame':time*24,'label':'visual key'} for i,time in enumerate((3,10))]})
            state=await call('audio_sync_plan',target|{'audio_state_sha256':state['audio_state_sha256'],'bindings':[
                {'clip_id':clip,'marker_set_sha256':cues['marker_set_sha256'],
                 'source_marker_id':cues['audio_markers'][0]['marker_id'],'layer_id':F['LID'],
                 'property':'opacity','key_index':i+1} for i,clip in enumerate(clips)]})
            for section,total in [('audio_clips',3),('audio_markers',2)]:
                page=await client.call_tool('operation_query',{'request':{'evidence_sha256':state['audio_state_sha256'],'section':section}})
                assert not page.isError and page.structuredContent['total']==total
            # Correct tool/schema, rejected guard: must not start a native job on fake AEPs.
            jobs_before=len(list((workspace/'jobs').iterdir()))
            invalid=await client.call_tool('audio_preview_render',{'request':{
                **target,'base_aep_sha256':'0'*64,'audio_state_sha256':state['audio_state_sha256'],'duration':20}})
            assert invalid.isError and len(list((workspace/'jobs').iterdir()))==jobs_before
    service=AudioService(Settings(workspace.resolve()))
    render=workspace/'render';render.mkdir()
    wav,measurement=service.render(AudioTarget(**target,audio_state_sha256=state['audio_state_sha256']),0,480,render)
    assert measurement['sample_count']==960000
    ffmpeg,ffprobe=media.binaries(service.settings)
    picture=render/'synthetic-picture.mp4';video=render/'audio-preview.mp4'
    media.run([ffmpeg,'-nostdin','-v','error','-n','-f','lavfi','-i',
        "color=c=black:s=320x180:r=24:d=20,drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='between(t,3,3.04)+between(t,10,10.04)'",
        '-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',str(picture)],render/'picture.log')
    picture_sha=digest(picture)
    media.run([ffmpeg,'-nostdin','-v','error','-n','-i',str(picture),'-i',str(wav),'-map','0:v:0','-map','1:a:0',
        '-c:v','copy','-c:a','aac','-b:a','192k','-t','20',str(video)],render/'mux.log')
    media.run([ffprobe,'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(video)],render/'probe.json')
    probe=json.loads((render/'probe.json').read_text(encoding='utf-8-sig'))
    verified=verify_probe(probe,{'width':320,'height':180,'duration':20,'fps':24,'frame_count':480})
    audio_verified=media.verify_audio_probe(probe,20,24)
    media.run([ffmpeg,'-nostdin','-v','error','-xerror','-i',str(video),'-map','0:v:0','-map','0:a:0','-f','null','-'],render/'decode.log')
    decoded=render/'decoded.wav';media.decode(ffmpeg,video,decoded,render/'decode-audio.log')
    analyzed=media.analyze_pcm(decoded)
    assert analyzed['peak_linear']<=10**(-0.1/20)
    assert abs(analyzed['duration']-20)<=1/24
    events=[m['sample']/48000 for m in analyzed['energy_onsets']]
    errors=[min(abs(t-event) for event in events)*24 for t in (3,10)]
    assert max(errors)<=1
    pixels=render/'visual-events.gray'
    media.run([ffmpeg,'-nostdin','-v','error','-n','-i',str(video),'-vf',
        r'select=eq(n\,71)+eq(n\,72)+eq(n\,73)+eq(n\,239)+eq(n\,240)+eq(n\,241),scale=1:1,format=gray',
        '-fps_mode','passthrough','-f','rawvideo',str(pixels)],render/'visual-events.log')
    brightness=list(pixels.read_bytes())
    assert len(brightness)==6 and [v>200 for v in brightness]==[False,True,False,False,True,False]
    assert source.read_bytes()==original and digest(picture)==picture_sha
    assert not (workspace/'ae-pending.json').exists() and not (workspace/'preview-pending.json').exists()
    report={'scope':'real MCP and FFmpeg; fake saved AEP metadata; synthetic picture/audio; no AE/native execution or artistic review',
        'result':'succeeded','video':str(video.resolve()),'video_sha256':digest(video),'verification':verified,
        'audio_verification':audio_verified,'decoded_peak_dbfs':analyzed['peak_dbfs'],'event_error_frames':errors,
        'visual_event_probe':{'frames':[71,72,73,239,240,241],'gray':brightness,'method':'decoded pixels; not artistic review'},
        'compact_response_bytes':[min(sizes),max(sizes)],'audio_state_sha256':state['audio_state_sha256'],
        'source_unchanged':True,'human_listening':False,'full_human_playback':False}
    write_json(workspace/'acceptance.json',report)
    return report


@pytest.mark.integration
@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'),reason='Local FFmpeg required')
def test_audio_tools_and_twenty_second_mix(tmp_path):
    report=asyncio.run(asyncio.wait_for(exercise(tmp_path),timeout=120))
    assert report['verification']['frame_count']==480


@pytest.mark.integration
@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'),reason='Local FFmpeg required')
def test_loud_mix_and_changed_owned_audio_are_rejected(tmp_path):
    source,comp=F['fake_project'](tmp_path)
    F['write_tone'](tmp_path/'loud.wav',0.5,10000,True)
    service=AudioService(Settings(tmp_path))
    inspected=service.inspect(AudioInspect(source_path=str(tmp_path/'loud.wav')))
    assert inspected.status=='succeeded',inspected.error
    asset_id=inspected.data['asset_id']
    target={'project_id':F['PID'],'composition_id':F['CID'],'base_aep_sha256':digest(source)}
    state=service.clip_set(AudioClipSet(**target,clip={'asset_id':asset_id,'duration_frames':12,'gain_db':12}))
    assert state.status=='succeeded',state.error
    render=tmp_path/'render';render.mkdir()
    with pytest.raises(ValueError,match='peak ceiling'):
        service.render(AudioTarget(**target,audio_state_sha256=state.data['audio_state_sha256']),0,24,render)
    assert digest(source)==target['base_aep_sha256']
    pcm=service.settings.contained_path(f'audio/assets/{asset_id}/analysis.wav')
    with pcm.open('ab') as output: output.write(b'changed')
    with pytest.raises(ValueError,match='changed'):
        service.assets(state.data)


if __name__=='__main__':
    workspace=Path('workspace')/('sprint10-offline-'+uuid4().hex)
    report=asyncio.run(asyncio.wait_for(exercise(workspace),timeout=120))
    print(json.dumps({'acceptance':str((workspace/'acceptance.json').resolve()),'result':report['result']}))
