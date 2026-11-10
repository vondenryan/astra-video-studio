import copy

import pytest
from pydantic import ValidationError

from astra_video_studio.scene_editing import (
    CompositionCreate, CompositionUpdate, LayerUpdate, LayerParent, LayerRemove,
    TrackMatte, Precompose, LayerInsert, prepare, validate_graph, equivalent, verify, stored_background,
)


PROJECT, COMP, A, B, C, OTHER = [str(i) * 32 for i in range(1, 7)]


@pytest.fixture
def scene():
    def layer(identifier, native):
        return {'layer_id': 'astra:layer:' + identifier, 'ae_id': native, 'name': identifier,
                'source_ae_id': None, 'source_kind': None, 'source_has_motion': False,
                'parent_ae_id': None, 'matte_ae_id': None, 'matte_mode': 'none', 'blend_mode': 'normal',
                'locked': False, 'editable_2d': True, 'animation_summary': {'key_count': 0, 'expressions': 0},
                'in_point': 0, 'out_point': 5, 'start_time': 0, 'auto_orient_none': True,
                'matte_api': True, 'transforms': {}, 'world_basis': [[0, 0], [1, 0], [0, 1]]}
    return {'footage': [], 'compositions': [
        {'composition_id': 'astra:composition:' + COMP, 'ae_id': 10, 'name': 'Master', 'fps': 24, 'duration': 20,
         'width': 960, 'height': 540, 'background': [0, 0, 0], 'layers': [layer(A, 11), layer(B, 12), layer(C, 13)]},
        {'composition_id': 'astra:composition:' + OTHER, 'ae_id': 20, 'name': 'Other', 'fps': 24, 'duration': 5,
         'width': 960, 'height': 540, 'background': [0, 0, 0], 'layers': []}]}


@pytest.mark.parametrize('cls,fields', [
    (CompositionCreate, {'background': [0, 0, 2]}),
    (CompositionCreate, {'fps': float('nan')}),
    (CompositionCreate, {'name': 'bad\nname'}),
    (CompositionUpdate, {}), (CompositionUpdate, {'fps': 30}),
    (CompositionUpdate, {'fps_policy': 'preserve_seconds'}),
    (CompositionUpdate, {'fps': 30, 'fps_policy': 'preserve_frames', 'duration': 20}),
    (LayerUpdate, {}), (LayerUpdate, {'shift_frames': 1, 'in_frame': 3}),
    (LayerUpdate, {'before_layer_id': A}), (LayerUpdate, {'blend_mode': 'arbitrary'}),
    (TrackMatte, {'mode': 'alpha'}), (TrackMatte, {'mode': 'none', 'matte_layer_id': B}),
    (TrackMatte, {'mode': 'alpha', 'matte_layer_id': A}),
    (LayerParent, {'parent_layer_id': B}),
    (Precompose, {'layer_ids': [A, A]}),
])
def test_reject_invalid_schemas(cls, fields):
    common = {'project_id': PROJECT, 'composition_id': COMP, 'layer_id': A}
    allowed = {key: value for key, value in common.items() if key in cls.model_fields}
    with pytest.raises(ValidationError):
        cls(**(allowed | fields))


def test_integer_frame_shift_and_no_input_mutation(scene):
    original = copy.deepcopy(scene)
    ctx = prepare('layer_update', LayerUpdate(project_id=PROJECT, composition_id=COMP, layer_id=A, shift_frames=6), scene)
    assert ctx['start_time'] == ctx['in_point'] == 0.25
    assert ctx['out_point'] == 5.25
    assert scene == original


def test_lifetime_and_animated_timing_protected(scene):
    with pytest.raises(ValueError, match='lifetime'):
        prepare('layer_update', LayerUpdate(project_id=PROJECT, composition_id=COMP, layer_id=A, out_frame=500), scene)
    scene['compositions'][0]['layers'][0]['animation_summary']['key_count'] = 2
    with pytest.raises(ValueError, match='static'):
        prepare('layer_update', LayerUpdate(project_id=PROJECT, composition_id=COMP, layer_id=A, shift_frames=1), scene)


def test_parent_and_matte_dependencies_block_removal(scene):
    scene['compositions'][0]['layers'][1]['parent_ae_id'] = 11
    with pytest.raises(ValueError, match='dependents'):
        prepare('layer_remove', LayerRemove(project_id=PROJECT, composition_id=COMP, layer_id=A), scene)
    scene['compositions'][0]['layers'][1]['parent_ae_id'] = None
    scene['compositions'][0]['layers'][1]['matte_ae_id'] = 11
    with pytest.raises(ValueError, match='dependents'):
        prepare('layer_remove', LayerRemove(project_id=PROJECT, composition_id=COMP, layer_id=A), scene)


