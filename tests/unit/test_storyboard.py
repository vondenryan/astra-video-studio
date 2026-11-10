import copy
import json

import pytest
from pydantic import ValidationError

from astra_video_studio.audio import AudioService
from astra_video_studio.config import Settings
from astra_video_studio.design import DesignTokens, TypeToken, FontSelection, store_tokens
from astra_video_studio.existing_projects import digest
from astra_video_studio.responses import EvidenceQuery, query_evidence, store_evidence, wire_size
from astra_video_studio.storyboard import (StoryboardService, StoryBrief, StoryExecute, StoryReview,
    reading_seconds, parse_patch, sample_schedule)


def brief_dict(token_id):
    return dict(objective='Apresentar o Astra',audience='Motion designers',message='Controle criativo local',
        brand_constraints=['Texto curto, fundo escuro e acento azul'],token_id=token_id,
        audio_bed_asset_id='a'*32,scenes=[
            dict(intent='Abrir com identidade',heading='IDEIAS EM MOVIMENTO',body='Direção com clareza.',layout='hero'),
            dict(intent='Mostrar o processo',heading='CONTROLE CRIATIVO',body='Cenas, forma e ritmo.',layout='split'),
            dict(intent='Concluir a mensagem',heading='DO BRIEF À ENTREGA',body='Crie. Revise. Entregue.',layout='editorial')])


@pytest.fixture
def studio(tmp_path,monkeypatch):
    settings=Settings(tmp_path)
    tokens=DesignTokens(name='Storyboard',colors={'foreground':(.96,.97,1),'background':(.01,.02,.04),'accent':(.2,.8,1)},
        typography={role:TypeToken(font=FontSelection(postscript_name='Arial-BoldMT'),size_ratio=size)
                    for role,size in [('heading',.05),('body',.027)]})
    record=store_tokens(settings,tokens)
    monkeypatch.setattr(AudioService,'_asset',lambda *args,**kw:dict(manifest_sha256='b'*64,sample_count=30*48000))
    return StoryboardService(settings),StoryBrief(**brief_dict(record.token_id))


def test_three_distinct_layouts_integer_timing_and_immutable_plan(studio):
    service,brief=studio
    result=service.plan(brief);plan=result.data
    assert len(plan['scenes'])==3 and len(plan['techniques'])==4
    assert plan['total_frames']==432
    assert len({s['card']['layout'] for s in plan['scenes']})==3
    assert len({e['layer_id'] for s in plan['scenes'] for e in s['elements']})==15
    assert plan['scenes'][0]['start_frame']==0 and plan['scenes'][-1]['end_frame']==432
    for a,b in zip(plan['scenes'],plan['scenes'][1:]):
        assert a['end_frame']-b['start_frame']==plan['transition_frames']
    original=service.load_plan(plan['plan_id'],plan['plan_sha256'])[0]
    assert original['scenes']==plan['scenes']
    evidence=service.settings.contained_path('responses/'+plan['plan_sha256']+'.json')
    evidence.write_text('{}')
    with pytest.raises(ValueError,match='changed'):service.load_plan(plan['plan_id'])


def test_reading_density_rejected_before_plan_or_native_work(studio):
    service,brief=studio
    raw=brief.model_dump();raw['scenes'][0]['body']=' '.join(['termo']*24)
    with pytest.raises(ValueError,match='reading budget'):service.plan(StoryBrief(**raw))
    assert not service.settings.contained_path('storyboards/plans').exists()


@pytest.mark.parametrize('instruction',[
    'Troque o título da cena 1 para "Ação" e apague tudo',
    'Trocar texto da cena 4 para "Outro"',
    'Trocar duração para 30 segundos',
    'Trocar título da cena 1 para "Um\nDois"',
])
def test_patch_parser_rejects_partial_or_ambiguous_work(instruction):
    with pytest.raises((ValueError,ValidationError)):parse_patch(instruction,3)


