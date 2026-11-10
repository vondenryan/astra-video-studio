"""Bounded compound layer creation with exact typography and one verified version."""
import copy
import json
import math
import shutil
from uuid import uuid4

from pydantic import Field,model_validator
from astra_video_studio.design import FontSelection
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import write_json
from astra_video_studio.layers import LayerSpec
from astra_video_studio.motion_engine.schemas import StrictModel
from astra_video_studio.project_identity import extend_project_ids,mapped_state
from astra_video_studio.project_manager import ProjectManager
from astra_video_studio.scene_editing import ID,find_comp,find_layer,equivalent
from astra_video_studio.ae_bridge.locking import AELock


class CreationTextStyle(StrictModel):
    font:FontSelection=Field(default_factory=lambda:FontSelection(postscript_name='Arial-BoldMT'))
    alignment:str=Field(default='center',pattern='^(left|center|right)$')
    leading:float|None=Field(default=None,ge=1,le=1000)


class NewLayer(StrictModel):
    role:str=Field(pattern=r'^[a-z][a-z0-9_]{0,39}$')
    layer:LayerSpec
    text_style:CreationTextStyle|None=None
    @model_validator(mode='after')
    def bounded_scope(self):
        if self.layer.kind=='media' or self.layer.asset_id is not None:raise ValueError('Batch creation supports native text/shapes/solids only; import media separately')
        if self.layer.kind!='text' and self.text_style is not None:raise ValueError('Text style belongs only to text')
        if self.layer.kind=='text' and self.text_style is None:self.text_style=CreationTextStyle()
        return self


class LayersCreate(StrictModel):
    project_id:ID
    composition_id:ID
    base_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    layers:list[NewLayer]=Field(min_length=1,max_length=20)
    @model_validator(mode='after')
    def unique(self):
        if len({x.role for x in self.layers})!=len(self.layers):raise ValueError('Batch roles must be unique')
        return self


def verify_batch(before,after,request,items):
    normalized=copy.deepcopy(after);comp=find_comp(normalized,request.composition_id)
    expected_order=['astra:layer:'+i['layer_id'] for i in reversed(items)]+[l['layer_id'] for l in find_comp(before,request.composition_id)['layers']]
    if [l['layer_id'] for l in comp['layers']]!=expected_order:raise ValueError('Batch stacking order mismatch')
    for item in items:
        spec=item['layer'];layer=find_layer(comp,item['layer_id'])
        if layer['name']!=spec['name'] or not layer['editable_2d'] or layer['three_d']:raise ValueError('Created layer identity/type mismatch')
        if layer['parent_ae_id'] is not None or layer['matte_ae_id'] is not None:raise ValueError('Unexpected new layer dependencies')
        if layer['locked'] or not layer['enabled']:raise ValueError('Unexpected new layer state')
        for track in layer['transforms'].values():
            if track.get('keys') or track.get('expression_present') or track.get('expression_enabled'):raise ValueError('Unexpected new animation/expression')
        equivalent(layer['transforms']['scale']['value'][:2],[100,100],'new scale')
        equivalent(layer['transforms']['rotation']['value'],0,'new rotation')
        equivalent(layer['position'][:2],spec['position'] or [comp['width']/2,comp['height']/2],'new position')
        equivalent(layer['transforms']['opacity']['value'],spec['opacity'],'new opacity')
        equivalent([layer['in_point'],layer['out_point']],[spec['in_point'],spec['out_point'] if spec['out_point'] is not None else comp['duration']],'new lifetime')
        if spec['kind']=='text':
            style=layer['text_style'];wanted=item['text_style']
            if layer['text'].replace('\r','\n')!=spec['text'].replace('\r\n','\n').replace('\r','\n'):raise ValueError('Created text mismatch')
            if style['font']!=wanted['font']['postscript_name'] or style['font_missing'] or style['box_overflow']:raise ValueError('Created font/overflow mismatch')
            for field,value in [('font_size',spec['font_size']),('tracking',spec['tracking']),('fill',spec['color']),('alignment',wanted['alignment'])]:equivalent(style[field],value,'new typography '+field)
            if wanted['leading'] is not None:equivalent(style['leading'],wanted['leading'],'new leading')
            if spec['text_box']:equivalent(style['box_size'],spec['text_box'],'new box')
        elif spec['kind']=='shape' and spec['shape']=='empty':
            if not layer['is_shape'] or layer['shape_groups']:raise ValueError('New empty shape mismatch')
        elif spec['kind']=='shape':
            if not layer['is_shape'] or len(layer['shape_groups'])!=1:raise ValueError('New shape structure mismatch')
            group=layer['shape_groups'][0]
            equivalent(group['fill']['color'][:3],spec['color'],'new shape color')
            if len(group['paths'])!=1 or group['paths'][0]['kind']!=spec['shape']:raise ValueError('New native shape kind mismatch')
            equivalent(group['paths'][0]['size'],spec['size'],'new shape size')
        elif spec['kind']=='solid':
            if layer['source_kind']!='footage':raise ValueError('New solid source mismatch')
            equivalent([layer['visual_bounds']['width'],layer['visual_bounds']['height']],[math.floor(v+.5) for v in spec['size']],'new solid size')
        comp['layers']=[l for l in comp['layers'] if l['layer_id']!='astra:layer:'+item['layer_id']]
    equivalent(normalized['compositions'],before['compositions'],'all non-target compositions/layers')
    equivalent(normalized.get('footage',[]),before.get('footage',[]),'non-target footage')


