import json
import time
from unittest.mock import patch

import pytest

from astra_video_studio.ae_bridge.idle_transport import IdleTransport
from astra_video_studio.config import Settings
from astra_video_studio.jobs import Job


def heartbeat(transport, **fields):
    transport.heartbeat.write_text(json.dumps({"instance_id": "a" * 32, "ae_version": "25.5x4", "time_ms": time.time() * 1000, "active_job": None} | fields))


def test_fresh_bridge_avoids_second_cli_launch(tmp_path):
    transport = IdleTransport(Settings(tmp_path))
    heartbeat(transport)
    with patch("subprocess.Popen") as launch:
        info = transport.ensure_ready("AfterFX.exe")
    launch.assert_not_called()
    assert info["transport"] == "idle_inbox"


def test_unresolved_active_bridge_job_is_not_overridden(tmp_path):
    transport = IdleTransport(Settings(tmp_path))
    heartbeat(transport, active_job="b" * 32)
    with patch("subprocess.Popen") as launch:
        with pytest.raises(BlockingIOError):
            transport.ensure_ready("AfterFX.exe")
    launch.assert_not_called()


def test_inbox_contains_only_generated_job_id_and_never_overwrites(tmp_path):
    settings = Settings(tmp_path)
    transport = IdleTransport(settings)
    first, second = Job(settings, "inspect"), Job(settings, "inspect")
    transport.publish(first)
    assert transport.inbox.read_text() == first.id
    with pytest.raises(BlockingIOError):
        transport.publish(second)
    assert transport.inbox.read_text() == first.id


def test_stale_and_invalid_heartbeat_are_not_success(tmp_path):
    transport = IdleTransport(Settings(tmp_path))
    heartbeat(transport, time_ms=0)
    assert transport.state() is None


def test_known_stale_session_never_relaunches_cli_automatically(tmp_path):
    transport = IdleTransport(Settings(tmp_path))
    heartbeat(transport, time_ms=0)
    (transport.directory / "session.json").write_text('{"instance_id":"old"}')
    with patch("subprocess.Popen") as launch:
        with pytest.raises(TimeoutError, match="stale"):
            transport.ensure_ready("AfterFX.exe")
    launch.assert_not_called()
    transport.heartbeat.write_text("partial")
    assert transport.state() is None
