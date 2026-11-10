from contextlib import nullcontext
import json
from pathlib import Path
import subprocess
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from astra_video_studio.ae_bridge.runner import BridgeRunner
from astra_video_studio.ae_bridge.templates import render_script
from astra_video_studio.config import Settings
from astra_video_studio.jobs import write_json
from astra_video_studio.project_manager import ProjectManager, valid_id
from astra_video_studio.schemas import ComponentStatus, ProjectCreateRequest


@pytest.mark.parametrize("fields", [{"width": 0}, {"height": 9000}, {"fps": 0}, {"duration": float("nan")}, {"fps": float("inf")}, {"title": ""}, {"title": "\x00"}, {"name": "   "}, {"execute_jsx": "x"}])
def test_invalid_requests(fields):
    with pytest.raises(ValidationError):
        ProjectCreateRequest(**fields)


def test_template_data_cannot_inject_code():
    title = '\"; app.quit(); //\nç\u2028'
    script = render_script("create", {"request": {"title": title}})
    encoded = script.split("var p = ", 1)[1].split(";\n", 1)[0]
    assert json.loads(encoded)["request"]["title"] == title
    assert "/*ASTRA_INPUT*/null" not in script
    with pytest.raises(ValueError):
        render_script("arbitrary_jsx", {})


def fake_launch(settings, status="succeeded", wrong_id=False):
    def launch(job):
        assert (job.directory / "operation.jsx").is_file()
        pending = json.loads((settings.workspace / "ae-pending.json").read_text())
        result = {"operation_id": "wrong" if wrong_id else pending["operation_id"], "status": status, "data": {}, "error": "AE failure" if status == "failed" else None}
        if settings.ae_result_transport == 'artifact-v1':
            import hashlib
            artifact = {"schema_version": 1, "protocol": "artifact-v1", "result": result}
            raw = json.dumps(artifact).encode('utf-8')
            (job.directory / 'native-result.json').write_bytes(raw)
            result = {"operation_id": result['operation_id'], "status": status, "protocol": "artifact-v1", "evidence": {"file": "native-result.json", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}}
        write_json(Path(pending["job_directory"]) / "result.json", result)
        return Mock(pid=123)
    return launch


@pytest.fixture
def runner_dependencies():
    with patch("astra_video_studio.ae_bridge.runner.AELock", side_effect=nullcontext), patch("astra_video_studio.ae_bridge.runner.discover_ae", return_value=ComponentStatus(available=True, path="AfterFX.exe", version="25.5")), patch("astra_video_studio.ae_bridge.runner.IdleTransport.ensure_ready", return_value={"transport": "idle_inbox", "instance_id": "unit"}):
        yield


@pytest.mark.parametrize("status", ["succeeded", "failed"])
@pytest.mark.parametrize('protocol', ['inline-v1', 'artifact-v1'])
def test_runner_acknowledgement_and_journal(tmp_path, runner_dependencies, status, protocol):
    settings = Settings(tmp_path, ae_result_transport=protocol)
    with patch("astra_video_studio.ae_bridge.runner.IdleTransport.publish", side_effect=fake_launch(settings, status)):
        result = BridgeRunner(settings).run("inspect", {"project_path": "test.aep"})
    assert result.status == status
    assert not (tmp_path / "ae-pending.json").exists()
    journal = json.loads((tmp_path / "jobs" / result.operation_id / "job.json").read_text())
    assert [e["status"] for e in journal["events"]] == ["prepared", "submitting", "submitted", status]


def test_runner_timeout_blocks_next_submission(tmp_path, runner_dependencies):
    settings = Settings(tmp_path)
    with patch("astra_video_studio.ae_bridge.runner.IdleTransport.publish") as launch:
        first = BridgeRunner(settings, timeout=0).run("inspect", {"project_path": "test.aep"})
        second = BridgeRunner(settings, timeout=0).run("inspect", {"project_path": "test.aep"})
    assert first.status == "timeout"
    assert (tmp_path / "jobs" / first.operation_id / "cancelled").exists()
    assert second.status == "blocked"
    assert launch.call_count == 1


def test_runner_wrong_ack_is_not_success(tmp_path, runner_dependencies):
    settings = Settings(tmp_path)
    with patch("astra_video_studio.ae_bridge.runner.IdleTransport.publish", side_effect=fake_launch(settings, wrong_id=True)):
        result = BridgeRunner(settings, timeout=1).run("inspect", {"project_path": "test.aep"})
    assert result.status == "timeout"
    assert (tmp_path / "ae-pending.json").is_file()


def test_runner_publish_failure_retains_uncertain_pending(tmp_path, runner_dependencies):
    with patch("astra_video_studio.ae_bridge.runner.IdleTransport.publish", side_effect=OSError("denied")):
        result = BridgeRunner(Settings(tmp_path)).run("inspect", {})
    assert result.status == "timeout" and 'uncertain' in result.error
    assert (tmp_path / "ae-pending.json").exists()


def test_runner_missing_ae_does_not_launch(tmp_path, runner_dependencies):
    with patch("astra_video_studio.ae_bridge.runner.discover_ae", return_value=ComponentStatus(error="missing AE")), patch("subprocess.Popen") as launch:
        result = BridgeRunner(Settings(tmp_path)).run("inspect", {})
    assert result.status == "failed"
    launch.assert_not_called()


def test_runner_busy_does_not_launch(tmp_path):
    with patch("astra_video_studio.ae_bridge.runner.AELock", side_effect=BlockingIOError("busy")), patch("subprocess.Popen") as launch:
        result = BridgeRunner(Settings(tmp_path)).run("inspect", {})
    assert result.status == "busy"
    launch.assert_not_called()


def test_unknown_and_invalid_ids(tmp_path):
    manager = ProjectManager(Settings(tmp_path))
    with pytest.raises(ValueError):
        valid_id("../x")
    with pytest.raises(ValueError, match="Unknown"):
        manager.inspect("0" * 32)


def test_create_does_not_accept_ack_without_aep(tmp_path, runner_dependencies):
    settings = Settings(tmp_path)
    with patch("astra_video_studio.ae_bridge.runner.IdleTransport.publish", side_effect=fake_launch(settings)):
        result = ProjectManager(settings).create(ProjectCreateRequest())
    assert result.status == "failed"
    assert "verification failed" in result.error
    journal = json.loads((tmp_path / "jobs" / result.operation_id / "job.json").read_text())
    assert journal["events"][-1]["status"] == "failed"
    assert not (tmp_path / "bridge-validation.json").exists()


@pytest.mark.parametrize("z", [[], [0]])
def test_title_center_validation(tmp_path, z):
    target = tmp_path / "test.aep"
    target.write_bytes(b"a" * 100)
    request = ProjectCreateRequest()
    layer = {"layer_id": "astra:layer:layer", "text": request.title, "position": [960, 540] + z, "anchor": [100, 20] + z, "bounds": {"left": 0, "top": 0, "width": 200, "height": 40}, "in_point": 0, "out_point": 5}
    data = {"project_path": str(target), "ae_version": "25.5x4", "compositions": [{"composition_id": "astra:composition:comp", "name": request.name, "width": 1920, "height": 1080, "fps": 30, "duration": 5, "layers": [layer]}]}
    ProjectManager._verify_created(data, request, target, "comp", "layer")
    layer["anchor"] = [0, 0]
    with pytest.raises(ValueError, match="anchor"):
        ProjectManager._verify_created(data, request, target, "comp", "layer")
