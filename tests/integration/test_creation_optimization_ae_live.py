"""Explicit native acceptance; creates new owned projects and preserves all old AEPs."""
import asyncio
import copy
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

import pytest
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import write_json
from astra_video_studio.local_client import resolve_response
from astra_video_studio.project_manager import ProjectManager
from astra_video_studio.responses import encoded,RECEIPT_BYTES


@pytest.mark.ae_live
@pytest.mark.skipif(os.environ.get('ASTRA_RUN_AE_TESTS')!='1',reason='Opt-in grouped creation native comparison')
def test_grouped_creation_matches_separate_calls_and_preserves_sources():
    settings=Settings.from_env();root=settings.contained_path('optimization-acceptance/'+uuid4().hex);root.mkdir(parents=True)
    baseline={p:digest(Path(p)) for p in ProjectManager(settings).managed_paths()}
    write_json(root/'preservation-baseline.json',baseline)
    evidence={'directory':str(root),'prior_aep_count':len(baseline),'routes':{}}
    specs=[{'kind':'text','name':'Title','text':'CLAREZA','font_size':48,'position':[320,100],'color':[1,1,1]},
        {'kind':'text','name':'Body','text':'Design em movimento','font_size':24,'position':[320,190]},
        {'kind':'text','name':'Footer','text':'VERTICE','font_size':16,'position':[320,290]},
        {'kind':'shape','name':'Bar','shape':'rectangle','size':[300,4],'position':[320,235]},
        {'kind':'shape','name':'Dot','shape':'ellipse','size':[20,20],'position':[140,290]}]
    async def run():
        async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','astra_video_studio.mcp_server'],env=dict(os.environ))) as (read,write):
            async with ClientSession(read,write) as client:
                await client.initialize()
                async def call(name,request):
                    response=await client.call_tool(name,{'request':request,'response_mode':'receipt'})
                    assert not response.isError,response.content
                    assert len(encoded(response.model_dump(mode='json',exclude_none=True)))<=RECEIPT_BYTES
                    raw=resolve_response(settings,response)
                    write_json(root/(raw['operation_id']+'-'+name+'.json'),raw)
                    assert raw['status']=='succeeded',raw.get('error')
                    return raw
                for route in ('separate','grouped'):
                    created=await call('project_create',{'name':'Optimization '+route,'title':'Sentinel','width':640,'height':360,'fps':30,'duration':2,'font_size':14})
                    pid=created['project_id'];cid=created['data']['compositions'][0]['composition_id'].split(':')[-1]
                    base={'project_id':pid,'composition_id':cid};before=copy.deepcopy(created['data']);start=time.perf_counter();calls=0
                    if route=='separate':
                        for spec in specs:
                            result=await call('layer_create',base|{'layer':spec});calls+=1
                            if spec['kind']=='text':
                                result=await call('text_style_set',base|{'layer_id':result['data']['layer_id'],'font':{'postscript_name':'Arial-BoldMT'},'font_size':spec['font_size'],'alignment':'center','leading':spec['font_size']*1.12});calls+=1
                    else:
                        result=await call('layers_create',base|{'base_sha256':digest(Path(created['project_path'])),
                            'layers':[{'role':'item_'+str(i),'layer':s,**({'text_style':{'leading':s['font_size']*1.12}} if s['kind']=='text' else {})} for i,s in enumerate(specs)]});calls=1
                        assert result['data']['created_count']==5
                        assert len({r['layer_id'] for r in result['data']['created_layers']})==5
                    evidence['routes'][route]={'mutation_calls':calls,'seconds':time.perf_counter()-start,'source':result['project_path'],'data':result['data']}
                    assert len(result['data']['compositions'][0]['layers'])==6
                    assert result['data']['compositions'][0]['layers'][-1]==before['compositions'][0]['layers'][0]
                def visual_metadata(data):
                    layers=copy.deepcopy(data['compositions'][0]['layers'][:-1])
                    for layer in layers:
                        for key in ('layer_id','ae_id','comment'):layer.pop(key,None)
                    return layers
                assert visual_metadata(evidence['routes']['separate']['data'])==visual_metadata(evidence['routes']['grouped']['data'])
    asyncio.run(asyncio.wait_for(run(),timeout=240))
    assert all(digest(Path(p))==sha for p,sha in baseline.items())
    evidence['prior_aep_preservation_verified']=True
    write_json(root/'acceptance.json',evidence)
    write_json(settings.contained_path('optimization-acceptance-current.json'),{'directory':str(root)})
