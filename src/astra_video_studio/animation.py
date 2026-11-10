"""Explicit, optimistic-concurrency guarded edits of native manual 2D tracks."""
import copy
import hashlib
import json
import math
import shutil
from typing import Literal
from uuid import uuid4

from pydantic import Field, model_validator

from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import write_json
from astra_video_studio.motion_engine.schemas import StrictModel, Target
from astra_video_studio.project_manager import ProjectManager
from astra_video_studio.scene_editing import ID, CompositionTarget, editable, equivalent, find_comp, find_layer

Property = Literal['position', 'anchor', 'scale', 'rotation', 'opacity']
Interpolation = Literal['linear', 'bezier', 'hold']


def semantic_state(value):
    """Linear/Hold ease records are AE-derived, not stored editable controls."""
    if isinstance(value, dict):
        ignored = {side + '_ease' for side in ('in', 'out') if value.get(side + '_type') in ('linear', 'hold')}
        return {k: semantic_state(v) for k, v in value.items() if k not in ignored}
    if isinstance(value, list): return [semantic_state(v) for v in value]
    return value


def fingerprint(value):
    def normalized(item):
        if isinstance(item, dict): return {k: normalized(v) for k, v in item.items() if k not in ('samples', 'world_basis')}
        if isinstance(item, list): return [normalized(v) for v in item]
        if isinstance(item, float): return round(item, 9)
        return item
    return hashlib.sha256(json.dumps(normalized(semantic_state(value)), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class AnimationInspect(CompositionTarget):
    layer_ids: list[ID] = Field(default_factory=list, max_length=20)
    sample_times: list[float] = Field(default_factory=list, max_length=32)

    @model_validator(mode='after')
    def times(self):
        if any(not 0 <= time <= 300 for time in self.sample_times): raise ValueError('Sample outside 0–300 seconds')
        if len(set(self.layer_ids)) != len(self.layer_ids): raise ValueError('Duplicate inspect target')
        return self


class Ease(StrictModel):
    speed: float = Field(ge=-1_000_000, le=1_000_000)
    influence: float = Field(default=100 / 3, ge=0.1, le=100)


class KeySpec(StrictModel):
    frame: int = Field(ge=0, le=36000)
    value: list[float] = Field(min_length=1, max_length=2)
    in_type: Interpolation | None = None
    out_type: Interpolation | None = None
    in_ease: list[Ease] | None = Field(default=None, min_length=1, max_length=2)
    out_ease: list[Ease] | None = Field(default=None, min_length=1, max_length=2)
    in_tangent: tuple[float, float] | None = None
    out_tangent: tuple[float, float] | None = None


class Window(StrictModel):
    start_frame: int = Field(ge=0, le=36000)
    end_frame: int = Field(gt=0, le=36000)
    boundary_policy: Literal['preserve_boundaries', 'allow_change']

    @model_validator(mode='after')
    def span(self):
        if self.end_frame <= self.start_frame: raise ValueError('Window must have positive duration')
        return self


class VersionGuard(StrictModel):
    base_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class TrackGuard(Target, Window, VersionGuard):
    property: Property
    expected_track_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class KeyframesEdit(TrackGuard):
    mode: Literal['insert', 'update', 'remove', 'replace', 'move']
    keys: list[KeySpec] = Field(default_factory=list, max_length=300)
    shift_frames: int | None = Field(default=None, ge=-36000, le=36000)

    @model_validator(mode='after')
    def intent(self):
        if self.mode in ('insert', 'update', 'replace') and not self.keys: raise ValueError('This mode requires keys')
        if self.mode in ('remove', 'move') and self.keys: raise ValueError('Remove/move uses the explicit window, not new keys')
        if (self.mode == 'move') != (self.shift_frames is not None): raise ValueError('shift_frames belongs only to move')
        if self.shift_frames == 0: raise ValueError('Move must have a nonzero shift')
        if len({key.frame for key in self.keys}) != len(self.keys): raise ValueError('Duplicate requested key frame')
        if any(not self.start_frame <= key.frame <= self.end_frame for key in self.keys): raise ValueError('Key outside authorized window')
        return self


class EasePatch(StrictModel):
    frame: int = Field(ge=0, le=36000)
    in_type: Interpolation | None = None
    out_type: Interpolation | None = None
    in_ease: list[Ease] | None = Field(default=None, min_length=1, max_length=2)
    out_ease: list[Ease] | None = Field(default=None, min_length=1, max_length=2)

    @model_validator(mode='after')
    def nonempty(self):
        if all(getattr(self, field) is None for field in ('in_type', 'out_type', 'in_ease', 'out_ease')): raise ValueError('No easing change')
        return self


class EasingSet(TrackGuard):
    edits: list[EasePatch] = Field(min_length=1, max_length=300)


class PathPatch(StrictModel):
    frame: int = Field(ge=0, le=36000)
    in_tangent: tuple[float, float] | None = None
    out_tangent: tuple[float, float] | None = None

    @model_validator(mode='after')
    def nonempty(self):
        if self.in_tangent is None and self.out_tangent is None: raise ValueError('No spatial tangent changes')
        if any(abs(v) > 20000 for values in (self.in_tangent, self.out_tangent) if values for v in values): raise ValueError('Tangent exceeds ±20000 px')
        return self


class MotionPathSet(TrackGuard):
    edits: list[PathPatch] = Field(min_length=1, max_length=300)


class TrackRef(StrictModel):
    layer_id: ID
    property: Property
    expected_track_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class AnimationRetime(CompositionTarget, Window, VersionGuard):
    targets: list[TrackRef] = Field(min_length=1, max_length=20)
    new_start_frame: int = Field(ge=0, le=36000)
    new_duration_frames: int = Field(gt=0, le=36000)
    rounding: Literal['nearest', 'floor', 'ceil']
    duration_policy: Literal['preserve_composition']

    @model_validator(mode='after')
    def unique(self):
        if len({(t.layer_id, t.property) for t in self.targets}) != len(self.targets): raise ValueError('Duplicate retime target')
        return self


class MotionBlurSet(CompositionTarget, VersionGuard):
    expected_composition_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    layer_ids: list[ID] = Field(min_length=1, max_length=20)
    composition_enabled: bool
    layers_enabled: bool
    shutter_angle: float = Field(ge=0, le=720)
    shutter_phase: float = Field(ge=-360, le=360)
    samples_per_frame: int = Field(ge=2, le=64)
    adaptive_sample_limit: int = Field(ge=16, le=256)

    @model_validator(mode='after')
    def unique(self):
        if len(set(self.layer_ids)) != len(self.layer_ids): raise ValueError('Duplicate blur target')
        return self


ANIMATION_REQUESTS = {'keyframes_edit': KeyframesEdit, 'easing_set': EasingSet, 'motion_path_set': MotionPathSet,
                      'animation_retime': AnimationRetime, 'motion_blur_set': MotionBlurSet}


def get_track(comp, layer_id, name, expected):
    layer = find_layer(comp, layer_id)
    editable(layer)
    track = layer['transforms'][name]
    if not track['available'] or track['separated'] or track.get('expression_present', track['expression_enabled']):
        raise ValueError('Unavailable/separated/expression track is protected')
    if fingerprint(track) != expected: raise ValueError('Track state conflict; inspect again')
    for key in track['keys']:
        if any(key.get(flag) for flag in ('temporal_auto', 'spatial_auto', 'roving', 'temporal_continuous', 'spatial_continuous')):
            raise ValueError('Automatic/continuous/roving tracks require explicit conversion outside this editor')
    return layer, track


def at_frame(keys, frame_number, fps):
    matches = [k for k in keys if abs(k['time'] * fps - frame_number) < 1e-5]
    if len(matches) != 1: raise ValueError('Expected exactly one existing key at frame ' + str(frame_number))
    return matches[0]


def validate_key(key, name, spatial):
    value = key['value'] if isinstance(key['value'], list) else [key['value']]
    if name in ('position', 'anchor'):
        if len(value) not in (2, 3) or any(abs(v) > 100000 for v in value[:2]): raise ValueError('Invalid position/anchor value')
    elif name == 'scale':
        if len(value) not in (2, 3) or any(not 0 < v <= 1000 for v in value[:2]): raise ValueError('Invalid scale value')
    elif len(value) != 1 or (name == 'opacity' and not 0 <= value[0] <= 100) or (name == 'rotation' and abs(value[0]) > 36000):
        raise ValueError('Invalid scalar key value')
    dimensions = 1 if spatial or name in ('rotation', 'opacity') else len(value)
    for side in ('in', 'out'):
        if len(key[side + '_ease']) != dimensions: raise ValueError('Ease dimensions mismatch')
        for ease in key[side + '_ease']:
            Ease.model_validate(ease)
            if spatial and ease['speed'] < 0: raise ValueError('Spatial speed must be nonnegative')
        tangent = key[side + '_spatial']
        if spatial:
            if not isinstance(tangent, list) or len(tangent) != len(value) or any(abs(v) > 20000 for v in tangent): raise ValueError('Spatial tangent dimensions/bounds mismatch')
        elif tangent is not None: raise ValueError('Nonspatial property cannot have spatial tangents')


def patch_key(key, patch, name, track, constants):
    spatial = track['spatial']
    for side in ('in', 'out'):
        if patch.get(side + '_type') is not None: key[side + '_type'] = patch[side + '_type']
        if patch.get(side + '_ease') is not None:
            if patch.get(side + '_type') in ('linear', 'hold'):
                raise ValueError('Explicit temporal ease controls require Bezier interpolation')
            values = copy.deepcopy(patch[side + '_ease'])
            if name == 'scale' and len(key['value']) == 3 and len(values) == 2: values.append({'speed': 0, 'influence': values[-1]['influence']})
            key[side + '_ease'] = values
            if patch.get(side + '_type') is None: key[side + '_type'] = 'bezier'
        if patch.get(side + '_tangent') is not None:
            if not spatial: raise ValueError('Tangents require a spatial property')
            values = list(patch[side + '_tangent'])
            if len(key['value']) == 3: values.append(0)
            key[side + '_spatial'] = values
        key[side + '_native'] = constants[key[side + '_type']]
    validate_key(key, name, spatial)


def make_key(spec, track, name, fps, constants, previous=None):
    value = list(spec.value)
    expected = 2 if name in ('position', 'anchor', 'scale') else 1
    if len(value) != expected: raise ValueError('Key value dimensions must match the 2D property')
    if expected == 2 and len(track['value']) == 3: value.append(100 if name == 'scale' else 0)
    scalar_value = value[0] if expected == 1 else value
    dimensions = 1 if track['spatial'] or expected == 1 else len(value)
    key = copy.deepcopy(previous) if previous else {
        'time': spec.frame / fps, 'value': scalar_value, 'in_type': 'linear', 'out_type': 'linear',
        'in_ease': [{'speed': 0, 'influence': 100 / 3}] * dimensions,
        'out_ease': [{'speed': 0, 'influence': 100 / 3}] * dimensions,
        'temporal_auto': False, 'temporal_continuous': False,
        'in_spatial': [0] * len(value) if track['spatial'] else None,
        'out_spatial': [0] * len(value) if track['spatial'] else None,
        'spatial_auto': False, 'spatial_continuous': False, 'roving': False,
    }
    key['value'] = scalar_value
    patch_key(key, spec.model_dump(mode='json', exclude_unset=True), name, track, constants)
    return key


def enforce_boundaries(old, new, start, end, policy, fps):
    if policy == 'allow_change': return
    if not old: raise ValueError('A new track requires allow_change; no existing boundaries to preserve')
    for boundary, side in ((start, 'in'), (end, 'out')):
        a, b = at_frame(old, boundary, fps), at_frame(new, boundary, fps)
        equivalent(b['value'], a['value'], 'boundary value')
        fields = [side + '_type', side + '_spatial']
        if a[side + '_type'] == 'bezier': fields.append(side + '_ease')
        for field in fields:
            equivalent(b[field], a[field], 'external boundary ' + field)


def compile_track(action, request, ref, comp, before):
    layer, track = get_track(comp, ref.layer_id, ref.property, ref.expected_track_sha256)
    fps, name = comp['fps'], ref.property
    old, keys = track['keys'], copy.deepcopy(track['keys'])
    selected = [k for k in keys if request.start_frame - 1e-5 <= k['time'] * fps <= request.end_frame + 1e-5]
    constants = before['interpolation_constants']
    if action == 'keyframes_edit':
        if request.mode in ('remove', 'move', 'update') and not selected: raise ValueError('No keys in selected interval')
        if request.mode in ('remove', 'replace'): keys = [k for k in keys if k not in selected]
        if request.mode == 'move':
            for key in selected: key['time'] += request.shift_frames / fps
        elif request.mode in ('insert', 'update', 'replace'):
            for spec in request.keys:
                existing = [k for k in keys if abs(k['time'] * fps - spec.frame) < 1e-5]
                if request.mode in ('insert', 'replace') and existing: raise ValueError('Insertion collides with existing key')
                previous = at_frame(keys, spec.frame, fps) if request.mode == 'update' else None
                fresh = make_key(spec, track, name, fps, constants, previous)
                if previous: keys[keys.index(previous)] = fresh
                else: keys.append(fresh)
    elif action in ('easing_set', 'motion_path_set'):
        if action == 'motion_path_set' and not track['spatial']: raise ValueError('Trajectory requires position/anchor spatial property')
        if len({e.frame for e in request.edits}) != len(request.edits): raise ValueError('Duplicate key edit frame')
        for edit in request.edits:
            if not request.start_frame <= edit.frame <= request.end_frame: raise ValueError('Patch outside authorized interval')
            key = at_frame(keys, edit.frame, fps)
            patch_key(key, edit.model_dump(mode='json', exclude_unset=True), name, track, constants)
    else:
        if not selected: raise ValueError('No keys to retime')
        source = copy.deepcopy(selected)
        duration = request.end_frame - request.start_frame
        for key in selected:
            mapped = request.new_start_frame + (key['time'] * fps - request.start_frame) * request.new_duration_frames / duration
            target = math.floor(mapped + 0.5) if request.rounding == 'nearest' else math.floor(mapped) if request.rounding == 'floor' else math.ceil(mapped)
            key['time'] = target / fps
        for index, key in enumerate(selected):
            for side, neighbor in (('in', index - 1), ('out', index + 1)):
                if not 0 <= neighbor < len(selected): continue
                old_span = abs(source[index]['time'] - source[neighbor]['time'])
                new_span = abs(selected[index]['time'] - selected[neighbor]['time'])
                if new_span <= 1e-8: raise ValueError('Retime rounding collides key times')
                for ease in key[side + '_ease']: ease['speed'] *= old_span / new_span
    keys.sort(key=lambda k: k['time'])
    if not keys: raise ValueError('Cannot remove the final key; static conversion needs a separate explicit API')
    if len(keys) > 900: raise ValueError('Track exceeds 900-key bound')
    if any(b['time'] - a['time'] < 1 / fps - 1e-6 for a, b in zip(keys, keys[1:])): raise ValueError('Key collision or subframe spacing')
    for key in keys:
        if key['time'] < max(0, layer['in_point']) - 1e-5 or key['time'] > min(comp['duration'], layer['out_point']) + 1e-5:
            raise ValueError('Resulting key outside layer/composition lifetime')
        validate_key(key, name, track['spatial'])
    enforce_boundaries(old, keys, request.start_frame, request.end_frame, request.boundary_policy, fps)
    return {'layer_id': ref.layer_id, 'property': name, 'keys': keys, 'old_key_count': len(old)}


def prepare_animation(action, request, before):
    comp = find_comp(before, request.composition_id)
    if before['project_dirty']: raise ValueError('Preserve unsaved edits before editing animation')
    if any(l['animation_summary']['expressions'] for c in before['compositions'] for l in c['layers']): raise ValueError('Stored project expressions are protected')
    if action == 'motion_blur_set':
        if fingerprint(comp) != request.expected_composition_sha256: raise ValueError('Composition state conflict')
        for identifier in request.layer_ids: editable(find_layer(comp, identifier))
        return {'tracks': []}
    refs = request.targets if action == 'animation_retime' else [TrackRef(layer_id=request.layer_id, property=request.property, expected_track_sha256=request.expected_track_sha256)]
    return {'tracks': [compile_track(action, request, ref, comp, before) for ref in refs], 'inactive_temporal_ease': 'AE-derived on Linear/Hold sides; only Bezier ease controls are writable/compared'}


def verify_animation(action, request, before, after, plan):
    normalized = copy.deepcopy(after)
    old_comp, new_comp = find_comp(before, request.composition_id), find_comp(normalized, request.composition_id)
    deltas = {}
    for changed in plan['tracks']:
        old, new = find_layer(old_comp, changed['layer_id']), find_layer(new_comp, changed['layer_id'])
        name = changed['property']
        equivalent(semantic_state(new['transforms'][name]['keys']), semantic_state(changed['keys']), 'native keys and curves')
        for field in ('available', 'separated', 'spatial', 'expression_enabled', 'expression_present'):
            equivalent(new['transforms'][name][field], old['transforms'][name][field], 'track flags')
        new['transforms'][name] = copy.deepcopy(old['transforms'][name])
        if name in ('position', 'anchor'): new[name] = copy.deepcopy(old[name])
        deltas[changed['layer_id']] = deltas.get(changed['layer_id'], 0) + len(changed['keys']) - changed['old_key_count']
    for identifier, delta in deltas.items():
        old, new = find_layer(old_comp, identifier), find_layer(new_comp, identifier)
        summary = dict(old['animation_summary']); summary['key_count'] += delta
        equivalent(new['animation_summary'], summary)
        new['animation_summary'] = copy.deepcopy(old['animation_summary'])
    if action == 'motion_blur_set':
        settings = {'motion_blur': request.composition_enabled, 'shutter_angle': request.shutter_angle, 'shutter_phase': request.shutter_phase,
                    'blur_samples': request.samples_per_frame, 'blur_adaptive_limit': request.adaptive_sample_limit}
        for field, expected in settings.items():
            equivalent(new_comp[field], expected, 'blur ' + field); new_comp[field] = old_comp[field]
        for identifier in request.layer_ids:
            old, new = find_layer(old_comp, identifier), find_layer(new_comp, identifier)
            equivalent(new['motion_blur'], request.layers_enabled); new['motion_blur'] = old['motion_blur']
    equivalent(semantic_state(normalized['compositions']), semantic_state(before['compositions']), 'retained project state')
    equivalent(normalized['footage'], before['footage'])


class AnimationService:
    def __init__(self, settings):
        self.settings, self.projects = settings, ProjectManager(settings)

    def inspect(self, request):
        manifest, source = self.projects.load(request.project_id)
        result = self.projects.runner.run('inspect', {'project_path': source.as_posix(), 'id_map': manifest.get('id_map'), 'sample_times': request.sample_times})
        result.project_id, result.project_path = request.project_id, str(source)
        if result.status == 'succeeded':
            comp = find_comp(result.data, request.composition_id)
            if any(t > comp['duration'] for t in request.sample_times): raise ValueError('Sample time outside composition')
            layers = [find_layer(comp, identifier) for identifier in request.layer_ids] if request.layer_ids else comp['layers']
            result.data['animation_state'] = {'base_sha256': digest(source), 'composition_sha256': fingerprint(comp),
                'tracks': [{'layer_id': layer['layer_id'].split(':')[-1], 'property': name, 'track_sha256': fingerprint(track), 'track': track} for layer in layers for name, track in layer['transforms'].items()]}
        self.projects._finalize_job(result)
        return result

    def apply(self, action, request):
        if action not in ANIMATION_REQUESTS or not isinstance(request, ANIMATION_REQUESTS[action]): raise ValueError('Unknown animation edit')
        manifest, source = self.projects.load(request.project_id)
        saved = json.loads((source.parent / 'version.json').read_text(encoding='utf-8')) if manifest.get('current_version') else manifest
        source_hash = digest(source)
        if source_hash != request.base_sha256 or source_hash != saved.get('sha256'): raise ValueError('Base version conflict; inspect current version')
        inspected = self.projects.inspect(request.project_id)
        if inspected.status != 'succeeded': return inspected
        plan = prepare_animation(action, request, inspected.data)
        identifier = uuid4().hex
        directory = self.settings.contained_path(f'projects/{request.project_id}/versions/{identifier}'); directory.mkdir(parents=True, exist_ok=False)
        output, snapshot = directory / 'project.aep', directory / 'source-snapshot.aep'
        shutil.copyfile(source, snapshot)
        if digest(snapshot) != source_hash: raise ValueError('Snapshot mismatch')
        version = {'version_id': identifier, 'status': 'prepared', 'source': str(source), 'snapshot': str(snapshot), 'source_sha256': source_hash, 'action': action, 'request': request.model_dump(), 'plan': plan}
        write_json(directory / 'version.json', version)
        result = self.projects.runner.run('animation_edit', {'project_path': source.as_posix(), 'version_path': output.as_posix(), 'id_map': manifest.get('id_map'), 'animation_action': action, 'request': request.model_dump(), 'animation_plan': plan, 'expected_state': inspected.data})
        result.project_id, result.project_path = request.project_id, str(output)
        if result.status == 'succeeded':
            try:
                if digest(source) != source_hash or not output.is_file(): raise ValueError('Source/output mismatch')
                verify_animation(action, request, inspected.data, result.data, plan)
                version['sha256'] = digest(output); manifest['current_version'] = identifier
                result.data.update(version_id=identifier, applied_animation_plan=plan)
                result.artifacts.extend([str(output), str(snapshot)])
            except (ValueError, OSError, KeyError, TypeError) as error:
                result.status, result.error = 'failed', 'Animation verification failed: ' + str(error)
        version.update(status=result.status, operation_id=result.operation_id, result=result.model_dump())
        write_json(directory / 'version.json', version)
        if result.status == 'succeeded': write_json(self.settings.contained_path(f'projects/{request.project_id}/project.json'), manifest)
        self.projects._finalize_job(result)
        return result
