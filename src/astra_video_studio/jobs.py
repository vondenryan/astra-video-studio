"""Durable operation journals; a timed-out AE must not receive another script."""
from datetime import datetime, timezone
import json
import os
import time
from pathlib import Path
from uuid import uuid4

from astra_video_studio.config import Settings


def read_json(path: Path) -> dict:
    """Retry only transient Windows sharing denial while reading an atomic journal.

    This never retries a service operation or accepts partial/invalid JSON.
    """
    for attempt in range(6):
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except PermissionError:
            if attempt == 5: raise
            time.sleep(min(0.01*2**attempt, 0.1))


def write_json(path: Path, data: dict) -> None:
    temp = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        with temp.open("x", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=True)
            stream.flush()
            os.fsync(stream.fileno())
        # A concurrent Windows reader/scanner can briefly deny atomic replacement.
        # Keep the old valid JSON until replacement succeeds; never write in place.
        for attempt in range(10):
            try:
                temp.replace(path)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(min(0.01 * 2 ** attempt, 0.1))
    finally:
        temp.unlink(missing_ok=True)


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class Job:
    def __init__(self, settings: Settings, action: str):
        from astra_video_studio.lifecycle import owner_identity
        self.settings = settings
        self.id = uuid4().hex
        self.directory = settings.contained_path(f"jobs/{self.id}")
        self.directory.mkdir(parents=True, exist_ok=False)
        self.journal = {"operation_id": self.id, "action": action, "status": "prepared", "events": [], "owner": owner_identity(), "lifecycle_version": 1}
        self.record("prepared")

    def record(self, status: str, **fields) -> None:
        self.journal.update(status=status, **fields)
        event={"timestamp":timestamp(),"status":status}
        for name in ('stage','process_pid','process_identity','process_exit_confirmed','process_returncode','dispatch_intent','native_preparation_intent'):
            if name in fields:event[name]=fields[name]
        self.journal["events"].append(event)
        write_json(self.directory / "job.json", self.journal)
