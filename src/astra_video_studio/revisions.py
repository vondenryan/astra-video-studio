"""Immutable, property-guarded revision plans and append-only version history."""
import copy
import json
import re
import shutil
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field, model_validator

from astra_video_studio.animation import (KeyframesEdit, EasingSet, MotionPathSet, AnimationRetime,
    fingerprint, semantic_state, prepare_animation, verify_animation)
from astra_video_studio.ae_bridge.result_artifacts import PROTOCOL, EVIDENCE_MAX_BYTES, revision_evidence_estimate
from astra_video_studio.design import TextStyleSet, prepare_design, verify_design, expanded_styles
from astra_video_studio.existing_projects import ExistingProjectService, digest
from astra_video_studio.jobs import write_json, timestamp
from astra_video_studio.motion_engine.schemas import StrictModel, Target, TransformRequest
from astra_video_studio.project_manager import ProjectManager, valid_id
from astra_video_studio.project_identity import build_id_map
from astra_video_studio.scene_editing import (ID, LayerUpdate, editable, find_comp, find_layer,
    prepare as prepare_scene, verify as verify_scene, equivalent)
from astra_video_studio.schemas import OperationResult

SHA = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
Version = ID | Literal['initial']


class ContentSet(Target):
    text: str = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def safe_text(self):
        if any(ord(c) < 32 and c not in '\r\n\t' for c in self.text):
            raise ValueError('Unsupported text control character')
        return self


class ContentPatch(StrictModel):
    action: Literal['content_set']
    request: ContentSet


class StylePatch(StrictModel):
    action: Literal['text_style_set']
    request: TextStyleSet


class TransformPatch(StrictModel):
    action: Literal['layer_transform']
    request: TransformRequest


class TimingPatch(StrictModel):
    action: Literal['layer_update']
    request: LayerUpdate

    @model_validator(mode='after')
    def timing_only(self):
        if any(getattr(self.request, k) is not None for k in ('name', 'before_layer_id', 'after_layer_id', 'blend_mode', 'enabled')):
            raise ValueError('Revision layer_update accepts timing only')
        return self


class KeysPatch(StrictModel):
    action: Literal['keyframes_edit']
    request: KeyframesEdit


class EasePatch(StrictModel):
    action: Literal['easing_set']
    request: EasingSet


class PathPatch(StrictModel):
    action: Literal['motion_path_set']
    request: MotionPathSet


class RetimePatch(StrictModel):
    action: Literal['animation_retime']
    request: AnimationRetime


Patch = Annotated[ContentPatch | StylePatch | TransformPatch | TimingPatch | KeysPatch | EasePatch | PathPatch | RetimePatch, Field(discriminator='action')]


class RevisionPlanRequest(StrictModel):
    project_id: ID
    base_sha256: SHA
    instruction: str = Field(min_length=1, max_length=2000)
    operations: list[Patch] = Field(min_length=1, max_length=8)

    @model_validator(mode='after')
    def project_scope(self):
        if any(op.request.project_id != self.project_id for op in self.operations):
            raise ValueError('Every operation must target the same project')
        if any(getattr(op.request, 'base_sha256', self.base_sha256) != self.base_sha256 for op in self.operations):
            raise ValueError('Animation base hash must match revision base')
        return self


class RevisionApplyRequest(StrictModel):
    revision_id: ID
    plan_sha256: SHA
    expected_current_sha256: SHA
    capture_manual: bool = False


class VersionCompareRequest(StrictModel):
    project_id: ID
    left: Version
    right: Version


class VersionRestoreRequest(StrictModel):
    project_id: ID
    version_id: Version
    expected_current_sha256: SHA
    reason: str = Field(min_length=1, max_length=2000)


class DirectorPatchRequest(Target):
    base_sha256: SHA
    instruction: str = Field(min_length=1, max_length=2000)


ANIMATIONS = {'keyframes_edit', 'easing_set', 'motion_path_set', 'animation_retime'}


def check_evidence_budget(settings, state, contexts):
    if settings.ae_result_transport == PROTOCOL:
        estimated, limit = revision_evidence_estimate(state, contexts), EVIDENCE_MAX_BYTES
    else:
        estimated, limit = len(json.dumps(state)) * (len(contexts) + 2), 1_200_000
    if estimated > limit: raise ValueError('Revision evidence exceeds bounded native evidence budget; split the patch/project')
    return {'protocol': settings.ae_result_transport, 'estimated_bytes': estimated, 'limit_bytes': limit}


