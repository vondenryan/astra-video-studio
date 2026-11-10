import hashlib
import json
import os
from pathlib import Path
import time
from contextlib import nullcontext
from unittest.mock import patch,Mock

import pytest

from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import Job,write_json,read_json
from astra_video_studio.lifecycle import RenderRegistry,owner_identity,owner_state
from astra_video_studio.project_manager import ProjectManager
from astra_video_studio.recovery import RecoveryService,JobReconcile,QueueInspect,CleanupPlan,ProjectDependencies
from astra_video_studio.media.preview import PreviewService,Cancelled


def test_owner_identity_detects_pid_reuse():
    owner=owner_identity();assert owner_state(owner)=='alive'
    with patch('astra_video_studio.lifecycle.process_identity',return_value={'state':'alive','created':'another_start'}):
        assert owner_state(owner)=='dead'
    assert owner_state({'pid':owner['pid']})=='unknown'


def test_durable_queue_capacity_shared_between_service_instances(tmp_path):
    s=Settings(tmp_path);jobs=[Job(s,'preview_render') for _ in range(5)]
    for job in jobs[:4]:RenderRegistry(s).admit(job)
    with pytest.raises(BlockingIOError,match='full'):RenderRegistry(s).admit(jobs[4])
    RenderRegistry(s).release(jobs[0]);RenderRegistry(s).admit(jobs[4])
    assert sum(not c['released'] for c in RenderRegistry(s).claims())==4
    with pytest.raises(ValueError,match='already admitted'):RenderRegistry(s).admit(jobs[0])


def test_worker_start_is_once_even_after_process_restart(tmp_path):
    s=Settings(tmp_path);job=Job(s,'preview_render');registry=RenderRegistry(s);registry.admit(job);registry.start(job)
    with pytest.raises(ValueError,match='conflict'):RenderRegistry(s).start(job)


def test_only_never_started_dead_owner_releases_without_changing_journal(tmp_path):
    s=Settings(tmp_path);job=Job(s,'preview_render');job.record('queued');RenderRegistry(s).admit(job)
    before=digest(job.directory/'job.json');service=RecoveryService(s)
    with patch('astra_video_studio.recovery.owner_state',return_value='dead'):
        checked=service.reconcile(JobReconcile(operation_id=job.id)).data
        assert checked['state']=='not_started_owner_exited'
        released=service.reconcile(JobReconcile(operation_id=job.id,mode='release_unstarted',expected_journal_sha256=before))
    assert released.data['released'] and digest(job.directory/'job.json')==before
    assert ProjectManager(s).job_status(job.id)['status']=='cancelled'
    assert read_json(RenderRegistry(s).path(job.id))['released']


@pytest.mark.parametrize('guard',['started','alive','unknown','pending','hash'])
def test_uncertainty_never_releases_or_replays(tmp_path,guard):
    s=Settings(tmp_path);job=Job(s,'preview_render');job.record('queued');r=RenderRegistry(s);r.admit(job)
    if guard=='started':r.start(job)
    if guard=='pending':write_json(s.contained_path('preview-pending.json'),{'job_id':job.id})
    status=guard if guard in ('alive','unknown') else 'dead'
    with patch('astra_video_studio.recovery.owner_state',return_value=status),patch('subprocess.Popen') as launch:
        with pytest.raises(ValueError):RecoveryService(s).reconcile(JobReconcile(operation_id=job.id,mode='release_unstarted',
            expected_journal_sha256='0'*64 if guard=='hash' else digest(job.directory/'job.json')))
        launch.assert_not_called()
    assert not read_json(r.path(job.id))['released']
    if guard=='pending':assert s.contained_path('preview-pending.json').exists()


