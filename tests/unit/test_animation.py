import copy

import pytest
from pydantic import ValidationError

from astra_video_studio.animation import (AnimationRetime, EasingSet, KeyframesEdit, MotionPathSet, MotionBlurSet,
                                         fingerprint, prepare_animation)
from astra_video_studio.motion_engine.schemas import MotionRequest
from astra_video_studio.motion_engine.skills import plan

IDS = {'project_id': '1' * 32, 'composition_id': '2' * 32, 'layer_id': '3' * 32}
GUARD = IDS | {'base_sha256': 'a' * 64, 'expected_track_sha256': 'b' * 64, 'property': 'position', 'start_frame': 0, 'end_frame': 30, 'boundary_policy': 'preserve_boundaries'}


@pytest.fixture
def state():
    def key(time, value):
        return {'time': time, 'value': [value, 200, 0], 'in_type': 'linear', 'out_type': 'linear', 'in_native': 'L', 'out_native': 'L',
                'in_ease': [{'speed': 0, 'influence': 100 / 3}], 'out_ease': [{'speed': 0, 'influence': 100 / 3}],
                'temporal_auto': False, 'temporal_continuous': False, 'spatial_auto': False, 'spatial_continuous': False, 'roving': False,
                'in_spatial': [0, 0, 0], 'out_spatial': [0, 0, 0]}
    track = {'available': True, 'spatial': True, 'separated': False, 'expression_enabled': False, 'expression_present': False,
             'value': [0, 200, 0], 'keys': [key(0, 0), key(1, 100), key(4, 100), key(5, 200)], 'samples': []}
    layer = {'layer_id': 'astra:layer:' + IDS['layer_id'], 'locked': False, 'editable_2d': True, 'in_point': 0, 'out_point': 5,
             'transforms': {'position': track}, 'animation_summary': {'key_count': 4, 'expressions': 0}}
    return {'project_dirty': False, 'interpolation_constants': {'linear': 'L', 'bezier': 'B', 'hold': 'H'},
            'compositions': [{'composition_id': 'astra:composition:' + IDS['composition_id'], 'fps': 30, 'duration': 5, 'layers': [layer]}]}


def guard(state, **overrides):
    return GUARD | {'expected_track_sha256': fingerprint(state['compositions'][0]['layers'][0]['transforms']['position'])} | overrides


@pytest.mark.parametrize('fields', [
    {'mode': 'replace'}, {'mode': 'move'}, {'mode': 'move', 'shift_frames': 0},
    {'mode': 'remove', 'keys': [{'frame': 15, 'value': [1, 2]}]},
    {'mode': 'insert', 'keys': [{'frame': 40, 'value': [1, 2]}]},
    {'mode': 'insert', 'keys': [{'frame': 15, 'value': [1, 2]}, {'frame': 15, 'value': [2, 3]}]},
    {'mode': 'insert', 'keys': [{'frame': 15, 'value': [float('nan'), 2]}]},
    {'mode': 'remove', 'base_sha256': 'guess'}, {'mode': 'remove', 'boundary_policy': 'auto'},
])
def test_invalid_key_edit(fields):
    with pytest.raises(ValidationError): KeyframesEdit.model_validate(GUARD | fields)


def test_insert_preserves_exit_and_input(state):
    original = copy.deepcopy(state)
    request = KeyframesEdit(**guard(state), mode='insert', keys=[{'frame': 15, 'value': [50, 170]}])
    out = prepare_animation('keyframes_edit', request, state)['tracks'][0]['keys']
    assert len(out) == 5 and out[-2:] == original['compositions'][0]['layers'][0]['transforms']['position']['keys'][-2:]
    assert state == original


@pytest.mark.parametrize('mode', ['insert', 'update', 'remove', 'replace', 'move'])
def test_explicit_crud_modes(state, mode):
    fields = {'mode': mode, 'boundary_policy': 'allow_change'}
    if mode in ('insert', 'update', 'replace'): fields['keys'] = [{'frame': 15 if mode == 'insert' else 0, 'value': [20, 200]}]
    if mode == 'move': fields['shift_frames'] = 3
    request = KeyframesEdit(**guard(state, **fields))
    out = prepare_animation('keyframes_edit', request, state)['tracks'][0]['keys']
    assert out[-2:] == state['compositions'][0]['layers'][0]['transforms']['position']['keys'][-2:]


