"""Immutable FFmpeg audio sidecars bound to verified saved AEPs; never edits AE."""
import copy
import json
import math
from pathlib import Path
import shutil
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field, model_validator

from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import Job, write_json
from astra_video_studio.media import audio as media
from astra_video_studio.motion_engine.schemas import StrictModel
from astra_video_studio.motion_engine.timeline import frame
from astra_video_studio.project_manager import ProjectManager
from astra_video_studio.responses import store_evidence
from astra_video_studio.scene_editing import ID
from astra_video_studio.schemas import OperationResult

SHA = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
AUDIO_SUFFIXES = {'.wav', '.mp3', '.aif', '.aiff', '.flac', '.m4a', '.ogg'}


class AudioInspect(StrictModel):
    source_path: str = Field(min_length=1, max_length=32767)


class AudioTarget(StrictModel):
    project_id: ID
    composition_id: ID
    base_aep_sha256: SHA
    audio_state_sha256: SHA | None = None


class ClipSpec(StrictModel):
    asset_id: ID
    start_frame: int = Field(default=0, ge=0, le=36000)
    duration_frames: int = Field(gt=0, le=36000)
    source_start_sample: int = Field(default=0, ge=0, le=media.MAX_SECONDS*media.RATE)
    gain_db: float = Field(default=0, ge=-60, le=12)
    fade_in_frames: int = Field(default=0, ge=0, le=36000)
    fade_out_frames: int = Field(default=0, ge=0, le=36000)

    @model_validator(mode='after')
    def fades(self):
        if self.fade_in_frames+self.fade_out_frames > self.duration_frames:
            raise ValueError('Audio fades overlap or exceed clip duration')
        return self


class AudioClipSet(AudioTarget):
    mode: Literal['add', 'replace', 'remove'] = 'add'
    clip_id: ID | None = None
    clip: ClipSpec | None = None

    @model_validator(mode='after')
    def scope(self):
        if (self.mode == 'add') != (self.clip_id is None):
            raise ValueError('Add generates an ID; replace/remove require an existing clip ID')
        if (self.mode == 'remove') != (self.clip is None):
            raise ValueError('Remove has no clip; add/replace require a clip')
        return self


class SourceMarker(StrictModel):
    sample: int = Field(ge=0, le=media.MAX_SECONDS*media.RATE)
    label: str = Field(default='Cue', min_length=1, max_length=120)


class AudioMarkersCreate(StrictModel):
    asset_id: ID
    method: Literal['manual', 'energy'] = 'manual'
    markers: list[SourceMarker] = Field(default_factory=list, max_length=256)

    @model_validator(mode='after')
    def method_inputs(self):
        if self.method == 'energy' and self.markers: raise ValueError('Energy analysis does not accept manual markers')
        if self.method == 'manual' and not self.markers: raise ValueError('Manual markers cannot be empty')
        return self


class TimelineMarker(StrictModel):
    marker_id: ID
    frame: int = Field(ge=0, le=36000)
    label: str = Field(min_length=1, max_length=120)


class TimelineMarkersSet(AudioTarget):
    mode: Literal['append', 'replace_all'] = 'append'
    markers: list[TimelineMarker] = Field(max_length=256)


class SyncBinding(StrictModel):
    clip_id: ID
    marker_set_sha256: SHA
    source_marker_id: ID
    layer_id: ID
    property: Literal['position', 'anchor', 'scale', 'rotation', 'opacity']
    key_index: int = Field(ge=0, le=10000)


class AudioSyncPlan(AudioTarget):
    audio_state_sha256: SHA
    bindings: list[SyncBinding] = Field(min_length=1, max_length=32)


