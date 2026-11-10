"""Safe, versioned transform and motion operations on verified Astra projects."""
import hashlib
import json
import math
import shutil
from uuid import uuid4

from astra_video_studio.config import Settings
from astra_video_studio.jobs import write_json
from astra_video_studio.motion_engine.schemas import MotionRequest, TransformRequest
from astra_video_studio.motion_engine.skills import plan
from astra_video_studio.project_manager import ProjectManager


def find_target(data: dict, composition_id: str, layer_id: str) -> tuple[dict, dict]:
    comps = [c for c in data["compositions"] if c["composition_id"] == "astra:composition:" + composition_id]
    if len(comps) != 1:
        raise ValueError("Composition ID is absent or not unique")
    layers = [l for l in comps[0]["layers"] if l["layer_id"] == "astra:layer:" + layer_id]
    if len(layers) != 1:
        raise ValueError("Layer ID is absent or not unique")
    return comps[0], layers[0]


def values_match(actual, expected) -> bool:
    if not isinstance(actual, list):
        actual = [actual]
    if not isinstance(expected, list):
        expected = [expected]
    return len(actual) >= len(expected) and all(math.isclose(a, b, rel_tol=1e-5, abs_tol=0.001) for a, b in zip(actual[:len(expected)], expected, strict=True))


def verify_edit(before: dict, after: dict, composition_id: str, layer_id: str, expected: dict, motion: bool) -> None:
    if motion and expected.get('mask_reveal'):
        from astra_video_studio.motion_engine.batch import verify_batch
        verify_batch(before, after, [{'composition_id': composition_id, 'layer_id': layer_id, 'plan': expected}])
        return
    comp, layer = find_target(after, composition_id, layer_id)
    old_comp, old_layer = find_target(before, composition_id, layer_id)
    if [(c["composition_id"], [l["layer_id"] for l in c["layers"]]) for c in before["compositions"]] != [(c["composition_id"], [l["layer_id"] for l in c["layers"]]) for c in after["compositions"]]:
        raise ValueError("Composition/layer identities changed")
    for name in ("width", "height", "fps", "duration"):
        if comp[name] != old_comp[name]:
            raise ValueError("Composition settings changed")
    if layer["text"] != old_layer["text"]:
        raise ValueError("Text content changed")
    for previous_comp, current_comp in zip(before["compositions"], after["compositions"], strict=True):
        if previous_comp["composition_id"] != "astra:composition:" + composition_id:
            if current_comp != previous_comp:
                raise ValueError("Unrelated composition changed")
        else:
            for old, new in zip(previous_comp["layers"], current_comp["layers"], strict=True):
                if old["layer_id"] != "astra:layer:" + layer_id and old != new:
                    raise ValueError("Unrelated layer changed")
            allowed_comp = {"layers", "motion_blur", "shutter_angle"} if motion else {"layers"}
            if any(current_comp.get(k) != v for k, v in previous_comp.items() if k not in allowed_comp):
                raise ValueError("Unrelated composition setting changed")
    allowed_layer = {"transforms", "position", "anchor", "motion_blur", "animation_summary"} if motion else {"transforms", "position", "anchor"}
    if motion and 'animation_summary' in old_layer:
        summary = dict(old_layer['animation_summary'])
        summary['key_count'] += sum(len(t['keys']) for t in expected['tracks'])
        if layer['animation_summary'] != summary:
            raise ValueError('Unexpected animation summary change')
    if any(layer.get(k) != v for k, v in old_layer.items() if k not in allowed_layer):
        raise ValueError("Unrelated target layer metadata changed")
    touched = {t["property"] for t in expected["tracks"]} if motion else set(expected)
    for name, previous in old_layer["transforms"].items():
        if name not in touched and layer["transforms"][name] != previous:
            raise ValueError(f"Unrelated transform changed: {name}")
    if motion:
        if expected["motion_blur"] and not (comp["motion_blur"] and layer["motion_blur"]):
            raise ValueError("Motion blur was not enabled at both levels")
        for item in expected["tracks"]:
            current = layer["transforms"][item["property"]]["keys"]
            original = old_layer["transforms"][item["property"]]["keys"]
            if len(current) != len(original) + len(item["keys"]):
                raise ValueError("Unexpected keyframe count")
            for key in item["keys"]:
                matches = [k for k in current if math.isclose(k["time"], key["time"], abs_tol=1e-5)]
                if len(matches) != 1 or not values_match(matches[0]["value"], key["value"]):
                    raise ValueError("Keyframe value/time mismatch")
                actual = matches[0]
                for side in ("in", "out"):
                    if actual[side + "_type"] != key[side + "_type"]:
                        raise ValueError("Keyframe interpolation mismatch")
                    if key[side + "_type"] == "bezier":
                        eases = actual[side + "_ease"]
                        if not values_match([ease["speed"] for ease in eases], key[side + "_speed"]) or any(not math.isclose(ease["influence"], 100 / 3, abs_tol=0.001) for ease in eases):
                            raise ValueError("Temporal easing speed/influence mismatch")
            for previous in original:
                matches = [k for k in current if math.isclose(k["time"], previous["time"], abs_tol=1e-5)]
                if len(matches) != 1 or matches[0] != previous:
                    raise ValueError("Previously existing keyframe changed")
    else:
        for name, value in expected.items():
            if layer["transforms"][name]["keys"] or not values_match(layer["transforms"][name]["value"], list(value) if isinstance(value, tuple) else value):
                raise ValueError(f"Static transform mismatch: {name}")


