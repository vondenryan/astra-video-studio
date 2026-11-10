"""Versioned 2D scene structure operations with dependency and state checks."""
import copy
import json
import math
import shutil
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field, model_validator

from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import write_json
from astra_video_studio.motion_engine.schemas import StrictModel, Target
from astra_video_studio.project_identity import extend_project_ids, mapped_state
from astra_video_studio.project_manager import ProjectManager

ID = Annotated[str, Field(pattern=r'^[0-9a-f]{32}$')]
Name = Annotated[str, Field(min_length=1, max_length=120, pattern=r'^[^\x00-\x1f]+$')]
Blend = Literal['normal', 'multiply', 'screen', 'add']


class CompositionTarget(StrictModel):
    project_id: ID
    composition_id: ID


class CompositionCreate(StrictModel):
    project_id: ID
    name: Name = 'Scene'
    width: int = Field(default=1920, ge=64, le=7680)
    height: int = Field(default=1080, ge=64, le=4320)
    fps: float = Field(default=30, ge=1, le=120)
    duration: float = Field(default=5, ge=0.1, le=300)
    background: tuple[float, float, float] = (0, 0, 0)

    @model_validator(mode='after')
    def color(self):
        if any(not 0 <= value <= 1 for value in self.background):
            raise ValueError('Background must be RGB in [0,1]')
        return self


class CompositionUpdate(CompositionTarget):
    name: Name | None = None
    width: int | None = Field(default=None, ge=64, le=7680)
    height: int | None = Field(default=None, ge=64, le=4320)
    fps: float | None = Field(default=None, ge=1, le=120)
    duration: float | None = Field(default=None, ge=0.1, le=300)
    background: tuple[float, float, float] | None = None
    fps_policy: Literal['preserve_seconds', 'preserve_frames'] | None = None

    @model_validator(mode='after')
    def changes(self):
        if not any(getattr(self, key) is not None for key in ('name', 'width', 'height', 'fps', 'duration', 'background')):
            raise ValueError('No composition changes')
        if (self.fps is None) != (self.fps_policy is None):
            raise ValueError('FPS changes require an explicit fps_policy, and vice versa')
        if self.fps_policy == 'preserve_frames' and self.duration is not None:
            raise ValueError('preserve_frames derives duration; do not supply duration')
        if self.background is not None and any(not 0 <= v <= 1 for v in self.background):
            raise ValueError('Background must be RGB in [0,1]')
        return self


class Precompose(CompositionTarget):
    layer_ids: list[ID] = Field(min_length=1, max_length=50)
    name: Name = 'Precomp'

    @model_validator(mode='after')
    def unique(self):
        if len(set(self.layer_ids)) != len(self.layer_ids):
            raise ValueError('Duplicate layer IDs')
        return self


class LayerInsert(CompositionTarget):
    name: Name = 'Precomp layer'
    source_composition_id: ID
    start_frame: int = Field(default=0, ge=0, le=36000)


class NullCreate(CompositionTarget):
    name: Name = 'Controller'


class LayerDuplicate(Target):
    name: Name = 'Layer copy'


class LayerUpdate(Target):
    name: Name | None = None
    before_layer_id: ID | None = None
    after_layer_id: ID | None = None
    start_frame: int | None = Field(default=None, ge=-36000, le=36000)
    in_frame: int | None = Field(default=None, ge=0, le=36000)
    out_frame: int | None = Field(default=None, gt=0, le=36000)
    shift_frames: int | None = Field(default=None, ge=-36000, le=36000)
    blend_mode: Blend | None = None
    enabled: bool | None = None

    @model_validator(mode='after')
    def changes(self):
        if not any(getattr(self, key) is not None for key in ('name', 'before_layer_id', 'after_layer_id', 'start_frame', 'in_frame', 'out_frame', 'shift_frames', 'blend_mode', 'enabled')):
            raise ValueError('No layer changes')
        if self.before_layer_id and self.after_layer_id:
            raise ValueError('Choose before or after')
        if self.layer_id in (self.before_layer_id, self.after_layer_id):
            raise ValueError('Cannot reorder relative to self')
        if self.shift_frames is not None and any(v is not None for v in (self.start_frame, self.in_frame, self.out_frame)):
            raise ValueError('Choose relative shift or absolute timing')
        return self


