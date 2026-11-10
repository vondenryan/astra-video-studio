import copy
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from astra_video_studio.config import Settings
from astra_video_studio.jobs import Job
from astra_video_studio.media.preview import PreviewRequest, PreviewService, frame_sequence, preview_plan, verify_probe, Cancelled
from astra_video_studio.treatments import EffectRequest, MaskRequest, mask_path, verify_treatment

IDS = dict(project_id="1" * 32, composition_id="2" * 32, layer_id="3" * 32)


@pytest.mark.parametrize("fields", [{"effect": "arbitrary_plugin"}, {"effect": "fill", "params": {"color": [2, 0, 0]}}, {"effect": "fill", "params": {"execute_jsx": "x"}}, {"effect": "gaussian_blur", "params": {"amount": float("nan")}}, {"effect": "gaussian_blur", "params": {"amount": 1000}}])
def test_effect_schema_limits(fields):
    with pytest.raises(ValidationError):
        EffectRequest(**IDS, **fields)


@pytest.mark.parametrize("bounds", [[0, 0, 0, 100], [0, 0, 100, -1], [float("inf"), 0, 100, 100], [0, 0, 20001, 100]])
def test_mask_bounds_rejected(bounds):
    with pytest.raises(ValidationError):
        MaskRequest(**IDS, bounds=bounds)


@pytest.mark.parametrize("shape", ["rectangle", "ellipse"])
def test_editable_mask_geometry(shape):
    result = mask_path(MaskRequest(**IDS, shape=shape, bounds=[10, 20, 100, 60]))
    assert result["closed"] and len(result["vertices"]) == 4
    assert len(result["in_tangents"]) == len(result["out_tangents"]) == 4
    assert min(p[0] for p in result["vertices"]) == 10
    assert max(p[0] for p in result["vertices"]) == 110
    assert min(p[1] for p in result["vertices"]) == 20
    assert max(p[1] for p in result["vertices"]) == 80


def test_preview_plan_rounds_frames_and_even_dimensions():
    request = PreviewRequest(project_id=IDS["project_id"], composition_id=IDS["composition_id"], start_time=0.65, duration=1, max_width=853)
    result = preview_plan(request, {"fps": 30, "duration": 10, "width": 1920, "height": 1080})
    assert result["start_time"] == 20 / 30
    assert result["frame_count"] == 30
    assert result["width"] % 2 == result["height"] % 2 == 0


@pytest.mark.parametrize("comp", [{"fps": 30, "duration": 1, "width": 1920, "height": 1080}, {"fps": 30, "duration": 10, "width": 8000, "height": 4000}])
def test_invalid_preview_interval_or_size(comp):
    with pytest.raises(ValueError):
        preview_plan(PreviewRequest(project_id=IDS["project_id"], composition_id=IDS["composition_id"]), comp)


def test_sequence_requires_exact_contiguous_nonempty_files(tmp_path):
    for index in [20, 21, 22]:
        (tmp_path / f"frame_{index:05d}.png").write_bytes(b"png placeholder")
    first, pattern = frame_sequence(tmp_path, 3)
    assert first == 20 and "%05d" in pattern
    (tmp_path / "frame_00021.png").unlink()
    with pytest.raises(ValueError):
        frame_sequence(tmp_path, 3)


def test_tiff_sequence_supported_and_mixed_formats_rejected(tmp_path):
    for index in [0, 1]:
        (tmp_path / f"frame_{index:05d}.tif").write_bytes(b"tiff placeholder")
    assert frame_sequence(tmp_path, 2)[1].endswith("frame_%05d.tif")
    (tmp_path / "frame_00002.png").write_bytes(b"png placeholder")
    with pytest.raises(ValueError):
        frame_sequence(tmp_path, 3)


def good_probe():
    return {"streams": [{"codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p", "width": 640, "height": 360, "avg_frame_rate": "30/1", "nb_read_frames": "90"}], "format": {"duration": "3.000"}}


@pytest.mark.parametrize("field,value", [("width", 100), ("nb_read_frames", "89"), ("avg_frame_rate", "25/1"), ("codec_name", "png"), ("pix_fmt", "yuv444p")])
def test_video_metadata_mismatch_is_failure(field, value):
    data = good_probe()
    data["streams"][0][field] = value
    with pytest.raises(ValueError):
        verify_probe(data, {"width": 640, "height": 360, "duration": 3, "fps": 30, "frame_count": 90})


@pytest.mark.parametrize("duration", ["1", "nan"])
def test_video_duration_must_be_plausible_and_finite(duration):
    data = good_probe()
    data["format"]["duration"] = duration
    with pytest.raises(ValueError):
        verify_probe(data, {"width": 640, "height": 360, "duration": 3, "fps": 30, "frame_count": 90})


def test_good_video_metadata_is_verified():
    assert verify_probe(good_probe(), {"width": 640, "height": 360, "duration": 3, "fps": 30, "frame_count": 90})["frame_count"] == 90


