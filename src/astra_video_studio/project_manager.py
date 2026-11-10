import hashlib
import json
import math
from pathlib import Path
from uuid import uuid4

from astra_video_studio.ae_bridge.runner import BridgeRunner
from astra_video_studio.config import Settings
from astra_video_studio.jobs import write_json, read_json, timestamp
from astra_video_studio.schemas import OperationResult, ProjectCreateRequest


def valid_id(value: str) -> str:
    if len(value) != 32 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("Expected a 32-character lowercase hexadecimal ID")
    return value


class ProjectManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.runner = BridgeRunner(settings)

    def managed_paths(self) -> list[str]:
        root = self.settings.contained_path("projects")
        paths = []
        if root.is_dir():
            for manifest in root.glob("*/project.json"):
                # Resolve each path again, rejecting symlinked project directories.
                checked = self.settings.contained_path(str(manifest.relative_to(self.settings.workspace)))
                data = json.loads(checked.read_text(encoding="utf-8"))
                if data.get("status") == "succeeded":
                    project_id = valid_id(data["project_id"])
                    path = self.settings.contained_path(f"projects/{project_id}/project.aep")
                    if path.is_file():
                        paths.append(str(path))
                    for version_manifest in path.parent.glob("versions/*/version.json"):
                        version_manifest = self.settings.contained_path(str(version_manifest.relative_to(self.settings.workspace)))
                        version = json.loads(version_manifest.read_text(encoding="utf-8"))
                        if version.get("status") == "succeeded":
                            candidate = version_manifest.parent / "project.aep"
                            if candidate.is_file():
                                paths.append(str(candidate))
        return paths

    def load(self, project_id: str) -> tuple[dict, Path]:
        project_id = valid_id(project_id)
        directory = self.settings.contained_path(f"projects/{project_id}")
        manifest_path = directory / "project.json"
        if not manifest_path.is_file():
            raise ValueError("Unknown project ID")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") != "succeeded":
            raise ValueError("Project creation has not been verified")
        suffix = f"versions/{valid_id(manifest['current_version'])}/project.aep" if manifest.get("current_version") else "project.aep"
        path = self.settings.contained_path(f"projects/{project_id}/{suffix}")
        return manifest, path

    def create(self, request: ProjectCreateRequest) -> OperationResult:
        project_id, composition_id, layer_id = uuid4().hex, uuid4().hex, uuid4().hex
        directory = self.settings.contained_path(f"projects/{project_id}")
        directory.mkdir(parents=True, exist_ok=False)
        target = directory / "project.aep"
        manifest = {"project_id": project_id, "status": "prepared", "request": request.model_dump(), "composition_id": composition_id, "layer_id": layer_id}
        write_json(directory / "project.json", manifest)
        result = self.runner.run("create", {
            "request": request.model_dump(), "project_path": target.as_posix(),
            "composition_id": composition_id, "layer_id": layer_id,
            "managed_paths": self.managed_paths(),
        })
        result.project_id, result.project_path = project_id, str(target)
        if result.status == "succeeded":
            try:
                self._verify_created(result.data, request, target, composition_id, layer_id)
                result.artifacts.append(str(target))
                manifest["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
            except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
                result.status = "failed"
                result.error = f"Saved-project verification failed: {exc}"
        manifest.update(status=result.status, operation_id=result.operation_id, result=result.model_dump())
        write_json(directory / "project.json", manifest)
        self._finalize_job(result)
        if result.status == "succeeded":
            write_json(self.settings.contained_path("bridge-validation.json"), {"operation_id": result.operation_id, "project_id": project_id, "ae_version": result.data["ae_version"]})
        return result

    @staticmethod
    def _verify_created(data, request, target, composition_id, layer_id):
        if not target.is_file() or target.stat().st_size < 64:
            raise ValueError("AEP file is missing or empty")
        if Path(data["project_path"]).resolve() != target.resolve():
            raise ValueError("AE acknowledged the wrong project path")
        if not data["ae_version"].startswith("25."):
            raise ValueError("Unexpected AE version")
        comps = data["compositions"]
        if len(comps) != 1:
            raise ValueError("Expected exactly one composition")
        comp = comps[0]
        if comp["composition_id"] != "astra:composition:" + composition_id or comp["name"] != request.name:
            raise ValueError("Composition identity mismatch")
        for key, expected in [("width", request.width), ("height", request.height), ("fps", request.fps), ("duration", request.duration)]:
            if not math.isclose(comp[key], expected, rel_tol=1e-5, abs_tol=1e-5):
                raise ValueError(f"Composition {key} mismatch")
        if len(comp["layers"]) != 1:
            raise ValueError("Expected exactly one title layer")
        layer = comp["layers"][0]
        if not math.isclose(layer["in_point"], 0, abs_tol=1e-5) or not math.isclose(layer["out_point"], request.duration, abs_tol=1e-5):
            raise ValueError("Title does not cover the full composition duration")
        # AE may normalize LF/CRLF to CR in TextDocument.
        if layer["layer_id"] != "astra:layer:" + layer_id or layer["text"].replace("\r\n", "\n").replace("\r", "\n") != request.title.replace("\r\n", "\n").replace("\r", "\n"):
            raise ValueError("Title identity/content mismatch")
        if len(layer["position"]) not in (2, 3) or len(layer["anchor"]) not in (2, 3):
            raise ValueError("Unexpected transform dimensions")
        if any(len(layer[key]) == 3 and not math.isclose(layer[key][2], 0, abs_tol=0.01) for key in ("position", "anchor")):
            raise ValueError("Unexpected nonzero Z on the 2D title")
        for actual, expected in zip(layer["position"][:2], [request.width / 2, request.height / 2]):
            if not math.isclose(actual, expected, abs_tol=0.01):
                raise ValueError("Title is not centered")
        bounds = layer["bounds"]
        expected_anchor = [bounds["left"] + bounds["width"] / 2, bounds["top"] + bounds["height"] / 2]
        if any(not math.isclose(a, b, abs_tol=0.01) for a, b in zip(layer["anchor"][:2], expected_anchor)):
            raise ValueError("Title anchor does not center its visible bounds")

    def inspect(self, project_id: str, sample_time: float = 0, include_world: bool = False) -> OperationResult:
        if not math.isfinite(sample_time) or not 0 <= sample_time <= 300:
            raise ValueError("Sample time must be finite and between 0 and 300 seconds")
        manifest, path = self.load(project_id)
        result = self.runner.run("inspect", {"project_path": path.as_posix(), "id_map": manifest.get("id_map"), "sample_time": sample_time, "include_world": include_world})
        result.project_id, result.project_path = project_id, str(path)
        self._finalize_job(result)
        return result

    def _finalize_job(self, result: OperationResult) -> None:
        path = self.settings.contained_path(f"jobs/{valid_id(result.operation_id)}/job.json")
        data = read_json(path)
        data.update(status=result.status, result=result.model_dump())
        data["events"].append({"timestamp": timestamp(), "status": result.status, "stage": "service_verification"})
        write_json(path, data)

    def job_status(self, operation_id: str) -> dict:
        path = self.settings.contained_path(f"jobs/{valid_id(operation_id)}/job.json")
        if not path.is_file():
            raise ValueError("Unknown operation ID")
        data = read_json(path)
        failure = path.parent / 'worker-failure.json'
        if data.get('action') in ('preview_render', 'render_final') and data.get('status') in ('prepared', 'queued', 'running') and failure.is_file():
            failed = json.loads(failure.read_text(encoding='utf-8'))
            result = OperationResult.model_validate(failed['result'])
            if failed.get('operation_id') != operation_id or result.operation_id != operation_id or result.status != 'failed':
                raise ValueError('Invalid preview worker failure record')
            data.update(status='failed', result=result.model_dump(), worker_failure_record=str(failure))
        if (path.parent / "cancel-requested").exists():
            data["cancel_requested"] = True
        claim_path=self.settings.contained_path(f'queue/claims/{operation_id}.json')
        if claim_path.is_file():
            claim=read_json(claim_path)
            if (claim.get('job_id')==operation_id and claim.get('release_reason')=='reconciled_never_started'
                and claim.get('reconciled_journal_sha256')==hashlib.sha256(path.read_bytes()).hexdigest()
                and claim.get('released') and not claim.get('worker_started')):
                data.update(status='cancelled',recovery_state='not_started_released',
                    result=OperationResult(operation_id=operation_id,status='cancelled',error='Owner exited before worker start; queue slot released explicitly, no replay').model_dump())
        if data['status'] not in ('succeeded','failed','blocked','busy','timeout','cancelled'):
            from astra_video_studio.lifecycle import owner_state
            data['owner_state']=owner_state(data.get('owner'))
            if data['owner_state']!='alive':data['recovery_hint']='Call job_reconcile; do not resubmit uncertain work'
        pointer=self.settings.contained_path(f'reconciliations/{operation_id}.json')
        if pointer.is_file() and not self.settings.contained_path('ae-pending.json').exists():
            receipt=read_json(pointer);sha=receipt.get('sha256','')
            if len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha):raise ValueError('Invalid recovery evidence hash')
            evidence=self.settings.contained_path(f'responses/{sha}.json')
            if hashlib.sha256(evidence.read_bytes()).hexdigest()!=sha:raise ValueError('Recovery evidence changed')
            recovered=read_json(evidence)
            state=recovered.get('result',{})
            if (recovered.get('kind')=='JobReconciliation' and state.get('job_id')==operation_id
                and state.get('journal_sha256')==hashlib.sha256(path.read_bytes()).hexdigest()
                and state.get('state')=='readonly_quarantine_released'):
                data.update(status='blocked',recovery_state='readonly_quarantine_released',
                    result=OperationResult(operation_id=operation_id,status='blocked',data={'reconciliation_sha256':sha},
                        error='Completed native read quarantine released explicitly; lost service result was not promoted. A new guarded read is allowed.').model_dump())
        return data
