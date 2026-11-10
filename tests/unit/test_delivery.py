import copy
import json
from pathlib import Path
import runpy
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from astra_video_studio.config import Settings
from astra_video_studio.delivery import DeliveryService,DeliveryCollect,DeliveryValidate,package_file,exclusive_json
from astra_video_studio.existing_projects import digest
from astra_video_studio.media.final_render import FinalRenderRequest,final_plan,RenderService,destination_path
from astra_video_studio.media.preview import PreviewRequest,AudioPreviewRequest
from astra_video_studio.schemas import OperationResult

F=runpy.run_path('tests/fixtures/audio_scene.py')


def request(**changes):
    return FinalRenderRequest(**({'project_id':F['PID'],'composition_id':F['CID'],'base_aep_sha256':'a'*64,
        'audio_state_sha256':'b'*64,'destination':'renders/final','fps':24,'duration':30,
        'color_policy':'interpret_native_rgb_as_srgb'}|changes))


def comp(): return {'width':1920,'height':1080,'fps':24,'duration':60}


def test_final_contract_is_independent_from_preview(tmp_path):
    for model in (PreviewRequest,AudioPreviewRequest):
        with pytest.raises(ValidationError): model(project_id=F['PID'],composition_id=F['CID'],duration=30)
    plan=final_plan(request(),comp(),Settings(tmp_path))
    assert plan['frame_count']==720 and plan['duration']==30 and plan['purpose']=='final'
    assert plan['estimated_bytes']==1920*1080*24*720


@pytest.mark.parametrize('changes',[{'fps':30},{'duration':61},{'start_time':40},{'width':3840,'height':2160}])
def test_final_timing_and_resolution_guards(tmp_path,changes):
    with pytest.raises(ValueError): final_plan(request(**changes),comp(),Settings(tmp_path))


@pytest.mark.parametrize('changes',[{'audio_state_sha256':None},{'width':1919},{'fps':float('nan')},{'color_policy':'guess'}])
def test_final_schema_rejects_ambiguous_policy(changes):
    with pytest.raises(ValidationError): request(**changes)


def test_alpha_can_be_silent_and_has_declared_8bit(tmp_path):
    plan=final_plan(request(preset='tiff_rgba8',audio_state_sha256=None,duration=1),comp(),Settings(tmp_path))
    assert plan['alpha'] and plan['output_depth_bits']==8
    with pytest.raises(ValueError,match='resolution'):
        final_plan(request(preset='tiff_rgba8',audio_state_sha256=None,width=640,height=360,duration=1),comp(),Settings(tmp_path))


@pytest.mark.parametrize('dest',['../outside','C:\\outside','/absolute','.'])
def test_destination_refuses_escape_absolute_or_root(tmp_path,dest):
    with pytest.raises(ValueError): destination_path(Settings(tmp_path),dest)


def test_destination_never_overwrites(tmp_path):
    (tmp_path/'existing').mkdir()
    with pytest.raises(ValueError): destination_path(Settings(tmp_path),'existing')


def test_disk_budget_fails_before_native_and_job(tmp_path):
    service=RenderService(Settings(tmp_path))
    with patch('astra_video_studio.media.final_render.shutil.disk_usage',return_value=Mock(free=100)):
        with pytest.raises(ValueError,match='disk'): service.make_plan(request(),comp())
    assert not (tmp_path/'jobs').exists()


@pytest.mark.parametrize('color',[{}, {'bits_per_channel':32,'linearized':False,'working_space':''},
    {'bits_per_channel':8,'linearized':True,'working_space':''},
    {'bits_per_channel':8,'linearized':False,'working_space':'ACEScg'}])
def test_no_silent_color_or_depth_conversion(color):
    with pytest.raises(ValueError): RenderService.check_color({'source_color':color})


def test_native_none_profile_is_untagged_under_explicit_policy():
    RenderService.check_color({'source_color':{'bits_per_channel':8,'linearized':False,'working_space':'None'}})


def test_package_path_cannot_escape_even_within_workspace(tmp_path):
    directory=tmp_path/'delivery';directory.mkdir()
    with pytest.raises(ValueError): package_file(Settings(tmp_path),directory,'../outside')
    assert package_file(Settings(tmp_path),directory,'media/a.png')==directory/'media/a.png'