class LayerRemove(Target):
    pass


class LayerParent(Target):
    parent_layer_id: ID | None = None
    policy: Literal['preserve_world', 'preserve_local']


class TrackMatte(Target):
    matte_layer_id: ID | None = None
    mode: Literal['alpha', 'alpha_inverted', 'luma', 'luma_inverted', 'none']

    @model_validator(mode='after')
    def valid_matte(self):
        if (self.mode == 'none') != (self.matte_layer_id is None):
            raise ValueError('none requires no matte; other modes require matte_layer_id')
        if self.matte_layer_id == self.layer_id:
            raise ValueError('Self matte is not allowed')
        return self


REQUESTS = {
    'composition_create': CompositionCreate, 'composition_update': CompositionUpdate,
    'precompose_layers': Precompose, 'composition_layer_add': LayerInsert,
    'null_create': NullCreate, 'layer_duplicate': LayerDuplicate,
    'layer_update': LayerUpdate, 'layer_remove': LayerRemove,
    'layer_parent': LayerParent, 'track_matte_set': TrackMatte,
}


def stored_background(values):
    """AE composition background is persisted in 8-bit RGB, even in this project."""
    return [math.floor(value * 255 + 0.5) / 255 for value in values]


def find_comp(data, identifier):
    matches = [c for c in data['compositions'] if c['composition_id'] == 'astra:composition:' + identifier]
    if len(matches) != 1:
        raise ValueError('Composition absent or ambiguous')
    return matches[0]


def find_layer(comp, identifier):
    matches = [l for l in comp['layers'] if l['layer_id'] == 'astra:layer:' + identifier]
    if len(matches) != 1:
        raise ValueError('Layer absent or ambiguous')
    return matches[0]


def require_static(layer):
    summary = layer['animation_summary']
    if summary['key_count'] or summary['expressions']:
        raise ValueError('This structural/timing operation requires static properties; animation editing is a later sprint')


def editable(layer):
    if layer['locked'] or not layer['editable_2d']:
        raise ValueError('Locked or unsupported 2D target')


def assert_acyclic(edges):
    visiting, visited = set(), set()
    def visit(node):
        if node in visiting:
            raise ValueError('Dependency cycle')
        if node in visited:
            return
        visiting.add(node)
        for child in edges.get(node, []):
            visit(child)
        visiting.remove(node)
        visited.add(node)
    for node in edges:
        visit(node)


def validate_graph(data):
    comps = {c['ae_id']: c for c in data['compositions']}
    edges = {key: [l['source_ae_id'] for l in c['layers'] if l['source_ae_id'] in comps] for key, c in comps.items()}
    assert_acyclic(edges)
    for comp in comps.values():
        layers = {l['ae_id']: l for l in comp['layers']}
        for field in ('parent_ae_id', 'matte_ae_id'):
            relations = {}
            for key, layer in layers.items():
                target = layer[field]
                if target is not None and target not in layers:
                    raise ValueError('Cross-composition or missing layer dependency')
                relations[key] = [target] if target is not None else []
            assert_acyclic(relations)