def targets(op):
    q = op.request
    if op.action == 'animation_retime': return [(t.layer_id, t.property) for t in q.targets]
    if op.action in ANIMATIONS: return [(q.layer_id, q.property)]
    if op.action == 'layer_transform': return [(q.layer_id, k) for k, v in q.values.model_dump().items() if v is not None]
    return [(q.layer_id, {'content_set': 'text', 'text_style_set': 'text_style', 'layer_update': 'timing'}[op.action])]


def footprints(op, state):
    """Compare properties read/written; unrelated manual style/layout may survive."""
    q = op.request
    comp = find_comp(state, q.composition_id)
    root = q.composition_id + '/'
    values = {root + 'timeline': {k: comp[k] for k in ('fps', 'duration')}}
    for layer_id, prop in targets(op):
        layer = find_layer(comp, layer_id)
        prefix = root + layer_id + '/'
        values[prefix + 'identity'] = {k: layer[k] for k in ('ae_id', 'locked', 'editable_2d', 'parent_ae_id', 'in_point', 'out_point', 'start_time')}
        if prop == 'timing':
            values[prefix + prop] = {k: layer[k] for k in ('start_time', 'in_point', 'out_point', 'transforms')}
        elif prop in layer['transforms']:
            values[prefix + prop] = layer['transforms'][prop]
        elif prop == 'text_style':
            # A document is the native write unit; keep full document styles guarded.
            values[prefix + prop] = {'text': layer['text'], 'style': layer['text_style']}
            if q.recenter_anchor: values[prefix + 'anchor'] = layer['transforms']['anchor']
        else: values[prefix + prop] = layer['text']
    return {key: fingerprint(value) for key, value in values.items()}


def check_disjoint(operations):
    used = set()
    for op in operations:
        for layer_id, prop in targets(op):
            key = (op.request.composition_id, layer_id, prop)
            siblings = {v[2] for v in used if v[:2] == key[:2]}
            if key in used or ('timing' in siblings) or (prop == 'timing' and siblings):
                raise ValueError('Ambiguous overlapping patch properties; split into separate reviewed revisions')
            if (prop == 'text' and 'text_style' in siblings) or (prop == 'text_style' and 'text' in siblings):
                raise ValueError('Content and style of one document require separate revision plans')
            used.add(key)
        if op.action == 'text_style_set' and op.request.recenter_anchor:
            key = (op.request.composition_id, op.request.layer_id, 'anchor')
            if key in used: raise ValueError('Overlapping anchor changes')
            used.add(key)


def prepare_patch(settings, op, state):
    if state['project_dirty']: raise ValueError('Capture manual state explicitly before patching')
    if any(l['animation_summary']['expressions'] for c in state['compositions'] for l in c['layers']):
        raise ValueError('Stored expressions are protected')
    if op.action in ANIMATIONS: return prepare_animation(op.action, op.request, state)
    if op.action == 'text_style_set': return prepare_design(settings, op.action, op.request, state)
    if op.action == 'layer_update': return prepare_scene(op.action, op.request, state)
    layer = find_layer(find_comp(state, op.request.composition_id), op.request.layer_id)
    editable(layer)
    if op.action == 'layer_transform':
        for _, name in targets(op):
            track = layer['transforms'][name]
            if not track['available'] or track['keys'] or track['expression_enabled'] or track.get('expression_present') or track['separated']:
                raise ValueError('Static transform patch cannot replace keys, separation or expressions')
        return {}
    if layer['text'] is None or layer['text_document_animated'] or layer['text_animators']:
        raise ValueError('Content patch requires a static text document without text animators')
    style = layer['text_style']
    if not layer['text'] or style['styles_truncated'] or style['font_missing']:
        raise ValueError('Complete nonempty text with installed font required')
    runs = expanded_styles(style, len(layer['text']))
    if any(r != runs[0] for r in runs): raise ValueError('Content patch refuses mixed character styles')
    if '\n' in layer['text'] or '\r' in layer['text'] or '\n' in op.request.text or '\r' in op.request.text:
        raise ValueError('Content patch currently supports one paragraph only')
    return {}


