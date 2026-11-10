"""Explicit Sprint10 native acceptance; creates a NEW AEP and leaves it open."""
import asyncio
import json
import os
from pathlib import Path
import runpy
import sys
import time
from uuid import uuid4

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest

from astra_video_studio.ae_bridge.idle_transport import IdleTransport
from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import write_json
from astra_video_studio.media.audio import analyze_pcm
from astra_video_studio.project_manager import ProjectManager

F=runpy.run_path('tests/fixtures/audio_scene.py')


@pytest.mark.ae_live
@pytest.mark.skipif(os.environ.get('ASTRA_RUN_AE_TESTS')!='1',reason='Opt-in Sprint10 native audio preview')
def test_twenty_second_native_picture_and_audio_through_mcp():
    settings=Settings.from_env()
    state=IdleTransport(settings).state()
    assert state and not state.get('active_job'), 'Reviewed bridge must already be ready; no automatic bootstrap in this test'
    assert not settings.contained_path('ae-pending.json').exists()
    assert not settings.contained_path('preview-pending.json').exists()
    existing={p:digest(Path(p)) for p in ProjectManager(settings).managed_paths()}
    out=settings.contained_path('sprint10-native-'+uuid4().hex);out.mkdir()
    F['write_tone'](out/'bed.wav',20,1000)
    F['write_tone'](out/'hit.wav',0.5,10000,True)
    async def exercise():
        params=StdioServerParameters(command=sys.executable,args=['-m','astra_video_studio.mcp_server'],env=dict(os.environ))
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as client:
                await client.initialize()
                operations=[]
                async def call(name,request):
                    response=await client.call_tool(name,{'request':request,'response_mode':'full'})
                    assert not response.isError,response.content
                    value=response.structuredContent
                    assert value['status']=='succeeded',value
                    operations.append({'tool':name,'operation_id':value['operation_id']})
                    return value
                created=await call('project_create',{'name':'Astra Sprint10 Audio Acceptance','title':'AUDIO SYNC',
                    'duration':20,'fps':24,'width':640,'height':360,'font_size':56})
                comp=created['data']['compositions'][0];layer=comp['layers'][0]
                pid=created['project_id'];cid=comp['composition_id'].split(':')[-1];lid=layer['layer_id'].split(':')[-1]
                animated=await call('motion_apply',{'project_id':pid,'composition_id':cid,'layer_id':lid,
                    'skill':'fade_in_out','duration':20,'params':{'fade_in':3,'fade_out':10,'motion_blur':False}})
                source=Path(animated['project_path']);source_sha=digest(source)
                keys=animated['data']['compositions'][0]['layers'][0]['transforms']['opacity']['keys']
                visual_indices=[next(i for i,k in enumerate(keys) if abs(k['time']-t)<1e-5) for t in (3,10)]
                target={'project_id':pid,'composition_id':cid,'base_aep_sha256':source_sha}
                bed=(await call('audio_inspect',{'source_path':str(out/'bed.wav')}))['data']
                hit=(await call('audio_inspect',{'source_path':str(out/'hit.wav')}))['data']
                cues=(await call('audio_markers_create',{'asset_id':hit['asset_id'],'markers':[{'sample':0,'label':'hit'}]}))['data']
                audio=(await call('audio_clip_set',target|{'clip':{'asset_id':bed['asset_id'],'duration_frames':480,
                    'gain_db':-6,'fade_in_frames':24,'fade_out_frames':48}}))['data']
                clips=[]
                for _ in range(2):
                    audio=(await call('audio_clip_set',target|{'audio_state_sha256':audio['audio_state_sha256'],
                        'clip':{'asset_id':hit['asset_id'],'duration_frames':12,'gain_db':-6,'fade_out_frames':2}}))['data']
                    clips.append(audio['clip_id'])
                audio=(await call('timeline_markers_set',target|{'audio_state_sha256':audio['audio_state_sha256'],
                    'markers':[{'marker_id':uuid4().hex,'frame':t*24,'label':'native opacity key'} for t in (3,10)]}))['data']
                audio=(await call('audio_sync_plan',target|{'audio_state_sha256':audio['audio_state_sha256'],'bindings':[
                    {'clip_id':clip,'marker_set_sha256':cues['marker_set_sha256'],
                        'source_marker_id':cues['audio_markers'][0]['marker_id'],'layer_id':lid,
                        'property':'opacity','key_index':index} for clip,index in zip(clips,visual_indices)]}))['data']
                submission=await client.call_tool('audio_preview_render',{'request':target|{
                    'audio_state_sha256':audio['audio_state_sha256'],'duration':20,'max_width':640}})
                assert not submission.isError,submission.content
                queued=submission.structuredContent;assert queued['status']=='queued',queued
                write_json(out/'submitted.json',{'project_id':pid,'source':str(source),'source_sha256':source_sha,
                    'job_id':queued['job_id'],'audio_state_sha256':audio['audio_state_sha256'],'operations':operations,
                    'existing_sources':existing,'scope':'native picture plus FFmpeg sidecar audio; no human playback/listening'})
                deadline=time.monotonic()+480
                last=None
                while time.monotonic()<deadline:
                    response=await client.call_tool('job_status',{'operation_id':queued['job_id'],'response_mode':'full'})
                    assert not response.isError,response.content
                    status=response.structuredContent
                    if status['status']!=last:print('native audio preview:',status['status'],flush=True);last=status['status']
                    if status['status'] not in ('queued','running'):break
                    await asyncio.sleep(1)
                assert status['status']=='succeeded',status
                result=status['result'];data=result['data']
                assert data['verification']['frame_count']==480 and data['verification']['duration']==pytest.approx(20,abs=1/24)
                assert data['audio_verification']['encoded_stream']['channels']==2
                decoded=analyze_pcm(Path(data['video_path']).parent/'audio-decoded.wav')
                events=[m['sample']/48000 for m in decoded['energy_onsets']]
                errors=[min(abs(t-event) for event in events)*24 for t in (3,10)]
                assert max(errors)<=1
                assert digest(source)==source_sha
                assert all(digest(Path(p))==h for p,h in existing.items())
                write_json(out/'acceptance.json',{'scope':'real native AE picture/keys and FFmpeg sidecar audio via MCP',
                    'result':result,'operations':operations,'event_error_frames':errors,'source_sha256':source_sha,
                    'existing_sources_preserved':True,'existing_sources':existing,'native_visual_key_times':[3,10],
                    'audio_state_sha256':audio['audio_state_sha256'],'human_listening':False,'human_full_playback':False,
                    'sampled_visual_review':'not_yet_performed'})
                print('SPRINT10_ACCEPTANCE='+str(out/'acceptance.json'),flush=True)
    asyncio.run(asyncio.wait_for(exercise(),timeout=600))
