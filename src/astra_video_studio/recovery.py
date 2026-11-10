"""Bounded recovery diagnostics. No replay, marker clearing, relink or deletion."""
import json
import os
from pathlib import Path
import re
import shutil
import time
from typing import Literal

from pydantic import Field,model_validator

from astra_video_studio.ae_bridge.discovery import discover_ae
from astra_video_studio.ae_bridge.idle_transport import IdleTransport
from astra_video_studio.ae_bridge.locking import AELock
from astra_video_studio.ae_bridge.result_artifacts import (PROTOCOL,ACK_MAX_BYTES,INLINE_MAX_BYTES,
    parse_json,load_artifact,validate_result)
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import Job,read_json,write_json,timestamp
from astra_video_studio.lifecycle import RenderRegistry,owner_state,process_identity
from astra_video_studio.motion_engine.schemas import StrictModel
from astra_video_studio.project_manager import ProjectManager,valid_id
from astra_video_studio.responses import store_evidence
from astra_video_studio.scene_editing import ID
from astra_video_studio.schemas import OperationResult

TERMINAL={'succeeded','failed','cancelled','blocked','busy','timeout'}


class QueueInspect(StrictModel):
    scope:Literal['active','all']='active'
    offset:int=Field(default=0,ge=0,le=100000)
    limit:int=Field(default=25,ge=1,le=100)


class JobReconcile(StrictModel):
    operation_id:ID
    mode:Literal['inspect','release_unstarted','release_completed','release_acknowledged_read']='inspect'
    expected_journal_sha256:str|None=Field(default=None,pattern=r'^[0-9a-f]{64}$')
    @model_validator(mode='after')
    def guard(self):
        if self.mode!='inspect' and not self.expected_journal_sha256:
            raise ValueError('Release requires the inspected journal SHA-256')
        return self


class ProjectDependencies(StrictModel):
    project_id:ID
    refresh:bool=False


class CleanupPlan(StrictModel):
    operation_ids:list[ID]=Field(min_length=1,max_length=50)
    minimum_age_hours:int=Field(default=168,ge=24,le=87600)


