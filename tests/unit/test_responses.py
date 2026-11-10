import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import write_json
from astra_video_studio.schemas import OperationResult, JobStatus
from astra_video_studio.responses import (present, response_policy, encoded, wire_size, store_evidence,
    query_evidence, query_project, EvidenceQuery, ProjectQuery, COMPACT_BYTES, PAGE_BYTES)


def scene(count):
    layers = []
    for index in range(count):
        transforms = {}
        for name in ('position', 'anchor', 'scale', 'rotation', 'opacity'):
            transforms[name] = {'available': True, 'value': [index, 10] if name in ('position', 'anchor', 'scale') else 10,
                'keys': [{'time': n / 24, 'value': [n, index], 'in_type': 'linear', 'out_type': 'linear'} for n in range(12)],
                'samples': [{'time': n / 24, 'value': [n, index]} for n in range(5)],
                'expression_enabled': False, 'expression_present': False, 'separated': False}
        layers.append({'layer_id': 'astra:layer:' + f'{index+10:032x}', 'ae_id': index + 10, 'name': f'Layer {index}', 'text': 'Título editável',
                       'transforms': transforms, 'animation_summary': {'key_count': 60, 'expressions': 0},
                       'text_style': {'fill': [1, 0, 0], 'style_runs': [{'start': n, 'end': n+1, 'style': {'fill': [1, 0, 0]}} for n in range(5)]},
                       'effects': [{'name': 'Fill', 'color': [1, 0, 0]}], 'masks': [], 'locked': False})
    return {'project_dirty': False, 'ae_version': '25.5x4', 'compositions': [{'composition_id': 'astra:composition:' + '2'*32, 'ae_id': 2, 'name': 'Fixture only', 'fps': 24, 'duration': 5, 'width': 960, 'height': 540, 'layers': layers}], 'footage': []}


def operation(count=3):
    return OperationResult(operation_id='1'*32, status='succeeded', project_id='3'*32, data=scene(count))


@pytest.mark.parametrize('count', [3, 40, 80])
def test_compact_constant_size_and_full_evidence_retained(tmp_path, count):
    original = operation(count); before = copy.deepcopy(original.model_dump())
    compact = present(original, 'compact', Settings(tmp_path))
    assert wire_size(compact) <= COMPACT_BYTES
    assert 'compositions' not in compact.data
    assert compact.data['counts']['layers'] == count
    assert compact.data['counts']['keys'] == count * 60
    assert original.model_dump() == before
    record = json.loads(Path(compact.evidence.path).read_text())
    assert record['result'] == before
    assert digest(Path(compact.evidence.path)) == compact.evidence.sha256
    assert len(encoded(compact.model_dump(mode='json'))) < 1800


def test_full_explicit_preserves_original_payload(tmp_path):
    original = operation(40)
    full = present(original, 'full', Settings(tmp_path))
    assert full.data == original.data
    assert full.operation_id == original.operation_id


def test_policy_keeps_service_validation_full_and_returns_compact_wire(tmp_path, monkeypatch):
    monkeypatch.setenv('ASTRA_WORKSPACE', str(tmp_path))
    original = operation(80)
    verified = []
    def mutation() -> OperationResult:
        assert len(original.data['compositions'][0]['layers']) == 80
        verified.append(True)
        return original
    fn = response_policy(mutation)
    output = fn()
    assert verified == [True]
    assert output.structuredContent['data']['counts']['layers'] == 80
    assert json.loads(output.content[0].text) == output.structuredContent
    assert len(encoded(output.model_dump(mode='json', exclude_none=True))) <= COMPACT_BYTES
    assert fn(response_mode='full').structuredContent == original.model_dump(mode='json')
    with pytest.raises(ValueError): fn(response_mode='unknown')


def test_failure_retains_full_diagnostic_and_caps_output(tmp_path):
    original = operation(40).model_copy(update={'status': 'failed', 'error': 'long diagnostic ' * 5000})
    output = present(original, 'compact', Settings(tmp_path))
    assert output.status == 'failed' and len(output.error) == 1024
    assert wire_size(output) <= COMPACT_BYTES
    assert json.loads(Path(output.evidence.path).read_text())['result']['error'] == original.error


