"""Versioned, deterministic multi-scene direction; no free-form native execution."""
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import Field, field_validator, model_validator

from astra_video_studio.audio import AudioService, AudioClipSet, ClipSpec, SHA
from astra_video_studio.design import load_tokens
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import Job, read_json, write_json, timestamp
from astra_video_studio.layers import LayerSpec
from astra_video_studio.media.audio import binaries, RATE
from astra_video_studio.media.final_render import RenderService, FinalRenderRequest
from astra_video_studio.motion_engine.batch import BatchService, BatchRequest
from astra_video_studio.motion_engine.schemas import StrictModel, MotionRequest
from astra_video_studio.project_manager import ProjectManager, valid_id
from astra_video_studio.responses import store_evidence
from astra_video_studio.revisions import (RevisionService, RevisionPlanRequest, RevisionApplyRequest,
    ContentPatch, ContentSet)
from astra_video_studio.scene_editing import ID, find_comp, find_layer
from astra_video_studio.schemas import OperationResult


class SceneCard(StrictModel):
    intent: str = Field(min_length=5, max_length=300)
    heading: str = Field(min_length=1, max_length=90)
    body: str = Field(min_length=1, max_length=180)
    layout: Literal['hero', 'split', 'editorial']

    @field_validator('heading', 'body')
    @classmethod
    def single_paragraph(cls, value):
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError('Storyboard text requires one nonempty paragraph without controls')
        return value


class ReferenceNote(StrictModel):
    reference_id: ID
    sample_indices: list[int] = Field(min_length=1, max_length=8)
    observation: str = Field(min_length=10, max_length=600)
    reviewer: Literal['operator', 'codex']


class StoryBrief(StrictModel):
    schema_version: Literal[2] = 2
    objective: str = Field(min_length=5, max_length=600)
    audience: str = Field(min_length=3, max_length=300)
    message: str = Field(min_length=5, max_length=600)
    brand_constraints: list[str] = Field(min_length=1, max_length=12)
    token_id: ID
    duration_seconds: int = Field(default=18, ge=15, le=30)
    width: int = Field(default=1280, ge=640, le=1920)
    height: int = Field(default=720, ge=360, le=1920)
    fps: int = Field(default=24, ge=12, le=60)
    scenes: list[SceneCard] = Field(min_length=3, max_length=6)
    audio_bed_asset_id: ID
    audio_gain_db: float = Field(default=-12, ge=-40, le=-3)
    reference_notes: list[ReferenceNote] = Field(default_factory=list, max_length=4)
    max_revisions: int = Field(default=3, ge=1, le=5)

    @model_validator(mode='after')
    def format(self):
        if self.width % 2 or self.height % 2: raise ValueError('Even resolution required')
        if len(set(c.layout for c in self.scenes)) < 2:
            raise ValueError('Combine at least two layout families; three are available')
        if any(not s.strip() or len(s) > 300 for s in self.brand_constraints):
            raise ValueError('Brand constraints must be nonempty and at most 300 characters')
        return self


class StoryExecute(StrictModel):
    plan_id: ID
    plan_sha256: SHA


class StoryRevision(StrictModel):
    execution_id: ID
    base_aep_sha256: SHA
    instruction: str = Field(min_length=10, max_length=500)
    rebuild_audio: Literal[True]


class ReviewSamples(StrictModel):
    execution_id: ID


class ReviewIssue(StrictModel):
    category: Literal['readability', 'layout', 'continuity', 'audio', 'brand']
    severity: Literal['minor', 'major', 'blocking']
    description: str = Field(min_length=10, max_length=600)
    sample_ids: list[ID] = Field(min_length=1, max_length=12)
    proposed_correction: str = Field(min_length=10, max_length=500)


class StoryReview(StrictModel):
    execution_id: ID
    samples_sha256: SHA
    inspected_sample_ids: list[ID] = Field(min_length=1, max_length=48)
    reviewer: Literal['operator', 'codex']
    assessment: Literal['acceptable_samples', 'needs_revision']
    notes: str = Field(min_length=10, max_length=2000)
    issues: list[ReviewIssue] = Field(default_factory=list, max_length=12)
    resolves_review_sha256: SHA | None = None


