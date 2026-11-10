import copy
import json
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import write_json
from astra_video_studio.revisions import (RevisionService, RevisionPlanRequest, RevisionApplyRequest,
    VersionCompareRequest, VersionRestoreRequest, check_disjoint, footprints, prepare_patch,
    verify_patch, state_changes, retained_metadata, fingerprint)
from astra_video_studio.schemas import OperationResult

IDS = {'project_id': '1' * 32, 'composition_id': '2' * 32, 'layer_id': '3' * 32}


@pytest.fixture
def state():
    track = {'available': True, 'spatial': False, 'separated': False, 'expression_enabled': False,
             'expression_present': False, 'value': 0, 'keys': [], 'samples': []}
    style = {'font': 'Arial-BoldMT', 'font_size': 60, 'tracking': 0, 'fill': [1, 1, 1],
             'font_missing': False, 'box_overflow': False, 'styles_truncated': False,
             'style_runs': [{'start': 0, 'end': 3, 'style': {'font': 'Arial-BoldMT', 'font_size': 60, 'tracking': 0, 'fill': [1, 1, 1]}}]}
    layer = {'layer_id': 'astra:layer:' + IDS['layer_id'], 'ae_id': 7, 'text': 'OLD', 'text_style': style,
             'text_document_animated': False, 'text_animators': [], 'locked': False, 'editable_2d': True,
             'parent_ae_id': None, 'in_point': 0, 'out_point': 5, 'start_time': 0,
             'animation_summary': {'expressions': 0, 'key_count': 0},
             'bounds': {}, 'visual_bounds': {}, 'layout_bounds': {}, 'transforms': {'rotation': track}}
    return {'project_dirty': False, 'compositions': [{'composition_id': 'astra:composition:' + IDS['composition_id'], 'fps': 24, 'duration': 5, 'layers': [layer]}], 'footage': []}


def request(base='a' * 64, **kwargs):
    return RevisionPlanRequest(project_id=IDS['project_id'], base_sha256=base, instruction='Change title',
                               operations=[{'action': 'content_set', 'request': IDS | {'text': 'NEW'}}], **kwargs)


def layer(state): return state['compositions'][0]['layers'][0]


def test_content_guard_allows_manual_color_and_position_but_rejects_text(state):
    op = request().operations[0]
    baseline = footprints(op, state)
    layer(state)['text_style']['fill'] = [1, 0, 0]
    layer(state)['transforms']['position'] = {'value': [20, 30]}
    assert footprints(op, state) == baseline
    layer(state)['text'] = 'MANUAL'
    assert footprints(op, state) != baseline


@pytest.mark.parametrize('change', ['dirty', 'expressions', 'locked', 'animated', 'animators', 'missing_font', 'mixed_style'])
def test_content_preflight_protects_unsupported_state(state, change, tmp_path):
    target = layer(state)
    if change == 'dirty': state['project_dirty'] = True
    if change == 'expressions': target['animation_summary']['expressions'] = 1
    if change == 'locked': target['locked'] = True
    if change == 'animated': target['text_document_animated'] = True
    if change == 'animators': target['text_animators'] = [{}]
    if change == 'missing_font': target['text_style']['font_missing'] = True
    if change == 'mixed_style': target['text_style']['style_runs'] = [target['text_style']['style_runs'][0] | {'end': 1}, target['text_style']['style_runs'][0] | {'start': 1, 'style': target['text_style']['style_runs'][0]['style'] | {'fill': [1, 0, 0]}}]
    with pytest.raises(ValueError): prepare_patch(Settings(tmp_path), request().operations[0], state)


def test_content_verification_checks_other_properties_and_preserves_manual_style(state):
    layer(state)['text_style']['fill'] = [1, 0, 0]
    layer(state)['text_style']['style_runs'][0]['style']['fill'] = [1, 0, 0]
    after = copy.deepcopy(state); layer(after)['text'] = 'NEW'
    verify_patch(request().operations[0], state, after, {})
    layer(after)['transforms']['rotation']['value'] = 12
    with pytest.raises(ValueError, match='preserved project'): verify_patch(request().operations[0], state, after, {})