class MotionService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.projects = ProjectManager(settings)

    def apply(self, request: MotionRequest):
        return self._edit(request, True)

    def transform(self, request: TransformRequest):
        return self._edit(request, False)

    def _edit(self, request, motion: bool):
        manifest, source = self.projects.load(request.project_id)
        original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        source_manifest = json.loads((source.parent / "version.json").read_text(encoding="utf-8")) if manifest.get("current_version") else manifest
        if original_hash != source_manifest.get("sha256"):
            raise ValueError("Saved project changed outside Astra; preserve/review it before editing")
        inspected = self.projects.inspect(request.project_id, request.start_time if motion else 0)
        if inspected.status != "succeeded":
            return inspected
        comp, layer = find_target(inspected.data, request.composition_id, request.layer_id)
        if layer.get("locked") or not layer.get("editable_2d", True):
            raise ValueError("Target layer is locked or does not support these 2D transforms")
        if motion:
            expected = plan(request, comp, layer)
        else:
            expected = request.values.model_dump(exclude_none=True)
            for name in expected:
                prop = layer["transforms"][name]
                if not prop.get("available", True) or prop.get("separated") or prop["keys"] or prop["expression_enabled"]:
                    raise ValueError("Static transforms cannot replace animated or expression-driven properties")
        version_id = uuid4().hex
        directory = self.settings.contained_path(f"projects/{request.project_id}/versions/{version_id}")
        directory.mkdir(parents=True, exist_ok=False)
        snapshot = directory / "source-snapshot.aep"
        shutil.copyfile(source, snapshot)
        if hashlib.sha256(snapshot.read_bytes()).hexdigest() != original_hash:
            raise ValueError("Source changed while snapshotting; refusing edit")
        target = directory / "project.aep"
        payload = {"project_path": source.as_posix(), "version_path": target.as_posix(), "id_map": manifest.get("id_map"), "composition_id": request.composition_id, "layer_id": request.layer_id, "sample_time": request.start_time if motion else 0, "plan" if motion else "values": expected}
        version = {"version_id": version_id, "source": str(source), "source_sha256": original_hash, "snapshot": str(snapshot), "status": "prepared", "request": request.model_dump(), "plan" if motion else "values": expected}
        write_json(directory / "version.json", version)
        result = self.projects.runner.run("motion" if motion else "transform", payload)
        result.project_id, result.project_path = request.project_id, str(target)
        if result.status == "succeeded":
            try:
                if not target.is_file() or target.stat().st_size < 64:
                    raise ValueError("No saved version file")
                if hashlib.sha256(source.read_bytes()).hexdigest() != original_hash:
                    raise ValueError("Source AEP was modified")
                from pathlib import Path
                if Path(result.data["project_path"]).resolve() != target.resolve():
                    raise ValueError("AE acknowledged the wrong version path")
                verify_edit(inspected.data, result.data, request.composition_id, request.layer_id, expected, motion)
                version["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
                manifest["current_version"] = version_id
                result.artifacts.extend([str(target), str(snapshot), str(directory / "version.json")])
                result.data["version_id"] = version_id
                result.data["applied_plan" if motion else "applied_transforms"] = expected
            except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
                result.status, result.error = "failed", f"Version verification failed: {exc}"
        version.update(status=result.status, operation_id=result.operation_id, result=result.model_dump())
        write_json(directory / "version.json", version)
        if result.status == "succeeded":
            write_json(self.settings.contained_path(f"projects/{request.project_id}/project.json"), manifest)
        self.projects._finalize_job(result)
        return result
