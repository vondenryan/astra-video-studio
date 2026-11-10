"""Local declarative scene direction, reproducible execution and bounded revisions."""
import copy
import hashlib
import json
import re
import shutil
from uuid import uuid4
from pathlib import Path
from typing import Literal
from pydantic import Field, model_validator

from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import Job, write_json, timestamp
from astra_video_studio.layers import LayerSpec
from astra_video_studio.media.preview import PreviewRequest, PreviewService
from astra_video_studio.motion_engine.batch import BatchRequest, BatchService
from astra_video_studio.motion_engine.schemas import StrictModel, MotionRequest
from astra_video_studio.project_manager import ProjectManager, valid_id
from astra_video_studio.motion_engine.timeline import frame
import math


class SceneBrief(StrictModel):
    brief: str = Field(min_length=5, max_length=4000)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    subtitle: str = Field(default='Motion design. Controle local.', max_length=160)
    closing: str = Field(default='IDEIAS EM MOVIMENTO', min_length=1, max_length=120)
    duration: float | None = Field(default=None, ge=10, le=15)
    width: int = Field(default=1920, ge=640, le=3840)
    height: int = Field(default=1080, ge=360, le=2160)
    fps: float = Field(default=30, ge=12, le=60)
    accent: tuple[float, float, float] = (0.2, 0.85, 1)
    entry_duration: float = Field(default=0.9, ge=0.4, le=2)
    overshoot: float = Field(default=0.05, ge=0, le=0.15)

    @model_validator(mode='after')
    def colors(self):
        if any(not 0 <= v <= 1 for v in self.accent): raise ValueError('Invalid accent color')
        return self


class SceneElement(StrictModel):
    role: str = Field(pattern=r'^[a-z_]+$')
    layer_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    decorative: bool = False
    layer: LayerSpec


class SceneAction(StrictModel):
    role: str
    motion: MotionRequest


class ScenePlan(StrictModel):
    plan_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    parent_plan_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{32}$')
    composition_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    width: int = Field(ge=640,le=3840)
    height: int = Field(ge=360,le=2160)
    fps: float = Field(ge=12,le=60)
    duration: float = Field(ge=10,le=15)
    background: tuple[float, float, float]
    brief: SceneBrief
    elements: list[SceneElement] = Field(min_length=1,max_length=20)
    actions: list[SceneAction] = Field(min_length=1,max_length=40)
    phases: list[dict]
    techniques: list[str]
    assumptions: list[str]

    @model_validator(mode='after')
    def consistent(self):
        roles = {e.role: e for e in self.elements}
        if len(roles) != len(self.elements) or len({e.layer_id for e in self.elements}) != len(self.elements): raise ValueError('Duplicate role/ID')
        for action in self.actions:
            if action.role not in roles or action.motion.layer_id != roles[action.role].layer_id or action.motion.composition_id != self.composition_id:
                raise ValueError('Action identity mismatch')
            if action.motion.start_time + action.motion.duration > self.duration + 1e-6: raise ValueError('Action exceeds scene')
        return self


