"""Bounded host presentation. Never compact service verification or native journals."""
import copy
from functools import wraps
import hashlib
import inspect
import json
import os
from pathlib import Path
from uuid import uuid4
from typing import Literal, Annotated

from pydantic import BaseModel, ConfigDict, Field
from mcp.types import CallToolResult, TextContent

from astra_video_studio.config import Settings
from astra_video_studio.director import SceneExecution, ScenePlan
from astra_video_studio.existing_projects import digest
from astra_video_studio.project_manager import ProjectManager
from astra_video_studio.schemas import OperationResult, JobStatus
from astra_video_studio.motion_engine.schemas import StrictModel
from astra_video_studio.scene_editing import ID
from astra_video_studio.animation import fingerprint
from astra_video_studio.host_runtime import presentation_metadata

COMPACT_BYTES = 8192
RECEIPT_BYTES = 3072
PAGE_BYTES = 16384
SHA = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
Mode = Literal['compact', 'receipt', 'full']


class EvidenceReference(StrictModel):
    sha256: SHA
    path: str
    bytes: int
    schema_version: Literal[1] = 1


class OperationResponse(OperationResult):
    response_mode: Mode = 'compact'
    evidence: EvidenceReference | None = None


class JobResponse(JobStatus):
    result: OperationResult | None = None
    response_mode: Mode = 'compact'
    evidence: EvidenceReference | None = None
    event_count: int = 0


class ExecutionResponse(SceneExecution):
    response_mode: Mode = 'compact'
    evidence: EvidenceReference | None = None


class PlanResponse(BaseModel):
    model_config = ConfigDict(extra='allow')
    plan_id: str
    composition_id: str
    response_mode: Mode = 'compact'
    evidence: EvidenceReference | None = None


def encoded(value):
    return json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def wire_result(value, metadata=None):
    payload = value.model_dump(mode='json')
    # Text-only hosts retain the same useful compact JSON. Account for BOTH
    # protocol representations rather than hiding a second large text response.
    return CallToolResult(content=[TextContent(type='text', text=encoded(payload).decode('utf-8'))], structuredContent=payload, _meta=metadata)


def wire_size(value, metadata=None):
    return len(encoded(wire_result(value, metadata).model_dump(mode='json', exclude_none=True)))


