from datetime import datetime, timezone
import logging
import json
import platform
import tempfile
from uuid import uuid4

from astra_video_studio.ae_bridge.discovery import discover_ae
from astra_video_studio.config import Settings
from astra_video_studio.media.ffmpeg import inspect_binary
from astra_video_studio.schemas import StudioStatus, WorkspaceStatus
from astra_video_studio.host_runtime import runtime_identity

log = logging.getLogger(__name__)


def studio_status(settings: Settings | None = None) -> StudioStatus:
    settings = settings or Settings.from_env()
    operation_id = uuid4().hex
    writable, error = False, None
    try:
        settings.workspace.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=settings.workspace) as handle:
            handle.write(b"astra permission probe")
            handle.flush()
        writable = True
    except OSError as exc:
        error = f"Workspace write probe failed: {type(exc).__name__}"
    ae = discover_ae(settings.ae_executable)
    ffmpeg = inspect_binary("ffmpeg", settings.ffmpeg)
    ffprobe = inspect_binary("ffprobe", settings.ffprobe)
    windows = platform.system() == "Windows" and platform.release() in ("10", "11")
    warnings = [item.error for item in (ae, ffmpeg, ffprobe) if item.error]
    if not windows:
        warnings.append("Editing is supported only on Windows 10/11; target platform is Windows 11.")
    if error:
        warnings.append(error)
    bridge_status = "not_validated"
    try:
        evidence = json.loads(settings.contained_path("bridge-validation.json").read_text(encoding="utf-8"))
        from astra_video_studio.project_manager import valid_id
        operation_id_from_evidence = valid_id(evidence["operation_id"])
        journal = json.loads(settings.contained_path(f"jobs/{operation_id_from_evidence}/job.json").read_text(encoding="utf-8"))
        if journal.get("action") == "create" and journal.get("status") == "succeeded" and journal.get("result", {}).get("status") == "succeeded":
            bridge_status = "acknowledged"
    except (OSError, ValueError, KeyError, TypeError):
        pass
    warnings.append("Prior project creation was acknowledged; this is not a live AE health check." if bridge_status == "acknowledged" else "No verified Sprint 1 creation recorded in this workspace. AE calls can fail or time out.")
    unresolved = settings.contained_path("ae-pending.json").exists()
    if unresolved:
        warnings.append("AE submission is unresolved: workspace quarantined; inspect ae-pending.json before retrying.")
    render_unresolved = settings.contained_path("preview-pending.json").exists()
    if render_unresolved:
        warnings.append("Native render is active or unresolved: previews serialized/blocked; inspect preview-pending.json before retrying.")
    runtime = {"transport": "idle_inbox", "ready": False, "active_job": None}
    bridge_dir = settings.contained_path("bridge")
    if bridge_dir.is_dir():
        from astra_video_studio.ae_bridge.idle_transport import IdleTransport
        state = IdleTransport(settings).state()
        if state:
            runtime.update(ready=not bool(state.get("active_job")), active_job=state.get("active_job"), instance_id=state.get("instance_id"))
    startup_unresolved = (bridge_dir / "startup-pending.json").exists() and not runtime["ready"]
    if (bridge_dir / "startup-pending.json").is_file():
        try:
            startup = json.loads((bridge_dir / "startup-pending.json").read_text(encoding="utf-8"))
            runtime["bootstrap_script"] = startup["command"][2]
        except (OSError, ValueError, KeyError, TypeError, IndexError):
            pass
    elif (bridge_dir / "session.json").is_file():
        try:
            session = json.loads((bridge_dir / "session.json").read_text(encoding="utf-8"))
            runtime["bootstrap_script"] = session.get("bootstrap_script")
        except (OSError, ValueError, TypeError):
            pass
    if startup_unresolved:
        warnings.append("Idle bridge bootstrap is unconfirmed; inspect bridge/startup-pending.json. No repeated automatic -r launch.")
    result = StudioStatus(
        operation_id=operation_id, timestamp=datetime.now(timezone.utc).isoformat(),
        status="ok" if windows and writable and not unresolved and not render_unresolved and not startup_unresolved and all(x.available and not x.error for x in (ae, ffmpeg, ffprobe)) else "degraded",
        platform=platform.platform(), windows_supported=windows, python_version=platform.python_version(),
        after_effects=ae, ffmpeg=ffmpeg, ffprobe=ffprobe,
        workspace=WorkspaceStatus(path=str(settings.workspace), writable=writable, error=error),
        bridge_status=bridge_status,
        bridge_runtime=runtime,
        mcp_runtime=runtime_identity(),
        warnings=warnings,
    )
    log.info("operation=%s tool=studio_status status=%s bridge=%s", operation_id, result.status, result.bridge_status)
    return result
