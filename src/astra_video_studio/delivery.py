"""Owned delivery packages with acknowledged AE relink/reopen and complete file hashes."""
import copy
import json
import os
from pathlib import Path, PureWindowsPath
import shutil

from pydantic import Field

from astra_video_studio.audio import AudioService, AudioTarget, SHA
from astra_video_studio.config import _containment_key
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import Job
from astra_video_studio.media import audio as media
from astra_video_studio.media.final_render import destination_path
from astra_video_studio.media.preview import verify_probe
from astra_video_studio.motion_engine.schemas import StrictModel
from astra_video_studio.project_manager import ProjectManager
from astra_video_studio.scene_editing import ID
from astra_video_studio.schemas import OperationResult

MEDIA_SUFFIXES={'.png','.jpg','.jpeg','.tif','.tiff','.mp4','.mov','.wav','.mp3','.aif','.aiff','.webm','.flac','.m4a','.ogg'}


class DeliveryCollect(StrictModel):
    project_id: ID
    base_aep_sha256: SHA
    render_job_id: ID
    destination: str = Field(min_length=1,max_length=240)


class DeliveryValidate(StrictModel):
    delivery_id: ID


def package_file(settings, directory, relative):
    if Path(relative).is_absolute() or PureWindowsPath(relative).drive:
        raise ValueError('Package files must use relative paths')
    checked=settings.contained_path(str((directory/relative).relative_to(settings.workspace)))
    if not _containment_key(checked).is_relative_to(_containment_key(directory.resolve())):
        raise ValueError('Package file escapes delivery directory')
    return checked


def exclusive_json(path, value):
    with path.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=True,indent=2,allow_nan=False)
        stream.flush();os.fsync(stream.fileno())


class NativeFailure(Exception):
    def __init__(self, result):
        self.result=result
        super().__init__(result.error or 'Native package operation did not succeed')