def prepare(action, request, data):
    """Preflight without AE mutation. All time inputs here are integer frames."""
    validate_graph(data)
    if any(l['animation_summary']['expressions'] for c in data['compositions'] for l in c['layers']):
        raise ValueError('Scene structure editing is blocked while project expressions may depend on names/indices/timing')
    context = {'new_composition_id': uuid4().hex, 'new_layer_id': uuid4().hex}
    if action == 'composition_create':
        return context
    comp = find_comp(data, request.composition_id)
    if action == 'composition_update':
        # Changing duration/FPS affects layers and nested references; do not retime opaque data.
        factor = comp['fps'] / request.fps if request.fps_policy == 'preserve_frames' else 1
        duration = request.duration if request.duration is not None else comp['duration'] * factor
        if not 0.1 <= duration <= 300:
            raise ValueError('Derived duration exceeds limits')
        context.update(time_factor=factor, duration=duration)
        if request.fps_policy == 'preserve_frames':
            for layer in comp['layers']:
                require_static(layer)
                editable(layer)
                if layer['source_kind'] == 'composition' or layer['source_has_motion']:
                    raise ValueError('Frame-preserving FPS change cannot retime nested composition/video/audio')
        for layer in comp['layers']:
            if layer['out_point'] * factor > duration + 1e-6:
                raise ValueError('Duration change would trim a layer; update its lifetime first')
        if request.fps_policy == 'preserve_frames' or duration < comp['duration']:
            if any(l['source_ae_id'] == comp['ae_id'] for c in data['compositions'] for l in c['layers']):
                raise ValueError('Referenced composition duration cannot be retimed/shortened in this sprint')
        return context
    if action in ('null_create', 'composition_layer_add'):
        if action == 'composition_layer_add':
            source = find_comp(data, request.source_composition_id)
            comp_ids = {c['ae_id'] for c in data['compositions']}
            edges = {c['ae_id']: [l['source_ae_id'] for l in c['layers'] if l['source_ae_id'] in comp_ids] for c in data['compositions']}
            edges[comp['ae_id']].append(source['ae_id'])
            assert_acyclic(edges)
            start = request.start_frame / comp['fps']
            if start >= comp['duration']:
                raise ValueError('Inserted composition starts outside timeline')
            context.update(start_time=start, out_point=min(comp['duration'], start + source['duration']))
        return context
    if action == 'precompose_layers':
        selected = [find_layer(comp, value) for value in request.layer_ids]
        selection = {l['ae_id'] for l in selected}
        for layer in selected:
            editable(layer)
        for layer in comp['layers']:
            for field in ('parent_ae_id', 'matte_ae_id'):
                if layer[field] is not None and ((layer['ae_id'] in selection) != (layer[field] in selection)):
                    raise ValueError('Precompose selection crosses parent/matte dependencies; include both sides')
        # Moving noncontiguous compositing layers can change their render order.
        positions = sorted(comp['layers'].index(layer) for layer in selected)
        if positions != list(range(positions[0], positions[-1] + 1)):
            raise ValueError('Precompose requires contiguous layers to preserve stacking')
        context['moved_ids'] = [l['layer_id'].split(':')[-1] for l in comp['layers'] if l['ae_id'] in selection]
    else:
        layer = find_layer(comp, request.layer_id)
        editable(layer)
        if action == 'layer_remove':
            dependents = [l['layer_id'] for l in comp['layers'] if l['parent_ae_id'] == layer['ae_id'] or l['matte_ae_id'] == layer['ae_id']]
            if dependents:
                raise ValueError('Layer has unresolved parent/matte dependents: ' + ', '.join(dependents))
        elif action == 'layer_update':
            anchor = request.before_layer_id or request.after_layer_id
            if anchor:
                editable(find_layer(comp, anchor))
            timing = any(v is not None for v in (request.start_frame, request.in_frame, request.out_frame, request.shift_frames))
            if timing:
                require_static(layer)
                old_start, old_in, old_out = layer['start_time'], layer['in_point'], layer['out_point']
                if request.shift_frames is not None:
                    shift = request.shift_frames / comp['fps']
                    start, incoming, outgoing = old_start + shift, old_in + shift, old_out + shift
                else:
                    start = old_start if request.start_frame is None else request.start_frame / comp['fps']
                    shift = start - old_start
                    incoming = old_in + shift if request.in_frame is None else request.in_frame / comp['fps']
                    outgoing = old_out + shift if request.out_frame is None else request.out_frame / comp['fps']
                if incoming < -1e-6 or outgoing <= incoming or outgoing > comp['duration'] + 1e-6:
                    raise ValueError('Invalid resulting layer lifetime')
                context.update(start_time=start, in_point=incoming, out_point=outgoing)
        elif action == 'layer_parent':
            parent = find_layer(comp, request.parent_layer_id) if request.parent_layer_id else None
            if parent:
                editable(parent)
            graph = {l['ae_id']: [l['parent_ae_id']] if l['parent_ae_id'] is not None else [] for l in comp['layers']}
            graph[layer['ae_id']] = [parent['ae_id']] if parent else []
            assert_acyclic(graph)
            if request.policy == 'preserve_world':
                # AE compensation is only promised for a static 2D ancestor chain.
                by_id = {l['ae_id']: l for l in comp['layers']}
                for head in (layer, parent, by_id.get(layer['parent_ae_id'])):
                    while head:
                        require_static(head)
                        editable(head)
                        if not head['auto_orient_none']:
                            raise ValueError('World-preserving parenting requires no auto orientation')
                        head = by_id.get(head['parent_ae_id'])
        elif action == 'track_matte_set':
            if not layer['matte_api']:
                raise ValueError('Track matte API unavailable')
            matte = find_layer(comp, request.matte_layer_id) if request.matte_layer_id else None
            if matte:
                editable(matte)
            graph = {l['ae_id']: [l['matte_ae_id']] if l['matte_ae_id'] is not None else [] for l in comp['layers']}
            graph[layer['ae_id']] = [matte['ae_id']] if matte else []
            assert_acyclic(graph)
    return context


