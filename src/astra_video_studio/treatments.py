"""Allowlisted effects and basic masks, with immutable source/version lifecycle."""
import copy
import json
import math
import shutil
from uuid import uuid4
from pathlib import Path
from typing import Literal
from pydantic import Field, model_validator

from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import write_json
from astra_video_studio.motion_engine.schemas import Target, StrictModel
from astra_video_studio.motion_engine.service import find_target
from astra_video_studio.project_manager import ProjectManager


class BlurParams(StrictModel):
    amount: float = Field(default=4, ge=0, le=100)
    repeat_edges: bool = True


class FillParams(StrictModel):
    color: tuple[float, float, float] = (0.3, 0.85, 1.0)

    @model_validator(mode="after")
    def color_range(self):
        if any(not 0 <= c <= 1 for c in self.color):
            raise ValueError("Color components must be between 0 and 1")
        return self


class EffectRequest(Target):
    effect: Literal["gaussian_blur", "fill"]
    params: BlurParams | FillParams = Field(default_factory=BlurParams)

    @model_validator(mode="before")
    @classmethod
    def select_params(cls, value):
        if isinstance(value, dict) and value.get("effect") in ("gaussian_blur", "fill"):
            value = dict(value)
            params = value.get("params", {})
            if hasattr(params, "model_dump"):
                params = params.model_dump()
            value["params"] = (BlurParams if value["effect"] == "gaussian_blur" else FillParams).model_validate(params)
        return value


class MaskRequest(Target):
    shape: Literal["rectangle", "ellipse"] = "rectangle"
    bounds: tuple[float, float, float, float]
    mode: Literal["add", "subtract"] = "add"
    feather: float = Field(default=0, ge=0, le=500)
    opacity: float = Field(default=100, ge=0, le=100)
    inverted: bool = False

    @model_validator(mode="after")
    def bounds_limits(self):
        x, y, width, height = self.bounds
        if abs(x) > 100000 or abs(y) > 100000 or not 0 < width <= 20000 or not 0 < height <= 20000:
            raise ValueError("Mask bounds exceed limits or have nonpositive dimensions")
        return self


def mask_path(request: MaskRequest) -> dict:
    x, y, w, h = request.bounds
    if request.shape == "rectangle":
        vertices = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
        incoming = outgoing = [[0, 0] for _ in range(4)]
    else:
        rx, ry, k = w / 2, h / 2, 0.5522847498307936
        vertices = [[x + rx, y], [x + w, y + ry], [x + rx, y + h], [x, y + ry]]
        incoming = [[-rx * k, 0], [0, -ry * k], [rx * k, 0], [0, ry * k]]
        outgoing = [[rx * k, 0], [0, ry * k], [-rx * k, 0], [0, -ry * k]]
    return {"vertices": vertices, "in_tangents": incoming, "out_tangents": outgoing, "closed": True}


def close_values(actual, expected) -> bool:
    if isinstance(expected, (tuple, list)):
        return isinstance(actual, list) and len(actual) == len(expected) and all(close_values(a, b) for a, b in zip(actual, expected, strict=True))
    return math.isclose(actual, expected, rel_tol=1e-5, abs_tol=0.001)


