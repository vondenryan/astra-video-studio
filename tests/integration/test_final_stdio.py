"""Real MCP and final encoders; generated RGBA replaces AE only in explicit fixture server."""
import asyncio
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
from uuid import uuid4

from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest

from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import write_json

F=runpy.run_path('tests/fixtures/audio_scene.py')


async def exercise(workspace):
    workspace.mkdir(parents=True,exist_ok=True)
    source,comp=F['fake_project'](workspace)
    F['write_tone'](workspace/'tone.wav',2,1000)
    params=StdioServerParameters(command=sys.executable,args=[str(Path('tests/fixtures/final_mcp_server.py').resolve())],
        env=dict(os.environ,ASTRA_WORKSPACE=str(workspace.resolve())))
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as client:
            await client.initialize()
            async def op(name,request=None):
                args={'response_mode':'full'}
                if request is not None:args['request']=request
                response=await client.call_tool(name,args)
                assert not response.isError,response.content
                assert response.structuredContent['status']=='succeeded',response.structuredContent
                return response.structuredContent['data']
            discovered=await op('render_presets_list')
            assert all(p['available'] for p in discovered['render_presets'])
            asset=await op('audio_inspect',{'source_path':str((workspace/'tone.wav').resolve())})
            target={'project_id':F['PID'],'composition_id':F['CID'],'base_aep_sha256':digest(source)}
            audio=await op('audio_clip_set',target|{'clip':{'asset_id':asset['asset_id'],'duration_frames':48}})
            products=[]
            for number,(preset,with_audio) in enumerate((('h264_aac',True),('tiff_rgba8',False),('tiff_rgba8',True))):
                request=target|{'preset':preset,'duration':0.5,'fps':24,'width':320,'height':180,
                    'destination':'output-'+preset+str(number),'color_policy':'interpret_native_rgb_as_srgb'}
                if with_audio:request['audio_state_sha256']=audio['audio_state_sha256']
                response=await client.call_tool('render_submit',{'request':request})
                assert not response.isError,response.content
                queued=response.structuredContent;assert queued['status']=='queued'
                for _ in range(80):
                    status=await client.call_tool('job_status',{'operation_id':queued['job_id'],'response_mode':'full'})
                    assert not status.isError
                    status=status.structuredContent
                    if status['status'] not in ('queued','running'):break
                    await asyncio.sleep(0.25)
                assert status['status']=='succeeded',status
                data=status['result']['data'];products.append(data)
                assert data['purpose']=='final' and data['ae_preparation']['fixture_only']
                if preset=='h264_aac':
                    assert data['verification']['frame_count']==12
                    assert data['verification']['color']['color_space']=='bt709'
                    assert data['audio_verification']['encoded_stream']['codec']=='aac'
                else:
                    seq=json.loads(Path(data['sequence_manifest_path']).read_text())
                    assert seq['frame_count']==12 and seq['alpha_min']==0 and seq['alpha_max']==255
                    assert seq['alpha_verified'] and seq['transparency_exercised']
                    assert len(seq['frames'])==12
                    if with_audio: assert digest(Path(data['destination_path'])/'audio-mix.wav')==data['audio_mix_sha256']
            assert digest(source)==target['base_aep_sha256']
            assert not (workspace/'ae-pending.json').exists() and not (workspace/'preview-pending.json').exists()
            report={'scope':'synthetic RGBA native provider; real stdio MCP/final encoders/alpha decode; not AE execution',
                'products':products,'source_preserved':True,'result':'succeeded'}
            write_json(workspace/'acceptance.json',report)
            return report


@pytest.mark.integration
@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'),reason='Local FFmpeg required')
def test_final_presets_rgba_alpha_and_h264_color_audio(tmp_path):
    report=asyncio.run(asyncio.wait_for(exercise(tmp_path),timeout=90))
    assert len(report['products'])==3


if __name__=='__main__':
    workspace=Path('workspace')/('sprint11-fixtures-'+uuid4().hex)
    asyncio.run(asyncio.wait_for(exercise(workspace),timeout=90))
    print('SPRINT11_FIXTURE_ACCEPTANCE='+str((workspace/'acceptance.json').resolve()))
