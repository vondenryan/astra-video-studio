import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from astra_video_studio.config import Settings
from astra_video_studio.schemas import OperationResult,JobStatus
from astra_video_studio.responses import present,wire_result,wire_size,RECEIPT_BYTES,EvidenceQuery,query_evidence
from astra_video_studio.local_client import resolve_response
from astra_video_studio.layer_batch import LayersCreate,LayerBatchService,verify_batch
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import write_json
from astra_video_studio.host_runtime import presentation_metadata
from contextlib import nullcontext

BASE={'project_id':'1'*32,'composition_id':'2'*32,'base_sha256':'a'*64}


@pytest.fixture(autouse=True)
def no_native_mutex_for_unit_fixtures(monkeypatch):
    monkeypatch.setattr('astra_video_studio.layer_batch.AELock',nullcontext)


@pytest.mark.parametrize('status',['succeeded','failed','timeout'])
def test_receipt_bounded_with_metadata_and_exact_local_result(tmp_path,status):
    settings=Settings(tmp_path)
    original=OperationResult(operation_id='3'*32,status=status,project_id='1'*32,
        data={'layers':['large '*1000]*80,'created_count':20},error='diagnostic '*5000 if status!='succeeded' else None)
    metadata=presentation_metadata('layers_create','receipt')
    output=present(original,'receipt',settings,metadata)
    assert wire_size(output,metadata)<=RECEIPT_BYTES
    assert output.data=={'created_count':20}
    assert resolve_response(settings,wire_result(output,metadata),'OperationResult')==original.model_dump(mode='json')
    assert present(original,'full',settings).data==original.data


def test_poll_receipt_retains_complete_terminal_result(tmp_path):
    settings=Settings(tmp_path)
    original=JobStatus(operation_id='3'*32,action='render',status='succeeded',
        events=[{'status':'running','detail':'x'*1000}]*300,
        result=OperationResult(operation_id='3'*32,status='succeeded',data={'verification':{'decoded':True}}))
    output=present(original,'receipt',settings,presentation_metadata('job_status','receipt'))
    assert output.events==[] and output.result is None and output.event_count==300
    assert resolve_response(settings,wire_result(output))['result']['data']['verification']['decoded']


def test_receipt_unicode_diagnostics_remain_within_wire_budget(tmp_path):
    settings=Settings(tmp_path)
    original=OperationResult(operation_id='3'*32,status='failed',error='漢'*10000)
    metadata=presentation_metadata('layers_create','receipt')
    output=present(original,'receipt',settings,metadata)
    assert wire_size(output,metadata)<=RECEIPT_BYTES
    assert resolve_response(settings,wire_result(output))['error']==original.error


def test_local_evidence_ignores_supplied_path_and_checks_identity_and_tampering(tmp_path):
    settings=Settings(tmp_path);original=OperationResult(operation_id='3'*32,status='succeeded')
    output=wire_result(present(original,'receipt',settings))
    output.structuredContent['evidence']['path']='C:/untrusted/file.json'
    assert resolve_response(settings,output)==original.model_dump(mode='json')
    output.structuredContent['operation_id']='4'*32
    with pytest.raises(ValueError,match='identity'):resolve_response(settings,output)
    output.structuredContent['operation_id']='3'*32
    path=tmp_path/'responses'/(output.structuredContent['evidence']['sha256']+'.json')
    path.write_bytes(b'{}')
    with pytest.raises(ValueError,match='hash'):resolve_response(settings,output)


@pytest.mark.parametrize('layers',[
    [],[{'role':'item','layer':{}}]*21,
    [{'role':'item','layer':{}},{'role':'item','layer':{}}],
    [{'role':'item','layer':{'kind':'media','asset_id':'a'*32}}],
    [{'role':'item','layer':{'kind':'shape'},'text_style':{'alignment':'left'}}],
    [{'role':'../escape','layer':{}}],
])
def test_batch_closed_scope(layers):
    with pytest.raises(ValidationError):LayersCreate(**BASE,layers=layers)


