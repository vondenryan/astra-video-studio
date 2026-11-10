import json
import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('ec0_smoke',Path('experimental/ec0/run_smoke.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def receipt():
    return {'protocol':'astra-ec0-v1','job_id':'a'*32,'status':'succeeded',
        'upstream_revision':module.REVISION,'backend':'effectcraft-cpu','width':160,'height':90,
        'fps':30,'frame_count':6,'project_roundtrip_equal':True,'pixel_probes_passed':True}


def test_ec0_ack_identity_and_required_checks():
    assert module.parse_receipt(json.dumps(receipt()).encode(),'a'*32)==receipt()
    for key,value in [('job_id','b'*32),('upstream_revision','b'*40),('frame_count',0),
        ('status','failed'),('project_roundtrip_equal',1),('pixel_probes_passed',False)]:
        with pytest.raises(ValueError):module.parse_receipt(json.dumps(receipt()|{key:value}).encode(),'a'*32)


@pytest.mark.parametrize('raw',[b'x'*8193,b'[]',b'{"status":"succeeded","status":"failed"}',b'{"bad":NaN}'])
def test_ec0_rejects_unbounded_or_ambiguous_protocol(raw):
    with pytest.raises(ValueError):module.parse_receipt(raw,'a'*32)


def test_ec0_graph_checks_reachable_frontends_only():
    spec=importlib.util.spec_from_file_location('ec0_graph',Path('experimental/ec0/check_dependencies.py'))
    graph=importlib.util.module_from_spec(spec);spec.loader.exec_module(graph)
    data={'resolve':{'root':'root','nodes':[{'id':'root','deps':[{'pkg':'render'}],'features':[]},
        {'id':'render','deps':[],'features':[]},{'id':'gui','deps':[],'features':[]}]},
        'packages':[{'id':key,'name':name,'version':'1','license':'MIT','source':None} for key,name in [('root','probe'),('render','effectcraft-render'),('gui','effectcraft-ui-egui')]]}
    assert graph.inspect_graph(data)['gui_packages']==[]
    data['resolve']['nodes'][1]['deps'].append({'pkg':'gui'})
    assert graph.inspect_graph(data)['gui_packages']==['effectcraft-ui-egui']