def verify_treatment(before: dict, after: dict, request, item_name: str, path: dict | None) -> None:
    _, old = find_target(before, request.composition_id, request.layer_id)
    _, new = find_target(after, request.composition_id, request.layer_id)
    field = "masks" if path is not None else "effects"
    previous, current = old[field], new[field]
    if len(current) != len(previous) + 1 or current[:-1] != previous or current[-1]["name"] != item_name:
        raise ValueError("Existing treatment changed or new item absent")
    item = current[-1]
    if field == "effects":
        expected_match = "ADBE Gaussian Blur 2" if request.effect == "gaussian_blur" else "ADBE Fill"
        if item["match_name"] != expected_match or not item["enabled"]:
            raise ValueError("Effect type/enabled state mismatch")
        if request.effect == "fill":
            if not close_values(item["parameters"]["color"][:3], request.params.color):
                raise ValueError("Effect color mismatch")
        elif not close_values(item["parameters"]["amount"], request.params.amount) or bool(item["parameters"]["repeat_edges"]) != request.params.repeat_edges:
            raise ValueError("Blur parameters mismatch")
    else:
        for key in ("vertices", "in_tangents", "out_tangents"):
            if not close_values(item["path"][key], path[key]):
                raise ValueError("Mask path mismatch")
        if not item["path"]["closed"] or item["mode"] != request.mode or item["inverted"] != request.inverted:
            raise ValueError("Mask mode/inversion mismatch")
        if not close_values(item["opacity"], request.opacity) or not close_values(item["feather"], [request.feather] * 2):
            raise ValueError("Mask opacity/feather mismatch")
    normalized = copy.deepcopy(after)
    _, target = find_target(normalized, request.composition_id, request.layer_id)
    target[field] = copy.deepcopy(previous)
    # sourceRectAtTime can be affected by a treatment on some layer types.
    target["bounds"] = copy.deepcopy(old["bounds"])
    if normalized["compositions"] != before["compositions"] or normalized.get("footage", []) != before.get("footage", []):
        raise ValueError("Unrelated project/layer state changed")


class TreatmentService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.projects = ProjectManager(settings)

    def apply(self, request: EffectRequest | MaskRequest):
        manifest, source = self.projects.load(request.project_id)
        source_hash = digest(source)
        previous = json.loads((source.parent / "version.json").read_text()) if manifest.get("current_version") else manifest
        if source_hash != previous.get("sha256"):
            raise ValueError("Saved source changed outside Astra")
        inspected = self.projects.inspect(request.project_id)
        if inspected.status != "succeeded":
            return inspected
        _, layer = find_target(inspected.data, request.composition_id, request.layer_id)
        if layer.get("locked") or not layer.get("editable_2d", False):
            raise ValueError("Target is locked or unsupported")
        is_mask = isinstance(request, MaskRequest)
        action = "mask" if is_mask else "effect"
        item_id, version_id = uuid4().hex, uuid4().hex
        item_name = f"Astra {action} [{item_id}]"
        path = mask_path(request) if is_mask else None
        directory = self.settings.contained_path(f"projects/{request.project_id}/versions/{version_id}")
        directory.mkdir(parents=True, exist_ok=False)
        target, snapshot = directory / "project.aep", directory / "source-snapshot.aep"
        shutil.copyfile(source, snapshot)
        if digest(snapshot) != source_hash or digest(source) != source_hash:
            raise ValueError("Source changed during snapshot")
        payload = {"project_path": source.as_posix(), "version_path": target.as_posix(), "id_map": manifest.get("id_map"), "composition_id": request.composition_id, "layer_id": request.layer_id, "request": request.model_dump(), "item_name": item_name, "mask_path": path}
        version = {"version_id": version_id, "kind": action, "status": "prepared", "source": str(source), "source_sha256": source_hash, "snapshot": str(snapshot), "request": request.model_dump()}
        write_json(directory / "version.json", version)
        result = self.projects.runner.run(action, payload)
        result.project_id, result.project_path = request.project_id, str(target)
        if result.status == "succeeded":
            try:
                if not target.is_file() or target.stat().st_size < 64 or Path(result.data["project_path"]).resolve() != target.resolve():
                    raise ValueError("No valid saved output version")
                if digest(source) != source_hash or digest(snapshot) != source_hash:
                    raise ValueError("Source/snapshot changed")
                verify_treatment(inspected.data, result.data, request, item_name, path)
                version["sha256"] = digest(target)
                manifest["current_version"] = version_id
                result.data.update(version_id=version_id, item_id=item_id)
                result.artifacts.extend([str(target), str(snapshot), str(directory / "version.json")])
            except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
                result.status, result.error = "failed", f"Treatment verification failed: {exc}"
        version.update(status=result.status, result=result.model_dump(), operation_id=result.operation_id)
        write_json(directory / "version.json", version)
        if result.status == "succeeded":
            write_json(self.settings.contained_path(f"projects/{request.project_id}/project.json"), manifest)
        self.projects._finalize_job(result)
        return result