def test_batch_hash_conflict_precedes_any_native_call(tmp_path):
    source=tmp_path/'project.aep';source.write_bytes(b'old')
    write_json(tmp_path/'project.json',{'sha256':digest(source)})
    service=LayerBatchService(Settings(tmp_path));service.projects=Mock()
    service.projects.load.return_value=({},source)
    with pytest.raises(ValueError,match='hash'):service.create(LayersCreate(**BASE,layers=[{'role':'title','layer':{}}]))
    service.projects.inspect.assert_not_called();service.projects.runner.run.assert_not_called()


def test_created_roles_query_is_bounded_and_ordered(tmp_path):
    settings=Settings(tmp_path)
    original=OperationResult(operation_id='3'*32,status='succeeded',data={'created_layers':[{'role':'a','layer_id':'4'*32},{'role':'b','layer_id':'5'*32}]})
    output=present(original,'receipt',settings)
    page=query_evidence(settings,EvidenceQuery(evidence_sha256=output.evidence.sha256,section='created_layers',limit=1))
    assert page.total==2 and page.next_offset==1 and page.items[0]['role']=='a'
    assert present(original,'compact',settings).data['created_layers']==original.data['created_layers']


@pytest.mark.parametrize('failure',['non_target','unexpected_layer','new_animation','wrong_order'])
def test_batch_failed_verification_never_promotes(tmp_path,failure):
    settings=Settings(tmp_path);directory=tmp_path/'projects'/('1'*32);directory.mkdir(parents=True)
    source=directory/'project.aep';source.write_bytes(b'checked-clean-source')
    manifest={'sha256':digest(source),'status':'succeeded','project_id':'1'*32}
    write_json(directory/'project.json',manifest)
    before={'project_dirty':False,'compositions':[{'composition_id':'astra:composition:'+'2'*32,
        'width':640,'height':360,'duration':2,'layers':[{'layer_id':'astra:layer:'+'9'*32,'name':'sentinel'}]}],'footage':[]}
    service=LayerBatchService(settings);service.projects=Mock();service.projects.load.return_value=(manifest.copy(),source)
    service.projects.inspect.return_value=OperationResult(operation_id='3'*32,status='succeeded',data=before)
    def native(action,payload):
        assert action=='layers_add';Path(payload['version_path']).write_bytes(b'new-disposable-version')
        after=copy.deepcopy(before);comp=after['compositions'][0]
        layer={'layer_id':'astra:layer:'+payload['items'][0]['layer_id'],'name':'New','editable_2d':True,'three_d':False,
            'parent_ae_id':None,'matte_ae_id':None,'locked':False,'enabled':True,'position':[320,180],
            'transforms':{'scale':{'value':[100,100],'keys':[]},'rotation':{'value':0,'keys':[]},'opacity':{'value':100,'keys':[]}},
            'in_point':0,'out_point':2,'is_shape':True,'shape_groups':[]}
        comp['layers'].insert(0,layer)
        if failure=='non_target':comp['layers'][1]['name']='changed'
        if failure=='unexpected_layer':comp['layers'].append({'layer_id':'astra:layer:'+'8'*32})
        if failure=='new_animation':layer['transforms']['opacity']['keys']=[{'time':0,'value':100}]
        if failure=='wrong_order':comp['layers'].reverse()
        return OperationResult(operation_id='4'*32,status='succeeded',data=after)
    service.projects.runner.run.side_effect=native
    result=service.create(LayersCreate(**(BASE|{'base_sha256':digest(source)}),layers=[{'role':'new','layer':{'name':'New','kind':'shape','shape':'empty'}}]))
    assert result.status=='failed' and 'verification failed' in result.error
    assert json.loads((directory/'project.json').read_text())==manifest
    assert source.read_bytes()==b'checked-clean-source'
