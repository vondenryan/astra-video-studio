"""Typed layer creation and approved media import into immutable AEP versions."""
import json
import shutil
from uuid import uuid4
from typing import Literal
from pydantic import Field, model_validator

from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import write_json
from astra_video_studio.motion_engine.schemas import StrictModel
from astra_video_studio.project_identity import extend_project_ids, mapped_state
from astra_video_studio.project_manager import ProjectManager


class LayerSpec(StrictModel):
    kind: Literal['text', 'shape', 'solid', 'media'] = 'text'
    name: str = Field(default='Layer', min_length=1, max_length=120)
    text: str = Field(default='ASTRA', max_length=500)
    font_size: float = Field(default=64, ge=8, le=500)
    tracking: int = Field(default=0, ge=-100, le=500)
    shape: Literal['rectangle', 'ellipse', 'empty'] = 'rectangle'
    text_box: tuple[float, float] | None = None
    size: tuple[float, float] = (240, 80)
    color: tuple[float, float, float] = (0.3, 0.85, 1)
    position: tuple[float, float] | None = None
    opacity: float = Field(default=100, ge=0, le=100)
    in_point: float = Field(default=0, ge=0, le=300)
    out_point: float | None = Field(default=None, gt=0, le=300)
    asset_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{32}$')

    @model_validator(mode='after')
    def limits(self):
        if any(not 0 <= v <= 1 for v in self.color) or any(not 0 < v <= 7680 for v in self.size): raise ValueError('Invalid color/size')
        if self.position and any(abs(v) > 100000 for v in self.position): raise ValueError('Position exceeds bounds')
        if self.kind == 'text' and (not self.text.strip() or any(ord(c) < 32 and c not in '\n\r\t' for c in self.text)): raise ValueError('Invalid text')
        if self.kind == 'media' and not self.asset_id: raise ValueError('Media layer requires an imported asset_id')
        if self.out_point is not None and self.out_point <= self.in_point: raise ValueError('Layer lifetime is empty')
        if self.text_box is not None and (self.kind != 'text' or any(not 1 <= v <= 7680 for v in self.text_box)):
            raise ValueError('text_box requires text and dimensions in [1,7680]')
        return self


class LayerCreateRequest(StrictModel):
    project_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    composition_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    layer: LayerSpec


class MediaImportRequest(StrictModel):
    project_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    source_path: str = Field(min_length=1, max_length=32767)