@pytest.mark.parametrize('mode', ['parent', 'matte'])
def test_relation_cycle(scene, mode):
    field = 'parent_ae_id' if mode == 'parent' else 'matte_ae_id'
    scene['compositions'][0]['layers'][1][field] = 11
    request = (LayerParent(project_id=PROJECT, composition_id=COMP, layer_id=A, parent_layer_id=B, policy='preserve_local')
               if mode == 'parent' else TrackMatte(project_id=PROJECT, composition_id=COMP, layer_id=A, matte_layer_id=B, mode='alpha'))
    with pytest.raises(ValueError, match='cycle'):
        prepare('layer_parent' if mode == 'parent' else 'track_matte_set', request, scene)


def test_composition_cycle(scene):
    # Source native IDs are authoritative even if a host type label is wrong.
    scene['compositions'][0]['layers'][0].update(source_ae_id=20, source_kind='footage')
    with pytest.raises(ValueError, match='cycle'):
        prepare('composition_layer_add', LayerInsert(project_id=PROJECT, composition_id=OTHER, source_composition_id=COMP), scene)


def test_frame_retime_of_referenced_comp_is_protected(scene):
    scene['compositions'][0]['layers'][0].update(source_ae_id=20, source_kind='composition')
    with pytest.raises(ValueError, match='Referenced'):
        prepare('composition_update', CompositionUpdate(project_id=PROJECT, composition_id=OTHER, fps=30, fps_policy='preserve_frames'), scene)


def test_animated_ancestor_blocks_world_compensation(scene):
    scene['compositions'][0]['layers'][1]['animation_summary']['key_count'] = 2
    with pytest.raises(ValueError, match='static'):
        prepare('layer_parent', LayerParent(project_id=PROJECT, composition_id=COMP, layer_id=A, parent_layer_id=B, policy='preserve_world'), scene)


def test_precompose_dependency_closure_and_stacking(scene):
    target = {'project_id': PROJECT, 'composition_id': COMP}
    with pytest.raises(ValueError, match='contiguous'):
        prepare('precompose_layers', Precompose(**target, layer_ids=[A, C]), scene)
    scene['compositions'][0]['layers'][1]['parent_ae_id'] = 11
    with pytest.raises(ValueError, match='dependencies'):
        prepare('precompose_layers', Precompose(**target, layer_ids=[A]), scene)
    ctx = prepare('precompose_layers', Precompose(**target, layer_ids=[B, A]), scene)
    assert ctx['moved_ids'] == [A, B]


def test_explicit_fps_policies(scene):
    target = {'project_id': PROJECT, 'composition_id': COMP, 'fps': 30}
    frames = prepare('composition_update', CompositionUpdate(**target, fps_policy='preserve_frames'), scene)
    seconds = prepare('composition_update', CompositionUpdate(**target, fps_policy='preserve_seconds'), scene)
    assert frames['duration'] == 16 and frames['time_factor'] == 0.8
    assert seconds['duration'] == 20 and seconds['time_factor'] == 1
    scene['compositions'][0]['layers'][0]['source_has_motion'] = True
    with pytest.raises(ValueError, match='video/audio'):
        prepare('composition_update', CompositionUpdate(**target, fps_policy='preserve_frames'), scene)


def test_expression_and_trim_guards(scene):
    with pytest.raises(ValueError, match='trim'):
        prepare('composition_update', CompositionUpdate(project_id=PROJECT, composition_id=COMP, duration=2), scene)
    scene['compositions'][0]['layers'][1]['animation_summary']['expressions'] = 1
    with pytest.raises(ValueError, match='expressions'):
        prepare('layer_update', LayerUpdate(project_id=PROJECT, composition_id=COMP, layer_id=A, name='Renamed'), scene)


def test_verifier_catches_unrelated_edits(scene):
    request = LayerUpdate(project_id=PROJECT, composition_id=COMP, layer_id=A, name='Renamed')
    ctx = prepare('layer_update', request, scene)
    after = copy.deepcopy(scene)
    after['compositions'][0]['layers'][0]['name'] = 'Renamed'
    verify('layer_update', request, scene, after, ctx)
    after['compositions'][1]['background'] = [1, 0, 0]
    with pytest.raises(ValueError):
        verify('layer_update', request, scene, after, ctx)


def test_missing_relation_and_numeric_tolerance(scene):
    scene['compositions'][0]['layers'][0]['parent_ae_id'] = 999
    with pytest.raises(ValueError, match='missing'):
        validate_graph(scene)
    equivalent([1.00000001], [1.0])
    with pytest.raises(ValueError):
        equivalent([1.1], [1.0])


def test_ae_background_quantization():
    assert stored_background([0.015, 0.025, 0.05]) == [4 / 255, 6 / 255, 13 / 255]


@pytest.mark.parametrize('action', ['composition_create', 'composition_update', 'null_create'])
def test_structural_guards_cover_early_return_operations(scene, action):
    from astra_video_studio.scene_editing import NullCreate
    scene['compositions'][0]['layers'][0]['animation_summary']['expressions'] = 1
    request = (CompositionCreate(project_id=PROJECT) if action == 'composition_create' else
               CompositionUpdate(project_id=PROJECT, composition_id=COMP, name='Changed') if action == 'composition_update' else
               NullCreate(project_id=PROJECT, composition_id=COMP))
    with pytest.raises(ValueError, match='expressions'):
        prepare(action, request, scene)