class DeliveryService:
    def __init__(self,settings):
        self.settings=settings
        self.projects=ProjectManager(settings)

    def _native(self,action,path,mapping,relinks=None):
        if self.settings.contained_path('preview-pending.json').exists():
            raise BlockingIOError('Native renderer active or unresolved; package inspection waits without clearing quarantine')
        result=self.projects.runner.run(action,{'project_path':path.as_posix(),'source_path':path.as_posix(),
            'managed_paths':self.projects.managed_paths(),'id_map':mapping,'relinks':relinks or []})
        if result.status!='succeeded': raise NativeFailure(result)
        if not result.data.get('reopened'): raise ValueError('Missing native package reopen confirmation')
        if result.data['before']['compositions']!=result.data['after']['compositions']:
            raise ValueError('Package non-target state mismatch')
        return result

    @staticmethod
    def _dependencies(deps):
        issues=list(deps.get('unsupported',[]))
        issues += ['missing_media:'+str(f['ae_id']) for f in deps['files'] if f.get('missing')]
        issues += ['missing_font:'+f['postscript_name'] for f in deps['fonts'] if not f.get('available')]
        if issues: raise ValueError('Uncollected/unsupported dependencies: '+', '.join(issues[:8]))

    def _copy(self,source,target,expected=None):
        before=digest(source)
        if expected is not None and before!=expected: raise ValueError('Delivery source hash changed')
        if target.exists(): raise ValueError('Delivery target already exists')
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        if digest(source)!=before or digest(target)!=before: raise ValueError('Delivery copy integrity mismatch')

    def _render(self,job_id,source_sha,project_id):
        record=self.projects.job_status(job_id)
        if record.get('action')!='render_final' or record.get('status')!='succeeded':
            raise ValueError('Delivery requires a completed verified final-render job')
        result=record['result']
        if result['status']!='succeeded' or result['project_id']!=project_id or result['data']['source_sha256']!=source_sha:
            raise ValueError('Render/project/source mismatch')
        return record,result['data']

    def collect(self,request):
        manifest,source=self.projects.load(request.project_id)
        saved=json.loads((source.parent/'version.json').read_text(encoding='utf-8')) if manifest.get('current_version') else manifest
        if digest(source)!=request.base_aep_sha256 or saved['sha256']!=request.base_aep_sha256:
            raise ValueError('Delivery base AEP conflict')
        _,render=self._render(request.render_job_id,request.base_aep_sha256,request.project_id)
        directory=destination_path(self.settings,request.destination)
        job=Job(self.settings,'delivery_collect')
        result=OperationResult(operation_id=job.id,status='failed',project_id=request.project_id,project_path=str(source))
        try:
            snapshot=job.directory/'source-snapshot.aep';self._copy(source,snapshot,request.base_aep_sha256)
            inspected_copy=job.directory/'dependency-copy.aep';self._copy(source,inspected_copy,request.base_aep_sha256)
            inspected=self._native('delivery_inspect',inspected_copy,manifest.get('id_map'))
            deps=inspected.data['dependencies']
            result.data={'dependencies':deps,'native_inspection_operation_id':inspected.operation_id,'ready_for_delivery':False}
            self._dependencies(deps)
            directory.mkdir(parents=True,exist_ok=False)
            aep=directory/'project.aep';self._copy(source,aep,request.base_aep_sha256)
            relinks=[]
            for item in deps['files']:
                approved=self.settings.read_path(item['path'],MEDIA_SUFFIXES)
                target=directory/'media'/(str(item['ae_id'])+approved.suffix.lower())
                self._copy(approved,target)
                relinks.append({'ae_id':item['ae_id'],'old_path':item['path'],'new_path':target.as_posix()})
            if render['preset']=='h264_aac':
                video=self.settings.contained_path(str(Path(render['video_path']).relative_to(self.settings.workspace)))
                self._copy(video,directory/'render/final.mp4',render['video_sha256'])
            else:
                sequence=self.settings.contained_path(str(Path(render['sequence_manifest_path']).relative_to(self.settings.workspace)))
                if digest(sequence)!=render['sequence_manifest_sha256']: raise ValueError('Sequence manifest changed')
                seq=json.loads(sequence.read_text(encoding='utf-8'))
                self._copy(sequence,directory/'render/sequence.json',render['sequence_manifest_sha256'])
                for f in seq['frames']:
                    source_frame=package_file(self.settings,sequence.parent,'frames/'+f['path'])
                    self._copy(source_frame,directory/'render/frames'/f['path'],f['sha256'])
            audio_package=None
            if render.get('audio_state_sha256'):
                target=AudioTarget(project_id=request.project_id,composition_id=render['ae_preparation'].get('composition_id',
                    self.projects.job_status(request.render_job_id)['request']['composition_id']),
                    base_aep_sha256=request.base_aep_sha256,audio_state_sha256=render['audio_state_sha256'])
                audio_service=AudioService(self.settings)
                _,_,state=audio_service.state(target)
                assets=audio_service.assets(state)
                audio_package={'schema_version':1,'kind':'delivery_audio_v1','original_audio_state_sha256':render['audio_state_sha256'],
                    'source_aep_sha256':request.base_aep_sha256,'audio_state':state,'assets':[]}
                for aid,asset in assets.items():
                    for filename,sha in [('source'+asset['suffix'],asset['source_sha256']),('analysis.wav',asset['pcm_sha256'])]:
                        audio_source=self.settings.contained_path(f'audio/assets/{aid}/{filename}')
                        self._copy(audio_source,directory/f'audio/{aid}/{filename}',sha)
                    audio_package['assets'].append({'asset_id':aid,'source_path':f'audio/{aid}/source'+asset['suffix'],
                        'pcm_path':f'audio/{aid}/analysis.wav','source_sha256':asset['source_sha256'],'pcm_sha256':asset['pcm_sha256'],
                        'sample_count':asset['sample_count'],'sample_rate':asset['sample_rate'],'channels':asset['channels']})
                mix=self.settings.contained_path(f'jobs/{request.render_job_id}/audio-mix.wav')
                self._copy(mix,directory/'audio/mix.wav',render.get('audio_mix_sha256'))
                exclusive_json(directory/'audio/plan.json',audio_package)
            collected=self._native('delivery_collect',aep,manifest.get('id_map'),relinks)
            after=collected.data
            self._dependencies(after['dependencies'])
            if inspected.data['after']['compositions']!=after['after']['compositions']:
                raise ValueError('Collected scene differs from inspected source')
            if len(after['dependencies']['files'])!=len(relinks): raise ValueError('Package footage count differs')
            by_id={r['ae_id']:r for r in relinks}
            for f in after['dependencies']['files']:
                if f['ae_id'] not in by_id or Path(f['path']).resolve()!=Path(by_id[f['ae_id']]['new_path']).resolve():
                    raise ValueError('Package media still links outside collected paths')
            if digest(source)!=request.base_aep_sha256: raise ValueError('Original source changed during collection')
            files=[{'path':p.relative_to(directory).as_posix(),'sha256':digest(p),'bytes':p.stat().st_size}
                for p in sorted(directory.rglob('*')) if p.is_file()]
            package={'schema_version':1,'delivery_id':job.id,'project_id':request.project_id,'source_aep_sha256':request.base_aep_sha256,
                'project_sha256':digest(aep),'project_path':'project.aep','render_job_id':request.render_job_id,
                'preset':render['preset'],'plan':render['plan'],'verification':render['verification'],
                'fonts':after['dependencies']['fonts'],'plugins':after['dependencies']['plugins'],
                'source_color':after['dependencies']['source_color'],'native_dependencies':after['dependencies']['files'],
                'id_map':manifest.get('id_map'),
                'packaged_compositions':after['after']['compositions'],'audio_sidecar':'audio/plan.json' if audio_package else None,
                'uncollected':[],'files':files,'native_reopen_operation_id':collected.operation_id,
                'human_playback':False,'artistic_approval':False}
            exclusive_json(directory/'manifest.json',package)
            index=self.settings.contained_path(f'deliveries/{job.id}.json');index.parent.mkdir(parents=True,exist_ok=True)
            exclusive_json(index,{'directory':str(directory),'manifest_sha256':digest(directory/'manifest.json')})
            result.status='succeeded'
            result.data.update(delivery_id=job.id,delivery_path=str(directory),manifest_sha256=digest(directory/'manifest.json'),
                packaged_project_sha256=digest(aep),ready_for_delivery=True,files_count=len(files),
                native_reopen_operation_id=collected.operation_id,fonts=package['fonts'],plugins=package['plugins'],
                limitations='Audio remains a separate portable sidecar; fonts/plugins are listed, not redistributed. Validate on the target machine.')
            result.artifacts=[str(directory/'manifest.json'),str(aep),str(snapshot)]
        except NativeFailure as exc:
            result.status=exc.result.status;result.error=str(exc);result.data['native_operation_id']=exc.result.operation_id
        except BlockingIOError as exc:
            result.status='blocked';result.error=str(exc)
        except Exception as exc:
            result.error=f'{type(exc).__name__}: {exc}'
        job.record(result.status,result=result.model_dump(mode='json'),request=request.model_dump(mode='json'))
        return result

    def validate(self,request):
        index=json.loads(self.settings.contained_path(f'deliveries/{request.delivery_id}.json').read_text(encoding='utf-8'))
        directory=self.settings.contained_path(str(Path(index['directory']).relative_to(self.settings.workspace)))
        path=directory/'manifest.json'
        if digest(path)!=index['manifest_sha256']: raise ValueError('Delivery manifest integrity failure')
        package=json.loads(path.read_text(encoding='utf-8'))
        if package.get('schema_version')!=1 or package.get('delivery_id')!=request.delivery_id:
            raise ValueError('Delivery identity/schema mismatch')
        listed=set()
        for item in package['files']:
            p=package_file(self.settings,directory,item['path'])
            if item['path'] in listed or not p.is_file() or p.stat().st_size!=item['bytes'] or digest(p)!=item['sha256']:
                raise ValueError('Delivery file identity/size/hash mismatch')
            listed.add(item['path'])
        actual={p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file() and p!=path}
        if actual!=listed: raise ValueError('Unexpected or missing package files')
        job=Job(self.settings,'delivery_validate')
        result=OperationResult(operation_id=job.id,status='failed',project_id=package['project_id'])
        try:
            aep=package_file(self.settings,directory,package['project_path'])
            if digest(aep)!=package['project_sha256']: raise ValueError('Packaged AEP changed')
            native=self._native('delivery_validate',aep,package.get('id_map'))
            self._dependencies(native.data['dependencies'])
            if native.data['after']['compositions']!=package['packaged_compositions']:
                raise ValueError('Reopened package scene changed')
            for media_file in native.data['dependencies']['files']:
                checked=self.settings.contained_path(str(Path(media_file['path']).relative_to(self.settings.workspace)))
                if not _containment_key(checked).is_relative_to(_containment_key(directory.resolve())):
                    raise ValueError('Reopened package links outside delivery')
                if checked.relative_to(directory).as_posix() not in listed: raise ValueError('Unmanifested package media')
            ffmpeg,ffprobe=media.binaries(self.settings)
            if package['preset']=='h264_aac':
                video=directory/'render/final.mp4'
                media.run([ffprobe,'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(video)],job.directory/'probe.json')
                probe=json.loads((job.directory/'probe.json').read_text(encoding='utf-8-sig'))
                verified=verify_probe(probe,package['plan'])
                audio_verified=media.verify_audio_probe(probe,package['plan']['duration'],package['plan']['fps'])
                media.run([ffmpeg,'-nostdin','-v','error','-xerror','-i',str(video),'-map','0:v:0','-map','0:a:0','-f','null','-'],job.directory/'decode.log',180)
                decoded=job.directory/'decoded.wav';media.decode(ffmpeg,video,decoded,job.directory/'audio-decode.log')
                peak=media.analyze_pcm(decoded)
                if peak['peak_linear']>10**(-0.1/20): raise ValueError('Packaged AAC peak exceeds ceiling')
            else:
                seq=json.loads((directory/'render/sequence.json').read_text(encoding='utf-8'))
                from astra_video_studio.media.preview import frame_sequence
                first,pattern=frame_sequence(directory/'render/frames',package['plan']['frame_count'])
                media.run([ffmpeg,'-nostdin','-v','error','-xerror','-framerate',str(package['plan']['fps']),'-start_number',str(first),
                    '-i',pattern,'-f','null','-'],job.directory/'decode.log',180)
                verified={'sequence_frames':len(seq['frames']),'alpha_verified_at_render':seq['alpha_verified']};audio_verified=None
            if package['audio_sidecar']:
                audio=json.loads(package_file(self.settings,directory,package['audio_sidecar']).read_text(encoding='utf-8'))
                packaged_assets={}
                for asset in audio['assets']:
                    if digest(package_file(self.settings,directory,asset['source_path']))!=asset['source_sha256'] or digest(package_file(self.settings,directory,asset['pcm_path']))!=asset['pcm_sha256']:
                        raise ValueError('Packaged audio asset mismatch')
                    packaged_assets[asset['asset_id']]={'pcm_path':str(package_file(self.settings,directory,asset['pcm_path']))}
                from astra_video_studio.motion_engine.timeline import frame
                start=frame(package['plan']['start_time'],package['plan']['fps'])
                rebuilt=job.directory/'rebuilt-audio.wav'
                media.run(media.mix_command(ffmpeg,audio['audio_state'],packaged_assets,start,
                    package['plan']['frame_count'],rebuilt),job.directory/'audio-rebuild.log')
                if digest(rebuilt)!=digest(package_file(self.settings,directory,'audio/mix.wav')):
                    raise ValueError('Packaged audio recipe does not reproduce the delivered PCM on this toolchain')
            # Native validation is read-only; file hashes must still match after reopen/decode.
            if any(digest(package_file(self.settings,directory,f['path']))!=f['sha256'] for f in package['files']):
                raise ValueError('Package changed during validation')
            result.status='succeeded';result.data={'delivery_id':request.delivery_id,'ready_for_delivery':True,
                'files_count':len(listed),'verification':verified,'audio_verification':audio_verified,
                'audio_sidecar_rebuild_verified':bool(package['audio_sidecar']),
                'native_reopen_operation_id':native.operation_id,'fonts':native.data['dependencies']['fonts'],
                'plugins':native.data['dependencies']['plugins'],'human_playback':False,'artistic_approval':False}
            result.artifacts=[str(path),str(job.directory)]
        except NativeFailure as exc:
            result.status=exc.result.status;result.error=str(exc);result.data['native_operation_id']=exc.result.operation_id
        except BlockingIOError as exc:
            result.status='blocked';result.error=str(exc)
        except Exception as exc: result.error=f'{type(exc).__name__}: {exc}'
        job.record(result.status,result=result.model_dump(mode='json'),request=request.model_dump(mode='json'))
        return result
