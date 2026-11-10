"""Real stdio planning and pagination, with real audio import and no AE commands."""
import asyncio
import json
import os
from pathlib import Path
import runpy
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest

from astra_video_studio.responses import encoded

F=runpy.run_path('tests/fixtures/audio_scene.py')


@pytest.mark.integration
def test_storyboard_brief_plan_and_compact_scene_pages_without_ae(tmp_path):
    F['write_tone'](tmp_path/'bed.wav',18,1000)
    async def exercise():
        params=StdioServerParameters(command=sys.executable,args=['-m','astra_video_studio.mcp_server'],
            env=dict(os.environ,ASTRA_WORKSPACE=str(tmp_path.resolve())))
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as client:
                await client.initialize()
                async def call(name,request):
                    response=await client.call_tool(name,{'request':request})
                    assert not response.isError,response.content
                    assert len(encoded(response.model_dump(mode='json',exclude_none=True)))<=8192
                    assert response.meta['astra_presentation']
                    raw=json.loads(Path(response.structuredContent['evidence']['path']).read_text(encoding='utf-8'))['result']
                    return response,raw['data']
                _,audio=await call('audio_inspect',{'source_path':str((tmp_path/'bed.wav').resolve())})
                tokens=await client.call_tool('design_tokens_set',{'request':{
                    'colors':{'background':[.01,.02,.04],'foreground':[.96,.97,1],'accent':[.2,.8,1]},
                    'typography':{r:{'font':{'postscript_name':'Arial-BoldMT'},'size_ratio':s}
                                  for r,s in [('heading',.05),('body',.027)]}}})
                assert not tokens.isError
                brief=dict(objective='Planejar um motion',audience='Criadores locais',message='Controle e clareza',
                    brand_constraints=['Contraste alto'],token_id=tokens.structuredContent['token_id'],audio_bed_asset_id=audio['asset_id'],
                    scenes=[dict(intent='Apresentar a ideia',heading='IDEIA',body='Controle local.',layout=layout)
                            for layout in ('hero','split','editorial')])
                await call('brief_validate',brief)
                response,plan=await call('storyboard_plan',brief)
                assert plan['schema_version']==2 and len(plan['scenes'])==3
                page=await client.call_tool('operation_query',{'request':{
                    'evidence_sha256':response.structuredContent['evidence']['sha256'],'section':'scenes','limit':1}})
                assert not page.isError,page.content
                assert page.structuredContent['total']==3 and page.structuredContent['next_offset']==1
                assert len(encoded(page.model_dump(mode='json',exclude_none=True)))<=16384
                assert not (tmp_path/'ae-pending.json').exists()
                assert not list((tmp_path/'jobs').glob('*/operation.jsx'))
    asyncio.run(exercise())