def test_collect_relinks_copy_and_refuses_tamper_before_native(tmp_path,monkeypatch):
    source,scene=F['fake_project'](tmp_path)
    picture=tmp_path/'image.png';picture.write_bytes(b'owned image fixture')
    render=tmp_path/'final.mp4';render.write_bytes(b'owned video fixture')
    service=DeliveryService(Settings(tmp_path))
    before=copy.deepcopy(scene)
    dependencies={'files':[{'ae_id':99,'path':str(picture),'missing':False,'sequence':False}],
        'fonts':[{'postscript_name':'Fixture','available':True,'copied':False}],'plugins':[],
        'unsupported':[],'source_color':{'bits_per_channel':8,'working_space':'','linearized':False}}
    def native(action,path,mapping,relinks=None):
        deps=copy.deepcopy(dependencies)
        if action=='delivery_collect':
            assert path!=source and path.name=='project.aep'
            assert relinks[0]['old_path']==str(picture)
            assert Path(relinks[0]['new_path']).read_bytes()==picture.read_bytes()
            deps['files'][0]['path']=relinks[0]['new_path']
            path.write_bytes(path.read_bytes()+b'only copied AEP relinked')
        return OperationResult(operation_id='8'*32,status='succeeded',data={'reopened':True,
            'before':{'compositions':[before]},'after':{'compositions':[before]},'dependencies':deps})
    monkeypatch.setattr(service,'_native',Mock(side_effect=native))
    monkeypatch.setattr(service,'_render',Mock(return_value=({}, {'preset':'h264_aac','video_path':str(render),
        'video_sha256':digest(render),'plan':{'duration':20,'fps':24},'verification':{}})))
    original=source.read_bytes()
    result=service.collect(DeliveryCollect(project_id=F['PID'],base_aep_sha256=digest(source),render_job_id='7'*32,destination='delivery'))
    assert result.status=='succeeded',result.error
    assert source.read_bytes()==original and result.data['ready_for_delivery']
    assert (tmp_path/'delivery/media/99.png').read_bytes()==picture.read_bytes()
    assert (tmp_path/'delivery/project.aep').read_bytes()!=original
    assert not list((tmp_path/'delivery').glob('*.ttf'))
    called=service._native.call_count
    (tmp_path/'delivery/render/final.mp4').write_bytes(b'tampered')
    with pytest.raises(ValueError,match='hash'): service.validate(DeliveryValidate(delivery_id=result.data['delivery_id']))
    assert service._native.call_count==called


def test_package_rejects_missing_and_unsupported_dependencies():
    base={'files':[],'fonts':[],'unsupported':[]}
    for change in ({'unsupported':['sequence']},{'files':[{'ae_id':1,'missing':True}]},
        {'fonts':[{'postscript_name':'missing','available':False}]}):
        with pytest.raises(ValueError): DeliveryService._dependencies(base|change)


def test_package_native_calls_respect_render_quarantine(tmp_path):
    service=DeliveryService(Settings(tmp_path))
    marker=tmp_path/'preview-pending.json';marker.write_text('{"status":"timeout"}')
    service.projects.runner.run=Mock(side_effect=AssertionError('No native submission allowed'))
    with pytest.raises(BlockingIOError,match='quarantine'):
        service._native('delivery_validate',tmp_path/'project.aep',None)
    service.projects.runner.run.assert_not_called()
    assert marker.read_text()=='{"status":"timeout"}'


def test_delivery_json_is_exclusive(tmp_path):
    path=tmp_path/'manifest.json';exclusive_json(path,{'first':True})
    with pytest.raises(FileExistsError): exclusive_json(path,{'first':False})
    assert json.loads(path.read_text())=={'first':True}


def test_journal_sharing_retry_is_read_only_and_bounded(tmp_path):
    from astra_video_studio.jobs import read_json
    path=tmp_path/'job.json'
    with patch.object(Path,'read_text',side_effect=[PermissionError('busy'),PermissionError('busy'),'{"status":"running"}']) as read, \
         patch('astra_video_studio.jobs.time.sleep'):
        assert read_json(path)=={'status':'running'}
        assert read.call_count==3
    with patch.object(Path,'read_text',side_effect=PermissionError('busy')) as read, \
         patch('astra_video_studio.jobs.time.sleep'):
        with pytest.raises(PermissionError):read_json(path)
        assert read.call_count==6
    with patch.object(Path,'read_text',return_value='{incomplete') as read:
        with pytest.raises(ValueError):read_json(path)
        assert read.call_count==1