class AudioService:
    def __init__(self, settings):
        self.settings = settings
        self.projects = ProjectManager(settings)

    def _read(self, sha, kind):
        if len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
            raise ValueError('Invalid audio evidence hash')
        path = self.settings.contained_path(f'responses/{sha}.json')
        if digest(path) != sha: raise ValueError('Audio evidence hash changed')
        record = json.loads(path.read_text(encoding='utf-8'))
        if record.get('kind') != kind or record.get('schema_version') != 1:
            raise ValueError('Wrong audio evidence kind/schema')
        return record['result']

    def _asset(self, asset_id, expected_manifest=None):
        # IDs are always validated, including values recovered from stored evidence.
        from astra_video_studio.project_manager import valid_id
        directory = self.settings.contained_path(f'audio/assets/{valid_id(asset_id)}')
        metadata = directory/'asset.json'
        if expected_manifest is not None and digest(metadata) != expected_manifest:
            raise ValueError('Audio asset manifest changed')
        value = json.loads(metadata.read_text(encoding='utf-8'))
        if value['asset_id'] != asset_id or value['suffix'] not in AUDIO_SUFFIXES:
            raise ValueError('Invalid audio asset')
        original = self.settings.contained_path(f'audio/assets/{asset_id}/source{value["suffix"]}')
        pcm = self.settings.contained_path(f'audio/assets/{asset_id}/analysis.wav')
        if digest(original) != value['source_sha256'] or digest(pcm) != value['pcm_sha256']:
            raise ValueError('Owned audio source/PCM changed')
        return value | {'manifest_sha256': digest(metadata), 'pcm_path': str(pcm)}

    def inspect(self, request):
        source = self.settings.read_path(request.source_path, AUDIO_SUFFIXES)
        if source.stat().st_size > 250*1024*1024: raise ValueError('Audio import exceeds 250 MiB')
        ffmpeg, ffprobe = media.binaries(self.settings)
        job = Job(self.settings, 'audio_inspect')
        result = OperationResult(operation_id=job.id, status='failed')
        try:
            asset_id = uuid4().hex
            directory = self.settings.contained_path(f'audio/assets/{asset_id}')
            directory.mkdir(parents=True, exist_ok=False)
            source_sha = digest(source)
            owned = directory/('source'+source.suffix.lower())
            shutil.copyfile(source, owned)
            if digest(owned) != source_sha or digest(source) != source_sha:
                raise ValueError('Audio source changed while copying')
            info = media.probe(ffprobe, owned, job.directory/'probe.log')
            streams = [s for s in info.get('streams', []) if s.get('codec_type') == 'audio']
            if len(streams) != 1 or any(s.get('codec_type') == 'video' for s in info.get('streams', [])):
                raise ValueError('Import requires a single audio stream and no video')
            duration = float(streams[0].get('duration', info.get('format', {}).get('duration', 'nan')))
            if not math.isfinite(duration) or not 0 < duration <= media.MAX_SECONDS:
                raise ValueError('Audio duration is missing or outside 0..300 seconds')
            pcm = directory/'analysis.wav'
            media.decode(ffmpeg, owned, pcm, job.directory/'decode.log')
            analysis = media.analyze_pcm(pcm)
            if digest(owned) != source_sha: raise ValueError('Owned source changed during analysis')
            value = analysis | {'asset_id': asset_id, 'source_sha256': source_sha, 'pcm_sha256': digest(pcm),
                'suffix': owned.suffix, 'source_sample_rate': int(streams[0]['sample_rate']),
                'source_channels': streams[0]['channels'], 'source_codec': streams[0]['codec_name']}
            write_json(directory/'asset.json', value)
            result.status = 'succeeded'
            result.data = {k:v for k,v in value.items() if k != 'energy_onsets'} | {
                'energy_onset_count': len(value['energy_onsets']), 'audio_backend': 'ffmpeg_postproduction'}
            result.artifacts = [str(directory/'asset.json'), str(pcm)]
        except Exception as exc:
            result.error = f'{type(exc).__name__}: {exc}'
        job.record(result.status, result=result.model_dump(mode='json'))
        return result

    def _project(self, request):
        manifest, source = self.projects.load(request.project_id)
        saved = json.loads((source.parent/'version.json').read_text(encoding='utf-8')) if manifest.get('current_version') else manifest
        if digest(source) != request.base_aep_sha256 or saved['sha256'] != request.base_aep_sha256:
            raise ValueError('Audio base AEP conflict; source must be the verified saved version')
        comps = [c for c in saved['result']['data']['compositions'] if c['composition_id'] == 'astra:composition:'+request.composition_id]
        if len(comps) != 1: raise ValueError('Audio composition absent/ambiguous')
        return source, comps[0]

    def state(self, request):
        source, comp = self._project(request)
        if request.audio_state_sha256:
            state = self._read(request.audio_state_sha256, 'AudioState')
            for key in ('project_id', 'composition_id', 'base_aep_sha256'):
                if state[key] != getattr(request, key): raise ValueError('Audio state belongs to another source/composition')
            if state['fps'] != comp['fps'] or state['duration_frames'] != frame(comp['duration'], comp['fps']):
                raise ValueError('Audio composition timing changed')
        else:
            state = {'schema_version': 1, 'project_id': request.project_id, 'composition_id': request.composition_id,
                'base_aep_sha256': request.base_aep_sha256, 'fps': comp['fps'], 'duration_frames': frame(comp['duration'], comp['fps']),
                'audio_clips': [], 'audio_markers': [], 'audio_backend': 'ffmpeg_postproduction',
                'provenance': 'verified_saved_AEP; excludes unsaved AE edits'}
        return source, comp, copy.deepcopy(state)

    @staticmethod
    def _check_clip(clip, state, asset):
        ClipSpec.model_validate({k:v for k,v in clip.items() if k not in ('clip_id', 'asset_manifest_sha256')})
        if clip['start_frame']+clip['duration_frames'] > state['duration_frames']:
            raise ValueError('Audio clip exceeds composition duration')
        if clip['source_start_sample']+media.sample_at_frame(clip['duration_frames'], state['fps']) > asset['sample_count']:
            raise ValueError('Audio trim exceeds source samples')

    def assets(self, state):
        if len(state['audio_clips']) > 16: raise ValueError('At most 16 audio clips per state')
        if len({c['clip_id'] for c in state['audio_clips']}) != len(state['audio_clips']):
            raise ValueError('Duplicate audio clip IDs')
        assets = {}
        for clip in state['audio_clips']:
            asset = self._asset(clip['asset_id'], clip['asset_manifest_sha256'])
            self._check_clip(clip, state, asset)
            assets[clip['asset_id']] = asset
        return assets

    def _commit(self, action, request, state, source, extra=None):
        self.assets(state)  # Conflicts/ranges/dependencies fail before snapshot or writes.
        job = Job(self.settings, action)
        result = OperationResult(operation_id=job.id, status='failed', project_id=request.project_id, project_path=str(source))
        try:
            snapshot = job.directory/'source-snapshot.aep'
            shutil.copyfile(source, snapshot)
            if digest(snapshot) != request.base_aep_sha256 or digest(source) != request.base_aep_sha256:
                raise ValueError('Audio source/snapshot conflict')
            state['parent_audio_state_sha256'] = request.audio_state_sha256
            reference = store_evidence(self.settings, 'AudioState', state)
            if digest(source) != request.base_aep_sha256: raise ValueError('AEP changed while saving audio sidecar')
            result.status = 'succeeded'
            result.data = state | {'audio_state_sha256': reference.sha256, 'audio_state_path': reference.path,
                'aep_modified': False, **(extra or {})}
            result.artifacts = [reference.path, str(snapshot)]
        except Exception as exc:
            result.error = f'{type(exc).__name__}: {exc}'
        job.record(result.status, request=request.model_dump(mode='json'), result=result.model_dump(mode='json'))
        return result

    def clip_set(self, request):
        source, comp, state = self.state(request)
        matches = [c for c in state['audio_clips'] if c['clip_id'] == request.clip_id]
        if request.mode != 'add' and len(matches) != 1: raise ValueError('Audio clip absent/ambiguous')
        clip_id = request.clip_id or uuid4().hex
        index = next((i for i,c in enumerate(state['audio_clips']) if c['clip_id'] == clip_id), None)
        if request.mode == 'remove': state['audio_clips'].pop(index)
        if request.clip:
            asset = self._asset(request.clip.asset_id)
            clip = request.clip.model_dump(mode='json') | {'clip_id': clip_id,
                'asset_manifest_sha256': asset['manifest_sha256']}
            if request.mode == 'replace': state['audio_clips'][index] = clip
            else: state['audio_clips'].append(clip)
        return self._commit('audio_clip_set', request, state, source, {'clip_id': clip_id})

    def markers_create(self, request):
        asset = self._asset(request.asset_id)
        raw = request.markers if request.method == 'manual' else asset['energy_onsets']
        markers = []
        for item in raw:
            value = item.model_dump() if isinstance(item, SourceMarker) else dict(item)
            if value['sample'] >= asset['sample_count']: raise ValueError('Audio marker outside source')
            markers.append(value | {'marker_id': uuid4().hex, 'confidence': value.get('confidence', 1.0),
                'label': value.get('label', 'Energy rise'), 'method': value.get('method', 'manual'),
                'uncertainty_samples': value.get('uncertainty_samples', 0)})
        job = Job(self.settings, 'audio_markers_create')
        data = {'asset_id': request.asset_id, 'asset_manifest_sha256': asset['manifest_sha256'],
            'sample_rate': media.RATE, 'audio_markers': markers, 'method': request.method}
        ref = store_evidence(self.settings, 'AudioMarkers', data)
        result = OperationResult(operation_id=job.id, status='succeeded', data=data | {'marker_set_sha256': ref.sha256}, artifacts=[ref.path])
        job.record('succeeded', result=result.model_dump(mode='json'))
        return result

    def timeline_set(self, request):
        source, comp, state = self.state(request)
        markers = [] if request.mode == 'replace_all' else state['audio_markers']
        markers += [m.model_dump(mode='json') for m in request.markers]
        if len(markers) > 256 or len({m['marker_id'] for m in markers}) != len(markers):
            raise ValueError('Too many or duplicate timeline markers')
        if any(m['frame'] >= state['duration_frames'] for m in markers): raise ValueError('Timeline marker outside composition')
        state['audio_markers'] = markers
        return self._commit('timeline_markers_set', request, state, source, {'marker_destination': 'audio_sidecar_not_AE'})

    def sync_plan(self, request):
        source, comp, state = self.state(request)
        changes, moved = [], {}
        for binding in request.bindings:
            clips = [c for c in state['audio_clips'] if c['clip_id'] == binding.clip_id]
            if len(clips) != 1: raise ValueError('Sync clip absent/ambiguous')
            clip = clips[0]
            markers = self._read(binding.marker_set_sha256, 'AudioMarkers')
            if markers['asset_id'] != clip['asset_id'] or markers['asset_manifest_sha256'] != clip['asset_manifest_sha256']:
                raise ValueError('Sync marker source changed/mismatched')
            matches = [m for m in markers['audio_markers'] if m['marker_id'] == binding.source_marker_id]
            if len(matches) != 1: raise ValueError('Sync source marker absent/ambiguous')
            marker = matches[0]
            offset = marker['sample']-clip['source_start_sample']
            if not 0 <= offset < media.sample_at_frame(clip['duration_frames'], state['fps']):
                raise ValueError('Sync marker is outside the retained clip')
            layers = [l for l in comp['layers'] if l['layer_id'] == 'astra:layer:'+binding.layer_id]
            if len(layers) != 1: raise ValueError('Sync visual layer absent/ambiguous')
            track = layers[0]['transforms'][binding.property]
            if track.get('expression_enabled') or track.get('expression_present'):
                raise ValueError('Sync cannot reference expression-driven tracks')
            if binding.key_index >= len(track.get('keys', [])): raise ValueError('Sync visual key absent')
            visual_frame = frame(track['keys'][binding.key_index]['time'], state['fps'])
            start = frame(visual_frame/state['fps']-offset/media.RATE, state['fps'])
            if binding.clip_id in moved and moved[binding.clip_id] != start:
                raise ValueError('Incompatible sync targets for the same clip')
            moved[binding.clip_id] = start
            clip['start_frame'] = start
            error = abs(start+offset*state['fps']/media.RATE-visual_frame)
            if start < 0 or error > 1: raise ValueError('Sync exceeds frame tolerance or starts before composition')
            changes.append(binding.model_dump(mode='json') | {'visual_frame': visual_frame, 'proposed_start_frame': start,
                'error_frames': error, 'detector_uncertainty_samples': marker.get('uncertainty_samples', 0)})
        return self._commit('audio_sync_plan', request, state, source,
            {'sync_events': changes, 'plan_only': True, 'native_keys_modified': False})

    def render(self, target, start_frame, count, directory):
        source, comp, state = self.state(target)
        if not state['audio_clips']: raise ValueError('Audio preview requires at least one clip')
        assets = self.assets(state)
        ffmpeg, _ = media.binaries(self.settings)
        wav = directory/'audio-mix.wav'
        media.run(media.mix_command(ffmpeg, state, assets, start_frame, count, wav), directory/'audio-mix.log')
        measured = media.analyze_pcm(wav)
        expected = media.sample_at_frame(start_frame+count, state['fps'])-media.sample_at_frame(start_frame, state['fps'])
        if measured['sample_count'] != expected: raise ValueError('Audio mix sample count mismatch')
        if measured['peak_linear'] > 10**(-1/20): raise ValueError('Audio mix exceeds -1dBFS sample-peak ceiling; reduce explicit clip gains')
        self.assets(state)
        if digest(source) != target.base_aep_sha256: raise ValueError('Audio base AEP changed while mixing')
        return wav, {k:v for k,v in measured.items() if k != 'energy_onsets'}