def store_evidence(settings, kind, result, provenance=None):
    record = {'schema_version': 1, 'kind': kind, 'result': result, 'provenance': provenance or {}}
    # Match write_json's actual UTF-8 bytes; sort dictionaries for stable reuse.
    record = json.loads(json.dumps(record, sort_keys=True, allow_nan=False))
    raw = json.dumps(record, indent=2, ensure_ascii=True).replace('\n', os.linesep).encode('utf-8')
    sha = hashlib.sha256(raw).hexdigest()
    path = settings.contained_path('responses/' + sha + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if digest(path) != sha: raise ValueError('Evidence integrity conflict; existing evidence was not overwritten')
    else:
        # Publish a completed file without replacing an existing evidence inode.
        # A hard link is atomic/exclusive on the same workspace filesystem and
        # avoids Windows rename/read races between simultaneous clients.
        temporary = path.with_name(sha + '.' + uuid4().hex + '.tmp')
        try:
            with temporary.open('xb') as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            try: os.link(temporary, path)
            except FileExistsError:
                if digest(path) != sha: raise ValueError('Evidence integrity conflict')
        finally: temporary.unlink(missing_ok=True)
    if digest(path) != sha: raise ValueError('Evidence publication integrity failure')
    return EvidenceReference(sha256=sha, path=str(path), bytes=path.stat().st_size)


def counts(data):
    comps = data.get('compositions', [])
    layers = [layer for comp in comps for layer in comp.get('layers', [])]
    return {'compositions': len(comps), 'layers': len(layers),
            'keys': sum(len(track.get('keys', [])) for layer in layers for track in layer.get('transforms', {}).values()),
            'samples': sum(len(track.get('samples', [])) for layer in layers for track in layer.get('transforms', {}).values())}


def summarize(data):
    """Constant-size projection; no full-scene lists or unbounded nested data."""
    result = {'counts': counts(data), 'detail_available': True}
    # Keep operational IDs, paths, hashes and scalar verification information.
    for key, value in data.items():
        if len(result) >= 32: break
        if isinstance(value, (bool, int, float)) or value is None:
            result[key] = value
        elif isinstance(value, str) and (key.endswith(('_id', '_sha256', '_path')) or key in ('version_id', 'ae_version', 'status', 'state', 'scope', 'next_action')):
            if len(value) <= 1024: result[key] = value
    comps = data.get('compositions', [])
    if comps:
        result['first_composition_id'] = comps[0].get('composition_id', '').split(':')[-1]
        layers = comps[0].get('layers', [])
        if layers: result['first_layer_id'] = layers[0].get('layer_id', '').split(':')[-1]
    for key in ('conflicts', 'changes', 'operations', 'warnings'):
        if isinstance(data.get(key), list):
            result[key + '_count'] = len(data[key])
            if key == 'operations':
                result[key] = [{'action': x.get('action'), 'changes': x.get('changes', [])[:4]} for x in data[key][:4]]
            elif key == 'conflicts':
                result[key] = [{k: v[:256] if isinstance(v, str) else v for k, v in x.items() if k in ('path', 'reason', 'expected_sha256', 'actual_sha256')} for x in data[key][:4]]
            elif key == 'changes': result['changed_paths'] = [x.get('path', '')[:256] for x in data[key][:8]]
            else: result[key] = [str(x)[:256] for x in data[key][:3]]
    for key in ('audio_clips', 'audio_markers', 'sync_events', 'render_presets'):
        if isinstance(data.get(key), list): result[key+'_count'] = len(data[key])
    if isinstance(data.get('created_layers'),list):
        result['created_layers']=[{k:str(row.get(k,''))[:40] for k in ('role','layer_id')} for row in data['created_layers'][:20]]
    animation = data.get('animation_state')
    if animation:
        result['animation_state'] = {k: animation[k] for k in ('base_sha256', 'composition_sha256') if k in animation}
        result['animation_state']['track_count'] = len(animation.get('tracks', []))
        result['animation_state']['tracks'] = [{k: t[k] for k in ('layer_id', 'property', 'track_sha256')} for t in animation.get('tracks', [])[:5]]
    for key in ('verification', 'checklist'):
        if isinstance(data.get(key), dict):
            result[key] = {k: v for k, v in list(data[key].items())[:16] if isinstance(v, (bool, int, float)) or isinstance(v, str) and len(v) < 128}
    if isinstance(data.get('preview'), dict): result['preview'] = summarize(data['preview'])
    if isinstance(data.get('render'), dict): result['render'] = summarize(data['render'])
    return result


def operation_projection(raw):
    return {k: raw.get(k) for k in ('operation_id', 'status', 'project_id', 'project_path')} | {
        'artifacts': raw.get('artifacts', [])[:3], 'data': summarize(raw.get('data', {})),
        'error': raw['error'][:1024] if raw.get('error') else None}


def present(value, mode, settings, metadata=None):
    if mode not in ('compact', 'receipt', 'full'): raise ValueError('response_mode must be compact, receipt or full')
    raw = value.model_dump(mode='json')
    try:
        evidence = store_evidence(settings, type(value).__name__, raw)
    except (OSError, ValueError) as error:
        identifier = raw.get('operation_id') or raw.get('execution_id') or raw.get('plan_id')
        raise ValueError(f'Host presentation failed after {type(value).__name__} {identifier} returned {raw.get("status", "planned")}. Inspect its complete existing service journal/plan before any retry. Cause: {error}') from error
    if isinstance(value, OperationResult):
        model, payload = OperationResponse, raw if mode == 'full' else operation_projection(raw)
    elif isinstance(value, JobStatus):
        model = JobResponse
        payload = copy.deepcopy(raw) if mode == 'full' else {
            'operation_id': value.operation_id, 'action': value.action, 'status': value.status,
            'events': raw['events'][-3:], 'result': operation_projection(raw['result']) if raw.get('result') else None,
            'cancel_requested': raw.get('cancel_requested', False)}
        payload['event_count'] = len(raw['events'])
    elif isinstance(value, SceneExecution):
        model, payload = ExecutionResponse, copy.deepcopy(raw)
        if mode == 'compact':
            payload['data'] = summarize(raw.get('data', {}))
            payload['error'] = raw['error'][:1024] if raw.get('error') else None
    elif isinstance(value, ScenePlan):
        model = PlanResponse
        payload = raw if mode == 'full' else {k: raw[k] for k in ('plan_id', 'parent_plan_id', 'composition_id', 'width', 'height', 'fps', 'duration')}
        if mode == 'compact': payload.update(element_count=len(value.elements), action_count=len(value.actions), review_detail='Read plan_elements/plan_actions via operation_query or request response_mode=full before reviewing complete intent.')
    else: return value
    if mode == 'receipt':
        # Opt-in orchestration receipt; full verification and legacy full output
        # stay unchanged. Details remain available through the evidence hash.
        if isinstance(value,OperationResult):
            data=raw.get('data',{})
            payload={k:raw.get(k) for k in ('operation_id','status','project_id')}
            payload.update(artifacts=[],error=raw['error'][:384] if raw.get('error') else None,
                data={k:v for k,v in data.items() if k in ('version_id','layer_id','asset_id','created_layer_id','created_composition_id','created_count','plan_id','plan_sha256','revision_id','audio_state_sha256','delivery_id','state','status') and (v is None or isinstance(v,(str,bool,int,float)))})
        elif isinstance(value,JobStatus):
            payload={'operation_id':value.operation_id,'action':value.action,'status':value.status,'events':[],
                'event_count':len(raw['events']),'result':None,'cancel_requested':raw.get('cancel_requested',False)}
        elif isinstance(value,SceneExecution):
            payload={k:raw.get(k) for k in ('execution_id','plan_id','status','project_id','preview_job_id')}
            payload.update(data={},error=raw['error'][:384] if raw.get('error') else None)
        elif isinstance(value,ScenePlan):payload={k:raw[k] for k in ('plan_id','composition_id')}
    payload.update(response_mode=mode, evidence=evidence.model_dump())
    result = model.model_validate(payload)
    budget=RECEIPT_BYTES if mode=='receipt' else COMPACT_BYTES
    if mode in ('compact','receipt') and wire_size(result, metadata) > budget:
        # Persisted full evidence retains every detail. Hard cap even diagnostics.
        if mode=='receipt' and payload.get('error'):payload['error']=payload['error'][:64]
        if 'data' in payload: payload['data'] = {'counts': counts(raw.get('data', {})), 'detail_available': True, 'summary_omitted_for_byte_budget': True}
        if isinstance(value, JobStatus):
            payload['events'] = []
            if payload.get('result'): payload['result'] = {'operation_id': raw['result']['operation_id'], 'status': raw['result']['status'], 'data': {'detail_available': True}}
        payload['artifacts'] = [] if 'artifacts' in payload else payload.get('artifacts', [])
        result = model.model_validate(payload)
        if wire_size(result, metadata) > budget: raise ValueError('Bounded envelope exceeds byte budget; evidence is retained at ' + evidence.path)
    return result


RESPONSE_TYPES = {OperationResult: OperationResponse, JobStatus: JobResponse, SceneExecution: ExecutionResponse, ScenePlan: PlanResponse}


def response_policy(fn):
    """Expose a typed keyword on the MCP boundary; service signatures stay intact."""
    signature = inspect.signature(fn)
    if signature.return_annotation is EvidencePage:
        @wraps(fn)
        def query_wrapped(*args, **kwargs): return wire_result(fn(*args, **kwargs))
        return query_wrapped
    response_type = RESPONSE_TYPES.get(signature.return_annotation)
    if response_type is None: return fn
    @wraps(fn)
    def wrapped(*args, response_mode='compact', **kwargs):
        if response_mode not in ('compact', 'receipt', 'full'): raise ValueError('Invalid response mode')
        original = fn(*args, **kwargs)
        metadata = presentation_metadata(fn.__name__, response_mode)
        value = present(original, response_mode, Settings.from_env(), metadata)
        if response_mode in ('compact','receipt'): return wire_result(value, metadata)
        # Strict legacy clients receive the exact original structured payload.
        # Reference metadata belongs to the MCP envelope, not their old schema.
        raw = original.model_dump(mode='json')
        return CallToolResult(content=[TextContent(type='text', text=json.dumps(raw, indent=2, ensure_ascii=True))],
                              structuredContent=raw, _meta=metadata | {'astra_evidence': value.evidence.model_dump()})
    wrapped.__signature__ = signature.replace(parameters=[*signature.parameters.values(), inspect.Parameter('response_mode', inspect.Parameter.KEYWORD_ONLY, default='compact', annotation=Mode)], return_annotation=response_type)
    wrapped.__annotations__ = fn.__annotations__ | {'response_mode': Mode, 'return': response_type}
    wrapped.__doc__ = (fn.__doc__ or '') + '\n\nCompact by default; receipt is an opt-in <=3KiB orchestration response; full explicitly returns legacy full output. Complete immutable evidence is referenced by hash; use operation_query for paged details.'
    return wrapped


Section = Literal['compositions', 'layers', 'transforms', 'keys', 'samples', 'effects', 'masks', 'text_style', 'style_runs', 'operations', 'changes', 'conflicts', 'fonts', 'events', 'plan_elements', 'plan_actions', 'fields', 'audio_clips', 'audio_markers', 'sync_events', 'render_presets', 'scenes', 'review_samples', 'issues', 'references', 'jobs', 'media', 'candidates', 'protected', 'diagnostics', 'created_layers']


class Selection(StrictModel):
    section: Section = 'layers'
    composition_id: ID | None = None
    layer_ids: list[ID] = Field(default_factory=list, max_length=50)
    properties: list[Literal['position', 'anchor', 'scale', 'rotation', 'opacity']] = Field(default_factory=list, max_length=5)
    offset: int = Field(default=0, ge=0, le=1_000_000)
    limit: int = Field(default=20, ge=1, le=50)


class EvidenceQuery(Selection):
    evidence_sha256: SHA


class ProjectQuery(Selection):
    project_id: ID
    refresh: bool = False
    expected_source_sha256: SHA | None = None


class EvidencePage(StrictModel):
    status: str
    evidence: EvidenceReference
    provenance: dict
    section: Section
    offset: int
    total: int
    next_offset: int | None
    items: list[dict]
    omitted_oversized_items: int = 0
    error: str | None = None


def rows_for(raw, selection):
    section = selection.section
    # Job records retain the OperationResult under result; operation snapshots
    # and plans are already direct records.
    if 'events' in raw and 'action' in raw:
        if section == 'events':
            yield from raw['events']; return
        raw = raw.get('result') or raw
    data = raw.get('data', raw)
    if section in ('scenes', 'review_samples', 'issues', 'references', 'jobs', 'media', 'candidates', 'protected', 'diagnostics', 'created_layers'):
        yield from data.get('samples' if section == 'review_samples' else section, []); return
    if section in ('plan_elements', 'plan_actions'):
        yield from raw.get('elements' if section == 'plan_elements' else 'actions', []); return
    if section == 'fields':
        for key, value in data.items():
            row = {'field': key, 'type': type(value).__name__}
            if isinstance(value, (list, dict)): row['count'] = len(value)
            elif not isinstance(value, str) or len(value) <= 1024: row['value'] = value
            else: row['value_omitted'] = True
            yield row
        return
    if section in ('operations', 'changes', 'conflicts', 'fonts', 'audio_clips', 'audio_markers', 'sync_events', 'render_presets'):
        yield from data.get(section, []); return
    for comp in data.get('compositions', []):
        cid = comp.get('composition_id', '').split(':')[-1]
        if selection.composition_id and cid != selection.composition_id: continue
        if section == 'compositions':
            yield {k: comp.get(k) for k in ('composition_id', 'name', 'width', 'height', 'fps', 'duration')} | {'layer_count': len(comp.get('layers', []))}; continue
        for layer in comp.get('layers', []):
            lid = layer.get('layer_id', '').split(':')[-1]
            if selection.layer_ids and lid not in selection.layer_ids: continue
            target = {'composition_id': cid, 'layer_id': lid}
            if section == 'layers':
                yield target | {k: layer.get(k) for k in ('name', 'locked', 'enabled', 'editable_2d', 'parent_ae_id', 'in_point', 'out_point', 'animation_summary')} | {'text': (layer.get('text') or '')[:200], 'text_truncated': len(layer.get('text') or '') > 200}
            elif section in ('transforms', 'keys', 'samples'):
                for name, track in layer.get('transforms', {}).items():
                    if selection.properties and name not in selection.properties: continue
                    head = target | {'property': name}
                    if section == 'transforms':
                        yield head | {k: track.get(k) for k in ('available', 'value', 'separated', 'expression_enabled', 'expression_present', 'spatial')} | {'key_count': len(track.get('keys', [])), 'sample_count': len(track.get('samples', [])), 'track_sha256': fingerprint(track)}
                    else:
                        for index, item in enumerate(track.get(section, [])): yield head | {'index': index, section[:-1]: item}
            elif section == 'text_style':
                yield target | {'style': {k: v for k, v in (layer.get('text_style') or {}).items() if k != 'style_runs'}}
            elif section == 'style_runs':
                for index, item in enumerate((layer.get('text_style') or {}).get('style_runs', [])): yield target | {'index': index, 'style_run': item}
            elif section in ('effects', 'masks'):
                for index, item in enumerate(layer.get(section, [])): yield target | {'index': index, 'value': item}


def page(record, reference, selection):
    items, total, omitted = [], 0, 0
    next_offset = None
    for index, row in enumerate(rows_for(record['result'], selection)):
        total += 1
        if index < selection.offset or next_offset is not None: continue
        if len(items) >= selection.limit:
            next_offset = index; continue
        # Reserve space for reference, provenance and pagination metadata.
        row_budget = (PAGE_BYTES - 3072) // 2
        if len(encoded(row)) > row_budget:
            row = {'index': index, 'omitted': 'item_exceeds_byte_budget', 'bytes': len(encoded(row)), 'detail': 'Complete item remains in referenced evidence file or explicit full response.'}
            omitted += 1
        if len(encoded(items + [row])) > row_budget:
            next_offset = index; continue
        items.append(row)
    result = EvidencePage(status=record['result'].get('status', 'succeeded'), evidence=reference, provenance=record.get('provenance', {}), section=selection.section,
                          offset=selection.offset, total=total, next_offset=next_offset, items=items, omitted_oversized_items=omitted)
    while wire_size(result) > PAGE_BYTES and result.items:
        removed = result.items.pop()
        if removed.get('omitted') == 'item_exceeds_byte_budget': result.omitted_oversized_items -= 1
        result.next_offset = selection.offset + len(result.items)
    if wire_size(result) > PAGE_BYTES: raise ValueError('Evidence page metadata exceeds byte budget')
    return result


def query_evidence(settings, request):
    path = settings.contained_path('responses/' + request.evidence_sha256 + '.json')
    if digest(path) != request.evidence_sha256: raise ValueError('Evidence integrity conflict')
    record = json.loads(path.read_text(encoding='utf-8'))
    if record.get('schema_version') != 1: raise ValueError('Unsupported evidence schema')
    return page(record, EvidenceReference(sha256=request.evidence_sha256, path=str(path), bytes=path.stat().st_size), request)


def query_project(settings, request):
    projects = ProjectManager(settings)
    manifest, source = projects.load(request.project_id)
    source_hash = digest(source)
    if request.expected_source_sha256 and request.expected_source_sha256 != source_hash: raise ValueError('Project source hash conflict')
    if request.refresh:
        result = projects.inspect(request.project_id)
        raw = result.model_dump(mode='json')
        provenance = {'state': 'live_ae_read', 'project_dirty': result.data.get('project_dirty'), 'source_sha256': source_hash, 'operation_id': result.operation_id}
    else:
        version_path = source.parent / ('version.json' if manifest.get('current_version') else 'project.json')
        version_path = settings.contained_path(str(version_path.relative_to(settings.workspace)))
        version = json.loads(version_path.read_text(encoding='utf-8'))
        if version.get('sha256') != source_hash or version.get('status') != 'succeeded': raise ValueError('Saved project version is changed or unverified')
        raw = copy.deepcopy(version['result'])
        raw.update(project_id=request.project_id, project_path=str(source))
        provenance = {'state': 'verified_saved_version', 'version_id': manifest.get('current_version', 'initial'), 'source_sha256': source_hash, 'unsaved_manual_edits_included': False}
    reference = store_evidence(settings, 'ProjectQuery', raw, provenance)
    record = json.loads(Path(reference.path).read_text(encoding='utf-8'))
    result_page = page(record, reference, request)
    if raw.get('error'): result_page.error = str(raw['error'])[:1024]
    return result_page