@pytest.mark.parametrize('change', [
    {'action': 'execute_jsx', 'request': IDS},
    {'action': 'content_set', 'request': IDS | {'text': 'x', 'code': 'alert(1)'}},
    {'action': 'content_set', 'request': IDS | {'project_id': '4' * 32, 'text': 'x'}},
    {'action': 'layer_update', 'request': IDS | {'name': 'reorder'}},
])
def test_closed_schema(change):
    with pytest.raises(ValidationError): RevisionPlanRequest(project_id=IDS['project_id'], base_sha256='a' * 64, instruction='x', operations=[change])


def test_duplicate_property_rejected():
    op = request().operations[0]
    with pytest.raises(ValueError, match='overlapping'): check_disjoint([op, op])


def test_diff_excludes_samples_but_identifies_actual_change(state):
    after = copy.deepcopy(state)
    layer(after)['transforms']['rotation']['samples'] = [{'time': 1, 'value': 2}]
    assert not state_changes(state, after)
    layer(after)['text'] = 'NEW'
    assert state_changes(state, after) == [{'path': '/compositions/0/layers/0/text', 'before': 'OLD', 'after': 'NEW'}]


@pytest.fixture
def service(tmp_path, state):
    service = RevisionService(Settings(tmp_path))
    directory = tmp_path / 'projects' / IDS['project_id']; directory.mkdir(parents=True)
    source = directory / 'project.aep'; source.write_bytes(b'saved-fixture' * 30)
    write_json(directory / 'project.json', {'project_id': IDS['project_id'], 'status': 'succeeded', 'sha256': digest(source), 'result': {'data': state}})
    service.projects.inspect = Mock(return_value=OperationResult(operation_id='0' * 32, status='succeeded', data=copy.deepcopy(state)))
    service.projects.runner = Mock()
    service.projects._finalize_job = Mock()
    return service, source


def planned(service):
    obj, source = service
    result = obj.plan(request(digest(source)))
    return RevisionApplyRequest(revision_id=result.data['revision_id'], plan_sha256=result.data['plan_sha256'], expected_current_sha256=digest(source))


def test_plan_is_read_only_and_tamper_checked(service):
    obj, source = service; original = source.read_bytes(); apply = planned(service)
    obj.projects.runner.run.assert_not_called(); assert source.read_bytes() == original
    path = obj._directory(apply.revision_id) / 'plan.json'; path.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='integrity'): obj.apply(apply)
    obj.projects.runner.run.assert_not_called()


def test_conflict_reports_property_without_mutation(service):
    obj, _ = service; apply = planned(service)
    layer(obj.projects.inspect.return_value.data)['text'] = 'HUMAN'
    result = obj.apply(apply)
    assert result.status == 'blocked'
    assert result.data['conflicts'][0]['path'].endswith('/text')
    assert not (obj._directory(apply.revision_id) / 'attempt.json').exists()
    obj.projects.runner.run.assert_not_called()


def test_dirty_state_requires_explicit_capture(service):
    obj, _ = service; apply = planned(service)
    obj.projects.inspect.return_value.data['project_dirty'] = True
    with pytest.raises(ValueError, match='capture_manual'): obj.apply(apply)
    obj.projects.runner.run.assert_not_called()


def test_current_hash_conflict_precedes_ae(service):
    obj, _ = service; apply = planned(service)
    obj.projects.inspect.reset_mock()
    with pytest.raises(ValueError, match='Current version hash'): obj.apply(apply.model_copy(update={'expected_current_sha256': '0' * 64}))
    obj.projects.inspect.assert_not_called()


def test_failed_or_timeout_edit_never_promotes_or_retries(service):
    obj, source = service; apply = planned(service)
    obj.projects.runner.run.return_value = OperationResult(operation_id='9' * 32, status='timeout', error='unknown')
    result = obj.apply(apply)
    assert result.status == 'timeout'
    assert not json.loads((source.parent / 'project.json').read_text()).get('current_version')
    with pytest.raises(ValueError, match='already attempted'): obj.apply(apply)
    assert obj.projects.runner.run.call_count == 1