def reading_seconds(heading, body):
    """Conservative explicit planning heuristic, never a legibility attestation."""
    return max(2.0, len((heading+' '+body).split()) / 3.0 + 0.7)


def parse_patch(instruction, count):
    match = re.fullmatch(r'\s*(?:trocar|troque)\s+(?:o\s+)?(t[íi]tulo|texto)\s+da\s+cena\s+([1-6])\s+para\s+["“]([^"”\r\n]+)["”]\s*[.!]?\s*', instruction, re.I)
    if not match: raise ValueError('Unsupported patch: trocar título/texto da cena N para "..."')
    index = int(match[2])-1
    if index >= count: raise ValueError('Scene absent')
    role = 'heading' if match[1].lower() in ('título', 'titulo') else 'body'
    value = match[3]
    SceneCard(intent='Patch validation', heading=value if role=='heading' else 'Title',
              body=value if role=='body' else 'Body', layout='hero')
    return index, role, value


def sample_schedule(plan, changed=None):
    fps, total = plan['brief']['fps'], plan['total_frames']
    samples = {}
    def add(frame, reason):
        frame = max(0, min(total-1, int(frame)))
        samples.setdefault(frame, []).append(reason)
    for i, scene in enumerate(plan['scenes']):
        a, b, t = scene['start_frame'], scene['end_frame'], plan['transition_frames']
        for f, phase in ((a+t, 'entry'), ((a+b)//2, 'hold'), (b-max(1,t//2), 'exit')):
            add(f, f'scene_{i+1}_{phase}')
        if i: add(a+t//2, f'scene_{i+1}_transition')
    if changed:
        a, b = changed
        for f in (a, (a+b)//2, b-1): add(f, 'changed_interval')
    return [{'frame': f, 'time': f/fps, 'reasons': why} for f, why in sorted(samples.items())]


class StoryboardService:
    def __init__(self, settings):
        self.settings, self.projects = settings, ProjectManager(settings)

    def _dir(self, kind, identifier):
        return self.settings.contained_path(f'storyboards/{kind}/{valid_id(identifier)}')

    def _read_evidence(self, sha, kind):
        if not re.fullmatch('[0-9a-f]{64}', sha): raise ValueError('Invalid evidence hash')
        path = self.settings.contained_path(f'responses/{sha}.json')
        if digest(path) != sha: raise ValueError('Storyboard evidence changed')
        value = read_json(path)
        if value.get('kind') != kind or value.get('schema_version') != 1:
            raise ValueError('Storyboard evidence kind mismatch')
        return value['result']

    def _result(self, action, data, project_id=None, project_path=None):
        job = Job(self.settings, action)
        result = OperationResult(operation_id=job.id, status='failed' if data.get('status')=='failed' else 'succeeded', project_id=project_id,
                                 project_path=project_path, data=data,error=data.get('error'))
        job.record(result.status, result=result.model_dump(mode='json'))
        return result

    def validate(self, brief):
        tokens = load_tokens(self.settings, brief.token_id)
        if not {'background','foreground','accent'}.issubset(tokens.colors):
            raise ValueError('Storyboard tokens require background, foreground and accent colors')
        if not {'heading','body'}.issubset(tokens.typography):
            raise ValueError('Storyboard tokens require heading and body typography')
        if tokens.typography['heading'].size_ratio <= tokens.typography['body'].size_ratio:
            raise ValueError('Heading typography must be larger than body typography')
        if tokens.typography['body'].size_ratio * brief.width < 16:
            raise ValueError('Storyboard body typography must be at least 16px')
        # WCAG relative luminance is a useful gate, not a complete artistic review.
        def lum(rgb):
            linear = [c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4 for c in rgb]
            return sum(c*w for c,w in zip(linear, (.2126,.7152,.0722)))
        for role in ('heading','body'):
            fg, bg = lum(tokens.colors[tokens.typography[role].color]), lum(tokens.colors['background'])
            if (max(fg,bg)+.05)/(min(fg,bg)+.05) < 4.5:
                raise ValueError('Text/background contrast is below 4.5:1')
        total, transition = brief.duration_seconds*brief.fps, round(.5*brief.fps)
        scenes = []
        for i, card in enumerate(brief.scenes):
            a = total*i//len(brief.scenes)
            b = min(total, total*(i+1)//len(brief.scenes)+transition)
            hold = (b-a-2*transition)/brief.fps
            required = reading_seconds(card.heading, card.body)
            if required > hold: raise ValueError(f'Scene {i+1} exceeds reading budget ({required:.2f}s > {hold:.2f}s)')
            scenes.append({'start_frame':a, 'end_frame':b, 'reading_seconds':required, 'hold_seconds':hold})
        audio = AudioService(self.settings)._asset(brief.audio_bed_asset_id)
        if audio['sample_count'] < brief.duration_seconds*RATE: raise ValueError('Audio bed is shorter than storyboard')
        references = []
        for note in brief.reference_notes:
            path = self.settings.contained_path(f'references/{note.reference_id}/report.json')
            report = read_json(path)
            if len(set(note.sample_indices)) != len(note.sample_indices): raise ValueError('Duplicate reference sample')
            samples = []
            for index in note.sample_indices:
                if not 0 <= index < len(report['samples']): raise ValueError('Reference sample absent')
                image = self.settings.contained_path(str(Path(report['samples'][index]).relative_to(self.settings.workspace)))
                samples.append({'index':index, 'path':str(image), 'sha256':digest(image)})
            references.append(note.model_dump() | {'report_sha256':digest(path), 'samples':samples,
                'scope':'caller_attested_sample_observation; metadata is not semantic analysis'})
        return {'schema_version':2, 'brief':brief.model_dump(mode='json'), 'tokens':tokens.model_dump(mode='json'),
                'total_frames':total, 'transition_frames':transition, 'timing':scenes,
                'audio_asset_manifest_sha256':audio['manifest_sha256'], 'references':references,
                'semantic_brand_compliance':'human_review_pending', 'reading_policy':'3 words/s + 0.7s; minimum 2s'}

    def brief_validate(self, brief):
        return self._result('brief_validate', self.validate(brief))

    def plan(self, brief):
        plan = self.validate(brief)
        plan.update(plan_id=uuid4().hex, composition_id=uuid4().hex,
                    techniques=['slide_in','text_reveal','scale_pop','fade_in_out'], scenes=[])
        w,h = brief.width, brief.height
        tokens = plan['tokens']; top,right,bottom,left = tokens['safe_area']
        x0,x1,y0,y1 = left*w,(1-right)*w,top*h,(1-bottom)*h
        width,height = x1-x0,y1-y0
        for card, timing in zip(brief.scenes, plan.pop('timing')):
            duration = (timing['end_frame']-timing['start_frame'])/brief.fps
            scene = timing | {'composition_id':uuid4().hex, 'master_layer_id':uuid4().hex,
                              'card':card.model_dump(), 'duration':duration, 'elements':[]}
            def add(role, **kwargs):
                scene['elements'].append({'role':role, 'layer_id':uuid4().hex,
                    'layer':LayerSpec(name=role, out_point=duration, **kwargs).model_dump(mode='json')})
            add('background', kind='shape', size=(w,h), position=(w/2,h/2),color=tokens['colors']['background'])
            if card.layout=='hero':
                boxes = {'heading':(.5,.34,.94,.25), 'body':(.5,.65,.84,.22)}
                accent = (.5,.85,.22)
            elif card.layout=='split':
                boxes = {'heading':(.24,.46,.44,.55), 'body':(.76,.48,.44,.45)}
                accent = (.5,.86,.8)
            else:
                boxes = {'heading':(.5,.24,.98,.25), 'body':(.5,.58,.98,.33)}
                accent = (.5,.9,.98)
            for role in ('heading','body'):
                x,y,bw,bh = boxes[role]; typography = tokens['typography'][role]
                px = x0+x*width - (bw*width/2 if card.layout!='hero' else 0)
                add(role,kind='text',text=getattr(card,role), position=(px,y0+y*height),
                    text_box=(bw*width,bh*height), font_size=max(8,min(500,w*typography['size_ratio'])),
                    tracking=typography['tracking'],color=tokens['colors'][typography['color']])
            add('kicker',kind='text',text=f'{len(plan["scenes"])+1:02d}',position=(x0+width*.5,y0+height*.045),
                text_box=(width*.15,height*.08),font_size=max(8,min(500,w*tokens['typography']['body']['size_ratio'])),
                color=tokens['colors']['accent'])
            ax,ay,aw = accent
            add('accent',kind='shape', size=(aw*width,max(3,w*tokens['spacing_ratio']*.12)),
                position=(x0+ax*width,y0+ay*height), color=tokens['colors']['accent'])
            scene['transition'] = {'kind':'crossfade','frames':plan['transition_frames']}
            scene['audio_map'] = {'bed_asset_id':brief.audio_bed_asset_id,
                                  'start_frame':timing['start_frame'],'end_frame':timing['end_frame']}
            plan['scenes'].append(scene)
        ref = store_evidence(self.settings, 'StoryboardPlan', plan)
        directory = self._dir('plans',plan['plan_id']);directory.mkdir(parents=True,exist_ok=False)
        write_json(directory/'record.json',{'plan_sha256':ref.sha256})
        return self._result('storyboard_plan', plan | {'plan_sha256':ref.sha256})

    def load_plan(self, identifier, sha=None):
        record = read_json(self._dir('plans',identifier)/'record.json')
        if sha and record['plan_sha256'] != sha: raise ValueError('Storyboard plan hash conflict')
        plan = self._read_evidence(record['plan_sha256'], 'StoryboardPlan')
        if plan['plan_id'] != identifier: raise ValueError('Storyboard plan identity conflict')
        return plan,record['plan_sha256']

    def _commit_execution(self, data):
        ref = store_evidence(self.settings, 'StoryboardExecution', data)
        directory = self._dir('executions',data['execution_id'])
        directory.mkdir(parents=True,exist_ok=True)
        write_json(directory/'head.json',{'execution_sha256':ref.sha256})
        return data | {'execution_sha256':ref.sha256}

    def _execution(self, identifier):
        record = read_json(self._dir('executions',identifier)/'head.json')
        value = self._read_evidence(record['execution_sha256'],'StoryboardExecution')
        if value['execution_id'] != identifier: raise ValueError('Execution identity mismatch')
        return value

    def _audio_and_render(self, execution, plan):
        audio = AudioService(self.settings)
        brief = plan['brief']
        audio._asset(brief['audio_bed_asset_id'], plan['audio_asset_manifest_sha256'])
        base = {'project_id':execution['project_id'],'composition_id':plan['composition_id'],
                'base_aep_sha256':execution['project_sha256']}
        result = audio.clip_set(AudioClipSet(**base,clip=ClipSpec(asset_id=brief['audio_bed_asset_id'],
            duration_frames=plan['total_frames'],gain_db=brief['audio_gain_db'],
            fade_in_frames=plan['transition_frames'],fade_out_frames=plan['transition_frames'])))
        if result.status != 'succeeded': raise ValueError(result.error or result.status)
        execution['audio_state_sha256'] = result.data['audio_state_sha256']
        render = RenderService(self.settings).submit(FinalRenderRequest(**base,
            audio_state_sha256=execution['audio_state_sha256'],duration=brief['duration_seconds'],
            fps=brief['fps'],width=brief['width'],height=brief['height'],
            destination='storyboards/renders/'+execution['execution_id'],color_policy='interpret_native_rgb_as_srgb'))
        if render.status != 'queued': raise ValueError(render.error or render.status)
        execution.update(render_job_id=render.job_id,status='rendering')

    def execute(self, request):
        plan,sha = self.load_plan(request.plan_id,request.plan_sha256)
        # Revalidate pinned dependencies BEFORE reserving native work.
        fresh = self.validate(StoryBrief.model_validate(plan['brief']))
        if fresh['tokens'] != plan['tokens'] or fresh['audio_asset_manifest_sha256'] != plan['audio_asset_manifest_sha256'] or fresh['references'] != plan['references']:
            raise ValueError('Storyboard dependencies changed')
        execution_id,project_id = uuid4().hex,uuid4().hex
        with (self._dir('plans',request.plan_id)/'attempt.json').open('x',encoding='utf-8') as stream:
            json.dump({'execution_id':execution_id,'timestamp':timestamp()},stream)
        data = {'schema_version':2,'execution_id':execution_id,'root_execution_id':execution_id,
                'plan_id':request.plan_id,'plan_sha256':sha,'status':'building','project_id':project_id,
                'parent_execution_id':None,'iteration':0,'human_full_playback':'pending','human_artistic_approval':'pending'}
        self._commit_execution(data)
        directory = self.settings.contained_path('projects/'+project_id);directory.mkdir(parents=True,exist_ok=False)
        target = directory/'project.aep'
        manifest = {'project_id':project_id,'kind':'storyboard_v2','status':'prepared','composition_id':plan['composition_id']}
        write_json(directory/'project.json',manifest)
        try:
            built = self.projects.runner.run('storyboard_build',{'storyboard':plan,'project_path':target.as_posix(),
                'output_path':target.as_posix(),'managed_paths':self.projects.managed_paths()})
            built.project_id,built.project_path = project_id,str(target)
            data.update(build_operation_id=built.operation_id,native_build_status=built.status)
            if built.status != 'succeeded': raise ValueError(built.error or built.status)
            self._verify_build(plan,built.data,target)
            manifest.update(status='succeeded',sha256=digest(target),result=built.model_dump(),operation_id=built.operation_id)
            write_json(directory/'project.json',manifest); self.projects._finalize_job(built)
            motions = []
            for scene in plan['scenes']:
                roles = {e['role']:e['layer_id'] for e in scene['elements']}
                def motion(role,skill,start,duration,params):
                    motions.append(MotionRequest(project_id=project_id,composition_id=scene['composition_id'],
                        layer_id=roles[role],skill=skill,start_time=start,duration=duration,params=params))
                motion('heading','slide_in',0,.75,{'direction':'left','distance_ratio':.08,'overshoot':0,'motion_blur':False})
                motion('kicker','text_reveal',0,.75,{'direction':'left','padding_px':8,'motion_blur':False})
                motion('accent','scale_pop',.5,.6,{'initial_scale':1,'overshoot':0,'motion_blur':False})
                motions.append(MotionRequest(project_id=project_id,composition_id=plan['composition_id'],
                    layer_id=scene['master_layer_id'],skill='fade_in_out',start_time=scene['start_frame']/plan['brief']['fps'],
                    duration=scene['duration'],params={'fade_in':.5,'fade_out':.5,'motion_blur':False}))
            applied = BatchService(self.settings).apply(BatchRequest(motions=motions))
            if applied.status != 'succeeded': raise ValueError(applied.error or applied.status)
            data.update(project_path=applied.project_path,project_sha256=digest(Path(applied.project_path)),
                        build_operation_id=built.operation_id,batch_operation_id=applied.operation_id)
            self._audio_and_render(data,plan)
        except Exception as exc:
            data.update(status='failed',error=f'{type(exc).__name__}: {exc}')
        return self._result('storyboard_execute',self._commit_execution(data),project_id,data.get('project_path'))

    @staticmethod
    def _verify_build(plan, data, target):
        if not target.is_file() or target.stat().st_size < 64: raise ValueError('Storyboard AEP missing')
        if Path(data['project_path']).resolve() != target.resolve() or data.get('project_dirty'):
            raise ValueError('Storyboard path/clean-state mismatch')
        if len(data['compositions']) != len(plan['scenes'])+1: raise ValueError('Storyboard composition count mismatch')
        for comp in data['compositions']:
            if comp['width'] != plan['brief']['width'] or comp['height'] != plan['brief']['height'] or abs(comp['fps']-plan['brief']['fps']) > 1e-5:
                raise ValueError('Storyboard resolution/FPS mismatch')
        master = find_comp(data,plan['composition_id'])
        if len(master['layers']) != len(plan['scenes']): raise ValueError('Storyboard master layer count mismatch')
        fps = plan['brief']['fps']
        if abs(master['duration']*fps-plan['total_frames']) > .01: raise ValueError('Master duration mismatch')
        for scene in plan['scenes']:
            comp = find_comp(data,scene['composition_id'])
            if abs(comp['duration']-scene['duration']) > 1e-5: raise ValueError('Scene duration mismatch')
            layer = find_layer(master,scene['master_layer_id'])
            if layer['source_ae_id'] != comp['ae_id']: raise ValueError('Wrong scene dependency')
            for key,expected in (('start_time',scene['start_frame']/fps),('in_point',scene['start_frame']/fps),('out_point',scene['end_frame']/fps)):
                if abs(layer[key]-expected) > 1e-5: raise ValueError('Scene placement mismatch')
            if len(comp['layers']) != len(scene['elements']): raise ValueError('Scene layer count mismatch')
            for element in scene['elements']:
                actual = find_layer(comp,element['layer_id'])
                if element['layer']['kind']=='text':
                    if actual['text'] != element['layer']['text']: raise ValueError('Storyboard text mismatch')
                    style = actual['text_style']
                    role = element['role']; token = plan['tokens']['typography']['body' if role=='kicker' else role]
                    if style.get('box_overflow') or style.get('font_missing') or style['font'] != token['font']['postscript_name']:
                        raise ValueError('Storyboard typography missing or overflowing')
        StoryboardService._verify_text_geometry(plan,data)

    @staticmethod
    def _verify_text_geometry(plan, state):
        w,h = plan['brief']['width'],plan['brief']['height']
        top,right,bottom,left = plan['tokens']['safe_area']
        for scene in plan['scenes']:
            comp = find_comp(state,scene['composition_id'])
            for element in scene['elements']:
                if element['layer']['kind'] != 'text': continue
                layer = find_layer(comp,element['layer_id'])
                style,rect = layer['text_style'],layer['bounds']
                if style['box_overflow'] or style['font_missing']: raise ValueError('Text overflow/missing font')
                if layer.get('parent_ae_id') or layer.get('three_d'):
                    raise ValueError('Storyboard text geometry requires unparented 2D layers')
                def at_hold(name):
                    track = layer['transforms'][name]
                    if track.get('expression_present') or track.get('expression_enabled'):
                        raise ValueError('Storyboard text expression is protected')
                    matching = [s['value'] for s in track['samples'] if abs(s['time']-comp['duration']/2)<1e-5]
                    if not matching: raise ValueError('Native midpoint geometry sample missing')
                    return matching[0]
                position,anchor,scale,rotation = (at_hold(k) for k in ('position','anchor','scale','rotation'))
                angle = math.radians(rotation);c,s = math.cos(angle),math.sin(angle)
                corners=[]
                for x in (rect['left'],rect['left']+rect['width']):
                    for y in (rect['top'],rect['top']+rect['height']):
                        dx,dy = (x-anchor[0])*scale[0]/100,(y-anchor[1])*scale[1]/100
                        corners.append((position[0]+dx*c-dy*s,position[1]+dx*s+dy*c))
                if any(x < left*w-1 or y < top*h-1 or x > (1-right)*w+1 or y > (1-bottom)*h+1 for x,y in corners):
                    raise ValueError('Storyboard text exceeds hold safe area')

    def status(self, identifier):
        data = self._execution(identifier)
        if data['status']=='rendering':
            job = self.projects.job_status(data['render_job_id'])
            if job['status']=='succeeded':
                data.update(status='succeeded',render=job['result']['data'],sampled_visual_review='pending')
                self._commit_execution(data)
            elif job['status'] not in ('prepared','queued','running'):
                data.update(status='failed',error=job.get('result',{}).get('error') or job['status'])
                self._commit_execution(data)
        return self._result('storyboard_status',data,data['project_id'],data.get('project_path'))

    def _reserve_iteration(self, root, maximum, identifier):
        directory = self._dir('executions',root)/'iterations';directory.mkdir(exist_ok=True)
        for slot in range(1,maximum+1):
            try:
                with (directory/f'{slot}.json').open('x',encoding='utf-8') as stream:
                    json.dump({'execution_id':identifier,'timestamp':timestamp(),'attempt':slot},stream)
                return slot
            except FileExistsError: pass
        raise ValueError('Storyboard revision budget exhausted; stop and review with operator')

    def revise(self, request):
        previous = self.status(request.execution_id).data
        if previous['status'] != 'succeeded': raise ValueError('Verified completed render required before revision')
        plan,_ = self.load_plan(previous['plan_id'],previous['plan_sha256'])
        iterations = self._dir('executions',previous['root_execution_id'])/'iterations'
        if sum((iterations/f'{i}.json').exists() for i in range(1,plan['brief']['max_revisions']+1)) >= plan['brief']['max_revisions']:
            raise ValueError('Storyboard revision budget exhausted; stop and review with operator')
        index,role,value = parse_patch(request.instruction,len(plan['scenes']))
        manifest,source = self.projects.load(previous['project_id'])
        if digest(source) != request.base_aep_sha256: raise ValueError('Revision base AEP hash conflict')
        saved = read_json(source.parent/'version.json') if manifest.get('current_version') else manifest
        state = saved['result']['data']; scene = plan['scenes'][index]
        self._verify_text_geometry(plan,state)
        comp = find_comp(state,scene['composition_id'])
        elements = {e['role']:e for e in scene['elements']}
        texts = {r:find_layer(comp,elements[r]['layer_id'])['text'] for r in ('heading','body')}
        texts[role] = value
        if reading_seconds(**texts) > scene['hold_seconds']: raise ValueError('Patch exceeds scene reading budget')
        audio = AudioService(self.settings)
        audio._asset(plan['brief']['audio_bed_asset_id'],plan['audio_asset_manifest_sha256'])
        revisions = RevisionService(self.settings)
        prepared = revisions.plan(RevisionPlanRequest(project_id=previous['project_id'],base_sha256=request.base_aep_sha256,
            instruction=request.instruction,operations=[ContentPatch(action='content_set',request=ContentSet(
                project_id=previous['project_id'],composition_id=scene['composition_id'],layer_id=elements[role]['layer_id'],text=value))]))
        if prepared.status != 'succeeded': raise ValueError(prepared.error or prepared.status)
        identifier = uuid4().hex
        # Failed/unknown native attempts consume this root-wide budget, including branches.
        iteration = self._reserve_iteration(previous['root_execution_id'],plan['brief']['max_revisions'],identifier)
        data = {k:previous[k] for k in ('schema_version','root_execution_id','plan_id','plan_sha256','project_id','human_full_playback','human_artistic_approval')}
        data.update(execution_id=identifier,parent_execution_id=request.execution_id,iteration=iteration,status='revising',
            instruction=request.instruction,changed_interval=[scene['start_frame'],scene['end_frame']],
            input_aep_sha256=request.base_aep_sha256)
        self._commit_execution(data)
        try:
            applied = revisions.apply(RevisionApplyRequest(revision_id=prepared.data['revision_id'],
                plan_sha256=prepared.data['plan_sha256'],expected_current_sha256=request.base_aep_sha256))
            data.update(revision_operation_id=applied.operation_id,native_revision_status=applied.status)
            if applied.status != 'succeeded': raise ValueError(applied.error or applied.status)
            self._verify_text_geometry(plan,applied.data)
            data.update(project_path=applied.project_path,project_sha256=digest(Path(applied.project_path)),
                        revision_operation_id=applied.operation_id)
            self._audio_and_render(data,plan)
        except Exception as exc:
            data.update(status='failed',error=f'{type(exc).__name__}: {exc}')
        return self._result('storyboard_revise',self._commit_execution(data),data['project_id'],data.get('project_path'))

    def samples(self, request):
        data = self.status(request.execution_id).data
        if data['status'] != 'succeeded': raise ValueError('Verified render required')
        plan,_ = self.load_plan(data['plan_id'],data['plan_sha256'])
        video = Path(data['render']['video_path'])
        video = self.settings.contained_path(str(video.relative_to(self.settings.workspace)))
        if digest(video) != data['render']['video_sha256']: raise ValueError('Render video changed')
        job = Job(self.settings,'review_samples_create'); ffmpeg,_ = binaries(self.settings)
        samples = []
        for item in sample_schedule(plan,data.get('changed_interval')):
            sample_id = uuid4().hex; image = job.directory/(sample_id+'.png')
            completed = subprocess.run([ffmpeg,'-nostdin','-v','error','-n','-i',str(video),'-vf',
                f"select=eq(n\\,{item['frame']}),scale=960:-2",'-frames:v','1',str(image)],
                capture_output=True,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if completed.returncode or not image.is_file(): raise ValueError('Sample extraction failed')
            samples.append(item | {'sample_id':sample_id,'path':str(image),'sha256':digest(image)})
        if digest(video) != data['render']['video_sha256']: raise ValueError('Video changed during sampling')
        record = {'execution_id':request.execution_id,'video_sha256':data['render']['video_sha256'],
                  'samples':samples,'scope':'frames_only; no inferred viewing or listening'}
        ref = store_evidence(self.settings,'StoryboardSamples',record)
        result = OperationResult(operation_id=job.id,status='succeeded',data=record|{'samples_sha256':ref.sha256})
        job.record('succeeded',result=result.model_dump());return result

    def review(self, request):
        execution = self.status(request.execution_id).data
        samples = self._read_evidence(request.samples_sha256,'StoryboardSamples')
        if execution['status'] != 'succeeded' or samples['execution_id'] != request.execution_id or samples['video_sha256'] != execution['render']['video_sha256']:
            raise ValueError('Review evidence belongs to another execution/video')
        video = self.settings.contained_path(str(Path(execution['render']['video_path']).relative_to(self.settings.workspace)))
        if digest(video) != samples['video_sha256']: raise ValueError('Review video changed')
        known = {s['sample_id']:s for s in samples['samples']}
        selected = set(request.inspected_sample_ids)
        if len(selected) != len(request.inspected_sample_ids) or not selected.issubset(known): raise ValueError('Invalid inspected sample IDs')
        for item in known.values():
            path = self.settings.contained_path(str(Path(item['path']).relative_to(self.settings.workspace)))
            if digest(path) != item['sha256']: raise ValueError('Review image changed')
        if any(not set(issue.sample_ids).issubset(selected) for issue in request.issues): raise ValueError('Issue evidence must be inspected')
        if bool(request.issues) != (request.assessment=='needs_revision'): raise ValueError('Assessment/issues mismatch')
        prior = None
        if request.resolves_review_sha256:
            prior = self._read_evidence(request.resolves_review_sha256,'StoryboardReview')
            if prior['execution_id'] != execution.get('parent_execution_id') or prior['assessment'] != 'needs_revision':
                raise ValueError('Reverification must reference parent execution issues')
            if not any('changed_interval' in known[s]['reasons'] for s in selected):
                raise ValueError('Reverification requires an inspected changed-interval sample')
        record = request.model_dump(mode='json') | {'timestamp':timestamp(),'scope':'caller_attested_sampled_frames',
            'full_video_watched':False,'audio_listened':False,'reverification':prior is not None}
        ref = store_evidence(self.settings,'StoryboardReview',record)
        return self._result('storyboard_review',record|{'review_sha256':ref.sha256})