def verify_patch(op, before, after, context):
    if op.action in ANIMATIONS: return verify_animation(op.action, op.request, before, after, context)
    if op.action == 'text_style_set': return verify_design(op.action, op.request, before, after, context)
    if op.action == 'layer_update': return verify_scene(op.action, op.request, before, after, context)
    normalized = copy.deepcopy(after)
    q = op.request
    old = find_layer(find_comp(before, q.composition_id), q.layer_id)
    new = find_layer(find_comp(normalized, q.composition_id), q.layer_id)
    if op.action == 'content_set':
        equivalent(new['text'], q.text, 'replacement text')
        equivalent(expanded_styles(new['text_style'], len(q.text)), [expanded_styles(old['text_style'], len(old['text']))[0]] * len(q.text), 'preserved character style')
        for key in old['text_style']:
            if key not in ('style_runs', 'box_overflow'):
                equivalent(new['text_style'][key], old['text_style'][key], 'preserved text ' + key)
        if new['text_style']['box_overflow']: raise ValueError('Replacement text overflows box')
        for key in ('text', 'text_style', 'bounds', 'visual_bounds', 'layout_bounds'): new[key] = copy.deepcopy(old[key])
    else:
        for _, name in targets(op):
            track = new['transforms'][name]
            expected = getattr(q.values, name)
            value = track['value']
            equivalent(value[:2] if isinstance(expected, tuple) else value, list(expected) if isinstance(expected, tuple) else expected, name)
            restored = copy.deepcopy(track); restored['value'] = copy.deepcopy(old['transforms'][name]['value']); restored['samples'] = copy.deepcopy(old['transforms'][name]['samples'])
            equivalent(restored, old['transforms'][name], 'static track flags')
            new['transforms'][name] = copy.deepcopy(old['transforms'][name])
            if name in ('anchor', 'position'): new[name] = copy.deepcopy(old[name])
    equivalent(semantic_state(normalized['compositions']), semantic_state(before['compositions']), 'preserved project')
    equivalent(normalized['footage'], before['footage'], 'preserved footage')


def state_changes(left, right, path=''):
    """Complete inspected metadata diff; derived samples are deliberately omitted."""
    if fingerprint(left) == fingerprint(right): return []
    if isinstance(left, dict) and isinstance(right, dict):
        return [change for key in sorted(set(left) | set(right)) if key not in ('samples', 'world_basis')
                for change in state_changes(left.get(key), right.get(key), path + '/' + key)]
    if isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
        return [change for i, (a, b) in enumerate(zip(left, right)) for change in state_changes(a, b, path + '/' + str(i))]
    return [{'path': path, 'before': left, 'after': right}]


def retained_metadata(state):
    """Compare stored/live states independently of optional inspection probes."""
    def strip(value):
        if isinstance(value, dict): return {k: strip(v) for k, v in value.items() if k not in ('samples', 'world_basis')}
        if isinstance(value, list): return [strip(v) for v in value]
        return value
    result = strip(semantic_state({'compositions': state['compositions'], 'footage': state['footage']}))
    for comp in result['compositions']:
        for layer in comp['layers']:
            # Legacy result aliases used a caller-selected sample time; tracks
            # always expose authoritative valueAtTime(0) plus all native keys.
            for name in ('position', 'anchor'):
                if name in layer and name in layer['transforms']:
                    layer[name] = copy.deepcopy(layer['transforms'][name]['value'])
    return result


