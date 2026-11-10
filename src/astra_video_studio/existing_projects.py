"""Open approved AEP sources as copies; explicitly save active state as a version."""
import hashlib
import json
from pathlib import Path
import shutil
from uuid import uuid4

from astra_video_studio.config import Settings
from astra_video_studio.jobs import write_json
from astra_video_studio.project_identity import build_id_map, mapped_state, extend_project_ids
from astra_video_studio.project_manager import ProjectManager
from astra_video_studio.schemas import ProjectOpenCopyRequest


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


class ExistingProjectService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.projects = ProjectManager(settings)

    def open_copy(self, request: ProjectOpenCopyRequest):
        source = self.settings.import_path(request.source_path)
        source_hash = digest(source)
        project_id = uuid4().hex
        directory = self.settings.contained_path(f"projects/{project_id}")
        directory.mkdir(parents=True, exist_ok=False)
        backup, target = directory / "original-source.aep", directory / "project.aep"
        shutil.copyfile(source, backup)
        shutil.copyfile(backup, target)
        if any(digest(path) != source_hash for path in (source, backup, target)):
            raise ValueError("Source changed while copying; refusing to open inconsistent copies")
        manifest = {"project_id": project_id, "kind": "opened_copy", "status": "prepared", "source_path": str(source), "source_sha256": source_hash, "backup_path": str(backup)}
        write_json(directory / "project.json", manifest)
        result = self.projects.runner.run("open_copy", {"project_path": target.as_posix(), "source_path": source.as_posix(), "managed_paths": self.projects.managed_paths()})
        result.project_id, result.project_path = project_id, str(target)
        if result.status == "succeeded":
            try:
                if Path(result.data["project_path"]).resolve() != target.resolve() or not result.data["ae_version"].startswith("25."):
                    raise ValueError("AE opened the wrong file/version")
                if any(digest(path) != source_hash for path in (source, backup, target)):
                    raise ValueError("Source/backup/copy was unexpectedly modified")
                mapping = build_id_map(result.data)
                result.data = mapped_state(result.data, mapping)
                manifest.update(id_map=mapping, sha256=source_hash)
                result.artifacts.extend([str(target), str(backup), str(directory / "project.json")])
                result.data["source_path"], result.data["backup_path"] = str(source), str(backup)
                missing = [f["path"] for f in result.data.get("footage", []) if f["missing"]]
                result.data["warnings"] = [f"Missing linked media: {path}" for path in missing]
            except (OSError, ValueError, TypeError, KeyError) as exc:
                result.status, result.error = "failed", f"Working-copy verification failed: {exc}"
        manifest.update(status=result.status, operation_id=result.operation_id, result=result.model_dump())
        write_json(directory / "project.json", manifest)
        self.projects._finalize_job(result)
        return result

    def save(self, project_id: str):
        manifest, source = self.projects.load(project_id)
        source_hash = digest(source)
        inspected = self.projects.inspect(project_id)
        if inspected.status != "succeeded":
            return inspected
        mapping = extend_project_ids(manifest, inspected.data)
        expected = mapped_state(inspected.data, mapping)
        version_id = uuid4().hex
        directory = self.settings.contained_path(f"projects/{project_id}/versions/{version_id}")
        directory.mkdir(parents=True, exist_ok=False)
        target, snapshot = directory / "project.aep", directory / "source-snapshot.aep"
        shutil.copyfile(source, snapshot)
        if digest(snapshot) != source_hash or digest(source) != source_hash:
            raise ValueError("Source changed while snapshotting")
        version = {"version_id": version_id, "kind": "explicit_save", "source": str(source), "source_sha256": source_hash, "snapshot": str(snapshot), "status": "prepared", "id_map": mapping}
        write_json(directory / "version.json", version)
        result = self.projects.runner.run("save_version", {"project_path": source.as_posix(), "version_path": target.as_posix(), "id_map": mapping})
        result.project_id, result.project_path = project_id, str(target)
        if result.status == "succeeded":
            try:
                if not target.is_file() or target.stat().st_size < 64 or Path(result.data["project_path"]).resolve() != target.resolve():
                    raise ValueError("No valid saved AEP at the expected path")
                if digest(source) != source_hash or digest(snapshot) != source_hash:
                    raise ValueError("Saved source/snapshot changed")
                if result.data["compositions"] != expected["compositions"] or result.data.get("footage", []) != expected.get("footage", []):
                    raise ValueError("Saved state differs after reopening")
                if result.data.get("project_dirty") is not False:
                    raise ValueError("Reopened project is not clean")
                version["sha256"] = digest(target)
                manifest.update(current_version=version_id, id_map=mapping)
                result.data["version_id"] = version_id
                result.artifacts.extend([str(target), str(snapshot), str(directory / "version.json")])
            except (OSError, ValueError, TypeError, KeyError) as exc:
                result.status, result.error = "failed", f"Saved-version verification failed: {exc}"
        version.update(status=result.status, operation_id=result.operation_id, result=result.model_dump())
        write_json(directory / "version.json", version)
        if result.status == "succeeded":
            write_json(self.settings.contained_path(f"projects/{project_id}/project.json"), manifest)
        self.projects._finalize_job(result)
        return result
