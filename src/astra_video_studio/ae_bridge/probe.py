"""Prepare a trusted diagnostic script. This module never launches AE."""
import json
from pathlib import Path
from uuid import uuid4

from astra_video_studio.config import Settings


def prepare_probe(settings: Settings) -> dict:
    job_id = uuid4().hex
    directory = settings.contained_path(f"bridge-probes/{job_id}")
    directory.mkdir(parents=True, exist_ok=False)
    result = directory / "result.json"
    # JSON string literals are valid ExtendScript literals; no user text is code.
    script = r'''// Astra Sprint 0: read-only AE state probe. Never creates/opens/saves a project.
(function () {
    function quote(value) {
        return '"' + String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"')
            .replace(/[\x00-\x1f]/g, function (c) {
                return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4);
            }) + '"';
    }
    var output = new File(__OUTPUT__);
    var status = 'succeeded', version = '', count = 0, error = '';
    try {
        version = app.version;
        count = app.project ? app.project.numItems : 0;
    } catch (e) { status = 'failed'; error = String(e); }
    output.encoding = 'UTF-8';
    if (!output.open('w')) { return; }
    try {
        output.write('{"job_id":' + quote(__JOB__) + ',"status":' + quote(status)
            + ',"ae_version":' + quote(version) + ',"project_item_count":' + count
            + ',"error":' + quote(error) + '}');
    } finally { output.close(); }
}());
'''.replace("__OUTPUT__", json.dumps(result.as_posix())).replace("__JOB__", json.dumps(job_id))
    script_path = directory / "probe.jsx"
    script_path.write_text(script, encoding="utf-8")
    manifest = {"job_id": job_id, "status": "prepared_not_executed", "script": str(script_path), "result": str(result)}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def verify_probe(settings: Settings, job_id: str) -> dict:
    if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
        raise ValueError("Expected a 32-character lowercase hex job ID")
    path = settings.contained_path(f"bridge-probes/{job_id}/result.json")
    if not path.is_file():
        return {"job_id": job_id, "status": "unconfirmed", "error": "No acknowledgement. Submission is not proof of execution."}
    if path.stat().st_size > 65536:
        raise ValueError("Acknowledgement exceeds size limit")
    result = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(result, dict) or result.get("job_id") != job_id:
        raise ValueError("Acknowledgement job ID mismatch")
    if result.get("status") not in ("succeeded", "failed"):
        raise ValueError("Invalid acknowledgement status")
    if result["status"] == "succeeded" and (
        not isinstance(result.get("ae_version"), str) or not result["ae_version"].startswith("25.")
        or type(result.get("project_item_count")) is not int or result["project_item_count"] < 0
    ):
        raise ValueError("Acknowledgement does not confirm AE 2025 with valid project metadata")
    return result