def fake_saved_project(tmp_path):
    root = tmp_path / "projects" / IDS["project_id"]
    root.mkdir(parents=True)
    source = root / "project.aep"
    source.write_bytes(b"fixture" * 30)
    manifest = {"status": "succeeded", "project_id": IDS["project_id"], "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "result": {"data": {"compositions": [{"composition_id": "astra:composition:" + IDS["composition_id"], "fps": 30, "duration": 5, "width": 640, "height": 360}]}}}
    (root / "project.json").write_text(json.dumps(manifest))
    return source


def test_queued_cancellation_never_launches_ae(tmp_path):
    fake_saved_project(tmp_path)
    settings = Settings(tmp_path)
    service = PreviewService(settings)
    with patch("astra_video_studio.media.preview._executor") as executor:
        submission = service.submit(PreviewRequest(project_id=IDS["project_id"], composition_id=IDS["composition_id"]))
        assert submission.status == "queued"
        state = service.cancel(submission.job_id)
        assert state["cancel_requested"]
        function, *args = executor.submit.call_args.args
        with patch("subprocess.Popen") as launch:
            function(*args)
        launch.assert_not_called()
    assert service.projects.job_status(submission.job_id)["status"] == "cancelled"


def test_source_change_while_queued_is_failed_not_rendered(tmp_path):
    source = fake_saved_project(tmp_path)
    service = PreviewService(Settings(tmp_path))
    with patch("astra_video_studio.media.preview._executor") as executor:
        submission = service.submit(PreviewRequest(project_id=IDS["project_id"], composition_id=IDS["composition_id"]))
        source.write_bytes(b"changed")
        function, *args = executor.submit.call_args.args
        with patch("subprocess.Popen") as launch:
            function(*args)
        launch.assert_not_called()
    state = service.projects.job_status(submission.job_id)
    assert state["status"] == "failed" and "changed" in state["result"]["error"]


def test_native_timeout_never_kills_interactive_ae(tmp_path):
    settings = Settings(tmp_path)
    job = Job(settings, "preview_render")
    process = Mock(pid=123)
    process.poll.return_value = None
    with patch("subprocess.Popen", return_value=process), patch("time.monotonic", side_effect=[0, 2]):
        with pytest.raises(TimeoutError):
            PreviewService(settings)._process(job, ["aerender.exe"], "aerender", 1, native=True)
    process.terminate.assert_not_called()
    process.kill.assert_not_called()
    assert (tmp_path / "preview-pending.json").is_file()


def test_renderer_nonzero_exit_is_explicit_failure(tmp_path):
    settings = Settings(tmp_path)
    process = Mock(returncode=1, pid=123)
    process.poll.return_value = 1
    with patch("subprocess.Popen", return_value=process):
        with pytest.raises(ValueError, match="failed"):
            PreviewService(settings)._process(Job(settings, "preview_render"), ["aerender.exe"], "aerender", 1, native=True)


def test_native_marker_precedes_launch_and_clears_only_after_exit(tmp_path):
    settings = Settings(tmp_path)
    job = Job(settings, "preview_render")
    marker = tmp_path / "preview-pending.json"
    def launch(*args, **kwargs):
        assert json.loads(marker.read_text())["job_id"] == job.id
        process = Mock(pid=123, returncode=0)
        process.poll.return_value = 0
        return process
    with patch("subprocess.Popen", side_effect=launch):
        PreviewService(settings)._process(job, ["aerender.exe"], "aerender", 1, native=True)
    assert not marker.exists()


def test_existing_native_marker_blocks_second_renderer(tmp_path):
    settings = Settings(tmp_path)
    job = Job(settings, "preview_render")
    (tmp_path / "preview-pending.json").write_text('{"job_id":"other"}')
    with patch("subprocess.Popen") as launch:
        with pytest.raises(BlockingIOError):
            PreviewService(settings)._process(job, ["aerender.exe"], "aerender", 1, native=True)
    launch.assert_not_called()


def test_treatment_verifier_preserves_existing_effects_and_other_layers():
    request = EffectRequest(**IDS, effect="fill", params={"color": [0.3, 0.85, 1]})
    layer = {"layer_id": "astra:layer:" + IDS["layer_id"], "effects": [], "bounds": None}
    before = {"compositions": [{"composition_id": "astra:composition:" + IDS["composition_id"], "layers": [layer]}]}
    after = copy.deepcopy(before)
    after["compositions"][0]["layers"][0]["effects"] = [{"name": "Astra effect", "match_name": "ADBE Fill", "enabled": True, "parameters": {"color": [0.3, 0.85, 1, 1]}}]
    verify_treatment(before, after, request, "Astra effect", None)
    after["compositions"][0]["layers"][0]["name"] = "Unexpected rename"
    with pytest.raises(ValueError, match="Unrelated"):
        verify_treatment(before, after, request, "Astra effect", None)
