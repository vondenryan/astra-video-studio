import json
import hashlib
import logging
import time

from astra_video_studio.ae_bridge.discovery import discover_ae
from astra_video_studio.ae_bridge.locking import AELock
from astra_video_studio.ae_bridge.templates import render_script
from astra_video_studio.ae_bridge.idle_transport import IdleTransport
from astra_video_studio.config import Settings
from astra_video_studio.jobs import Job, write_json
from astra_video_studio.schemas import OperationResult
from astra_video_studio.ae_bridge.result_artifacts import (PROTOCOL, ACK_MAX_BYTES, INLINE_MAX_BYTES, load_artifact, parse_json, validate_result)

log = logging.getLogger(__name__)


class BridgeRunner:
    def __init__(self, settings: Settings, timeout: float = 60):
        self.settings = settings
        self.timeout = timeout

    def run(self, action: str, payload: dict) -> OperationResult:
        job = Job(self.settings, action)
        try:
            with AELock():
                return self._run_locked(job, action, payload)
        except (OSError,ValueError) as exc:
            uncertain=bool(job.journal.get('dispatch_intent') and self.settings.contained_path('ae-pending.json').exists())
            status='timeout' if uncertain else 'busy' if isinstance(exc,BlockingIOError) else 'failed'
            result = OperationResult(operation_id=job.id,status=status,
                error=('Submission delivery uncertain; workspace quarantined, do not resend. ' if uncertain else '')+str(exc))
        job.record(result.status, result=result.model_dump())
        return result

    def _run_locked(self, job: Job, action: str, payload: dict) -> OperationResult:
        pending = self.settings.contained_path("ae-pending.json")
        if pending.exists():
            result = OperationResult(operation_id=job.id, status="blocked", error="AE has an unresolved submission. Inspect ae-pending.json and AE; no automatic retry is allowed.")
            job.record(result.status, result=result.model_dump())
            return result
        ae = discover_ae(self.settings.ae_executable)
        if not ae.available or ae.error:
            result = OperationResult(operation_id=job.id, status="failed", error=ae.error or "AE unavailable")
            job.record(result.status, result=result.model_dump())
            return result
        script_path = job.directory / "operation.jsx"
        result_path = job.directory / "result.json"
        cancel_path = job.directory / "cancelled"
        protocol = self.settings.ae_result_transport
        inputs = dict(payload, operation_id=job.id, result_path=result_path.as_posix(), cancel_path=cancel_path.as_posix(), result_protocol=protocol)
        script_path.write_text(render_script(action, inputs), encoding="utf-8")
        transport = IdleTransport(self.settings)
        transport_info = transport.ensure_ready(ae.path)
        write_json(pending, {"operation_id": job.id, "job_directory": str(job.directory), "transport": transport_info, "script": str(script_path), 'result_protocol': protocol})
        job.record("submitting", script=str(script_path), script_sha256=hashlib.sha256(script_path.read_bytes()).hexdigest(), result_protocol=protocol, dispatch_intent=True, **transport_info)
        try:
            transport.publish(job)
        except OSError:
            # An error can occur after publication. Preserve the intent and
            # quarantine; absence of an acknowledgement is never proof of no run.
            raise
        job.record("submitted", **transport_info)
        deadline = time.monotonic() + self.timeout
        invalid_reason = None
        while time.monotonic() < deadline:
            if result_path.is_file():
                ack_limit = ACK_MAX_BYTES if protocol == PROTOCOL else INLINE_MAX_BYTES
                if result_path.stat().st_size > ack_limit:
                    invalid_reason = 'Acknowledgement exceeds its protocol byte bound'
                    break
                try:
                    with result_path.open('rb') as stream: raw_ack = stream.read(ack_limit + 1)
                    if len(raw_ack) > ack_limit:
                        invalid_reason = 'Acknowledgement grew beyond its byte bound'
                        break
                    ack = parse_json(raw_ack)
                except (ValueError, OSError):
                    # AE may still have the file open or only partially written.
                    time.sleep(0.1)
                    continue
                evidence = None
                try:
                    if protocol == PROTOCOL:
                        ack, evidence = load_artifact(self.settings, job.directory, job.id, ack)
                    else:
                        if isinstance(ack, dict) and ack.get('protocol') is not None: raise ValueError('Unexpected protocol in legacy acknowledgement')
                        ack = validate_result(ack, job.id)
                except OSError as error:
                    invalid_reason = 'Evidence unavailable: ' + str(error)
                    time.sleep(0.1)
                    continue
                except (ValueError, TypeError, KeyError) as error:
                    invalid_reason = str(error)
                    break
                result = OperationResult(
                    operation_id=job.id, status=ack["status"], data=ack["data"], error=ack.get("error"),
                    artifacts=[str(script_path), str(result_path), str(job.directory / "job.json")],
                )
                if evidence: result.artifacts.append(evidence['path'])
                # Keep the global mutex until the deferred ack callback has also
                # returned. This is conservative spacing, not proof of UI readiness.
                time.sleep(0.75)
                fields = {'native_evidence': evidence} if evidence else {}
                job.record(result.status, result=result.model_dump(), **fields)
                pending.unlink()
                log.info("operation=%s action=%s status=%s", job.id, action, result.status)
                return result
            time.sleep(0.1)
        cancel_path.touch(exist_ok=True)
        result = OperationResult(
            operation_id=job.id, status="timeout",
            error="No valid matching AE acknowledgement/evidence. Workspace quarantined; AE was not terminated. Inspect the job and AE before manual recovery." + (' Detail: ' + invalid_reason if invalid_reason else ''),
            artifacts=[str(script_path), str(job.directory / "job.json"), str(pending)],
        )
        result.artifacts.extend(str(path) for path in (result_path, job.directory / 'native-result.json', job.directory / 'native-result.incomplete.json') if path.exists())
        job.record(result.status, result=result.model_dump())
        return result
