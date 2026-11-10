import subprocess
from unittest.mock import patch

import pytest

from astra_video_studio.ae_bridge.discovery import discover_ae
from astra_video_studio.config import Settings
from astra_video_studio.media.ffmpeg import inspect_binary
from astra_video_studio.schemas import ComponentStatus
from astra_video_studio.status import studio_status


def test_missing_explicit_ae_does_not_fallback(tmp_path):
    result = discover_ae(str(tmp_path / "missing.exe"))
    assert not result.available
    assert result.error


@pytest.mark.parametrize("version,error", [("25.5.0.0", False), ("26.0.0.0", True), (None, True)])
def test_ae_version_validation(tmp_path, version, error):
    path = tmp_path / "AfterFX.exe"
    path.touch()
    with patch("astra_video_studio.ae_bridge.discovery.executable_version", return_value=version):
        result = discover_ae(str(path))
    assert result.available
    assert bool(result.error) == error


def test_missing_media(tmp_path):
    assert not inspect_binary("ffmpeg", str(tmp_path / "missing.exe")).available


@pytest.mark.parametrize("outcome", [subprocess.TimeoutExpired("ffmpeg", 5), OSError("denied")])
def test_media_launch_failures(tmp_path, outcome):
    path = tmp_path / "ffmpeg.exe"
    path.touch()
    with patch("subprocess.run", side_effect=outcome):
        result = inspect_binary("ffmpeg", str(path))
    assert not result.available
    assert "failed" in result.error


@pytest.mark.parametrize("code,text,available", [(0, "ffmpeg version test\nextra", True), (1, "failure", False), (0, "", False), (0, "wrong executable", False)])
def test_media_response_validation(tmp_path, code, text, available):
    path = tmp_path / "ffmpeg.exe"
    path.touch()
    with patch("subprocess.run", return_value=subprocess.CompletedProcess([], code, text, "")) as run:
        result = inspect_binary("ffmpeg", str(path))
    assert result.available == available
    assert run.call_args.kwargs["shell"] is False
    assert run.call_args.kwargs["timeout"] == 5


def test_status_success_keeps_bridge_unverified(tmp_path):
    good = ComponentStatus(available=True, version="25.5")
    with patch("astra_video_studio.status.discover_ae", return_value=good), patch("astra_video_studio.status.inspect_binary", return_value=good), patch("platform.system", return_value="Windows"), patch("platform.release", return_value="11"):
        result = studio_status(Settings(tmp_path))
    assert result.status == "ok"
    assert result.bridge_status == "not_validated"
    assert result.workspace.writable
    assert list(tmp_path.iterdir()) == []


def test_unwritable_workspace_reports_failure(tmp_path):
    blocked = tmp_path / "file"
    blocked.touch()
    with patch("astra_video_studio.status.discover_ae", return_value=ComponentStatus()), patch("astra_video_studio.status.inspect_binary", return_value=ComponentStatus()):
        result = studio_status(Settings(blocked))
    assert result.status == "degraded"
    assert not result.workspace.writable
    assert result.workspace.error


def test_unsupported_platform(tmp_path):
    with patch("platform.system", return_value="Linux"):
        result = studio_status(Settings(tmp_path, ae_executable=str(tmp_path / "missing")))
    assert not result.windows_supported
    assert result.status == "degraded"