def test_success_promotes_only_verified_version_and_keeps_source(service):
    obj, source = service; apply = planned(service); original = source.read_bytes()
    def native(action, payload):
        after = copy.deepcopy(payload['expected_state']); layer(after)['text'] = 'NEW'
        from pathlib import Path
        Path(payload['version_path']).write_bytes(b'new-version' * 30)
        return OperationResult(operation_id='8' * 32, status='succeeded', data=after | {'revision_steps': [copy.deepcopy(after)]})
    obj.projects.runner.run.side_effect = native
    result = obj.apply(apply)
    assert result.status == 'succeeded'
    assert json.loads((source.parent / 'project.json').read_text())['current_version'] == result.data['version_id']
    assert source.read_bytes() == original


def test_verification_failure_keeps_parent_manifest(service):
    obj, source = service; apply = planned(service)
    obj.projects.runner.run.return_value = OperationResult(operation_id='8' * 32, status='succeeded', data={})
    assert obj.apply(apply).status == 'failed'
    assert not json.loads((source.parent / 'project.json').read_text()).get('current_version')


def test_restore_rejects_changed_version_before_ae(service):
    obj, source = service; source.write_bytes(b'manually overwritten')
    with pytest.raises(ValueError, match='changed on disk'):
        obj.restore(VersionRestoreRequest(project_id=IDS['project_id'], version_id='initial', expected_current_sha256=digest(source), reason='restore'))
    obj.projects.runner.run.assert_not_called()


def test_compare_same_version_is_empty(service):
    obj, _ = service
    assert obj.compare(VersionCompareRequest(project_id=IDS['project_id'], left='initial', right='initial')).data['changes'] == []


def test_director_rejects_unknown_clause_no_partial_plan(service):
    from astra_video_studio.revisions import DirectorPatchRequest
    obj, source = service
    with pytest.raises(ValueError, match='Unsupported clause'):
        obj.director_plan(DirectorPatchRequest(**IDS, base_sha256=digest(source), instruction='trocar título para "NEW"; invente qualquer coisa'))
    assert not obj.settings.contained_path('revisions').exists()
    obj.projects.runner.run.assert_not_called()


def test_optional_probe_differences_do_not_block_planning(service):
    obj, source = service
    state = obj.projects.inspect.return_value.data
    layer(state)['world_basis'] = None
    record_path = source.parent / 'project.json'
    record = json.loads(record_path.read_text())
    layer(record['result']['data'])['world_basis'] = {'origin': [0, 0]}
    write_json(record_path, record)
    assert obj.plan(request(digest(source))).status == 'succeeded'


def test_retained_metadata_normalizes_legacy_alias_samples(state):
    layer(state)['position'] = [60, 30]
    layer(state)['transforms']['position'] = {'value': [0, 0], 'keys': [{'time': 0, 'value': [0, 0]}], 'samples': []}
    after = copy.deepcopy(state); layer(after)['position'] = [0, 0]
    assert retained_metadata(state) == retained_metadata(after)


def test_restore_reconstructs_legacy_sidecar_from_verified_metadata(service):
    obj, source = service
    record_path = source.parent / 'project.json'; record = json.loads(record_path.read_text())
    record['result']['data']['compositions'][0]['ae_id'] = 2
    layer(record['result']['data'])['comment'] = 'Client comment left intact'
    write_json(record_path, record)
    before = copy.deepcopy(record['result']['data']); obj.projects.inspect.return_value.data = before
    def native(action, payload):
        assert action == 'version_restore'
        assert payload['restore_id_map']['layers']['7'] == IDS['layer_id']
        assert payload['restore_id_map']['compositions']['2'] == IDS['composition_id']
        return OperationResult(operation_id='7' * 32, status='succeeded', data=copy.deepcopy(before))
    obj.projects.runner.run.side_effect = native
    result = obj.restore(VersionRestoreRequest(project_id=IDS['project_id'], version_id='initial', expected_current_sha256=digest(source), reason='test legacy sidecar'))
    assert result.status == 'succeeded'
    assert source.read_bytes() == __import__('pathlib').Path(result.project_path).read_bytes()
    assert layer(result.data)['comment'] == 'Client comment left intact'