def test_stale_hash_expression_and_automatic_tracks_protected(state):
    with pytest.raises(ValueError, match='conflict'):
        prepare_animation('keyframes_edit', KeyframesEdit(**GUARD, mode='remove'), state)
    track = state['compositions'][0]['layers'][0]['transforms']['position']
    track['expression_present'] = True
    with pytest.raises(ValueError, match='protected'):
        prepare_animation('keyframes_edit', KeyframesEdit(**guard(state), mode='remove'), state)
    track['expression_present'] = False
    track['keys'][0]['spatial_auto'] = True
    with pytest.raises(ValueError, match='Automatic'):
        prepare_animation('keyframes_edit', KeyframesEdit(**guard(state), mode='remove'), state)


def test_boundary_value_and_external_tangent_guards(state):
    request = KeyframesEdit(**guard(state), mode='update', keys=[{'frame': 0, 'value': [10, 200]}])
    with pytest.raises(ValueError, match='boundary'):
        prepare_animation('keyframes_edit', request, state)
    request = MotionPathSet(**guard(state), edits=[{'frame': 0, 'in_tangent': [10, 10]}])
    with pytest.raises(ValueError, match='boundary'):
        prepare_animation('motion_path_set', request, state)
    allowed = MotionPathSet(**guard(state), edits=[{'frame': 0, 'out_tangent': [50, -80]}, {'frame': 30, 'in_tangent': [-50, -80]}])
    keys = prepare_animation('motion_path_set', allowed, state)['tracks'][0]['keys']
    assert keys[0]['out_spatial'] == [50, -80, 0] and keys[-2:] == state['compositions'][0]['layers'][0]['transforms']['position']['keys'][-2:]


def test_easing_dimensions_speed_and_window_validation(state):
    bad = EasingSet(**guard(state), edits=[{'frame': 0, 'out_ease': [{'speed': -5, 'influence': 40}]}])
    with pytest.raises(ValueError, match='nonnegative'): prepare_animation('easing_set', bad, state)
    bad = EasingSet(**guard(state), edits=[{'frame': 40, 'out_type': 'hold'}])
    with pytest.raises(ValueError, match='outside'): prepare_animation('easing_set', bad, state)
    good = EasingSet(**guard(state), edits=[{'frame': 0, 'out_ease': [{'speed': 120, 'influence': 50}]}])
    result = prepare_animation('easing_set', good, state)['tracks'][0]['keys']
    assert result[0]['out_type'] == 'bezier' and result[0]['in_type'] == 'linear'


def test_retime_group_scales_internal_speed_and_protects_exit(state):
    track = state['compositions'][0]['layers'][0]['transforms']['position']
    track['keys'][0]['out_ease'][0]['speed'] = 120
    track['keys'][0].update(out_type='bezier', out_native='B')
    target = {'layer_id': IDS['layer_id'], 'property': 'position', 'expected_track_sha256': fingerprint(track)}
    request = AnimationRetime(project_id=IDS['project_id'], composition_id=IDS['composition_id'], base_sha256='a' * 64,
        start_frame=0, end_frame=30, boundary_policy='allow_change', targets=[target], new_start_frame=0, new_duration_frames=60, rounding='nearest', duration_policy='preserve_composition')
    result = prepare_animation('animation_retime', request, state)['tracks'][0]['keys']
    assert result[1]['time'] == 2 and result[0]['out_ease'][0]['speed'] == 60
    assert result[-2:] == track['keys'][-2:]
    with pytest.raises(ValueError, match='collision'):
        prepare_animation('animation_retime', request.model_copy(update={'new_start_frame': 120, 'new_duration_frames': 30}), state)
    with pytest.raises(ValueError, match='lifetime'):
        prepare_animation('animation_retime', request.model_copy(update={'new_start_frame': 140, 'new_duration_frames': 60}), state)


