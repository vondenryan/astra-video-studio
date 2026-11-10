from pathlib import Path
import shutil
import subprocess

from astra_video_studio.schemas import ComponentStatus


def inspect_binary(name: str, override: str | None = None) -> ComponentStatus:
    candidate = str(Path(override).expanduser().resolve()) if override else shutil.which(name)
    if not candidate or not Path(candidate).is_file():
        return ComponentStatus(path=candidate, error=f"{name} not found; configure ASTRA_{name.upper()} or PATH.")
    try:
        result = subprocess.run(
            [candidate, "-version"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=5, shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        line = (result.stdout or result.stderr).splitlines()
        if result.returncode or not line or not line[0].startswith(f"{name} version "):
            return ComponentStatus(path=candidate, error=f"{name} version check failed (exit {result.returncode}).")
        return ComponentStatus(available=True, path=candidate, version=line[0])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ComponentStatus(path=candidate, error=f"{name} check failed: {type(exc).__name__}")
