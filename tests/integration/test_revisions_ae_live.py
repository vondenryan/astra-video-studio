"""Sprint 9: simulated unsaved operator edits in a disposable native fixture."""
import copy
import json
import os
from pathlib import Path
import time
from unittest.mock import patch

import pytest

from astra_video_studio.ae_bridge.runner import BridgeRunner
from astra_video_studio.ae_bridge.templates import render_script
from astra_video_studio.animation import fingerprint
from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import ExistingProjectService, digest
from astra_video_studio.jobs import write_json
from astra_video_studio.layers import LayerService, LayerCreateRequest
from astra_video_studio.media.preview import PreviewService, PreviewRequest
from astra_video_studio.motion_engine.service import MotionService
from astra_video_studio.motion_engine.schemas import MotionRequest
from astra_video_studio.project_manager import ProjectManager
from astra_video_studio.revisions import (RevisionService, DirectorPatchRequest, RevisionPlanRequest,
    RevisionApplyRequest, VersionCompareRequest, VersionRestoreRequest)
from astra_video_studio.scene_editing import find_comp, find_layer, equivalent
from astra_video_studio.schemas import ProjectCreateRequest


@pytest.mark.ae_live
@pytest.mark.skipif(os.environ.get('ASTRA_RUN_AE_TESTS') != '1', reason='Opt-in native revision/manual collaboration acceptance')
def test_manual_capture_patch_conflict_and_restore():
    settings = Settings.from_env(); projects = ProjectManager(settings); revisions = RevisionService(settings)
    preserved = {}
    def good(result):
        assert result.status == 'succeeded', result.model_dump()
        if result.project_path:
            path = Path(result.project_path); preserved[str(path)] = digest(path)
        return result
    created = good(projects.create(ProjectCreateRequest(name='Astra — Revisão pontual', title='TÍTULO ORIGINAL', width=960, height=540, fps=24, duration=5, font_size=50)))
    project_id = created.project_id
    comp_id = created.data['compositions'][0]['composition_id'].split(':')[-1]
    title_id = created.data['compositions'][0]['layers'][0]['layer_id'].split(':')[-1]
    base = {'project_id': project_id, 'composition_id': comp_id}
    target = base | {'layer_id': title_id}
    sentinel = good(LayerService(settings).create(LayerCreateRequest(**base, layer={'name': 'Preservada', 'text': 'EDIÇÃO HUMANA PRESERVADA', 'font_size': 24, 'position': [480, 440]})))
    sentinel_id = sentinel.data['layer_id']
    good(MotionService(settings).apply(MotionRequest(**target, skill='slide_in', duration=1, params={'distance_px': 240, 'overshoot': 0})))
    manifest, source = projects.load(project_id)
    baseline_version = manifest['current_version']; baseline_hash = digest(source)
    baseline = good(projects.inspect(project_id)).data
    old_title = find_layer(find_comp(baseline, comp_id), title_id)
    old_sentinel = copy.deepcopy(find_layer(find_comp(baseline, comp_id), sentinel_id))
    plan = good(revisions.director_plan(DirectorPatchRequest(**target, base_sha256=baseline_hash,
        instruction='trocar título para "REVISÃO PONTUAL"; atrasar entrada 6 frames entre 0 e 24')))
    apply = RevisionApplyRequest(revision_id=plan.data['revision_id'], plan_sha256=plan.data['plan_sha256'], expected_current_sha256=baseline_hash)
    native_title = old_title['ae_id']
    def manual(code):
        current_manifest, current = projects.load(project_id)
        def fixture(action, payload):
            script = render_script(action, payload)
            if action == 'inspect':
                # Test-only fixture injection; no arbitrary-code tool is exposed.
                code_block = "\nvar manualLayer = null;\nfor(var ci=1;ci<=app.project.numItems;ci++){var mc=app.project.item(ci);if(mc instanceof CompItem){for(var li=1;li<=mc.numLayers;li++){if(mc.layer(li).id === " + str(native_title) + "){manualLayer=mc.layer(li);}}}}\nif(!manualLayer){throw new Error('FIXTURE_LAYER_MISSING');}\n" + code + '\n'
                script = script.replace('        /*ASTRA_RESULT_COLLECTION*/', code_block + '        /*ASTRA_RESULT_COLLECTION*/', 1)
            return script
        with patch('astra_video_studio.ae_bridge.runner.render_script', side_effect=fixture):
            result = BridgeRunner(settings).run('inspect', {'project_path': current.as_posix(), 'id_map': current_manifest.get('id_map')})
        assert result.status == 'succeeded' and result.data['project_dirty'], result.model_dump()
        return result.data
    human = manual("var tdProp=manualLayer.property('ADBE Text Properties').property('ADBE Text Document');var td=tdProp.value;td.fillColor=[0.95,0.45,0.15];tdProp.setValue(td);var ap=manualLayer.property('ADBE Transform Group').property('ADBE Anchor Point');var av=ap.value;ap.setValue([av[0]+15,av[1]+8]);")
    assert digest(source) == baseline_hash  # Unsaved edits never overwrite source.
    with pytest.raises(ValueError, match='capture_manual'): revisions.apply(apply)
    revised = good(revisions.apply(apply.model_copy(update={'capture_manual': True})))
    captured_version, patched_version = revised.data['captured_manual_version'], revised.data['version_id']
    assert captured_version and patched_version != captured_version
    new_title = find_layer(find_comp(revised.data, comp_id), title_id)
    human_title = find_layer(find_comp(human, comp_id), title_id)
    assert new_title['text'] == 'REVISÃO PONTUAL'
    equivalent(new_title['text_style']['fill'], human_title['text_style']['fill'])
    equivalent(new_title['transforms']['anchor'], human_title['transforms']['anchor'])
    equivalent(find_layer(find_comp(revised.data, comp_id), sentinel_id), old_sentinel)
    old_keys, new_keys = old_title['transforms']['position']['keys'], new_title['transforms']['position']['keys']
    assert len(old_keys) == len(new_keys)
    for old, new in zip(old_keys, new_keys, strict=True):
        assert new['time'] == pytest.approx(old['time'] + 6 / 24)
        equivalent(new['value'], old['value'])
    comparison = good(revisions.compare(VersionCompareRequest(project_id=project_id, left=captured_version, right=patched_version)))
    assert any(change['path'].endswith('/text') for change in comparison.data['changes'])
    assert not any('/anchor/' in change['path'] or '/fill/' in change['path'] for change in comparison.data['changes'])
    _, current = projects.load(project_id); patched_hash = digest(current)
    conflict_plan = good(revisions.plan(RevisionPlanRequest(project_id=project_id, base_sha256=patched_hash, instruction='change title again',
        operations=[{'action': 'content_set', 'request': target | {'text': 'SECOND'}}])))
    manual("var tp=manualLayer.property('ADBE Text Properties').property('ADBE Text Document');var doc=tp.value;doc.text='TÍTULO MANUAL';tp.setValue(doc);")
    conflict = revisions.apply(RevisionApplyRequest(revision_id=conflict_plan.data['revision_id'], plan_sha256=conflict_plan.data['plan_sha256'], expected_current_sha256=patched_hash, capture_manual=True))
    assert conflict.status == 'blocked' and any(c['path'].endswith('/text') for c in conflict.data['conflicts'])
    assert projects.load(project_id)[0]['current_version'] == patched_version
    captured_conflict = good(ExistingProjectService(settings).save(project_id))
    restored = good(revisions.restore(VersionRestoreRequest(project_id=project_id, version_id=patched_version,
        expected_current_sha256=digest(Path(captured_conflict.project_path)), reason='Preserve conflicting manual title and return to accepted patch as a new version')))
    assert restored.data['version_id'] not in (patched_version, captured_version)
    assert digest(Path(restored.project_path)) == patched_hash
    # Exercise the other typed categories on a separate static layer, in one patch.
    sentinel_target = base | {'layer_id': sentinel_id}
    extra_plan = good(revisions.plan(RevisionPlanRequest(project_id=project_id, base_sha256=patched_hash, instruction='Style and static rotation', operations=[
        {'action': 'text_style_set', 'request': sentinel_target | {'fill': [0.4, 0.7, 0.8], 'recenter_anchor': False}},
        {'action': 'layer_transform', 'request': sentinel_target | {'values': {'rotation': -2}}},
    ])))
    extra = good(revisions.apply(RevisionApplyRequest(revision_id=extra_plan.data['revision_id'], plan_sha256=extra_plan.data['plan_sha256'], expected_current_sha256=patched_hash)))
    _, source = projects.load(project_id); extra_hash = digest(source)
    timing_plan = good(revisions.plan(RevisionPlanRequest(project_id=project_id, base_sha256=extra_hash, instruction='Trim static sentinel', operations=[
        {'action': 'layer_update', 'request': sentinel_target | {'in_frame': 6, 'out_frame': 114}},
    ])))
    timed = good(revisions.apply(RevisionApplyRequest(revision_id=timing_plan.data['revision_id'], plan_sha256=timing_plan.data['plan_sha256'], expected_current_sha256=extra_hash)))
    final = good(revisions.restore(VersionRestoreRequest(project_id=project_id, version_id=patched_version,
        expected_current_sha256=digest(Path(timed.project_path)), reason='Leave title patch and original sentinel as final acceptance output')))
    preview = PreviewService(settings)
    queued = preview.submit(PreviewRequest(**base, duration=5, max_width=960))
    assert queued.status == 'queued'
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        status = projects.job_status(queued.job_id)
        if status['status'] not in ('queued', 'running', 'prepared'):
            assert status['status'] == 'succeeded', status
            video = status['result']['data']; break
        time.sleep(2)
    else: pytest.fail('Native revision preview timed out; do not resubmit')
    for path, sha in preserved.items(): assert digest(Path(path)) == sha
    write_json(settings.contained_path('sprint9-acceptance.json'), {'project_id': project_id, 'composition_id': comp_id,
        'project_path': final.project_path, 'project_sha256': digest(Path(final.project_path)), 'baseline_version': baseline_version,
        'captured_manual_version': captured_version, 'patched_version': patched_version, 'final_version': final.data['version_id'],
        'revision_id': plan.data['revision_id'], 'plan_sha256': plan.data['plan_sha256'], 'conflict': conflict.model_dump(),
        'preserved_aep_files': preserved, 'manual_style_and_layout_preserved': True, 'entry_delay_frames': 6,
        'video': video, 'full_playback_reviewed': False})