def test_portuguese_patches_and_reading_heuristic():
    assert parse_patch('Troque o título da cena 1 para “AÇÃO”.',3)==(0,'heading','AÇÃO')
    assert parse_patch('trocar texto da cena 2 para "Controle local."',3)==(1,'body','Controle local.')
    assert reading_seconds('One','Two')==2


def test_root_wide_attempt_budget_is_exclusive_and_retains_unknown(studio):
    service,_=studio;root='c'*32
    service._dir('executions',root).mkdir(parents=True)
    assert service._reserve_iteration(root,2,'d'*32)==1
    assert service._reserve_iteration(root,2,'e'*32)==2
    with pytest.raises(ValueError,match='budget exhausted'):service._reserve_iteration(root,2,'f'*32)
    assert len(list((service._dir('executions',root)/'iterations').glob('*.json')))==2


def test_samples_cover_phases_transitions_and_changed_interval(studio):
    service,brief=studio;plan=service.plan(brief).data
    samples=sample_schedule(plan,[144,300]);reasons={r for s in samples for r in s['reasons']}
    assert {'scene_1_entry','scene_2_hold','scene_3_exit','scene_2_transition','changed_interval'}<=reasons
    assert len({s['frame'] for s in samples})==len(samples)<=48
    assert all(0<=s['frame']<432 for s in samples)
    for i,scene in enumerate(plan['scenes']):
        exit_frame=next(s['frame'] for s in samples if f'scene_{i+1}_exit' in s['reasons'])
        assert scene['end_frame']-plan['transition_frames'] < exit_frame < scene['end_frame']


def test_storyboard_compaction_and_paged_scenes(studio):
    service,brief=studio;result=service.plan(brief)
    # Exercise the same compact projection used by all OperationResult MCP tools.
    from astra_video_studio.responses import present
    response=present(result,'compact',service.settings)
    assert wire_size(response)<=8192
    page=query_evidence(service.settings,EvidenceQuery(evidence_sha256=response.evidence.sha256,section='scenes',limit=1))
    assert page.total==3 and page.next_offset==1 and page.items[0]['card']['layout']=='hero'


def test_failed_native_attempt_cannot_be_executed_again(studio,monkeypatch):
    service,brief=studio;result=service.plan(brief)
    from astra_video_studio.schemas import OperationResult
    calls=[]
    monkeypatch.setattr(service.projects.runner,'run',lambda *a,**kw:(calls.append(a) or OperationResult(operation_id='f'*32,status='timeout',error='uncertain')))
    request=StoryExecute(plan_id=result.data['plan_id'],plan_sha256=result.data['plan_sha256'])
    failed=service.execute(request)
    assert failed.status=='failed' and failed.data['status']=='failed'
    with pytest.raises(FileExistsError):service.execute(request)
    assert len(calls)==1


def test_review_integrity_scope_and_append_only_reverification(studio):
    service,brief=studio;identifier='c'*32
    video=service.settings.workspace/'test.mp4';video.write_bytes(b'verified-video-fixture')
    image=service.settings.workspace/'frame.png';image.write_bytes(b'image-fixture')
    execution=dict(schema_version=2,execution_id=identifier,project_id='d'*32,status='succeeded',
        render=dict(video_path=str(video),video_sha256=digest(video)))
    service._commit_execution(execution)
    samples=dict(execution_id=identifier,video_sha256=digest(video),samples=[dict(sample_id='e'*32,path=str(image),sha256=digest(image))])
    ref=store_evidence(service.settings,'StoryboardSamples',samples)
    request=StoryReview(execution_id=identifier,samples_sha256=ref.sha256,inspected_sample_ids=['e'*32],
        reviewer='codex',assessment='acceptable_samples',notes='Amostra inspecionada pelo chamador.')
    first=service.review(request);second=service.review(request)
    assert first.data['full_video_watched'] is False and first.data['audio_listened'] is False
    assert service._read_evidence(first.data['review_sha256'],'StoryboardReview')['notes']==request.notes
    image.write_bytes(b'changed')
    with pytest.raises(ValueError,match='image changed'):service.review(request)