class RevisionChanges(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    subtitle: str | None = Field(default=None, max_length=160)
    closing: str | None = Field(default=None, min_length=1, max_length=120)
    duration: float | None = Field(default=None, ge=10, le=15)
    entry_duration: float | None = Field(default=None, ge=0.4, le=2)
    overshoot: float | None = Field(default=None, ge=0, le=0.15)
    accent: tuple[float, float, float] | None = None


class SceneRevision(StrictModel):
    plan_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    instruction: str = Field(min_length=5, max_length=2000)
    changes: RevisionChanges | None = None


class SceneExecution(StrictModel):
    execution_id: str
    plan_id: str
    status: str
    project_id: str | None = None
    project_path: str | None = None
    preview_job_id: str | None = None
    data: dict = Field(default_factory=dict)
    error: str | None = None


class ReviewRecord(StrictModel):
    execution_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    inspected_samples: list[int] = Field(min_length=1, max_length=3)
    notes: str = Field(min_length=10, max_length=3000)
    assessment: Literal['acceptable_samples', 'needs_revision']
    reviewer: Literal['operator', 'codex'] = 'codex'
    reference_ids: list[str] = Field(default_factory=list,max_length=8)


def build_plan(brief: SceneBrief, prior: ScenePlan | None = None) -> ScenePlan:
    duration = brief.duration
    assumptions = ['Deterministic local scene template; Codex can supply structured fields for richer briefs.', 'Silent preview; no generative API or paid processing.']
    if duration is None:
        match = re.search(r'\b(\d+(?:[.,]\d+)?)\s*(?:s\b|segundos?\b|seconds?\b)', brief.brief, flags=re.I)
        duration = float(match.group(1).replace(',', '.')) if match else 12
        if not 10 <= duration <= 15: raise ValueError('Brief duration must be 10–15 seconds')
        assumptions.append('Duration extracted from brief.' if match else 'Default duration: 12 seconds.')
    title = brief.title
    if title is None:
        match = re.search(r'["“](.+?)["”]', brief.brief)
        title = match.group(1) if match else 'ASTRA VIDEO STUDIO'
        assumptions.append('Title extracted from quotes.' if match else 'Default title: ASTRA VIDEO STUDIO.')
    duration = max(math.ceil(10*brief.fps), min(math.floor(15*brief.fps), frame(duration,brief.fps))) / brief.fps
    normalized = brief.model_copy(update={'duration': duration, 'title': title})
    w, h, d = brief.width, brief.height, duration
    main_end = d - 2.2
    comp_id = prior.composition_id if prior else uuid4().hex
    old_ids = {e.role: e.layer_id for e in prior.elements} if prior else {}
    elements = []
    def add(role, kind='text', text='', position=(0.5, 0.5), size=(100, 20), color=None, font=0.04, opacity=100, start=0, end=None, shape='rectangle', decorative=False, tracking=0):
        spec = LayerSpec(kind=kind, name=role.replace('_',' ').title(), text=text, font_size=max(8,min(500,w*font)), tracking=tracking,
            shape=shape, size=size, color=color or brief.accent, position=(w*position[0],h*position[1]), opacity=opacity, in_point=frame(start,brief.fps)/brief.fps, out_point=frame(d if end is None else end,brief.fps)/brief.fps)
        elements.append(SceneElement(role=role, layer_id=old_ids.get(role, uuid4().hex), decorative=decorative, layer=spec))
    bg = (0.018,0.028,0.055)
    add('background', 'shape', size=(w,h), color=bg, decorative=True)
    add('ambient', 'shape', position=(0.88,0.12), size=(w*0.75,w*0.75), color=(0.02,0.19,0.25), opacity=25, shape='ellipse', decorative=True)
    add('accent_left','shape',position=(0.47,0.57),size=(w*0.045,3),decorative=True,end=main_end)
    add('accent_right','shape',position=(0.53,0.57),size=(w*0.045,3),decorative=True,end=main_end)
    add('kicker',text='ASTRA / MOTION SYSTEM',position=(0.5,0.23),font=0.014,tracking=180,color=(0.52,0.66,0.73),end=main_end)
    add('title',text=title,position=(0.5,0.43),font=0.07,tracking=40,color=(0.94,0.97,1),end=main_end)
    add('subtitle',text=brief.subtitle,position=(0.5,0.66),font=0.023,color=(0.64,0.73,0.8),start=0.8,end=main_end)
    add('closing',text=brief.closing,position=(0.5,0.46),font=0.052,tracking=40,start=main_end)
    add('signature',text='ASTRA VIDEO STUDIO',position=(0.5,0.62),font=0.016,tracking=150,color=(0.65,0.75,0.8),start=main_end)
    roles = {e.role:e for e in elements}
    actions = []
    def motion(role,skill,start,length,params=None):
        actions.append(SceneAction(role=role,motion=MotionRequest(project_id='0'*32,composition_id=comp_id,layer_id=roles[role].layer_id,skill=skill,start_time=start,duration=length,params=params or {})))
    motion('ambient','parallax_2d',0,d,{'depth':0.7,'displacement':[0.05,0.04],'motion_blur':False})
    motion('kicker','fade_in_out',0,main_end,{'fade_in':0.6,'fade_out':0.5})
    motion('title','slide_in',0.25,brief.entry_duration,{'direction':'left','distance_ratio':0.19,'overshoot':brief.overshoot})
    motion('title','scale_pop',0.25,brief.entry_duration,{'initial_scale':94,'overshoot':brief.overshoot*0.6})
    motion('title','fade_in_out',0,main_end,{'fade_in':0.55,'fade_out':0.5})
    motion('subtitle','text_reveal',0.9,0.9,{'direction':'left','padding_px':10})
    motion('subtitle','fade_in_out',0.8,main_end-0.8,{'fade_in':0.35,'fade_out':0.5})
    for i,role in enumerate(('accent_left','accent_right')):
        motion(role,'scale_pop',0.8+i*0.12,0.6,{'initial_scale':1,'overshoot':0})
        motion(role,'fade_in_out',0,main_end,{'fade_in':0.5,'fade_out':0.5})
    motion('closing','scale_pop',main_end+0.1,0.65,{'initial_scale':90,'overshoot':0.03})
    motion('closing','shake',main_end+0.9,0.45,{'amplitude_px':1.5,'frequency_hz':4,'decay':4,'seed':7})
    motion('closing','fade_in_out',main_end,d-main_end,{'fade_in':0.4,'fade_out':0.45})
    motion('signature','fade_in_out',main_end,d-main_end,{'fade_in':0.65,'fade_out':0.45})
    return ScenePlan(plan_id=uuid4().hex,parent_plan_id=prior.plan_id if prior else None,composition_id=comp_id,width=w,height=h,fps=brief.fps,duration=d,background=bg,brief=normalized,elements=elements,actions=actions,
        phases=[{'name':'entry','start':0,'end':max(2,0.4+brief.entry_duration)},{'name':'hold','start':max(2,0.4+brief.entry_duration),'end':main_end},{'name':'closing','start':main_end,'end':d}],techniques=['slide_in','scale_pop','fade_in_out','text_reveal','stagger_layers','parallax_2d','shake'],assumptions=assumptions)


def natural_changes(instruction: str, previous: ScenePlan) -> RevisionChanges:
    remaining = instruction
    changes = {}
    patterns = [('title',r'\b(?:t[ií]tulo|title)\s+(?:para|to)\s+["“](.+?)["”]'),('subtitle',r'\b(?:subt[ií]tulo|subtitle)\s+(?:para|to)\s+["“](.+?)["”]'),('overshoot',r'\bovershoot\s+(?:para|to)\s+(\d+(?:[.,]\d+)?)\s*%'),('duration',r'\b(?:dura[çc][ãa]o|duration)\s+(?:para|to)\s+(\d+(?:[.,]\d+)?)\s*(?:s\b|segundos?\b|seconds?\b)')]
    for key, pattern in patterns:
        match = re.search(pattern,remaining,flags=re.I)
        if match:
            value = match.group(1)
            changes[key] = value if key in ('title','subtitle') else float(value.replace(',','.')) / (100 if key=='overshoot' else 1)
            remaining = remaining[:match.start()] + ' ' + remaining[match.end():]
    if re.search(r'entrada\s+mais\s+lenta|slower\s+entrance',remaining,flags=re.I):
        changes['entry_duration'] = min(2,previous.brief.entry_duration*1.3)
        remaining = re.sub(r'entrada\s+mais\s+lenta|slower\s+entrance',' ',remaining,flags=re.I)
    remaining = re.sub(r'\b(?:troque|altere|mude|reduza|aumente|change|set|reduce|please|por|favor|o|a|e|and)\b',' ',remaining,flags=re.I)
    if not changes or re.sub(r'[\s,.;:!]+','',remaining):
        raise ValueError('Unsupported/ambiguous natural revision. Use quoted title/subtitle, overshoot to N%, duration to N seconds, slower entrance, or explicit typed changes.')
    return RevisionChanges(**changes)


class Director:
    def __init__(self, settings: Settings): self.settings,self.projects=settings,ProjectManager(settings)

    def _directory(self,plan_id): return self.settings.contained_path('plans/'+valid_id(plan_id))
    def load(self,plan_id):
        directory=self._directory(plan_id)
        if digest(directory/'plan.json')!=json.loads((directory/'integrity.json').read_text())['sha256']:
            raise ValueError('Plan file changed; create a typed revision instead')
        return ScenePlan.model_validate(json.loads((directory/'plan.json').read_text(encoding='utf-8')))

    def store(self,plan):
        directory=self._directory(plan.plan_id); directory.mkdir(parents=True,exist_ok=False)
        write_json(directory/'plan.json',plan.model_dump())
        write_json(directory/'integrity.json',{'sha256':digest(directory/'plan.json')})
        return plan

    def plan(self,brief): return self.store(build_plan(brief))

    def revision_patch(self, request):
        """Plan a bounded property revision; unlike revise(), never rebuilds a scene."""
        from astra_video_studio.revisions import RevisionService
        return RevisionService(self.settings).director_plan(request)

    def revise(self,request):
        previous=self.load(request.plan_id)
        changes=request.changes or natural_changes(request.instruction,previous)
        values=changes.model_dump(exclude_none=True)
        if not values: raise ValueError('Revision contains no changes')
        brief=SceneBrief.model_validate(previous.brief.model_dump()|values)
        revised=self.store(build_plan(brief,previous))
        write_json(self._directory(revised.plan_id)/'revision.json',{'instruction':request.instruction,'changes':values,'parent_plan_id':previous.plan_id})
        return revised

    def execute(self,plan_id):
        scene=self.load(plan_id)
        job=Job(self.settings,'scene_execute')
        execution=SceneExecution(execution_id=job.id,plan_id=plan_id,status='building')
        directory=self._directory(plan_id)
        if (directory/'execution.json').exists(): raise ValueError('Plan already executed; create a revision instead of overwriting history')
        previous=None
        if scene.parent_plan_id:
            prior_path=self._directory(scene.parent_plan_id)/'execution.json'
            previous=SceneExecution.model_validate(json.loads(prior_path.read_text()))
            if previous.status!='succeeded': raise ValueError('Parent scene must have a verified preview before revision')
            manifest,source=self.projects.load(previous.project_id)
            if str(source)!=previous.project_path or digest(source)!=previous.data['project_sha256']:
                raise ValueError('Scene was changed outside its recorded execution; preserve/review manual edits first')
            project_id=previous.project_id
            version_id=uuid4().hex
            output_dir=self.settings.contained_path(f'projects/{project_id}/versions/{version_id}'); output_dir.mkdir(parents=True,exist_ok=False)
            target,snapshot=output_dir/'project.aep',output_dir/'source-snapshot.aep'; shutil.copyfile(source,snapshot)
            if digest(snapshot)!=previous.data['project_sha256']: raise ValueError('Revision snapshot mismatch')
            manifest_path=self.settings.contained_path(f'projects/{project_id}/project.json')
        else:
            project_id=uuid4().hex; output_dir=self.settings.contained_path('projects/'+project_id); output_dir.mkdir(parents=True,exist_ok=False)
            target=output_dir/'project.aep'; source=None; snapshot=None
            manifest={'project_id':project_id,'kind':'directed_scene','status':'prepared','composition_id':scene.composition_id}
            manifest_path=output_dir/'project.json'; write_json(manifest_path,manifest)
        payload={'project_path':source.as_posix() if source else target.as_posix(),'output_path':target.as_posix(),'rebuilding':bool(previous),'managed_paths':self.projects.managed_paths(),'scene':scene.model_dump()}
        build=self.projects.runner.run('scene_build',payload)
        build.project_id,build.project_path=project_id,str(target)
        execution.project_id,execution.project_path=project_id,str(target)
        try:
            if build.status!='succeeded': raise ValueError(build.error or build.status)
            comps=build.data['compositions']
            if len(comps)!=1 or comps[0]['duration']!=scene.duration or len(comps[0]['layers'])!=len(scene.elements): raise ValueError('Scene structure mismatch')
            by_id={l['layer_id']:l for l in comps[0]['layers']}
            for element in scene.elements:
                layer=by_id['astra:layer:'+element.layer_id]
                if element.layer.kind=='text' and layer['text'].replace('\r','\n')!=element.layer.text.replace('\r','\n'): raise ValueError('Scene text mismatch')
            if previous and digest(source)!=previous.data['project_sha256']: raise ValueError('Parent scene overwritten')
            record={'status':'succeeded','sha256':digest(target),'operation_id':build.operation_id,'result':build.model_dump(),'scene_plan_id':plan_id}
            if previous:
                write_json(output_dir/'version.json',record|{'version_id':version_id,'source':str(source),'snapshot':str(snapshot)})
                manifest.update(current_version=version_id,scene_plan_id=plan_id)
            else: manifest.update(record)
            write_json(manifest_path,manifest)
            self.projects._finalize_job(build)
            motions=[MotionRequest.model_validate(action.motion.model_dump()|{'project_id':project_id}) for action in scene.actions]
            applied=BatchService(self.settings).apply(BatchRequest(motions=motions))
            if applied.status!='succeeded': raise ValueError(applied.error or applied.status)
            execution.project_path=applied.project_path
            execution.data={'project_sha256':digest(Path(applied.project_path)),'build_operation':build.operation_id,'batch_operation':applied.operation_id,'techniques':scene.techniques,'inspection':applied.data}
            preview=PreviewService(self.settings).submit(PreviewRequest(project_id=project_id,composition_id=scene.composition_id,duration=scene.duration,max_width=1280))
            if preview.status!='queued': raise ValueError(preview.error)
            execution.preview_job_id=preview.job_id; execution.status='rendering'
        except (ValueError,OSError,KeyError,TypeError) as error:
            execution.status,execution.error='failed',str(error)
        write_json(directory/'execution.json',execution.model_dump())
        job.record('queued' if execution.status=='rendering' else 'failed',execution=execution.model_dump())
        return execution

    def status(self,execution_id):
        job=self.projects.job_status(execution_id)
        execution=SceneExecution.model_validate(job['execution'])
        directory=self._directory(execution.plan_id)
        if execution.status=='rendering':
            preview=self.projects.job_status(execution.preview_job_id)
            if preview['status']=='succeeded':
                execution.status='succeeded'; execution.data['preview']=preview['result']['data']
                execution.data['checklist']={'editable_project':True,'native_keyframes_verified':True,'preview_fully_decoded':True,'source_preservation_verified':True,'sampled_visual_review':'pending','rhythm_full_playback':'human_review_pending'}
            elif preview['status'] not in ('prepared','queued','running'):
                execution.status='failed'; execution.error=preview.get('result',{}).get('error') or preview['status']
            write_json(directory/'execution.json',execution.model_dump())
            job.update(status='succeeded' if execution.status=='succeeded' else 'failed' if execution.status=='failed' else 'running',execution=execution.model_dump())
            write_json(self.settings.contained_path(f'jobs/{valid_id(execution_id)}/job.json'),job)
        return execution

    def review(self,request):
        execution=self.status(request.execution_id)
        if execution.status!='succeeded': raise ValueError('Verified preview required before recording review')
        if len(set(request.inspected_samples))!=len(request.inspected_samples) or any(i not in (0,1,2) for i in request.inspected_samples): raise ValueError('Invalid sample selection')
        samples=execution.data['preview']['samples']
        if any(not Path(samples[i]).is_file() for i in request.inspected_samples): raise ValueError('Sample image missing')
        record=request.model_dump()|{'timestamp':timestamp(),'scope':'sampled_frames_only','full_video_watched':False,'artifacts':[samples[i] for i in request.inspected_samples]}
        for reference_id in request.reference_ids:
            path=self.settings.contained_path(f'references/{valid_id(reference_id)}/report.json')
            reference=json.loads(path.read_text(encoding='utf-8'))
            if reference['source_sha256']!=execution.data['preview']['video_sha256']: raise ValueError('Review reference belongs to another video')
            if not all(Path(p).is_file() for p in reference['samples']): raise ValueError('Reference samples missing')
            record['artifacts'].extend(reference['samples'])
        write_json(self._directory(execution.plan_id)/'review.json',record)
        execution.data['checklist']['sampled_visual_review']=request.assessment
        execution.data['review']=record
        job=self.projects.job_status(request.execution_id); job['execution']=execution.model_dump()
        write_json(self.settings.contained_path(f'jobs/{request.execution_id}/job.json'),job)
        write_json(self._directory(execution.plan_id)/'execution.json',execution.model_dump())
        return execution
