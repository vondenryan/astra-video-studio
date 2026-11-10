"""Opt-in Sprint11: new 30s1080p AEP, distribution+alpha render, collected package/reopen."""
import asyncio
import json
import os
from pathlib import Path
import runpy
import struct
import sys
import time
from uuid import uuid4
import zlib

from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest

from astra_video_studio.ae_bridge.idle_transport import IdleTransport
from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import write_json
from astra_video_studio.media.audio import analyze_pcm
from astra_video_studio.project_manager import ProjectManager

F=runpy.run_path('tests/fixtures/audio_scene.py')


def png(path):
    def chunk(name,data):return struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data)&0xffffffff)
    pixels=b''.join(b'\0'+bytes([40,180,220,255])*64 for _ in range(64))
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',64,64,8,6,0,0,0))+
        chunk(b'IDAT',zlib.compress(pixels))+chunk(b'IEND',b''))


@pytest.mark.ae_live
@pytest.mark.skipif(os.environ.get('ASTRA_RUN_AE_TESTS')!='1',reason='Opt-in Sprint11 native delivery acceptance')
def test_final_1080p_audio_alpha_and_collected_project():
    settings=Settings.from_env();state=IdleTransport(settings).state()
    assert state and not state.get('active_job'),'Reviewed bridge must already be ready'
    assert not settings.contained_path('ae-pending.json').exists()
    assert not settings.contained_path('preview-pending.json').exists()
    original={p:digest(Path(p)) for p in ProjectManager(settings).managed_paths()}
    out=settings.contained_path('sprint11-native-'+uuid4().hex);out.mkdir()
    write_json(out/'preservation-baseline.json',{'existing_sources':original,'scope':'baseline before native Sprint11 operations'})
    png(out/'mark.png');F['write_tone'](out/'bed.wav',30,1000);F['write_tone'](out/'hit.wav',0.5,10000,True)
    async def exercise():
        params=StdioServerParameters(command=sys.executable,args=['-m','astra_video_studio.mcp_server'],env=dict(os.environ))
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as client:
                await client.initialize()
                operations=[]
                async def call(name,request=None):
                    args={'response_mode':'full'}
                    if request is not None:args['request']=request
                    response=await client.call_tool(name,args)
                    assert not response.isError,response.content
                    result=response.structuredContent;assert result['status']=='succeeded',result
                    operations.append({'tool':name,'operation_id':result['operation_id']})
                    write_json(out/'operations.json',{'operations':operations})
                    return result
                presets=await call('render_presets_list')
                assert all(p['available'] for p in presets['data']['render_presets'])
                created=await call('project_create',{'name':'Astra Sprint11 Final Delivery','title':'FINAL DELIVERY',
                    'width':1920,'height':1080,'fps':24,'duration':30,'font_size':96})
                comp=created['data']['compositions'][0];layer=comp['layers'][0]
                pid=created['project_id'];cid=comp['composition_id'].split(':')[-1];lid=layer['layer_id'].split(':')[-1]
                await call('motion_apply',{'project_id':pid,'composition_id':cid,'layer_id':lid,'skill':'fade_in_out','duration':30,
                    'params':{'fade_in':3,'fade_out':10,'motion_blur':False}})
                imported=await call('media_import',{'project_id':pid,'source_path':str(out/'mark.png')})
                await call('layer_create',{'project_id':pid,'composition_id':cid,'layer':{'kind':'media',
                    'name':'Collected mark','asset_id':imported['data']['asset_id'],'position':[400,700],'out_point':30}})
                final=await call('effect_apply',{'project_id':pid,'composition_id':cid,'layer_id':lid,'effect':'fill',
                    'params':{'color':[0.3,0.85,1]}})
                source=Path(final['project_path']);source_sha=digest(source)
                write_json(out/'source.json',{'source':str(source),'source_sha256':source_sha,'project_id':pid,'composition_id':cid})
                keys=next(l for l in final['data']['compositions'][0]['layers'] if l['layer_id']=='astra:layer:'+lid)['transforms']['opacity']['keys']
                indices=[next(i for i,k in enumerate(keys) if abs(k['time']-t)<1e-5) for t in (3,20)]
                base={'project_id':pid,'composition_id':cid,'base_aep_sha256':source_sha}
                bed=(await call('audio_inspect',{'source_path':str(out/'bed.wav')}))['data']
                hit=(await call('audio_inspect',{'source_path':str(out/'hit.wav')}))['data']
                cues=(await call('audio_markers_create',{'asset_id':hit['asset_id'],'markers':[{'sample':0,'label':'hit'}]}))['data']
                audio=(await call('audio_clip_set',base|{'clip':{'asset_id':bed['asset_id'],'duration_frames':720,
                    'gain_db':-6,'fade_in_frames':24,'fade_out_frames':48}}))['data']
                clips=[]
                for _ in range(2):
                    audio=(await call('audio_clip_set',base|{'audio_state_sha256':audio['audio_state_sha256'],
                        'clip':{'asset_id':hit['asset_id'],'duration_frames':12,'gain_db':-6,'fade_out_frames':2}}))['data']
                    clips.append(audio['clip_id'])
                audio=(await call('audio_sync_plan',base|{'audio_state_sha256':audio['audio_state_sha256'],'bindings':[
                    {'clip_id':clip,'marker_set_sha256':cues['marker_set_sha256'],
                        'source_marker_id':cues['audio_markers'][0]['marker_id'],'layer_id':lid,'property':'opacity','key_index':i}
                    for clip,i in zip(clips,indices)]}))['data']
                async def render(request,label):
                    response=await client.call_tool('render_submit',{'request':request})
                    assert not response.isError,response.content
                    queued=response.structuredContent;assert queued['status']=='queued',queued
                    write_json(out/(label+'-submitted.json'),{'job_id':queued['job_id'],'request':request})
                    deadline=time.monotonic()+1000;last=None
                    while time.monotonic()<deadline:
                        response=await client.call_tool('job_status',{'operation_id':queued['job_id'],'response_mode':'full'})
                        assert not response.isError,response.content
                        record=response.structuredContent
                        current=(record['status'],record.get('stage'))
                        if current!=last:print(label,current,flush=True);last=current
                        if record['status'] not in ('queued','running'):break
                        await asyncio.sleep(2)
                    assert record['status']=='succeeded',record
                    return queued['job_id'],record['result']
                movie_job,movie=await render(base|{'audio_state_sha256':audio['audio_state_sha256'],'preset':'h264_aac',
                    'duration':30,'width':1920,'height':1080,'fps':24,'destination':out.relative_to(settings.workspace).as_posix()+'/movie',
                    'color_policy':'interpret_native_rgb_as_srgb'},'distribution')
                assert movie['data']['verification']['frame_count']==720
                assert movie['data']['verification']['width']==1920 and movie['data']['verification']['height']==1080
                decoded=analyze_pcm(settings.contained_path(f'jobs/{movie_job}/audio-decoded.wav'))
                onsets=[m['sample']/48000 for m in decoded['energy_onsets']]
                errors=[min(abs(t-a) for a in onsets)*24 for t in (3,20)]
                assert max(errors)<=1
                alpha_job,alpha=await render(base|{'preset':'tiff_rgba8','duration':0.25,'start_time':3,'width':1920,'height':1080,'fps':24,
                    'destination':out.relative_to(settings.workspace).as_posix()+'/alpha','color_policy':'interpret_native_rgb_as_srgb'},'intermediate')
                assert alpha['data']['verification']['alpha_verified'] and alpha['data']['verification']['transparency_exercised']
                collected=await call('delivery_collect',{'project_id':pid,'base_aep_sha256':source_sha,'render_job_id':movie_job,
                    'destination':out.relative_to(settings.workspace).as_posix()+'/package'})
                verified=await call('delivery_validate',{'delivery_id':collected['data']['delivery_id']})
                assert verified['data']['ready_for_delivery']
                package=Path(collected['data']['delivery_path'])
                manifest=json.loads((package/'manifest.json').read_text())
                assert manifest['fonts'] and all(f['available'] and not f['copied'] for f in manifest['fonts'])
                assert manifest['plugins'] and manifest['native_dependencies']
                assert manifest['audio_sidecar']=='audio/plan.json'
                assert (package/'render/final.mp4').is_file() and (package/'media').is_dir()
                assert all(digest(Path(p))==h for p,h in original.items()) and digest(source)==source_sha
                write_json(out/'acceptance.json',{'scope':'real AE/FFmpeg final and alpha render; copied/relinked/reopened package; no human playback/listening/artistic approval',
                    'source':str(source),'source_sha256':source_sha,'project_id':pid,'distribution_job':movie_job,'distribution':movie,
                    'alpha_job':alpha_job,'alpha':alpha,'collection':collected,'validation':verified,'operations':operations,
                    'event_error_frames':errors,'existing_sources_preserved':True,'existing_sources':original,
                    'sampled_visual_review':'not_yet_performed'})
                print('SPRINT11_ACCEPTANCE='+str(out/'acceptance.json'),flush=True)
    asyncio.run(asyncio.wait_for(exercise(),timeout=1200))