class LayerBatchService:
    def __init__(self,settings):self.settings,self.projects=settings,ProjectManager(settings)
    def create(self,request):
        # Windows mutex ownership is recursive on this synchronous service thread.
        # Hold admission through saved-head load, native checks and promotion,
        # preventing two batch clients from silently promoting the same base.
        with AELock():return self._create_locked(request)
    def _create_locked(self,request):
        manifest,source=self.projects.load(request.project_id)
        saved=json.loads((source.parent/('version.json' if manifest.get('current_version') else 'project.json')).read_text(encoding='utf-8'))
        if digest(source)!=request.base_sha256 or saved['sha256']!=request.base_sha256:raise ValueError('Batch source hash conflict')
        inspection=self.projects.inspect(request.project_id)
        if inspection.status!='succeeded':return inspection
        if inspection.data['project_dirty']:raise ValueError('Capture manual changes before batch creation')
        comp=find_comp(inspection.data,request.composition_id);items=[]
        for entry in request.layers:
            if entry.layer.in_point>=comp['duration'] or entry.layer.out_point and entry.layer.out_point>comp['duration']:
                raise ValueError('Batch layer exceeds composition')
            items.append(entry.model_dump(mode='json')|{'layer_id':uuid4().hex})
        version_id=uuid4().hex;directory=self.settings.contained_path(f'projects/{request.project_id}/versions/{version_id}');directory.mkdir(parents=True,exist_ok=False)
        snapshot,target=directory/'source-snapshot.aep',directory/'project.aep';shutil.copyfile(source,snapshot)
        if digest(source)!=request.base_sha256 or digest(snapshot)!=request.base_sha256:raise ValueError('Batch snapshot hash conflict')
        record={'status':'prepared','version_id':version_id,'source':str(source),'source_sha256':request.base_sha256,'snapshot':str(snapshot),'request':request.model_dump(mode='json')}
        write_json(directory/'version.json',record)
        result=self.projects.runner.run('layers_add',{'project_path':source.as_posix(),'version_path':target.as_posix(),
            'id_map':manifest.get('id_map'),'composition_id':request.composition_id,'items':items,'expected_state':inspection.data})
        result.project_id,result.project_path=request.project_id,str(target)
        if result.status=='succeeded':
            try:
                if digest(source)!=request.base_sha256 or digest(snapshot)!=request.base_sha256 or not target.is_file():raise ValueError('Batch source/output conflict')
                verify_batch(inspection.data,result.data,request,items)
                mapping=extend_project_ids(manifest,result.data);manifest['id_map']=mapping;result.data=mapped_state(result.data,mapping)
                result.data.update(version_id=version_id,created_layers=[{'role':i['role'],'layer_id':i['layer_id']} for i in items],created_count=len(items))
                record['sha256']=digest(target);manifest['current_version']=version_id
                result.artifacts.extend([str(target),str(snapshot)])
            except (OSError,ValueError,KeyError,TypeError) as exc:result.status,result.error='failed','Batch verification failed: '+str(exc)
        record.update(status=result.status,operation_id=result.operation_id,result=result.model_dump());write_json(directory/'version.json',record)
        if result.status=='succeeded':write_json(self.settings.contained_path(f'projects/{request.project_id}/project.json'),manifest)
        self.projects._finalize_job(result);return result