def test_late_ack_authenticated_but_never_promoted_or_cleared(tmp_path):
    s=Settings(tmp_path);job=Job(s,'create');job.record('submitted',dispatch_intent=True,result_protocol='artifact-v1')
    payload={'schema_version':1,'protocol':'artifact-v1','result':{'operation_id':job.id,'status':'succeeded','data':{'fake':'fixture'}}}
    raw=json.dumps(payload).encode();(job.directory/'native-result.json').write_bytes(raw)
    write_json(job.directory/'result.json',{'operation_id':job.id,'status':'succeeded','protocol':'artifact-v1',
        'evidence':{'file':'native-result.json','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}})
    write_json(s.contained_path('ae-pending.json'),{'operation_id':job.id,'result_protocol':'artifact-v1'})
    service=RecoveryService(s);before=digest(job.directory/'job.json')
    checked=service.reconcile(JobReconcile(operation_id=job.id)).data
    assert checked['state']=='late_native_acknowledged_quarantined' and checked['native_ack']['status']=='succeeded'
    assert s.contained_path('ae-pending.json').exists() and digest(job.directory/'job.json')==before
    (job.directory/'native-result.json').write_bytes(b'tampered')
    checked=service.reconcile(JobReconcile(operation_id=job.id)).data
    assert checked['native_ack_error'] and not checked['native_ack']


def test_cleanup_plan_keeps_snapshots_outputs_and_unknown_files(tmp_path):
    s=Settings(tmp_path);job=Job(s,'fixture');job.record('succeeded')
    staging=job.directory/('job.json.'+'a'*32+'.tmp');staging.write_bytes(b'old staging')
    os.utime(staging,(time.time()-900000,time.time()-900000))
    for name in ('source-snapshot.aep','render-copy.aep','result.json','native-result.json','final.mp4','unowned.tmp'):
        (job.directory/name).write_bytes(b'preserve')
    write_json(job.directory/'result.json',dict(operation_id=job.id,status='succeeded',data={}))
    before={p.name:digest(p) for p in job.directory.iterdir()}
    plan=RecoveryService(s).cleanup(CleanupPlan(operation_ids=[job.id],minimum_age_hours=24)).data
    assert [Path(x['path']).name for x in plan['candidates']]==[staging.name]
    assert plan['deletion_performed'] is False and {p.name:digest(p) for p in job.directory.iterdir()}==before
    write_json(s.contained_path('preview-pending.json'),{'job_id':'f'*32})
    assert not RecoveryService(s).cleanup(CleanupPlan(operation_ids=[job.id],minimum_age_hours=24)).data['candidates']


def test_stale_bridge_diagnostic_never_launches(tmp_path):
    s=Settings(tmp_path);root=s.contained_path('bridge');root.mkdir()
    script=root/('bootstrap-'+'a'*32+'.jsx');script.write_text('//fixture')
    write_json(root/'session.json',{'instance_id':'a'*32})
    with patch('subprocess.Popen') as launch:
        diagnostic=RecoveryService(s).bridge();launch.assert_not_called()
    assert not diagnostic['ready'] and diagnostic['bootstrap_script']==str(script)
    assert 'Save work' in diagnostic['manual_reactivation']


def test_owned_encoder_cancel_is_distinct_from_native_wait(tmp_path):
    s=Settings(tmp_path);job=Job(s,'preview_render');(job.directory/'cancel-requested').touch()
    child=Mock(pid=123,returncode=0);child.poll.return_value=None
    with patch('subprocess.Popen',return_value=child):
        with pytest.raises(Cancelled):PreviewService(s)._process(job,['ffmpeg'],'encode',30)
    child.terminate.assert_called_once();child.kill.assert_not_called()


def test_saved_dependencies_report_missing_media_fonts_and_unverified_plugin(tmp_path):
    s=Settings(tmp_path);pid='a'*32;directory=s.contained_path('projects/'+pid);directory.mkdir(parents=True)
    source=directory/'project.aep';source.write_bytes(b'fixture aep bytes'*20)
    state={'footage':[{'path':str(tmp_path/'missing.png'),'ae_id':1,'missing':False}],
        'compositions':[{'layers':[{'ae_id':2,'text_style':{'font':'MissingFont','font_missing':True,
            'style_runs':[{'style':{'font':'OtherFont'}}]},'effects':[{'match_name':'External Unverified'}]}]}]}
    write_json(directory/'project.json',dict(project_id=pid,status='succeeded',sha256=digest(source),result={'data':state}))
    with patch('subprocess.Popen') as launch:
        result=RecoveryService(s).dependencies(ProjectDependencies(project_id=pid));launch.assert_not_called()
    assert {i['kind'] for i in result.data['issues']}=={'media','font','font_unverified','plugin_unverified'}
    assert result.data['unsaved_changes_included'] is False and not result.data['automatic_install_or_relink']


def test_corrupt_claim_fails_admission_closed(tmp_path):
    s=Settings(tmp_path);registry=RenderRegistry(s);job=Job(s,'preview_render');registry.admit(job)
    value=read_json(registry.path(job.id));value['worker_started']='false';write_json(registry.path(job.id),value)
    with pytest.raises(ValueError,match='Invalid durable'):registry.admit(Job(s,'preview_render'))


def test_owner_mismatch_does_not_prove_unstarted_release(tmp_path):
    s=Settings(tmp_path);job=Job(s,'preview_render');job.record('queued');r=RenderRegistry(s);r.admit(job)
    value=read_json(r.path(job.id));value['owner']['created']='1';write_json(r.path(job.id),value)
    with patch('astra_video_studio.recovery.owner_state',return_value='dead'):
        assert not RecoveryService(s).inspect_job(job.id)['safe_release_unstarted']


def test_cleanup_does_not_propose_hardlinked_snapshot(tmp_path):
    s=Settings(tmp_path);job=Job(s,'fixture');job.record('succeeded')
    snapshot=job.directory/'source-snapshot.aep';snapshot.write_bytes(b'customer project')
    staging=job.directory/('job.json.'+'f'*32+'.tmp');os.link(snapshot,staging)
    os.utime(staging,(time.time()-900000,time.time()-900000))
    plan=RecoveryService(s).cleanup(CleanupPlan(operation_ids=[job.id],minimum_age_hours=24)).data
    assert not plan['candidates'] and snapshot.read_bytes()==b'customer project'


@pytest.mark.parametrize('action',['inspect','create','inspect_old_heartbeat'])
def test_read_ack_release_never_releases_mutation_quarantine(tmp_path,action):
    s=Settings(tmp_path);job=Job(s,'inspect' if action.startswith('inspect') else action)
    script=job.directory/'operation.jsx';script.write_bytes(b'controlled fixture template')
    job.record('submitting',dispatch_intent=True,script_sha256=digest(script),result_protocol='artifact-v1')
    raw=json.dumps({'schema_version':1,'protocol':'artifact-v1','result':dict(operation_id=job.id,status='succeeded',data={})}).encode()
    (job.directory/'native-result.json').write_bytes(raw)
    write_json(job.directory/'result.json',dict(operation_id=job.id,status='succeeded',protocol='artifact-v1',evidence={
        'file':'native-result.json','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}))
    write_json(s.contained_path('ae-pending.json'),{'operation_id':job.id,'transport':{'instance_id':'a'*32},'result_protocol':'artifact-v1'})
    heartbeat={'instance_id':'a'*32,'ae_version':'25.5x4','active_job':None,'time_ms':time.time()*1000+10}
    if action=='inspect_old_heartbeat':heartbeat['time_ms']=0
    with patch('astra_video_studio.recovery.owner_state',return_value='dead'),patch('astra_video_studio.recovery.IdleTransport.state',return_value=heartbeat),patch('astra_video_studio.recovery.AELock',side_effect=nullcontext):
        service=RecoveryService(s);request=JobReconcile(operation_id=job.id,mode='release_acknowledged_read',expected_journal_sha256=digest(job.directory/'job.json'))
        if action!='inspect':
            with pytest.raises(ValueError,match='Only a hash-pinned'):service.reconcile(request)
            assert s.contained_path('ae-pending.json').exists()
        else:
            result=service.reconcile(request)
            assert result.data['archived_marker'] and not s.contained_path('ae-pending.json').exists()
            assert ProjectManager(s).job_status(job.id)['recovery_state']=='readonly_quarantine_released'


@pytest.mark.parametrize('tamper',[False,True])
def test_completed_render_slot_can_release_without_reencoding_only_with_hashes(tmp_path,tamper):
    s=Settings(tmp_path);job=Job(s,'preview_render');r=RenderRegistry(s);r.admit(job);r.start(job)
    source=tmp_path/'source.aep';source.write_bytes(b'fixture source, no AE')
    video=job.directory/'preview.mp4';video.write_bytes(b'fixture output, not real video')
    job.record('succeeded',source=str(source),source_sha256=digest(source),result=dict(operation_id=job.id,status='succeeded',
        data={'video_path':str(video),'video_sha256':digest(video),'fixture_only':True}))
    before=digest(job.directory/'job.json')
    if tamper:video.write_bytes(b'changed')
    with patch('astra_video_studio.recovery.owner_state',return_value='dead'),patch('subprocess.Popen') as launch:
        request=JobReconcile(operation_id=job.id,mode='release_completed',expected_journal_sha256=before)
        if tamper:
            with pytest.raises(ValueError,match='does not prove'):RecoveryService(s).reconcile(request)
        else:
            assert RecoveryService(s).reconcile(request).data['state']=='completed_slot_released'
            assert ProjectManager(s).job_status(job.id)['status']=='succeeded'
        launch.assert_not_called()
    assert digest(job.directory/'job.json')==before