def equivalent(actual, expected, path='state'):
    if isinstance(expected, dict):
        if set(actual) != set(expected):
            raise ValueError(f'{path}: fields changed')
        for key in expected:
            equivalent(actual[key], expected[key], path + '.' + key)
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise ValueError(f'{path}: list changed')
        for index, value in enumerate(expected):
            equivalent(actual[index], value, f'{path}[{index}]')
    elif isinstance(expected, (float, int)) and not isinstance(expected, bool):
        if not isinstance(actual, (int, float)) or not math.isclose(actual, expected, rel_tol=1e-6, abs_tol=1e-5):
            raise ValueError(f'{path}: {actual} != {expected}')
    elif actual != expected:
        raise ValueError(f'{path}: {actual} != {expected}')


def verify(action, request, before, after, context):
    """Build expected state, compare all retained metadata, validate new objects."""
    validate_graph(after)
    expected = copy.deepcopy(before['compositions'])
    actual = copy.deepcopy(after['compositions'])
    equivalent(after['footage'], before['footage'], 'footage')
    def new_comp():
        matches = [c for c in actual if c['composition_id'] == 'astra:composition:' + context['new_composition_id']]
        if len(matches) != 1:
            raise ValueError('New composition identity absent/ambiguous')
        return matches[0]
    if action == 'composition_create':
        new = new_comp()
        for field in ('name', 'width', 'height', 'fps', 'duration', 'background'):
            equivalent(new[field], stored_background(request.background) if field == 'background' else getattr(request, field), field)
        if new['layers']:
            raise ValueError('New composition is not empty')
        actual.remove(new)
    else:
        old = find_comp({'compositions': expected}, request.composition_id)
        changed = find_comp({'compositions': actual}, request.composition_id)
        if action == 'composition_update':
            for field in ('name', 'width', 'height', 'fps', 'background'):
                value = getattr(request, field)
                if value is not None:
                    old[field] = stored_background(value) if field == 'background' else value
            old['duration'] = context['duration']
            for layer in old['layers']:
                for field in ('start_time', 'in_point', 'out_point'):
                    layer[field] *= context['time_factor']
            # Sampling instants depend on duration/fps; keys and static values remain checked.
            if request.fps is not None or request.duration is not None:
                for collection in (old['layers'], changed['layers']):
                    for layer in collection:
                        for track in layer['transforms'].values():
                            track['samples'] = []
        elif action in ('null_create', 'composition_layer_add', 'layer_duplicate', 'precompose_layers'):
            inserted = find_layer(changed, context['new_layer_id'])
            if inserted['name'] != request.name or not inserted['editable_2d'] or inserted['three_d']:
                raise ValueError('Inserted layer metadata mismatch')
            if action == 'null_create':
                if not inserted['is_null']:
                    raise ValueError('New layer is not a null')
            elif action == 'composition_layer_add':
                source = find_comp(before, request.source_composition_id)
                equivalent(inserted['source_ae_id'], source['ae_id'])
                equivalent(inserted['source_kind'], 'composition')
                for field in ('start_time', 'out_point'):
                    equivalent(inserted[field], context[field], field)
                equivalent(inserted['in_point'], context['start_time'])
            elif action == 'layer_duplicate':
                source = copy.deepcopy(find_layer(old, request.layer_id))
                for field in ('layer_id', 'ae_id', 'comment', 'name'):
                    source[field] = inserted[field]
                equivalent(inserted, source, 'duplicated layer')
            else:
                new = new_comp()
                equivalent(new['duration'], old['duration'])
                for field in ('name', 'width', 'height', 'fps', 'background'):
                    equivalent(new[field], request.name if field == 'name' else old[field], field)
                moved = [l for l in old['layers'] if l['layer_id'].split(':')[-1] in context['moved_ids']]
                # Native precompose may replace native IDs; translate internal relations explicitly.
                translation = {a['ae_id']: b['ae_id'] for a, b in zip(moved, new['layers'], strict=True)}
                for a, b in zip(moved, new['layers'], strict=True):
                    a['ae_id'] = b['ae_id']
                    for field in ('parent_ae_id', 'matte_ae_id'):
                        if a[field] is not None:
                            a[field] = translation[a[field]]
                    equivalent(b, a, 'precomposed layer')
                old['layers'] = [l for l in old['layers'] if l not in moved]
                equivalent(inserted['source_ae_id'], new['ae_id'])
                actual.remove(new)
            changed['layers'].remove(inserted)
        else:
            layer = find_layer(old, request.layer_id)
            target = find_layer(changed, request.layer_id) if action != 'layer_remove' else None
            if action == 'layer_remove':
                old['layers'].remove(layer)
            elif action == 'layer_update':
                for field in ('name', 'blend_mode', 'enabled'):
                    value = getattr(request, field)
                    if value is not None:
                        layer[field] = value
                for field in ('start_time', 'in_point', 'out_point'):
                    if field in context:
                        layer[field] = context[field]
                anchor_id = request.before_layer_id or request.after_layer_id
                if anchor_id:
                    old['layers'].remove(layer)
                    index = old['layers'].index(find_layer(old, anchor_id)) + (1 if request.after_layer_id else 0)
                    old['layers'].insert(index, layer)
            elif action == 'track_matte_set':
                layer['matte_ae_id'] = find_layer(old, request.matte_layer_id)['ae_id'] if request.matte_layer_id else None
                layer['matte_mode'] = request.mode
                # Native assignment may change matte visibility. Require that the template restore it.
            elif action == 'layer_parent':
                layer['parent_ae_id'] = find_layer(old, request.parent_layer_id)['ae_id'] if request.parent_layer_id else None
                if request.policy == 'preserve_world':
                    if any(t['keys'] or t['expression_enabled'] for t in target['transforms'].values()):
                        raise ValueError('Parenting unexpectedly animated a property')
                    # Native world basis must match pre-parent samples, not only local transform values.
                    equivalent(target['world_basis'], layer['world_basis'], 'world transform')
                    for field in ('position', 'anchor', 'transforms'):
                        layer[field] = copy.deepcopy(target[field])
    # World basis is derived; local tracks and relations are checked above. For preserve_world
    # the world comparison is explicit; preserve_local intentionally changes world space.
    for comps in (expected, actual):
        for comp in comps:
            for layer in comp['layers']:
                layer.pop('world_basis', None)
    # Null backing solids are not file footage and are represented on the layer itself.
    equivalent(sorted(actual, key=lambda c: c['ae_id']), sorted(expected, key=lambda c: c['ae_id']))


