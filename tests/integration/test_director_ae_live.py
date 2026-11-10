"""Final acceptance: brief → editable 12 s scene → preview → natural revision."""
import asyncio
import hashlib
import os
from pathlib import Path
import sys
import time

from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest


@pytest.mark.ae_live
@pytest.mark.skipif(os.environ.get('ASTRA_RUN_AE_TESTS')!='1',reason='Opt-in complete director AE/render test')
def test_brief_to_scene_and_natural_language_revision():
    async def exercise():
        params=StdioServerParameters(command=sys.executable,args=['-m','astra_video_studio.mcp_server'],env=dict(os.environ))
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                async def call(name,args):
                    response=await session.call_tool(name,args)
                    assert not response.isError,response.content
                    return response.structuredContent
                async def finished(identifier):
                    deadline=time.monotonic()+500
                    while time.monotonic()<deadline:
                        state=await call('scene_status',{'execution_id':identifier})
                        if state['status']!='rendering': return state
                        await asyncio.sleep(2)
                    pytest.fail('Scene render deadline exceeded')
                plan=await call('scene_plan',{'request':{'brief':'Crie um motion de 12 segundos com o título "ASTRA VIDEO STUDIO", entrada suave, hierarquia clara e encerramento elegante.','width':1280,'height':720,'fps':24}})
                assert plan['duration']==12 and len(plan['techniques'])>=3
                first=await call('scene_execute',{'plan_id':plan['plan_id']})
                assert first['status']=='rendering',first
                first=await finished(first['execution_id'])
                assert first['status']=='succeeded',first
                original_path=Path(first['project_path']); original_hash=hashlib.sha256(original_path.read_bytes()).hexdigest()
                assert first['data']['preview']['verification']['frame_count']==288
                revised=await call('scene_revise',{'request':{'plan_id':plan['plan_id'],'instruction':'Troque o título para "ASTRA EM AÇÃO" e reduza overshoot para 3%.'}})
                assert revised['brief']['title']=='ASTRA EM AÇÃO' and revised['brief']['overshoot']==0.03
                second=await call('scene_execute',{'plan_id':revised['plan_id']})
                assert second['status']=='rendering',second
                second=await finished(second['execution_id'])
                assert second['status']=='succeeded',second
                assert second['project_id']==first['project_id'] and second['project_path']!=first['project_path']
                assert hashlib.sha256(original_path.read_bytes()).hexdigest()==original_hash
                inspected=await call('composition_inspect',{'project_id':second['project_id']})
                titles=[l['text'] for l in inspected['data']['compositions'][0]['layers'] if l['text']]
                assert 'ASTRA EM AÇÃO' in titles and len(inspected['data']['compositions'][0]['layers'])==9
                assert all(not layer['text_style']['all_caps'] for layer in inspected['data']['compositions'][0]['layers'] if layer['text'])
                reference=await call('reference_analyze',{'request':{'source_path':second['data']['preview']['video_path']}})
                assert not reference['visual_analysis_performed'] and reference['metadata']['duration']==pytest.approx(12,abs=0.05)
                assert len(reference['samples'])==3
                print(f"first_execution={first['execution_id']}\nexecution_id={second['execution_id']}\nplan_id={revised['plan_id']}\nproject_path={second['project_path']}\nvideo_path={second['data']['preview']['video_path']}")
    asyncio.run(asyncio.wait_for(exercise(),timeout=1100))