def test_job_polling_summary_and_immutable_snapshots(tmp_path):
    settings = Settings(tmp_path)
    job = JobStatus(operation_id='1'*32, action='test_fixture', status='succeeded', events=[{'status': 'running', 'timestamp': str(i)} for i in range(500)], result=operation(80), extra_payload=scene(80))
    output = present(job, 'compact', settings)
    assert len(output.events) == 3 and output.event_count == 500
    assert 'extra_payload' not in output.model_dump()
    assert wire_size(output) <= COMPACT_BYTES
    assert 'compositions' not in output.result.data
    old_sha = output.evidence.sha256
    job.events.append({'status': 'later'})
    latest = present(job, 'compact', settings)
    assert latest.evidence.sha256 != old_sha
    old = query_evidence(settings, EvidenceQuery(evidence_sha256=old_sha, section='events', offset=499))
    assert old.total == 500


def test_concurrent_identical_evidence_is_reused(tmp_path):
    settings = Settings(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        refs = list(pool.map(lambda _: store_evidence(settings, 'fixture', {'data': scene(3)}), range(12)))
    assert len({r.sha256 for r in refs}) == 1
    assert len(list((tmp_path/'responses').glob('*.json'))) == 1


def test_tampered_evidence_is_never_overwritten_or_read(tmp_path):
    settings = Settings(tmp_path); output = present(operation(), 'compact', settings)
    Path(output.evidence.path).write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='integrity'): present(operation(), 'compact', settings)
    with pytest.raises(ValueError, match='integrity'): query_evidence(settings, EvidenceQuery(evidence_sha256=output.evidence.sha256))
    assert Path(output.evidence.path).read_text() == '{}'


@pytest.mark.parametrize('kwargs', [{'evidence_sha256': '../escape'}, {'evidence_sha256': 'a'*64, 'section': 'execute_jsx'}, {'evidence_sha256': 'a'*64, 'limit': 51}, {'evidence_sha256': 'a'*64, 'offset': -1}, {'evidence_sha256': 'a'*64, 'path': 'outside'}])
def test_closed_query_contract(kwargs):
    with pytest.raises(ValidationError): EvidenceQuery(**kwargs)


def test_pagination_no_loss_or_duplication(tmp_path):
    settings = Settings(tmp_path); ref = present(operation(80), 'compact', settings).evidence
    ids, offset = [], 0
    while offset is not None:
        result = query_evidence(settings, EvidenceQuery(evidence_sha256=ref.sha256, limit=50, offset=offset))
        assert wire_size(result) <= PAGE_BYTES
        assert result.total == 80
        ids.extend(row['layer_id'] for row in result.items)
        assert result.next_offset is None or result.next_offset > offset
        offset = result.next_offset
    assert len(ids) == len(set(ids)) == 80


def test_property_filters_and_explicit_samples_keys(tmp_path):
    settings = Settings(tmp_path); raw = operation(40)
    ref = present(raw, 'compact', settings).evidence
    filters = {'evidence_sha256': ref.sha256, 'composition_id': '2'*32, 'layer_ids': [f'{10:032x}'], 'properties': ['position']}
    track = query_evidence(settings, EvidenceQuery(**filters, section='transforms'))
    assert track.total == 1 and 'keys' not in track.items[0] and 'samples' not in track.items[0]
    assert track.items[0]['key_count'] == 12
    assert query_evidence(settings, EvidenceQuery(**filters, section='keys')).total == 12
    assert query_evidence(settings, EvidenceQuery(**filters, section='samples')).total == 5
    assert query_evidence(settings, EvidenceQuery(**filters, section='compositions')).total == 1


def test_oversized_item_is_explicitly_omitted_not_silently_truncated(tmp_path):
    settings = Settings(tmp_path)
    ref = store_evidence(settings, 'fixture', {'data': {'operations': [{'action': 'large', 'request': 'x'*50000}, {'action': 'small'}]}})
    output = query_evidence(settings, EvidenceQuery(evidence_sha256=ref.sha256, section='operations'))
    assert output.omitted_oversized_items == 1
    assert output.items[0]['omitted'] == 'item_exceeds_byte_budget'
    assert output.items[1]['action'] == 'small'
    assert wire_size(output) <= PAGE_BYTES


@pytest.fixture
def saved_project(tmp_path):
    directory = tmp_path/'projects'/('3'*32); directory.mkdir(parents=True)
    source = directory/'project.aep'; source.write_bytes(b'fixture-not-native-aep'*20)
    write_json(directory/'project.json', {'status': 'succeeded', 'sha256': digest(source), 'result': operation(80).model_dump()})
    return Settings(tmp_path), source


