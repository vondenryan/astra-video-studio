"""Preflight and verify a bounded multi-layer motion batch in one saved version."""
import copy
import json
import math
import shutil
from uuid import uuid4
from pydantic import Field, model_validator

from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import write_json
from astra_video_studio.motion_engine.schemas import StrictModel, MotionRequest, SlideParams, ScalePopParams, RevealParams, PARAMS
from astra_video_studio.motion_engine.service import find_target, values_match
from astra_video_studio.motion_engine.skills import plan
from astra_video_studio.project_manager import ProjectManager


class BatchRequest(StrictModel):
    motions: list[MotionRequest] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def same_project(self):
        if len({m.project_id for m in self.motions}) != 1:
            raise ValueError("Batch must target one project")
        return self


class StaggerRequest(StrictModel):
    project_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    composition_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    layer_ids: list[str] = Field(min_length=1, max_length=20)
    start_time: float = Field(default=0, ge=0, le=300)
    duration: float = Field(default=0.8, gt=0, le=300)
    interval: float = Field(default=0.12, ge=0.01, le=5)
    skill: str = "slide_in"
    params: dict = Field(default_factory=dict)
    reverse: bool = False

    @model_validator(mode="after")
    def validate_targets(self):
        from astra_video_studio.project_manager import valid_id
        if len(set(self.layer_ids)) != len(self.layer_ids):
            raise ValueError("Stagger layer IDs must be unique")
        for value in self.layer_ids: valid_id(value)
        if self.skill not in PARAMS:
            raise ValueError("Unknown stagger base skill")
        PARAMS[self.skill].model_validate(self.params)
        return self

    def batch(self) -> BatchRequest:
        layers = list(reversed(self.layer_ids)) if self.reverse else self.layer_ids
        return BatchRequest(motions=[MotionRequest(project_id=self.project_id, composition_id=self.composition_id, layer_id=layer, skill=self.skill, start_time=self.start_time + i * self.interval, duration=self.duration, params=self.params) for i, layer in enumerate(layers)])


def compile_batch(request: BatchRequest, data: dict) -> list[dict]:
    compiled, intervals = [], {}
    reveals = set()
    position_history = {}
    for motion in sorted(request.motions,key=lambda item:item.start_time):
        comp, layer = find_target(data, motion.composition_id, motion.layer_id)
        if layer.get("locked") or not layer.get("editable_2d", True):
            raise ValueError("Locked or unsupported batch target")
        working=copy.deepcopy(layer)
        target_key=(motion.composition_id,motion.layer_id)
        existing=layer.get('transforms',{}).get('position',{}).get('keys',[])
        candidates=list(position_history.get(target_key,[]))
        if existing and existing[-1]['time']<motion.start_time-1e-6:
            candidates.append((existing[-1]['time'],existing[-1]['value']))
        earlier=[(t,value) for t,value in candidates if t<motion.start_time-1e-6]
        if earlier: working['position']=max(earlier,key=lambda pair:pair[0])[1]
        result = plan(motion, comp, working)
        for track in result["tracks"]:
            key = (motion.composition_id, motion.layer_id, track["property"])
            span = (track["keys"][0]["time"], track["keys"][-1]["time"])
            if any(not (span[1] < a - 1e-6 or span[0] > b + 1e-6) for a, b in intervals.get(key, [])):
                raise ValueError("Overlapping batch tracks")
            intervals.setdefault(key, []).append(span)
            if track['property']=='position': position_history.setdefault(target_key,[]).append((span[1],track['keys'][-1]['value']))
        if result.get("mask_reveal"):
            key = (motion.composition_id, motion.layer_id)
            if key in reveals:
                raise ValueError("Only one reveal mask per layer in a batch")
            reveals.add(key)
        compiled.append({"composition_id": motion.composition_id, "layer_id": motion.layer_id, "plan": result})
    return compiled