def test_fingerprint_ignores_samples_but_not_curves(state):
    track = state['compositions'][0]['layers'][0]['transforms']['position']
    other = copy.deepcopy(track); other['samples'] = [{'time': 0.5, 'value': [50, 200, 0]}]
    assert fingerprint(track) == fingerprint(other)
    other['keys'][0]['out_spatial'][0] = 10
    assert fingerprint(track) != fingerprint(other)


def test_composed_anticipation_settlement_is_editable_and_bounded():
    request = MotionRequest(**IDS, skill='anticipate_settle', duration=1.5, params={'distance_px': 300, 'overshoot': 0.05})
    result = plan(request, {'fps': 24, 'width': 960, 'height': 540, 'duration': 5}, {'position': [480, 270, 0], 'in_point': 0, 'out_point': 5, 'transforms': {}})
    keys = result['tracks'][0]['keys']
    assert min(k['value'][0] for k in keys) < keys[0]['value'][0] < 480
    assert max(k['value'][0] for k in keys) > 480 and keys[-1]['value'] == [480, 270]
    with pytest.raises(ValueError, match='10 frames'):
        plan(request.model_copy(update={'duration': 0.2}), {'fps': 24, 'width': 960, 'height': 540, 'duration': 5}, {'position': [480, 270], 'in_point': 0, 'out_point': 5, 'transforms': {}})


@pytest.mark.parametrize('rounding,middle', [('nearest', 23), ('floor', 22), ('ceil', 23)])
def test_retime_rounding_policy(state, rounding, middle):
    tr = state['compositions'][0]['layers'][0]['transforms']['position']
    key = copy.deepcopy(tr['keys'][0]); key.update(time=0.5, value=[50, 200, 0]); tr['keys'].insert(1, key)
    q = AnimationRetime(project_id=IDS['project_id'], composition_id=IDS['composition_id'], base_sha256='a' * 64,
        start_frame=0, end_frame=30, boundary_policy='allow_change', targets=[{'layer_id': IDS['layer_id'], 'property': 'position', 'expected_track_sha256': fingerprint(tr)}],
        new_start_frame=0, new_duration_frames=45, rounding=rounding, duration_policy='preserve_composition')
    assert prepare_animation('animation_retime', q, state)['tracks'][0]['keys'][1]['time'] == middle / 30


def test_stale_base_refused_before_ae_inspection(tmp_path):
    from unittest.mock import Mock
    from astra_video_studio.animation import AnimationService
    from astra_video_studio.config import Settings
    from astra_video_studio.existing_projects import digest
    path = tmp_path / 'project.aep'; path.write_bytes(b'original saved AEP fixture')
    service = AnimationService(Settings(tmp_path)); service.projects = Mock()
    service.projects.load.return_value = ({'sha256': digest(path)}, path)
    with pytest.raises(ValueError, match='Base version conflict'):
        service.apply('keyframes_edit', KeyframesEdit(**GUARD, mode='remove'))
    service.projects.inspect.assert_not_called()
    assert path.read_bytes() == b'original saved AEP fixture'
    assert not (tmp_path / 'versions').exists()


def test_inactive_linear_ease_is_derived_but_bezier_controls_are_guarded(state):
    track = state['compositions'][0]['layers'][0]['transforms']['position']
    other = copy.deepcopy(track)
    other['keys'][0]['out_ease'][0].update(speed=100, influence=16.666666667)
    assert fingerprint(track) == fingerprint(other)
    for item in (track, other): item['keys'][0]['out_type'] = 'bezier'
    assert fingerprint(track) != fingerprint(other)
    bad = EasingSet(**guard(state), edits=[{'frame': 0, 'out_type': 'linear', 'out_ease': [{'speed': 10, 'influence': 50}]}])
    with pytest.raises(ValueError, match='require Bezier'):
        prepare_animation('easing_set', bad, state)