def test_saved_project_query_never_calls_ae(saved_project, monkeypatch):
    settings, source = saved_project
    native = Mock(side_effect=AssertionError('No native call allowed'))
    monkeypatch.setattr('astra_video_studio.project_manager.ProjectManager.inspect', native)
    result = query_project(settings, ProjectQuery(project_id='3'*32, limit=2))
    assert result.total == 80
    assert result.provenance['state'] == 'verified_saved_version'
    assert result.provenance['unsaved_manual_edits_included'] is False
    assert result.provenance['source_sha256'] == digest(source)
    native.assert_not_called()


def test_live_query_labels_unsaved_manual_state_and_retains_failure(saved_project, monkeypatch):
    settings, _ = saved_project
    raw = operation(40); raw.data['project_dirty'] = True
    monkeypatch.setattr('astra_video_studio.project_manager.ProjectManager.inspect', Mock(return_value=raw))
    result = query_project(settings, ProjectQuery(project_id='3'*32, refresh=True))
    assert result.provenance['state'] == 'live_ae_read' and result.provenance['project_dirty']
    raw.status, raw.error, raw.data = 'blocked', 'pending execution', {}
    result = query_project(settings, ProjectQuery(project_id='3'*32, refresh=True))
    assert result.status == 'blocked' and result.error == 'pending execution'


def test_changed_saved_project_refused_before_native(saved_project, monkeypatch):
    settings, source = saved_project
    native = Mock(); monkeypatch.setattr('astra_video_studio.project_manager.ProjectManager.inspect', native)
    with pytest.raises(ValueError, match='source hash'): query_project(settings, ProjectQuery(project_id='3'*32, expected_source_sha256='0'*64))
    source.write_bytes(b'modified file')
    with pytest.raises(ValueError, match='changed or unverified'): query_project(settings, ProjectQuery(project_id='3'*32))
    native.assert_not_called()


def test_director_plan_summary_is_paged_without_losing_intent(tmp_path):
    from astra_video_studio.director import SceneBrief, build_plan
    plan = build_plan(SceneBrief(brief='Fixture scene of 10 seconds', title='Fixture', duration=10, width=960, height=540, fps=24))
    settings = Settings(tmp_path)
    compact = present(plan, 'compact', settings)
    assert wire_size(compact) <= COMPACT_BYTES
    assert 'elements' not in compact.model_dump()
    page = query_evidence(settings, EvidenceQuery(evidence_sha256=compact.evidence.sha256, section='plan_elements'))
    assert page.total == len(plan.elements)
    full = present(plan, 'full', settings).model_dump(mode='json')
    for key, value in plan.model_dump(mode='json').items(): assert full[key] == value


def test_director_execution_keeps_complete_state_in_evidence(tmp_path):
    from astra_video_studio.director import SceneExecution
    execution = SceneExecution(execution_id='1'*32, plan_id='2'*32, status='succeeded', data=scene(80) | {'preview': {'video_path': 'preview.mp4', 'verification': {'frame_count': 120}}})
    compact = present(execution, 'compact', Settings(tmp_path))
    assert wire_size(compact) <= COMPACT_BYTES
    assert compact.data['preview']['video_path'] == 'preview.mp4'
    assert 'compositions' not in compact.data
    assert json.loads(Path(compact.evidence.path).read_text())['result']['data'] == execution.data


def test_byte_budget_fallback_drops_large_event_fields_explicitly(tmp_path):
    job = JobStatus(operation_id='1'*32, action='fixture', status='succeeded', events=[{'status': 'running', 'diagnostic': 'x'*100000}], result=operation(80))
    compact = present(job, 'compact', Settings(tmp_path))
    assert wire_size(compact) <= COMPACT_BYTES
    assert compact.events == [] and compact.event_count == 1
    assert compact.result.data['detail_available']


def test_runtime_metadata_counts_toward_compact_budget(tmp_path):
    original = operation(80)
    original.data.update({f'asset_{i}_path': 'x'*1000 for i in range(3)})
    metadata = {'diagnostic_fixture': 'x'*2000}
    # The projection fits before metadata; the complete wire envelope does not.
    unbudgeted = present(original, 'compact', Settings(tmp_path))
    assert wire_size(unbudgeted) <= COMPACT_BYTES
    assert wire_size(unbudgeted, metadata) > COMPACT_BYTES
    budgeted = present(original, 'compact', Settings(tmp_path), metadata)
    assert wire_size(budgeted, metadata) <= COMPACT_BYTES
    assert budgeted.data['summary_omitted_for_byte_budget'] is True
    assert json.loads(Path(budgeted.evidence.path).read_text())['result'] == original.model_dump(mode='json')
