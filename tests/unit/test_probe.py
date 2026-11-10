import json
from pathlib import Path

import pytest

from astra_video_studio.ae_bridge.probe import prepare_probe, verify_probe
from astra_video_studio.config import Settings


def test_probe_preparation_is_unique_and_never_launches(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Probe preparation must not launch applications")
    monkeypatch.setattr("subprocess.Popen", forbidden)
    settings = Settings(tmp_path)
    first, second = prepare_probe(settings), prepare_probe(settings)
    assert first["job_id"] != second["job_id"]
    assert first["status"] == "prepared_not_executed"
    script = Path(first["script"]).read_text()
    assert "app.version" in script
    assert "app.newProject" not in script
    assert "app.open" not in script
    assert "app.project.save" not in script
    assert verify_probe(settings, first["job_id"])["status"] == "unconfirmed"


@pytest.mark.parametrize("job", ["../escape", "a" * 31, "G" * 32])
def test_invalid_probe_id(tmp_path, job):
    with pytest.raises(ValueError):
        verify_probe(Settings(tmp_path), job)


@pytest.mark.parametrize("payload,valid", [
    ({"status": "succeeded", "ae_version": "25.5", "project_item_count": 0}, True),
    ({"status": "failed", "error": "permission denied"}, True),
    ({"status": "submitted"}, False),
    ({"status": "succeeded", "ae_version": "26.0", "project_item_count": 0}, False),
    ({"status": "succeeded", "ae_version": "25.5", "project_item_count": -1}, False),
    ({"status": "succeeded", "ae_version": "25.5", "project_item_count": True}, False),
])
def test_acknowledgement_validation(tmp_path, payload, valid):
    settings = Settings(tmp_path)
    manifest = prepare_probe(settings)
    payload["job_id"] = manifest["job_id"]
    Path(manifest["result"]).write_text(json.dumps(payload), encoding="utf-8-sig")
    if valid:
        assert verify_probe(settings, manifest["job_id"])["status"] == payload["status"]
    else:
        with pytest.raises(ValueError):
            verify_probe(settings, manifest["job_id"])


def test_wrong_acknowledgement_job(tmp_path):
    settings = Settings(tmp_path)
    manifest = prepare_probe(settings)
    Path(manifest["result"]).write_text('{"job_id":"other"}')
    with pytest.raises(ValueError, match="mismatch"):
        verify_probe(settings, manifest["job_id"])


def test_oversized_acknowledgement(tmp_path):
    settings = Settings(tmp_path)
    manifest = prepare_probe(settings)
    Path(manifest["result"]).write_text(" " * 65537)
    with pytest.raises(ValueError, match="size"):
        verify_probe(settings, manifest["job_id"])
