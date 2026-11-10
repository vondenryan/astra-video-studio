import copy
import json
from pathlib import Path
import runpy
from unittest.mock import Mock

from pydantic import ValidationError
import pytest

from astra_video_studio.audio import (AudioService, AudioClipSet, ClipSpec, AudioTarget, AudioMarkersCreate,
    TimelineMarkersSet, AudioSyncPlan)
from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.media.preview import PreviewRequest, AudioPreviewRequest
from astra_video_studio.responses import store_evidence, query_evidence, EvidenceQuery

F = runpy.run_path('tests/fixtures/audio_scene.py')
PID, CID, LID = (F[k] for k in ('PID','CID','LID'))


@pytest.fixture
def audio(tmp_path, monkeypatch):
    source, comp = F['fake_project'](tmp_path)
    service = AudioService(Settings(tmp_path))
    monkeypatch.setattr(service.projects.runner, 'run', Mock(side_effect=AssertionError('No native call allowed')))
    monkeypatch.setattr(service, '_asset', Mock(return_value={'manifest_sha256': 'a'*64, 'sample_count': 960000,
        'energy_onsets': [{'sample': 48000, 'confidence': 0.8, 'uncertainty_samples': 960}]}))
    target = {'project_id': PID, 'composition_id': CID, 'base_aep_sha256': digest(source)}
    return service, target, source


def add(service, target, **clip):
    result = service.clip_set(AudioClipSet(**target, clip=ClipSpec(asset_id='4'*32, duration_frames=24, **clip)))
    assert result.status == 'succeeded', result.error
    return result


@pytest.mark.parametrize('changes', [dict(gain_db=float('nan')),dict(duration_frames=0),
    dict(fade_in_frames=20,fade_out_frames=20),dict(start_frame=-1)])
def test_reject_invalid_clip(changes):
    with pytest.raises(ValidationError): ClipSpec(**({'asset_id':'4'*32,'duration_frames':24}|changes))


def test_silent_limit_unchanged_and_audio_requires_hashes():
    with pytest.raises(ValidationError): PreviewRequest(project_id=PID,composition_id=CID,duration=20)
    with pytest.raises(ValidationError): AudioPreviewRequest(project_id=PID,composition_id=CID,duration=20)
    assert AudioPreviewRequest(project_id=PID,composition_id=CID,duration=20,
        base_aep_sha256='a'*64,audio_state_sha256='b'*64).duration==20


def test_audio_versions_no_aep_mutation_and_explicit_replace(audio):
    service,target,source=audio
    before=source.read_bytes()
    first=add(service,target)
    parent=Path(first.data['audio_state_path']).read_bytes()
    second=service.clip_set(AudioClipSet(**(target|{'audio_state_sha256':first.data['audio_state_sha256']}),
        mode='replace',clip_id=first.data['clip_id'],clip=ClipSpec(asset_id='4'*32,duration_frames=48,gain_db=-6)))
    assert second.status=='succeeded' and second.data['audio_clips'][0]['duration_frames']==48
    assert Path(first.data['audio_state_path']).read_bytes()==parent
    assert source.read_bytes()==before
    assert Path(second.artifacts[1]).read_bytes()==before
    service.projects.runner.run.assert_not_called()
    page=query_evidence(service.settings,EvidenceQuery(evidence_sha256=second.data['audio_state_sha256'],section='audio_clips'))
    assert page.total==1 and page.items[0]['gain_db']==-6


@pytest.mark.parametrize('clip', [dict(start_frame=479),dict(source_start_sample=960000)])
def test_ranges_fail_before_snapshot(audio,clip):
    service,target,source=audio
    with pytest.raises(ValueError): add(service,target,**clip)
    assert not service.settings.contained_path('jobs').exists()


def test_source_and_state_conflicts_before_writes(audio):
    service,target,source=audio
    with pytest.raises(ValueError,match='conflict'): add(service,target|{'base_aep_sha256':'0'*64})
    assert not service.settings.contained_path('jobs').exists()
    first=add(service,target)
    Path(first.data['audio_state_path']).write_text('{}')
    with pytest.raises(ValueError,match='hash'): add(service,target|{'audio_state_sha256':first.data['audio_state_sha256']})


def test_markers_timeline_and_sync_only_selected_clip(audio):
    service,target,source=audio
    first=add(service,target)
    second=add(service,target|{'audio_state_sha256':first.data['audio_state_sha256']},start_frame=240)
    non_target=copy.deepcopy(second.data['audio_clips'][1])
    cues=service.markers_create(AudioMarkersCreate(asset_id='4'*32,markers=[{'sample':4800,'label':'hit'}]))
    state_target=target|{'audio_state_sha256':second.data['audio_state_sha256']}
    marked=service.timeline_set(TimelineMarkersSet(**state_target,markers=[{'marker_id':'5'*32,'frame':72,'label':'visual'}]))
    planned=service.sync_plan(AudioSyncPlan(**(target|{'audio_state_sha256':marked.data['audio_state_sha256']}),bindings=[{
        'clip_id':first.data['clip_id'],'marker_set_sha256':cues.data['marker_set_sha256'],
        'source_marker_id':cues.data['audio_markers'][0]['marker_id'],'layer_id':LID,'property':'opacity','key_index':1}]))
    assert planned.status=='succeeded',planned.error
    assert planned.data['plan_only'] and not planned.data['native_keys_modified']
    assert planned.data['audio_clips'][1]==non_target
    assert planned.data['audio_markers']==marked.data['audio_markers']
    assert planned.data['sync_events'][0]['error_frames']<=0.5
    assert digest(source)==target['base_aep_sha256']


def test_duplicate_timeline_marker_rejected(audio):
    service,target,source=audio
    marker={'marker_id':'5'*32,'frame':72,'label':'hit'}
    with pytest.raises(ValueError,match='duplicate'):
        service.timeline_set(TimelineMarkersSet(**target,markers=[marker,marker]))


def test_energy_candidates_keep_uncertainty(audio):
    service,target,source=audio
    result=service.markers_create(AudioMarkersCreate(asset_id='4'*32,method='energy'))
    assert result.data['audio_markers'][0]['uncertainty_samples']==960
    assert result.data['audio_markers'][0]['confidence']==0.8
