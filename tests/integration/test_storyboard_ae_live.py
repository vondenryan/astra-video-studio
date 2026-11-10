"""Opt-in V2 storyboard acceptance. Never enables other native tests implicitly."""
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
from astra_video_studio.project_manager import ProjectManager

F=runpy.run_path('tests/fixtures/audio_scene.py')


@pytest.mark.ae_live
@pytest.mark.skipif(os.environ.get('ASTRA_RUN_AE_TESTS')!='1',reason='Opt-in Sprint12 storyboard acceptance')
def test_three_scene_storyboard_two_portuguese_patches_and_preservation():
    settings=Settings.from_env();state=IdleTransport(settings).state()
    assert state and not state.get('active_job'),'Reviewed bridge must already be ready'
    assert not settings.contained_path('ae-pending.json').exists()
    assert not settings.contained_path('preview-pending.json').exists()
    original={p:digest(Path(p)) for p in ProjectManager(settings).managed_paths()}
    out=settings.contained_path('sprint12-native-'+uuid4().hex);out.mkdir()
    write_json(out/'preservation-baseline.json',{'existing_sources':original})
    F['write_tone'](out/'bed.wav',18,1000)

    async def exercise():
        params=StdioServerParameters(command=sys.executable,args=['-m','astra_video_studio.mcp_server'],env=dict(os.environ))
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as client:
                await client.initialize();operations=[]
                async def call(name,request=None,**kwargs):
                    args={'response_mode':'full',**kwargs}
                    if request is not None:args['request']=request
                    response=await client.call_tool(name,args)
                    assert not response.isError,response.content
                    result=response.structuredContent;assert result['status']=='succeeded',result
                    operations.append({'tool':name,'operation_id':result['operation_id']})
                    write_json(out/'operations.json',{'operations':operations})
                    return result
                audio=(await call('audio_inspect',{'source_path':str(out/'bed.wav')}))['data']
                tokens_response=await client.call_tool('design_tokens_set',{'request':{
                    'name':'Astra Sprint12','colors':{'background':[.012,.022,.045],'foreground':[.96,.97,1],'accent':[.2,.8,1]},
                    'typography':{role:{'font':{'postscript_name':'Arial-BoldMT'},'size_ratio':size}
                                  for role,size in [('heading',.05),('body',.027)]}}})
                assert not tokens_response.isError,tokens_response.content
                tokens=tokens_response.structuredContent
                brief=dict(objective='Apresentar um fluxo de motion dirigido',audience='Designers e criadores',
                    message='A ideia ganha forma com controle e revisão',brand_constraints=['Fundo escuro, acento ciano, linguagem concisa'],
                    token_id=tokens['token_id'],audio_bed_asset_id=audio['asset_id'],max_revisions=2,
                    scenes=[dict(intent='Introduzir a identidade',heading='IDEIAS EM MOVIMENTO',body='Direção com clareza.',layout='hero'),
                        dict(intent='Mostrar controle',heading='CONTROLE CRIATIVO',body='Cenas, forma e ritmo.',layout='split'),
                        dict(intent='Concluir com entrega',heading='DO BRIEF À ENTREGA',body='Crie. Revise. Entregue.',layout='editorial')])
                await call('brief_validate',brief)
                plan=(await call('storyboard_plan',brief))['data'];write_json(out/'plan.json',plan)
                assert len(plan['scenes'])==3 and len(plan['techniques'])>=4
                executed=(await call('storyboard_execute',{'plan_id':plan['plan_id'],'plan_sha256':plan['plan_sha256']}))['data']
                write_json(out/'initial-submitted.json',executed)
                async def completed(execution,label):
                    deadline=time.monotonic()+900
                    while time.monotonic()<deadline:
                        response=await call('storyboard_status',execution_id=execution['execution_id'])
                        current=response['data']
                        if current['status']=='succeeded':
                            assert current['render']['verification']
                            write_json(out/(label+'.json'),current)
                            samples=(await call('review_samples_create',{'execution_id':execution['execution_id']}))['data']
                            write_json(out/(label+'-samples.json'),samples)
                            return current
                        assert current['status']=='rendering',current
                        await asyncio.sleep(2)
                    pytest.fail('Storyboard render timed out; do not retry native work')
                first=await completed(executed,'initial')
                pid=first['project_id'];scene=plan['scenes'][2]
                accent=next(e for e in scene['elements'] if e['role']=='accent')
                expected=[accent['layer']['position'][0]+10,accent['layer']['position'][1]]
                # A separately saved typed edit models a compatible intervening edit.
                # This is not claimed as a human action in the acceptance record.
                edited=await call('layer_transform',dict(project_id=pid,composition_id=scene['composition_id'],
                    layer_id=accent['layer_id'],values={'position':expected}))
                retained=Path(edited['project_path']);retained_sha=digest(retained)
                revisions=[];base=retained_sha;parent=first
                for i,instruction in enumerate(['Troque o título da cena 1 para "IDEIAS COM DIREÇÃO"',
                                                 'Trocar texto da cena 2 para "Ritmo com intenção."']):
                    revised=(await call('storyboard_revise',{'execution_id':parent['execution_id'],'base_aep_sha256':base,
                        'instruction':instruction,'rebuild_audio':True}))['data']
                    assert revised['status']=='rendering',revised
                    parent=await completed(revised,f'revision-{i+1}');revisions.append(parent)
                    base=parent['project_sha256']
                final=(await call('composition_inspect',project_id=pid))['data']
                comp=next(c for c in final['compositions'] if c['composition_id'].endswith(scene['composition_id']))
                actual=next(l for l in comp['layers'] if l['layer_id'].endswith(accent['layer_id']))
                assert actual['position'][:2]==pytest.approx(expected)
                assert digest(retained)==retained_sha
                assert digest(Path(first['project_path']))==first['project_sha256']
                assert digest(Path(revisions[0]['project_path']))==revisions[0]['project_sha256']
                exhausted=await client.call_tool('storyboard_revise',{'request':{
                    'execution_id':parent['execution_id'],'base_aep_sha256':base,
                    'instruction':'Trocar título da cena 1 para "Outra ideia"','rebuild_audio':True}})
                assert exhausted.isError and 'budget exhausted' in str(exhausted.content)
                write_json(out/'acceptance.json',{'initial':first,'revisions':revisions,'preserved_saved_edit':{
                    'scope':'separate typed saved edit; not a human manual-action claim','path':str(retained),'sha256':retained_sha,
                    'layer_id':accent['layer_id'],'position':expected},'attempt_budget_stop_verified':True,
                    'sampled_visual_review':'pending','human_playback_listening_artistic_review':'pending'})
    try:asyncio.run(exercise())
    finally:
        unchanged={p:digest(Path(p))==sha for p,sha in original.items()}
        write_json(out/'preservation-result.json',{'count':len(original),'all_preserved':all(unchanged.values()),
            'changed':[p for p,ok in unchanged.items() if not ok]})
        assert all(unchanged.values()),'Preexisting managed AEP changed'