class LayerService:
    def __init__(self, settings: Settings): self.settings, self.projects = settings, ProjectManager(settings)

    def create(self, request: LayerCreateRequest): return self._edit(request, False)
    def import_media(self, request: MediaImportRequest): return self._edit(request, True)

    def _edit(self, request, importing):
        manifest, source = self.projects.load(request.project_id)
        saved = json.loads((source.parent / 'version.json').read_text()) if manifest.get('current_version') else manifest
        source_hash = digest(source)
        if source_hash != saved.get('sha256'): raise ValueError('Source changed outside Astra')
        inspected = self.projects.inspect(request.project_id)
        if inspected.status != 'succeeded': return inspected
        item_id = uuid4().hex
        extra = {}
        if importing:
            original = self.settings.read_path(request.source_path, {'.png','.jpg','.jpeg','.tif','.tiff','.mp4','.mov','.wav','.mp3','.aif','.aiff','.webm'})
            if original.stat().st_size>2_000_000_000: raise ValueError('Media import exceeds 2 GB limit')
            asset_dir = self.settings.contained_path('assets/' + item_id); asset_dir.mkdir(parents=True, exist_ok=False)
            asset = asset_dir / ('original' + original.suffix.lower()); before_hash = digest(original)
            shutil.copyfile(original, asset)
            if digest(asset) != before_hash or digest(original) != before_hash: raise ValueError('Asset changed during copy')
            extra = {'asset_path': asset.as_posix(), 'asset_id': item_id}
        else:
            comps = [c for c in inspected.data['compositions'] if c['composition_id'] == 'astra:composition:' + request.composition_id]
            if len(comps) != 1: raise ValueError('Composition absent/ambiguous')
            if request.layer.in_point >= comps[0]['duration'] or (request.layer.out_point and request.layer.out_point > comps[0]['duration']): raise ValueError('Layer exceeds composition')
            native_asset = manifest.get('assets', {}).get(request.layer.asset_id)
            if request.layer.kind == 'media' and native_asset is None: raise ValueError('Unknown imported asset')
            extra = {'composition_id': request.composition_id, 'layer_spec': request.layer.model_dump(), 'layer_id': item_id, 'native_asset': native_asset}
        version_id = uuid4().hex
        directory = self.settings.contained_path(f'projects/{request.project_id}/versions/{version_id}'); directory.mkdir(parents=True, exist_ok=False)
        target, snapshot = directory / 'project.aep', directory / 'source-snapshot.aep'; shutil.copyfile(source, snapshot)
        if digest(snapshot) != source_hash: raise ValueError('Snapshot mismatch')
        version = {'status': 'prepared', 'version_id': version_id, 'source': str(source), 'source_sha256': source_hash, 'snapshot': str(snapshot), 'request': request.model_dump()}
        write_json(directory / 'version.json', version)
        result = self.projects.runner.run('asset_import' if importing else 'layer_add', {'project_path': source.as_posix(), 'version_path': target.as_posix(), 'id_map': manifest.get('id_map'), **extra})
        result.project_id, result.project_path = request.project_id, str(target)
        if result.status == 'succeeded':
            try:
                if digest(source) != source_hash or not target.is_file(): raise ValueError('Source/output mismatch')
                if importing:
                    if result.data['compositions'] != inspected.data['compositions']: raise ValueError('Import changed composition state')
                    if digest(original) != before_hash or digest(asset) != before_hash: raise ValueError('Original/copied asset changed')
                    imported = result.data['imported_asset']
                    manifest.setdefault('assets', {})[item_id] = imported['ae_id']
                    result.data.update(asset_id=item_id, asset_path=str(asset), asset_sha256=before_hash)
                    result.artifacts.append(str(asset))
                else:
                    import copy
                    normalized = copy.deepcopy(result.data)
                    comp = next(c for c in normalized['compositions'] if c['composition_id'] == 'astra:composition:' + request.composition_id)
                    matches = [l for l in comp['layers'] if l['layer_id'] == 'astra:layer:' + item_id]
                    if len(matches) != 1 or matches[0]['name'] != request.layer.name: raise ValueError('Created layer mismatch')
                    if request.layer.kind == 'text' and matches[0]['text'].replace('\r','\n') != request.layer.text.replace('\r\n','\n').replace('\r','\n'): raise ValueError('Text content mismatch')
                    comp['layers'] = [l for l in comp['layers'] if l['layer_id'] != 'astra:layer:' + item_id]
                    if normalized['compositions'] != inspected.data['compositions']: raise ValueError('Other layer state changed')
                    mapping = extend_project_ids(manifest, result.data); manifest['id_map'] = mapping; result.data = mapped_state(result.data, mapping)
                    result.data['layer_id'] = item_id
                version['sha256'] = digest(target); manifest['current_version'] = version_id
                result.data['version_id'] = version_id; result.artifacts.extend([str(target), str(snapshot)])
            except (OSError, ValueError, KeyError, TypeError, StopIteration) as error: result.status, result.error = 'failed', 'Layer/import verification failed: ' + str(error)
        version.update(status=result.status, result=result.model_dump(), operation_id=result.operation_id); write_json(directory / 'version.json', version)
        if result.status == 'succeeded': write_json(self.settings.contained_path(f'projects/{request.project_id}/project.json'), manifest)
        self.projects._finalize_job(result)
        return result