def verify_batch(before: dict, after: dict, motions: list[dict]) -> None:
    normalized = copy.deepcopy(after)
    targets = {(m["composition_id"], m["layer_id"]) for m in motions}
    for comp_id, layer_id in targets:
        old_comp, old = find_target(before, comp_id, layer_id)
        comp, layer = find_target(normalized, comp_id, layer_id)
        plans = [m["plan"] for m in motions if m["composition_id"] == comp_id and m["layer_id"] == layer_id]
        if any(p["motion_blur"] for p in plans) and not (comp["motion_blur"] and layer["motion_blur"]):
            raise ValueError("Batch blur not enabled")
        grouped = {}
        for motion in plans:
            for item in motion["tracks"]: grouped.setdefault(item["property"], []).extend(item["keys"])
        for name, keys in grouped.items():
            actual = layer["transforms"][name]
            previous = old["transforms"][name]
            if actual["expression_enabled"] or len(actual["keys"]) != len(previous["keys"]) + len(keys):
                raise ValueError("Batch key count/expression mismatch")
            for key in keys:
                match = [k for k in actual["keys"] if math.isclose(k["time"], key["time"], abs_tol=1e-5)]
                if len(match) != 1 or not values_match(match[0]["value"], key["value"]):
                    raise ValueError("Batch key value/time mismatch")
                for side in ("in", "out"):
                    if match[0][side + "_type"] != key[side + "_type"]:
                        raise ValueError("Batch interpolation mismatch")
                    if key[side + "_type"] == "bezier":
                        ease = match[0][side + "_ease"]
                        if not values_match([e["speed"] for e in ease], key[side + "_speed"]) or any(not math.isclose(e["influence"], 100 / 3, abs_tol=0.001) for e in ease):
                            raise ValueError("Batch easing mismatch")
            for key in previous["keys"]:
                if key not in actual["keys"]: raise ValueError("Previous key changed")
            layer["transforms"][name] = copy.deepcopy(previous)
        reveal = [p["mask_reveal"] for p in plans if p.get("mask_reveal")]
        if reveal:
            if len(layer["masks"]) != len(old["masks"]) + 1 or layer["masks"][:-1] != old["masks"]:
                raise ValueError("Reveal replaced prior masks")
            current = layer["masks"][-1]
            if current["mode"] != "add" or len(current["path_keys"]) != len(reveal[0]["keys"]):
                raise ValueError("Reveal mask mode/keys mismatch")
            for a, b in zip(current["path_keys"], reveal[0]["keys"], strict=True):
                if not math.isclose(a["time"], b["time"], abs_tol=1e-5) or any(not values_match(x, y) for x, y in zip(a["vertices"], b["vertices"], strict=True)):
                    raise ValueError("Reveal geometry/time mismatch")
            layer["masks"] = copy.deepcopy(old["masks"])
        if 'animation_summary' in old:
            summary = dict(old['animation_summary'])
            summary['key_count'] += sum(len(t['keys']) for p in plans for t in p['tracks']) + sum(len(p['mask_reveal']['keys']) for p in plans if p.get('mask_reveal'))
            if layer['animation_summary'] != summary:
                raise ValueError('Unexpected batch animation summary change')
            layer['animation_summary'] = copy.deepcopy(old['animation_summary'])
        for field in ("position", "anchor", "motion_blur"):
            layer[field] = copy.deepcopy(old[field])
    for comp_id in {m['composition_id'] for m in motions}:
        original_comp = next(c for c in before['compositions'] if c['composition_id'] == 'astra:composition:' + comp_id)
        current_comp = next(c for c in normalized['compositions'] if c['composition_id'] == 'astra:composition:' + comp_id)
        current_comp['motion_blur'], current_comp['shutter_angle'] = original_comp['motion_blur'], original_comp['shutter_angle']
    if normalized["compositions"] != before["compositions"] or normalized.get("footage", []) != before.get("footage", []):
        raise ValueError("Unrelated batch state changed")


class BatchService:
    def __init__(self, settings: Settings):
        self.settings, self.projects = settings, ProjectManager(settings)

    def apply(self, request: BatchRequest):
        project_id = request.motions[0].project_id
        manifest, source = self.projects.load(project_id)
        source_hash = digest(source)
        saved = json.loads((source.parent / 'version.json').read_text()) if manifest.get('current_version') else manifest
        if source_hash != saved.get('sha256'): raise ValueError('Source changed outside Astra')
        inspected = self.projects.inspect(project_id)
        if inspected.status != 'succeeded': return inspected
        compiled = compile_batch(request, inspected.data)
        version_id = uuid4().hex
        directory = self.settings.contained_path(f'projects/{project_id}/versions/{version_id}')
        directory.mkdir(parents=True, exist_ok=False)
        snapshot, target = directory / 'source-snapshot.aep', directory / 'project.aep'
        shutil.copyfile(source, snapshot)
        if digest(snapshot) != source_hash: raise ValueError('Snapshot mismatch')
        version = {'version_id': version_id, 'kind': 'batch_motion', 'status': 'prepared', 'source': str(source), 'source_sha256': source_hash, 'snapshot': str(snapshot), 'motions': compiled}
        write_json(directory / 'version.json', version)
        result = self.projects.runner.run('batch_motion', {'project_path': source.as_posix(), 'version_path': target.as_posix(), 'id_map': manifest.get('id_map'), 'motions': compiled})
        result.project_id, result.project_path = project_id, str(target)
        if result.status == 'succeeded':
            try:
                if digest(source) != source_hash or not target.is_file() or digest(snapshot) != source_hash: raise ValueError('Source/output mismatch')
                verify_batch(inspected.data, result.data, compiled)
                version['sha256'] = digest(target)
                manifest['current_version'] = version_id
                result.data.update(version_id=version_id, applied_motions=compiled)
                result.artifacts.extend([str(target), str(snapshot), str(directory / 'version.json')])
            except (ValueError, OSError, KeyError, TypeError) as error:
                result.status, result.error = 'failed', 'Batch verification failed: ' + str(error)
        version.update(status=result.status, operation_id=result.operation_id, result=result.model_dump())
        write_json(directory / 'version.json', version)
        if result.status == 'succeeded': write_json(self.settings.contained_path(f'projects/{project_id}/project.json'), manifest)
        self.projects._finalize_job(result)
        return result