class SceneService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.projects = ProjectManager(settings)

    def apply(self, action, request):
        if action not in REQUESTS or not isinstance(request, REQUESTS[action]):
            raise ValueError('Unknown/mismatched scene operation')
        manifest, source = self.projects.load(request.project_id)
        saved = json.loads((source.parent / 'version.json').read_text()) if manifest.get('current_version') else manifest
        source_hash = digest(source)
        if source_hash != saved.get('sha256'):
            raise ValueError('Source changed outside Astra')
        inspection = self.projects.inspect(request.project_id, include_world=True)
        if inspection.status != 'succeeded':
            return inspection
        before = inspection.data
        if before['project_dirty']:
            raise ValueError('Preserve unsaved changes before scene editing')
        context = prepare(action, request, before)
        version_id = uuid4().hex
        directory = self.settings.contained_path(f'projects/{request.project_id}/versions/{version_id}')
        directory.mkdir(parents=True, exist_ok=False)
        output, snapshot = directory / 'project.aep', directory / 'source-snapshot.aep'
        shutil.copyfile(source, snapshot)
        if digest(snapshot) != source_hash:
            raise ValueError('Snapshot mismatch')
        version = {'version_id': version_id, 'status': 'prepared', 'source': str(source), 'source_sha256': source_hash, 'snapshot': str(snapshot), 'action': action, 'request': request.model_dump()}
        write_json(directory / 'version.json', version)
        result = self.projects.runner.run('scene_edit', {
            'project_path': source.as_posix(), 'version_path': output.as_posix(),
            'id_map': manifest.get('id_map'), 'scene_action': action, 'include_world': True,
            'request': request.model_dump(), 'context': context, 'expected_state': before,
        })
        result.project_id, result.project_path = request.project_id, str(output)
        if result.status == 'succeeded':
            try:
                if digest(source) != source_hash or not output.is_file():
                    raise ValueError('Source/output preservation mismatch')
                # Seed known IDs before allowing a duplicate's inherited comment to enter mappings.
                mapping = extend_project_ids(manifest, result.data)
                moved = result.data.get('scene_edit', {}).get('moved_native_ids', [])
                if action == 'precompose_layers':
                    if len(moved) != len(context['moved_ids']):
                        raise ValueError('Precompose identity correspondence missing')
                    for native, stable in zip(moved, context['moved_ids'], strict=True):
                        mapping['layers'][str(native)] = stable
                state = mapped_state(result.data, mapping)
                verify(action, request, before, state, context)
                manifest['id_map'] = mapping
                manifest['current_version'] = version_id
                result.data = state
                result.data.update(version_id=version_id, created_composition_id=context['new_composition_id'] if action in ('composition_create', 'precompose_layers') else None,
                                   created_layer_id=context['new_layer_id'] if action in ('null_create', 'composition_layer_add', 'layer_duplicate', 'precompose_layers') else None)
                version['sha256'] = digest(output)
                result.artifacts.extend([str(output), str(snapshot)])
            except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
                result.status, result.error = 'failed', 'Scene verification failed: ' + str(error)
        version.update(status=result.status, operation_id=result.operation_id, result=result.model_dump())
        write_json(directory / 'version.json', version)
        if result.status == 'succeeded':
            write_json(self.settings.contained_path(f'projects/{request.project_id}/project.json'), manifest)
        self.projects._finalize_job(result)
        return result
