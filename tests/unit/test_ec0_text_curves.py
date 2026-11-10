import importlib.util
import json
from pathlib import Path
from unittest.mock import patch
import pytest


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,Path('experimental/ec0')/path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


oracle=load('text_curves_oracles','text_curves_oracles.py')
with patch.dict('sys.modules',{'text_curves_oracles':oracle}):
    runner=load('ec0_text_runner','run_text_curves.py')


def test_closed_form_scalar_references_and_boundary_values():
    assert [oracle.scalar_at('linear',f) for f in (-1,0,30,60,61)]==[0,0,50,100,100]
    assert [oracle.scalar_at('hold',f) for f in (-1,0,59,60,61)]==[0,0,0,100,100]
    assert [oracle.scalar_at('bezier',f) for f in (0,15,30,45,60)]==[0,15.625,50,84.375,100]


def test_arc_reference_endpoints_symmetry_and_nonzero_join():
    assert oracle.spatial_at(-1)==pytest.approx((100,300))
    assert oracle.spatial_at(1)==pytest.approx((320,240))
    assert oracle.spatial_at(3)==pytest.approx((540,300))
    left=oracle.spatial_at(.5);right=oracle.spatial_at(1.5)
    assert left[0]+right[0]==pytest.approx(640,abs=1e-6)
    assert left[1]==pytest.approx(right[1],abs=1e-6)
    a,b=oracle.spatial_at(.9999),oracle.spatial_at(1.0001)
    assert (b[0]-a[0])/.0002==pytest.approx(180,abs=.2)


@pytest.mark.parametrize('raw',[{'t':'Scalar','v':float('nan')},{'t':'Scalar','v':True},{'t':'Vec2','v':[1,2]}])
def test_untrusted_scalar_samples_reject_nonfinite_bool_and_wrong_type(raw):
    with pytest.raises(ValueError):oracle.value(raw,'Scalar')


def test_incomplete_curves_and_absent_text_cannot_pass():
    with pytest.raises(ValueError):oracle.verify_curves({'samples':[]})
    with pytest.raises(ValueError):oracle.raster_text_bounds(b'',640,360,{})
    with pytest.raises(ValueError):oracle.raster_text_bounds(bytes(640*360*4),640,360,{})


@pytest.mark.parametrize('case,prefix',[('missing-font','FONT_MISSING:'),('unsupported-glyph','GLYPH_UNSUPPORTED:'),('wrong-font-hash','FONT_HASH_MISMATCH')])
def test_expected_font_refusal_requires_exact_identity_and_no_system_scan(case,prefix):
    data={'protocol':'astra-ec0-text-curves-v1','job_id':'a'*32,'case':case,'status':'failed','error':prefix,'system_fonts_scanned':False}
    assert runner.receipt(json.dumps(data).encode(),'a'*32,case)==data
    for patch_value in ({'job_id':'b'*32},{'system_fonts_scanned':True},{'status':'succeeded'},{'error':'other'}):
        with pytest.raises(ValueError):runner.receipt(json.dumps(data|patch_value).encode(),'a'*32,case)


@pytest.mark.parametrize('raw',[b'x'*8193,b'[]',b'{"job_id":"a","job_id":"b"}',b'{"bad":NaN}'])
def test_second_protocol_strict_decoding(raw):
    with pytest.raises(ValueError):runner.receipt(raw,'a'*32,'text-curves')