class RecoveryService:
    def __init__(self,settings):self.settings,self.projects=settings,ProjectManager(settings)
    def _result(self,action,data,project_id=None):
        job=Job(self.settings,action)
        result=OperationResult(operation_id=job.id,status='succeeded',project_id=project_id,data=data)
        job.record('succeeded',result=result.model_dump(mode='json'));return result

    def _marker(self,name):
        path=self.settings.contained_path(name)
        if not path.exists():return None
        try:
            if path.stat().st_size>65536:raise ValueError('Marker exceeds bound')
            value=read_json(path)
            if not isinstance(value,dict):raise ValueError('Marker is not an object')
            return value|{'marker_path':str(path),'marker_sha256':digest(path)}
        except (OSError,ValueError,TypeError) as exc:
            return {'marker_path':str(path),'invalid':str(exc),'quarantine_retained':True}

    def bridge(self):
        transport=IdleTransport(self.settings);state=transport.state()
        pending=self._marker('ae-pending.json');native=self._marker('preview-pending.json')
        startup=self._marker('bridge/startup-pending.json');session=self._marker('bridge/session.json')
        instance=(startup or session or {}).get('instance_id')
        bootstrap=None
        if isinstance(instance,str) and re.fullmatch('[0-9a-f]{32}',instance):
            candidate=self.settings.contained_path(f'bridge/bootstrap-{instance}.jsx')
            if candidate.is_file():bootstrap=str(candidate)
        ready=bool(state and not state.get('active_job') and not pending and not native)
        return dict(ready=ready,heartbeat=state,ae_quarantine=pending,render_quarantine=native,
            bootstrap_script=bootstrap,automatic_launch_permitted=False,
            manual_reactivation='Inspect pending jobs first; do not run bootstrap while execution is uncertain.' if pending or native else
                'Save work, then File > Scripts > Run Script File and choose the existing reviewed bootstrap.' if not ready else 'No reactivation needed.',
            modal_possible=bool(pending and not state),modal_diagnosis='Stale heartbeat can indicate AE closed, busy or a modal; it does not prove a modal exists.')

    def inspect_job(self,identifier,persist_native=False):
        path=self.settings.contained_path(f'jobs/{valid_id(identifier)}/job.json')
        sha=digest(path);record=read_json(path)
        if record.get('operation_id')!=identifier:raise ValueError('Job identity mismatch')
        if digest(path)!=sha:raise ValueError('Job changed during inspection; inspect again, never resubmit')
        directory=path.parent;owner=owner_state(record.get('owner'))
        claim_path=RenderRegistry(self.settings).path(identifier)
        claim=RenderRegistry.validate(read_json(claim_path),identifier) if claim_path.exists() else None
        native=self._marker('ae-pending.json');renderer=self._marker('preview-pending.json')
        pending=bool(native and (native.get('operation_id')==identifier or native.get('invalid')))
        render_pending=bool(renderer and (renderer.get('job_id')==identifier or renderer.get('invalid')))
        child=owner_state(record.get('process_identity')) if record.get('process_identity') else 'unknown'
        state='owned_process_alive' if owner=='alive' and record['status'] not in TERMINAL else 'interrupted_unknown'
        if owner=='dead' and child=='alive' and not record.get('process_exit_confirmed'):state='orphan_child_process_alive'
        ack_info=None;ack_error=None
        ackpath=self.settings.contained_path(f'jobs/{identifier}/result.json')
        if ackpath.is_file():
            try:
                protocol=record.get('result_protocol') or (native or {}).get('result_protocol')
                limit=ACK_MAX_BYTES if protocol==PROTOCOL else INLINE_MAX_BYTES
                if ackpath.stat().st_size>limit:raise ValueError('Acknowledgement exceeds bound')
                raw=ackpath.read_bytes()
                if len(raw)>limit:raise ValueError('Acknowledgement grew beyond bound')
                ack=parse_json(raw)
                if protocol==PROTOCOL:result,evidence=load_artifact(self.settings,directory,identifier,ack)
                else:
                    if ack.get('protocol') is not None:raise ValueError('Unknown/unrecorded protocol; no inferred downgrade')
                    result,evidence=validate_result(ack,identifier),None
                ack_info={'status':result['status'],'evidence':evidence,'ack_sha256':digest(ackpath)}
                if persist_native:
                    ref=store_evidence(self.settings,'RecoveredNativeResult',result,{'operation_id':identifier,'semantic_verification':'not_performed','replay':False})
                    ack_info['result_evidence_sha256']=ref.sha256
                state='native_acknowledged_unverified'
            except (OSError,ValueError,KeyError,TypeError) as exc:
                ack_error=str(exc);state='invalid_native_evidence'
        if record['status'] in TERMINAL and not pending and not render_pending and not ack_error:
            state='recorded_terminal'
        if ack_info and record['status']=='succeeded' and any(e.get('stage')=='service_verification' for e in record.get('events',[])):
            state='service_verified_recorded'
        if pending or render_pending:
            state=('late_native_acknowledged_quarantined' if ack_info else 'native_execution_uncertain')
        if render_pending and child=='alive':state='orphan_renderer_alive' if owner=='dead' else 'renderer_owned_process_alive'
        safe_release=bool(claim and not claim.get('released') and not claim.get('worker_started') and owner=='dead'
            and claim['owner']==record.get('owner')
            and record.get('lifecycle_version')==1 and record.get('status') in ('prepared','queued')
            and not record.get('dispatch_intent') and not record.get('native_preparation_intent')
            and not record.get('process_launch_intent') and not ackpath.exists() and not pending and not render_pending)
        if safe_release:state='not_started_owner_exited'
        if (claim and claim.get('release_reason')=='reconciled_never_started' and claim['released']
            and not claim['worker_started'] and claim.get('reconciled_journal_sha256')==sha
            and claim['owner']==record.get('owner')):state='not_started_released'
        artifacts=[]
        result=record.get('result') or {};data=result.get('data',{})
        for name,hash_name in [('video_path','video_sha256'),('sequence_manifest_path','sequence_manifest_sha256')]:
            if data.get(name):
                try:
                    artifact=self.settings.contained_path(str(Path(data[name]).relative_to(self.settings.workspace)))
                    artifacts.append({'path':str(artifact),'hash_matches':artifact.is_file() and digest(artifact)==data.get(hash_name)})
                except (OSError,ValueError):artifacts.append({'path':data[name],'hash_matches':False})
        if any(not a['hash_matches'] for a in artifacts):state='recorded_artifacts_changed'
        source_matches=False
        source_hash=record.get('source_sha256') or data.get('source_sha256')
        if record.get('source') and source_hash:
            try:
                source=self.settings.contained_path(str(Path(record['source']).relative_to(self.settings.workspace)))
                source_matches=source.is_file() and digest(source)==source_hash
            except (OSError,ValueError):pass
        safe_completed_release=bool(claim and not claim['released'] and claim['worker_started']
            and claim['owner']==record.get('owner') and owner=='dead' and record.get('lifecycle_version')==1
            and record['action'] in ('preview_render','render_final') and not native and not renderer and source_matches
            and ((record['status']=='succeeded' and result.get('status')=='succeeded' and artifacts and all(a['hash_matches'] for a in artifacts))
                 or (record['status']=='cancelled' and result.get('status')=='cancelled' and record.get('process_exit_confirmed') is True and child!='alive')))
        heartbeat=IdleTransport(self.settings).state()
        transport=native.get('transport') if native and isinstance(native.get('transport'),dict) else {}
        script=self.settings.contained_path(f'jobs/{identifier}/operation.jsx')
        safe_read_release=bool(record['action'] in ('inspect','design_fonts','dependencies_inspect')
            and record.get('lifecycle_version')==1 and owner=='dead' and pending and ack_info and not ack_error
            and native and native.get('operation_id')==identifier and heartbeat and not heartbeat.get('active_job')
            and heartbeat.get('time_ms',0)>=int(ackpath.stat().st_mtime*1000)
            and heartbeat.get('instance_id')==transport.get('instance_id')
            and not self.settings.contained_path('bridge/inbox.txt').exists()
            and record.get('dispatch_intent') is True and script.is_file()
            and digest(script)==record.get('script_sha256')
            and not renderer)
        return dict(job_id=identifier,action=record['action'],journal_status=record['status'],journal_sha256=sha,
            state=state,stage=record.get('stage'),owner_state=owner,owner=record.get('owner'),child_state=child,
            native_ack=ack_info,native_ack_error=ack_error,ae_quarantine=pending,render_quarantine=render_pending,
            native_result_evidence_sha256=(ack_info or {}).get('result_evidence_sha256'),
            claim=claim,safe_release_unstarted=safe_release,safe_release_completed=safe_completed_release,
            safe_release_acknowledged_read=safe_read_release,artifacts=artifacts,source_hash_matches=source_matches,
            dispatch_intent=record.get('dispatch_intent',False),native_acknowledged=ack_info is not None,
            process_exit_confirmed=record.get('process_exit_confirmed'),process_returncode=record.get('process_returncode'),
            diagnostic_error=result.get('error') or record.get('error'),
            verification_scope='Recorded acknowledgement/hash checks only; no new semantic acceptance, decode, promotion or replay.',
            cancel_requested=(directory/'cancel-requested').exists(),automatic_retry_allowed=False)

    def reconcile(self,request):
        registry=RenderRegistry(self.settings)
        if request.mode=='release_acknowledged_read':
            # The mutex excludes another publisher while matching the exact
            # late read acknowledgement and archiving its retained marker.
            with AELock():
                data=self.inspect_job(request.operation_id,persist_native=True)
                if data['journal_sha256']!=request.expected_journal_sha256:raise ValueError('Job journal hash conflict')
                if not data['safe_release_acknowledged_read']:raise ValueError('Only a hash-pinned acknowledged read with exited owner and matching idle bridge can release AE quarantine')
                marker=self._marker('ae-pending.json')
                pending=self.settings.contained_path('ae-pending.json')
                raw=pending.read_bytes()
                if len(raw)>65536 or digest(pending)!=marker['marker_sha256']:raise ValueError('AE marker changed; no release')
                archive=self.settings.contained_path(f'jobs/{request.operation_id}/ae-pending-released-{marker["marker_sha256"]}.json')
                try:
                    with archive.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
                except FileExistsError:
                    if digest(archive)!=marker['marker_sha256']:raise ValueError('Archived marker conflict')
                if digest(archive)!=marker['marker_sha256']:raise ValueError('Archived marker bytes changed')
                data.update(state='readonly_quarantine_released',released=True,archived_marker=marker,
                    archived_marker_path=str(archive),safe_release_acknowledged_read=False)
                ref=store_evidence(self.settings,'JobReconciliation',data)
                pointer=self.settings.contained_path(f'reconciliations/{request.operation_id}.json');pointer.parent.mkdir(parents=True,exist_ok=True)
                write_json(pointer,{'sha256':ref.sha256})
                if digest(pending)!=marker['marker_sha256']:raise ValueError('AE marker changed; no release')
                pending.unlink()  # Known completed read only. Never a mutation/render marker.
        elif request.mode in ('release_unstarted','release_completed'):
            with registry.lock():
                data=self.inspect_job(request.operation_id,persist_native=True)
                if data['journal_sha256']!=request.expected_journal_sha256:raise ValueError('Job journal hash conflict')
                key='safe_release_unstarted' if request.mode=='release_unstarted' else 'safe_release_completed'
                if not data[key]:raise ValueError('Job does not prove safe slot release in the requested mode; quarantine retained')
                claim=data['claim'];claim.update(released=True,release_reason='reconciled_never_started' if request.mode=='release_unstarted' else 'reconciled_completed',released_at=timestamp(),reconciled_journal_sha256=data['journal_sha256'])
                write_json(registry.path(request.operation_id),claim)
                data.update(state='not_started_released' if request.mode=='release_unstarted' else 'completed_slot_released',safe_release_unstarted=False,safe_release_completed=False,released=True)
                ref=store_evidence(self.settings,'JobReconciliation',data)
                pointer=self.settings.contained_path(f'reconciliations/{request.operation_id}.json');pointer.parent.mkdir(parents=True,exist_ok=True)
                write_json(pointer,{'sha256':ref.sha256})
        else:
            data=self.inspect_job(request.operation_id,persist_native=True);ref=store_evidence(self.settings,'JobReconciliation',data)
        return self._result('job_reconcile',data|{'reconciliation_sha256':ref.sha256})

    def queue(self,request):
        registry=RenderRegistry(self.settings)
        with registry.lock():claims=registry.claims()
        active=[c for c in claims if not c.get('released')]
        identifiers={c['job_id'] for c in active}
        for name,key in [('ae-pending.json','operation_id'),('preview-pending.json','job_id')]:
            marker=self._marker(name)
            if marker and isinstance(marker.get(key),str) and re.fullmatch('[0-9a-f]{32}',marker[key]):identifiers.add(marker[key])
        if request.scope=='all':
            root=self.settings.contained_path('jobs')
            identifiers={p.name for p in root.iterdir() if p.is_dir() and re.fullmatch('[0-9a-f]{32}',p.name)} if root.exists() else set()
        ids=sorted(identifiers)
        if len(ids)>100000:raise ValueError('Job inventory exceeds diagnostic limit')
        jobs=[]
        for identifier in ids[request.offset:request.offset+request.limit]:
            try:jobs.append(self.inspect_job(identifier))
            except (OSError,ValueError,KeyError,TypeError) as exc:jobs.append({'job_id':identifier,'state':'invalid_record','error':str(exc)})
        ae=discover_ae(self.settings.ae_executable)
        bridge=self.bridge()
        return self._result('queue_inspect',dict(jobs=jobs,total=len(ids),offset=request.offset,
            next_offset=request.offset+len(jobs) if request.offset+len(jobs)<len(ids) else None,
            capacity=4,outstanding_claims=len(active),queue_full=len(active)>=4,bridge=bridge,
            bridge_ready=bridge['ready'],bootstrap_script_path=bridge['bootstrap_script'],next_action=bridge['manual_reactivation'],
            diagnostics=[{'component':'bridge',**bridge}],
            disk_free_bytes=shutil.disk_usage(self.settings.workspace).free,ae_executable_available=ae.available,
            ae_discovery_error=ae.error,process_liveness_scope='OS process identity, not worker responsiveness or AE execution proof'))

    def dependencies(self,request):
        manifest,source=self.projects.load(request.project_id)
        saved=read_json(source.parent/('version.json' if manifest.get('current_version') else 'project.json'))
        if digest(source)!=saved['sha256']:raise ValueError('Saved project hash conflict')
        if request.refresh:
            result=self.projects.runner.run('dependencies_inspect',{'project_path':source.as_posix(),'id_map':manifest.get('id_map')})
            if result.status!='succeeded':return result
            if Path(result.data['inspection']['project_path']).resolve()!=source.resolve():raise ValueError('Dependency read returned wrong active project')
            deps=result.data['dependencies'];scope='acknowledged_live_read'
            operation=result.operation_id
            dirty=result.data['inspection']['project_dirty']
        else:
            state=saved['result']['data'];fonts={};plugins={};unsupported=[]
            for comp in state['compositions']:
                for layer in comp['layers']:
                    style=layer.get('text_style') or {}
                    if style.get('font'):fonts[style['font']]={'postscript_name':style['font'],'available':not style.get('font_missing',False),'scope':'saved_substitution_state'}
                    if style.get('styles_truncated'):unsupported.append('uninspected_text_styles:'+str(layer.get('ae_id')))
                    for run in style.get('style_runs',[]):
                        name=run['style'].get('font')
                        if name and name not in fonts:fonts[name]={'postscript_name':name,'available':None,'scope':'saved_style_name_only; refresh to check installed font'}
                    for effect in layer.get('effects',[]):plugins[effect['match_name']]={'match_name':effect['match_name'],
                        'availability':'native_dependency' if effect['match_name'].startswith('ADBE ') else 'not_verified'}
            deps={'files':state.get('footage',[]),'fonts':list(fonts.values()),'plugins':list(plugins.values()),'unsupported':unsupported}
            scope='saved_metadata_plus_current_filesystem';operation=None;dirty=None
        media=[]
        for file in deps['files']:
            item=dict(file)
            try:item['exists_now']=Path(file['path']).is_file()
            except OSError:item['exists_now']=False
            media.append(item)
        missing=[{'kind':'media','path':m['path']} for m in media if m.get('missing') or not m['exists_now']]
        missing += [{'kind':'font' if f.get('available') is False else 'font_unverified','name':f['postscript_name']} for f in deps['fonts'] if f.get('available') is not True]
        missing += [{'kind':'plugin_unverified','name':p['match_name']} for p in deps['plugins'] if p.get('availability')=='not_verified']
        if digest(source)!=saved['sha256']:raise ValueError('AEP changed during dependency inspection')
        if request.refresh:
            result.project_id,result.project_path=request.project_id,str(source)
            self.projects._finalize_job(result)
        return self._result('project_dependencies',dict(source_sha256=saved['sha256'],scope=scope,
            project_dirty=dirty,unsaved_changes_included=bool(request.refresh and dirty),
            native_operation_id=operation,media=media,fonts=deps['fonts'],plugins=deps['plugins'],issues=missing,
            unsupported=deps.get('unsupported',[]),automatic_install_or_relink=False),request.project_id)

    def cleanup(self,request):
        candidates=[];protected=[]
        quarantine=bool(self._marker('ae-pending.json') or self._marker('preview-pending.json'))
        for identifier in dict.fromkeys(request.operation_ids):
            data=self.inspect_job(identifier)
            # Even a plan never guesses ownership of old/orphan/unresolved artifacts.
            if quarantine or data['journal_status']!='succeeded' or data['owner_state']=='unknown' or data['state'] not in ('recorded_terminal','service_verified_recorded'):
                protected.append({'job_id':identifier,'reason':'not a verified terminal job or quarantine/ownership unresolved'});continue
            directory=self.settings.contained_path('jobs/'+identifier)
            for path in directory.iterdir():
                if not re.fullmatch(r'(job|result|worker-failure)\.json\.[0-9a-f]{32}\.tmp',path.name):continue
                checked=self.settings.contained_path(f'jobs/{identifier}/{path.name}')
                if path.is_symlink() or checked.parent!=directory or checked.name!=path.name:continue
                if not checked.is_file() or time.time()-checked.stat().st_mtime<request.minimum_age_hours*3600:continue
                if checked.stat().st_nlink!=1:continue
                if checked.stat().st_size>16*1024*1024:continue
                candidates.append({'job_id':identifier,'path':str(checked),'bytes':checked.stat().st_size,'sha256':digest(checked),
                    'reason':'old atomic JSON staging file in owned completed job'})
                if len(candidates)>2000:raise ValueError('Cleanup plan exceeds 2000-file bound; narrow job selection')
        plan={'schema_version':1,'candidates':candidates,'protected':protected,'total_bytes':sum(c['bytes'] for c in candidates),
            'deletion_performed':False,'apply_tool_available':False,
            'retained':['all AEPs/snapshots','native evidence/acknowledgements','journals/logs','renders/frames/audio','unknown or unresolved outputs']}
        ref=store_evidence(self.settings,'WorkspaceCleanupPlan',plan)
        return self._result('workspace_cleanup_plan',plan|{'cleanup_plan_sha256':ref.sha256})
