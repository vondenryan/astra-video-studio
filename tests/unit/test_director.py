import copy
import pytest
from pydantic import ValidationError

from astra_video_studio.config import Settings
from astra_video_studio.director import SceneBrief, SceneRevision, Director, build_plan, natural_changes
from astra_video_studio.motion_engine.schemas import MotionRequest
from astra_video_studio.motion_engine.skills import plan
from astra_video_studio.motion_engine.batch import BatchRequest, compile_batch, StaggerRequest

IDS={'project_id':'1'*32,'composition_id':'2'*32,'layer_id':'3'*32}
COMP={'width':1280,'height':720,'fps':24,'duration':12}
LAYER={'text':'ASTRA','bounds':{'left':-150,'top':-30,'width':300,'height':60},'position':[640,360,0],'in_point':0,'out_point':12,'transforms':{},'editable_2d':True,'locked':False}


def test_brief_produces_editable_structured_twelve_second_plan():
    scene=build_plan(SceneBrief(brief='Crie um motion de 12 segundos com o título "ASTRA VIDEO STUDIO".'))
    assert scene.duration==12 and scene.brief.title=='ASTRA VIDEO STUDIO'
    assert len(scene.elements)>=8 and len(scene.techniques)>=3
    assert len({e.layer_id for e in scene.elements})==len(scene.elements)
    assert {p['name'] for p in scene.phases}=={'entry','hold','closing'}
    assert all(a.motion.start_time+a.motion.duration<=12 for a in scene.actions)


@pytest.mark.parametrize('fps',[24,29.97,30])
def test_scene_lifetimes_and_duration_are_frame_aligned(fps):
    scene=build_plan(SceneBrief(brief='Um vídeo de 15 segundos.',fps=fps))
    assert 10<=scene.duration<=15
    for element in scene.elements:
        assert element.layer.in_point*fps==pytest.approx(round(element.layer.in_point*fps))
        assert element.layer.out_point*fps==pytest.approx(round(element.layer.out_point*fps))


def test_supported_natural_revision_keeps_original_and_stable_roles(tmp_path):
    director=Director(Settings(tmp_path))
    first=director.plan(SceneBrief(brief='Crie um motion de 12 segundos.'))
    before=(tmp_path/'plans'/first.plan_id/'plan.json').read_bytes()
    revised=director.revise(SceneRevision(plan_id=first.plan_id,instruction='Troque o título para "ASTRA EM AÇÃO" e reduza overshoot para 3%.'))
    assert revised.brief.title=='ASTRA EM AÇÃO' and revised.brief.overshoot==0.03
    assert revised.composition_id==first.composition_id
    assert [e.layer_id for e in revised.elements]==[e.layer_id for e in first.elements]
    assert (tmp_path/'plans'/first.plan_id/'plan.json').read_bytes()==before


def test_unknown_natural_revision_is_not_silently_partially_applied():
    scene=build_plan(SceneBrief(brief='Crie um motion de 12 segundos.'))
    with pytest.raises(ValueError,match='Unsupported'):
        natural_changes('Troque o título para "Novo" e apague o disco.',scene)


@pytest.mark.parametrize('skill',['text_reveal','shake','parallax_2d'])
def test_expanded_skills_have_native_bounded_plans(skill):
    result=plan(MotionRequest(**IDS,skill=skill,start_time=1,duration=1),COMP,LAYER)
    if skill=='text_reveal':
        assert len(result['mask_reveal']['keys'])>=3 and not result['tracks']
        assert result['mask_reveal']['keys'][-1]['vertices'][1][0]-result['mask_reveal']['keys'][-1]['vertices'][0][0]==316
    else:
        assert result['tracks'][0]['property']=='position'
        assert len(result['tracks'][0]['keys'])<=900


def test_shake_is_reproducible_and_returns_to_baseline():
    request=MotionRequest(**IDS,skill='shake',start_time=1,duration=1,params={'seed':9})
    first=plan(request,COMP,LAYER)
    assert first==plan(request,COMP,LAYER)
    assert first['tracks'][0]['keys'][0]['value']==first['tracks'][0]['keys'][-1]['value']==[640,360]


def test_stagger_offsets_and_overlap_preflight():
    request=StaggerRequest(project_id=IDS['project_id'],composition_id=IDS['composition_id'],layer_ids=['3'*32,'4'*32],interval=0.2)
    assert request.batch().motions[1].start_time==0.2
    data={'compositions':[COMP|{'composition_id':'astra:composition:'+IDS['composition_id'],'layers':[LAYER|{'layer_id':'astra:layer:'+IDS['layer_id']}]}]}
    motion=MotionRequest(**IDS,skill='scale_pop',duration=1)
    with pytest.raises(ValueError,match='Overlapping'):
        compile_batch(BatchRequest(motions=[motion,motion]),data)


def test_all_scene_actions_preflight_together():
    scene=build_plan(SceneBrief(brief='Crie uma animação de 12 segundos.',width=1280,height=720,fps=24))
    layers=[]
    for element in scene.elements:
        layers.append(copy.deepcopy(LAYER)|{'layer_id':'astra:layer:'+element.layer_id,'text':element.layer.text if element.layer.kind=='text' else None,'position':list(element.layer.position)+[0],'in_point':element.layer.in_point,'out_point':element.layer.out_point})
    data={'compositions':[COMP|{'composition_id':'astra:composition:'+scene.composition_id,'layers':layers}]}
    assert len(compile_batch(BatchRequest(motions=[a.motion for a in scene.actions]),data))==len(scene.actions)


def test_project_lifetimes_reject_invalid_fields():
    with pytest.raises(ValidationError): SceneBrief(brief='Teste válido',duration=3)
    with pytest.raises(ValidationError): SceneBrief(brief='Teste válido',accent=[2,0,0])


def test_explicit_unsupported_duration_in_brief_is_not_silently_ignored():
    with pytest.raises(ValueError,match='10'):
        build_plan(SceneBrief(brief='Crie um vídeo de 45 segundos.'))


def test_plan_integrity_rejects_external_edits(tmp_path):
    director=Director(Settings(tmp_path))
    scene=director.plan(SceneBrief(brief='Motion de 12 segundos.'))
    path=tmp_path/'plans'/scene.plan_id/'plan.json'
    path.write_text(path.read_text()+' ')
    with pytest.raises(ValueError,match='changed'):
        director.load(scene.plan_id)


def test_append_shake_uses_last_saved_position_not_time_zero():
    layer=copy.deepcopy(LAYER)|{'layer_id':'astra:layer:'+IDS['layer_id']}
    layer['transforms']['position']={'keys':[{'time':0,'value':[0,0]},{'time':1,'value':[200,100]}],'expression_enabled':False}
    data={'compositions':[COMP|{'composition_id':'astra:composition:'+IDS['composition_id'],'layers':[layer]}]}
    compiled=compile_batch(BatchRequest(motions=[MotionRequest(**IDS,skill='shake',start_time=2,duration=1)]),data)
    assert compiled[0]['plan']['tracks'][0]['keys'][0]['value']==[200,100]