class RevisionService:
    def __init__(self, settings):
        self.settings, self.projects = settings, ProjectManager(settings)

    def _directory(self, revision_id):
        return self.settings.contained_path('revisions/' + valid_id(revision_id))

    def _load_plan(self, revision_id, expected_hash):
        directory = self._directory(revision_id)
        if digest(directory / 'plan.json') != expected_hash: raise ValueError('Revision plan integrity conflict')
        plan = json.loads((directory / 'plan.json').read_text(encoding='utf-8'))
        request = RevisionPlanRequest.model_validate(plan['request'])
        if plan['revision_id'] != revision_id: raise ValueError('Revision identity conflict')
        return directory, plan, request

    def _version(self, project_id, version):
        valid_id(project_id)
        suffix = '' if version == 'initial' else '/versions/' + valid_id(version)
        directory = self.settings.contained_path(f'projects/{project_id}' + suffix)
        record_path = self.settings.contained_path(str((directory / ('project.json' if version == 'initial' else 'version.json')).relative_to(self.settings.workspace)))
        record = json.loads(record_path.read_text(encoding='utf-8'))
        source = self.settings.contained_path(str((directory / 'project.aep').relative_to(self.settings.workspace)))
        if record.get('status') != 'succeeded' or digest(source) != record.get('sha256'):
            raise ValueError('Selected version is unverified or changed on disk')
        state = record['result']['data']
        return record, source, state

    def _result(self, kind, project_id, data, status='succeeded', error=None):
        from astra_video_studio.jobs import Job
        job = Job(self.settings, kind)
        result = OperationResult(operation_id=job.id, status=status, project_id=project_id, data=data, error=error)
        job.record(status, result=result.model_dump())
        return result

    def plan(self, request):
        manifest, source = self.projects.load(request.project_id)
        _, _, saved = self._version(request.project_id, manifest.get('current_version', 'initial'))
        if digest(source) != request.base_sha256: raise ValueError('Base version hash conflict')
        inspected = self.projects.inspect(request.project_id)
        if inspected.status != 'succeeded': return inspected
        if inspected.data['project_dirty']: raise ValueError('Use project_save to capture manual edits before planning')
        equivalent(retained_metadata(inspected.data), retained_metadata(saved), 'base metadata')
        check_disjoint(request.operations)
        contexts = [prepare_patch(self.settings, op, inspected.data) for op in request.operations]
        budget = check_evidence_budget(self.settings, inspected.data, contexts)
        operations = []
        for op in request.operations:
            guards = footprints(op, inspected.data)
            operations.append({'action': op.action, 'request': op.request.model_dump(mode='json'), 'expected_properties': guards,
                               'changes': [f'{op.request.composition_id}/{layer}/{prop}' for layer, prop in targets(op)]})
        revision_id = uuid4().hex
        directory = self._directory(revision_id); directory.mkdir(parents=True, exist_ok=False)
        plan = {'revision_id': revision_id, 'created_at': timestamp(), 'request': request.model_dump(mode='json'),
                'base_version': manifest.get('current_version', 'initial'), 'base_path': str(source), 'operations': operations, 'native_evidence_budget': budget,
                'preserves': ['all non-target inspected properties', 'manual character style for content-only edits', 'existing version files'],
                'policy': 'single native edit; promote only after all operations and disk round-trip verify; no automatic retry'}
        write_json(directory / 'plan.json', plan)
        return self._result('revision_plan', request.project_id, plan | {'plan_sha256': digest(directory / 'plan.json')})

    def apply(self, request):
        directory, plan, original = self._load_plan(request.revision_id, request.plan_sha256)
        # Reserve one immutable attempt. A timeout/failed attempt cannot be replayed.
        if (directory / 'attempt.json').exists(): raise ValueError('Revision already attempted; inspect history and create a new plan')
        manifest, source = self.projects.load(original.project_id)
        source_hash = digest(source)
        if source_hash != request.expected_current_sha256: raise ValueError('Current version hash conflict')
        self._version(original.project_id, manifest.get('current_version', 'initial'))
        inspected = self.projects.inspect(original.project_id)
        if inspected.status != 'succeeded': return inspected
        conflicts = []
        for op, stored in zip(original.operations, plan['operations'], strict=True):
            try: actual = footprints(op, inspected.data)
            except ValueError as exc:
                conflicts.append({'path': op.request.composition_id, 'reason': str(exc)}); continue
            for key, expected in stored['expected_properties'].items():
                if actual.get(key) != expected: conflicts.append({'path': key, 'expected_sha256': expected, 'actual_sha256': actual.get(key)})
        if conflicts:
            return self._result('revision_conflict', original.project_id, {'revision_id': request.revision_id, 'conflicts': conflicts}, 'blocked', 'Property conflict; no project mutation')
        dirty = inspected.data['project_dirty']
        if dirty and not request.capture_manual: raise ValueError('Manual edits require capture_manual=true or explicit project_save')
        clean = copy.deepcopy(inspected.data); clean['project_dirty'] = False
        contexts = [prepare_patch(self.settings, op, clean) for op in original.operations]
        check_evidence_budget(self.settings, clean, contexts)
        # No bridge writes have happened before conflict checks and complete preflight.
        capture = None
        if dirty:
            capture = ExistingProjectService(self.settings).save(original.project_id)
            if capture.status != 'succeeded': return capture
            manifest, source = self.projects.load(original.project_id)
            source_hash = digest(source)
            inspected = self.projects.inspect(original.project_id)
            if inspected.status != 'succeeded': return inspected
            equivalent(semantic_state(inspected.data['compositions']), semantic_state(clean['compositions']), 'captured manual state')
        identifier = uuid4().hex
        version_dir = self.settings.contained_path(f'projects/{original.project_id}/versions/{identifier}')
        version_dir.mkdir(parents=True, exist_ok=False)
        output, snapshot = version_dir / 'project.aep', version_dir / 'source-snapshot.aep'
        shutil.copyfile(source, snapshot)
        if digest(snapshot) != source_hash or digest(source) != source_hash: raise ValueError('Source snapshot conflict')
        version = {'version_id': identifier, 'status': 'prepared', 'kind': 'revision_patch', 'revision_id': request.revision_id,
                   'source': str(source), 'source_sha256': source_hash, 'snapshot': str(snapshot), 'parent_version': manifest.get('current_version', 'initial'), 'id_map': manifest.get('id_map')}
        write_json(version_dir / 'version.json', version)
        # Exclusive create also prevents simultaneous clients consuming one plan.
        with (directory / 'attempt.json').open('x', encoding='utf-8') as stream:
            json.dump({'request': request.model_dump(), 'version_id': identifier, 'capture_operation_id': capture.operation_id if capture else None, 'started_at': timestamp()}, stream)
        result = self.projects.runner.run('revision_edit', {'project_path': source.as_posix(), 'version_path': output.as_posix(), 'id_map': manifest.get('id_map'),
            'expected_state': inspected.data, 'revision_operations': [op.model_dump(mode='json') | {'context': ctx} for op, ctx in zip(original.operations, contexts, strict=True)]})
        result.project_id, result.project_path = original.project_id, str(output)
        if result.status == 'succeeded':
            try:
                if digest(source) != source_hash or digest(snapshot) != source_hash or not output.is_file(): raise ValueError('Source/output integrity conflict')
                steps = result.data.pop('revision_steps')
                if len(steps) != len(original.operations): raise ValueError('Missing revision verification steps')
                before = inspected.data
                for op, ctx, after in zip(original.operations, contexts, steps, strict=True):
                    verify_patch(op, before, after, ctx); before = after
                equivalent(semantic_state(result.data['compositions']), semantic_state(before['compositions']), 'saved round-trip')
                equivalent(result.data['footage'], before['footage'])
                if result.data['project_dirty'] or digest(output) == source_hash: raise ValueError('Revision output not clean/changed')
                version['sha256'] = digest(output)
                result.data.update(version_id=identifier, revision_id=request.revision_id, captured_manual_version=capture.data['version_id'] if capture else None)
                result.artifacts.extend([str(output), str(snapshot), str(directory / 'plan.json')])
            except (ValueError, KeyError, TypeError, OSError) as error:
                result.status, result.error = 'failed', 'Revision verification failed: ' + str(error)
        version.update(status=result.status, operation_id=result.operation_id, result=result.model_dump())
        write_json(version_dir / 'version.json', version)
        write_json(directory / 'result.json', {'plan_sha256': request.plan_sha256, 'result': result.model_dump(), 'completed_at': timestamp()})
        if result.status == 'succeeded':
            manifest['current_version'] = identifier
            write_json(self.settings.contained_path(f'projects/{original.project_id}/project.json'), manifest)
        self.projects._finalize_job(result)
        return result

    def compare(self, request):
        left, _, a = self._version(request.project_id, request.left)
        right, _, b = self._version(request.project_id, request.right)
        changes = state_changes(retained_metadata(a), retained_metadata(b))
        return self._result('version_compare', request.project_id, {'left': request.left, 'right': request.right, 'left_sha256': left['sha256'], 'right_sha256': right['sha256'], 'changes': changes, 'scope': 'inspected metadata, not binary or visual equivalence'})

    def restore(self, request):
        manifest, current = self.projects.load(request.project_id)
        self._version(request.project_id, manifest.get('current_version', 'initial'))
        chosen, source, expected = self._version(request.project_id, request.version_id)
        # Older version records did not persist a sidecar. Rebuild it from their
        # VERIFIED UUID/native-ID pairs, never from the live layer order/comments.
        restore_map = build_id_map(expected, preserve_comments=True)
        current_hash, selected_hash = digest(current), digest(source)
        if current_hash != request.expected_current_sha256: raise ValueError('Current version hash conflict')
        inspected = self.projects.inspect(request.project_id)
        if inspected.status != 'succeeded': return inspected
        if inspected.data['project_dirty']: raise ValueError('Capture manual edits with project_save before restoring')
        identifier = uuid4().hex
        directory = self.settings.contained_path(f'projects/{request.project_id}/versions/{identifier}')
        directory.mkdir(parents=True, exist_ok=False)
        output, snapshot = directory / 'project.aep', directory / 'source-snapshot.aep'
        shutil.copyfile(current, snapshot); shutil.copyfile(source, output)
        if digest(snapshot) != current_hash or digest(output) != selected_hash: raise ValueError('Restore copy integrity conflict')
        version = {'version_id': identifier, 'kind': 'version_restore', 'status': 'prepared', 'restored_from': request.version_id,
                   'parent_version': manifest.get('current_version', 'initial'), 'reason': request.reason, 'source': str(current), 'source_sha256': current_hash, 'snapshot': str(snapshot), 'id_map': restore_map}
        write_json(directory / 'version.json', version)
        result = self.projects.runner.run('version_restore', {'project_path': current.as_posix(), 'version_path': output.as_posix(), 'id_map': manifest.get('id_map'), 'restore_id_map': restore_map, 'expected_state': inspected.data})
        result.project_id, result.project_path = request.project_id, str(output)
        if result.status == 'succeeded':
            try:
                if digest(current) != current_hash or digest(snapshot) != current_hash or digest(source) != selected_hash or digest(output) != selected_hash:
                    raise ValueError('Restore modified retained file')
                equivalent(retained_metadata(result.data), retained_metadata(expected), 'restored metadata')
                if result.data['project_dirty']: raise ValueError('Restored project is dirty')
                version['sha256'] = selected_hash
                result.data.update(version_id=identifier, restored_from=request.version_id)
                result.artifacts.extend([str(output), str(snapshot)])
            except (ValueError, KeyError, TypeError, OSError) as error:
                result.status, result.error = 'failed', 'Restore verification failed: ' + str(error)
        version.update(status=result.status, operation_id=result.operation_id, result=result.model_dump())
        write_json(directory / 'version.json', version)
        if result.status == 'succeeded':
            manifest.update(current_version=identifier, id_map=restore_map)
            write_json(self.settings.contained_path(f'projects/{request.project_id}/project.json'), manifest)
        self.projects._finalize_job(result)
        return result

    def director_plan(self, request):
        """Tiny declared PT vocabulary; host can instead submit typed operations."""
        clauses = [c.strip() for c in request.instruction.split(';')]
        operations = []
        manifest, source = self.projects.load(request.project_id)
        if digest(source) != request.base_sha256: raise ValueError('Director base hash conflict')
        inspected = self.projects.inspect(request.project_id)
        if inspected.status != 'succeeded': return inspected
        layer = find_layer(find_comp(inspected.data, request.composition_id), request.layer_id)
        target = {k: getattr(request, k) for k in ('project_id', 'composition_id', 'layer_id')}
        for clause in clauses:
            title = re.fullmatch(r'trocar título para "([^"\r\n]+)"', clause, flags=re.IGNORECASE)
            delay = re.fullmatch(r'atrasar entrada (\d+) frames entre (\d+) e (\d+)', clause, flags=re.IGNORECASE)
            if title:
                operations.append({'action': 'content_set', 'request': target | {'text': title[1]}})
            elif delay:
                shift, start, end = map(int, delay.groups())
                if not shift: raise ValueError('Delay must be positive')
                # Exact named entry window; never infer other tracks or move exits.
                operations.append({'action': 'keyframes_edit', 'request': target | {'base_sha256': request.base_sha256,
                    'property': 'position', 'expected_track_sha256': fingerprint(layer['transforms']['position']),
                    'start_frame': start, 'end_frame': end, 'boundary_policy': 'allow_change', 'mode': 'move', 'shift_frames': shift}})
            else: raise ValueError('Unsupported clause. Vocabulary: trocar título para "TEXT"; atrasar entrada N frames entre A e B. No partial interpretation.')
        return self.plan(RevisionPlanRequest(project_id=request.project_id, base_sha256=request.base_sha256, instruction=request.instruction, operations=operations))


REVISION_REQUESTS = {'revision_plan': RevisionPlanRequest, 'revision_apply': RevisionApplyRequest,
    'version_compare': VersionCompareRequest, 'version_restore': VersionRestoreRequest, 'director_revision_plan': DirectorPatchRequest}