def geometry_fixture():
    def track(value,keys=None):
        return dict(value=value,keys=keys or [],samples=[dict(time=3,value=value)],expression_present=False)
    layer=dict(layer_id='astra:layer:'+'b'*32,text_style=dict(box_overflow=False,font_missing=False),
        bounds=dict(left=0,top=0,width=100,height=20),parent_ae_id=None,three_d=False,
        transforms=dict(position=track([500,300]),anchor=track([50,10]),scale=track([100,100]),rotation=track(0)))
    state=dict(compositions=[dict(composition_id='astra:composition:'+'a'*32,duration=6,layers=[layer])])
    plan=dict(brief=dict(width=1000,height=600),tokens=dict(safe_area=[.1,.1,.1,.1]),
        scenes=[dict(composition_id='a'*32,elements=[dict(layer_id='b'*32,layer=dict(kind='text'))])])
    return plan,state,layer


def test_hold_geometry_uses_native_midpoint_not_last_key():
    plan,state,layer=geometry_fixture()
    layer['transforms']['position']['keys']=[dict(time=5,value=[5000,300])]
    StoryboardService._verify_text_geometry(plan,state)
    layer['transforms']['position']['samples'][0]['value']=[50,300]
    with pytest.raises(ValueError,match='safe area'):StoryboardService._verify_text_geometry(plan,state)


@pytest.mark.parametrize('alteration',['scale','rotation','expression','parent','missing_sample'])
def test_geometry_rejects_unsafe_or_unmeasurable_manual_transforms(alteration):
    plan,state,layer=geometry_fixture()
    if alteration=='scale':layer['transforms']['scale']['samples'][0]['value']=[1000,1000]
    if alteration=='rotation':
        layer['transforms']['position']['samples'][0]['value']=[150,65]
        layer['transforms']['rotation']['samples'][0]['value']=45
    if alteration=='expression':layer['transforms']['position']['expression_present']=True
    if alteration=='parent':layer['parent_ae_id']=3
    if alteration=='missing_sample':layer['transforms']['position']['samples']=[]
    with pytest.raises(ValueError):StoryboardService._verify_text_geometry(plan,state)


def test_plan_dependency_change_fails_before_attempt_or_native(studio,monkeypatch):
    service,brief=studio;plan=service.plan(brief).data
    monkeypatch.setattr(AudioService,'_asset',lambda *args,**kw:dict(manifest_sha256='c'*64,sample_count=30*48000))
    with pytest.raises(ValueError,match='dependencies changed'):
        service.execute(StoryExecute(plan_id=plan['plan_id'],plan_sha256=plan['plan_sha256']))
    assert not (service._dir('plans',plan['plan_id'])/'attempt.json').exists()


def test_low_contrast_brand_is_rejected(studio):
    service,brief=studio
    record=service.settings.contained_path('design-tokens/'+brief.token_id+'/record.json')
    tokens=DesignTokens.model_validate(json.loads(record.read_text())['tokens'])
    tokens.colors['foreground']=(.02,.02,.02)
    new=store_tokens(service.settings,tokens)
    bad=brief.model_copy(update={'token_id':new.token_id})
    with pytest.raises(ValueError,match='contrast'):service.validate(bad)


def test_compact_completed_status_keeps_video_path_and_hash(studio):
    service,_=studio
    from astra_video_studio.responses import present
    identifier='c'*32
    service._commit_execution(dict(execution_id=identifier,status='succeeded',project_id='d'*32,
        render=dict(video_path='C:/workspace/final.mp4',video_sha256='f'*64,
                    ae_preparation={'large':'not for host presentation'*10000})))
    status=service.status(identifier)
    compact=present(status,'compact',service.settings)
    assert compact.data['render']['video_path']=='C:/workspace/final.mp4'
    assert compact.data['render']['video_sha256']=='f'*64
    assert 'ae_preparation' not in compact.data['render']
    assert wire_size(compact)<=8192
