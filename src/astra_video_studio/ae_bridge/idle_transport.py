"""One -r bootstrap per AE session; subsequent reviewed scripts use an idle inbox."""
import json
import os
import re
from pathlib import Path
import subprocess
import time
from uuid import uuid4

from astra_video_studio.config import Settings
from astra_video_studio.jobs import Job, write_json


class IdleTransport:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.directory = settings.contained_path("bridge")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.heartbeat = self.directory / "heartbeat.json"
        self.inbox = self.directory / "inbox.txt"

    def state(self) -> dict | None:
        for _ in range(3):
            try:
                data = json.loads(self.heartbeat.read_text(encoding="utf-8-sig"))
                if not isinstance(data, dict) or not isinstance(data.get("instance_id"), str) or not re.fullmatch(r"[0-9a-f]{32}", data["instance_id"]) or not data.get("ae_version", "").startswith("25."):
                    return None
                if abs(time.time() * 1000 - data["time_ms"]) > 5000:
                    return None
                return data
            except FileNotFoundError:
                return None
            except (OSError, ValueError, TypeError, KeyError):
                # The native File writer may be between truncate/write/close.
                time.sleep(0.02)
        return None

    def ensure_ready(self, executable: str) -> dict:
        startup = self.directory / "startup-pending.json"
        state = self.state()
        expected = None
        if startup.exists():
            expected = json.loads(startup.read_text(encoding="utf-8"))["instance_id"]
        if state and (not expected or state["instance_id"] == expected):
            if state.get("active_job"):
                raise BlockingIOError("AE idle bridge has an unresolved active job")
            startup.unlink(missing_ok=True)
            write_json(self.directory / "session.json", {"instance_id": state["instance_id"], "bootstrap_script": str(self.directory / ("bootstrap-" + state["instance_id"] + ".jsx"))})
            return {"instance_id": state["instance_id"], "transport": "idle_inbox"}
        pid = None
        if expected is None:
            if (self.directory / "session.json").exists():
                raise TimeoutError("Known idle bridge heartbeat is stale. Inspect AE and restart the reviewed bootstrap manually; no automatic second -r launch.")
            expected = uuid4().hex
            config = {"workspace": self.settings.workspace.resolve().as_posix(), "instance_id": expected}
            source = (Path(__file__).parent / "scripts" / "idle_bridge.jsx").read_text(encoding="utf-8")
            script = self.directory / f"bootstrap-{expected}.jsx"
            script.write_text(source.replace("/*ASTRA_BRIDGE_CONFIG*/null", json.dumps(config, ensure_ascii=True)), encoding="utf-8")
            command = [executable, "-r", str(script)]
            write_json(startup, {"instance_id": expected, "command": command})
            try:
                process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except OSError:
                startup.unlink(missing_ok=True)
                write_json(self.directory / "session.json", {"instance_id": expected, "bootstrap_script": str(script) if pid is not None else str(self.directory / ("bootstrap-" + expected + ".jsx"))})
                raise
            pid = process.pid
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            state = self.state()
            if state and state["instance_id"] == expected and not state.get("active_job"):
                startup.unlink(missing_ok=True)
                if pid is not None:
                    process.poll()
                return {"instance_id": expected, "transport": "idle_inbox", "bootstrap_pid": pid}
            time.sleep(0.1)
        raise TimeoutError("AE idle bridge did not acknowledge bootstrap. startup-pending.json retained; no job submitted and no automatic re-bootstrap.")

    def publish(self, job: Job) -> None:
        if self.inbox.exists():
            raise BlockingIOError("AE inbox is occupied; do not overwrite/retry")
        temp = self.directory / (job.id + ".tmp")
        temp.write_text(job.id, encoding="ascii")
        try:
            try: os.link(temp,self.inbox)
            except FileExistsError as exc: raise BlockingIOError('AE inbox is occupied; do not overwrite/retry') from exc
        finally:
            temp.unlink(missing_ok=True)
