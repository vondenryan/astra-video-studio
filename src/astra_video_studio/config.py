from dataclasses import dataclass
import os
from pathlib import Path, PureWindowsPath
import re
import math


def _containment_key(path):
    """Compare already-resolved paths in the same Windows namespace.

    Concurrent hard-link publication can make realpath retain the extended
    prefix on only one operand. Do not strip arbitrary device namespaces or
    replace realpath: symlinks/junctions must still resolve before this step.
    """
    if isinstance(path, PureWindowsPath):
        value = str(path)
        if value.startswith('\\\\?\\UNC\\'):
            return PureWindowsPath('\\\\' + value[8:])
        if re.match(r'^\\\\\?\\[A-Za-z]:\\', value):
            return PureWindowsPath(value[4:])
    return path


@dataclass(frozen=True)
class Settings:
    workspace: Path
    ae_executable: str | None = None
    ffmpeg: str | None = None
    ffprobe: str | None = None
    import_roots: tuple[Path, ...] = ()
    png_template: str = "PNG Sequence"
    ae_result_transport: str = 'artifact-v1'
    final_max_seconds: float = 60
    final_max_frames: int = 1800
    final_timeout: int = 900

    def __post_init__(self):
        if self.ae_result_transport not in ('inline-v1', 'artifact-v1'):
            raise ValueError('ASTRA_AE_RESULT_TRANSPORT must be inline-v1 or artifact-v1')
        if not math.isfinite(self.final_max_seconds) or not 0 < self.final_max_seconds <= 300:
            raise ValueError('Final render seconds limit must be in (0,300]')
        if not 1 <= self.final_max_frames <= 36000 or not 60 <= self.final_timeout <= 3600:
            raise ValueError('Invalid final render frame/time budget')

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            workspace=Path(os.environ.get("ASTRA_WORKSPACE", "workspace")).expanduser().resolve(),
            ae_executable=os.environ.get("ASTRA_AE_EXECUTABLE") or None,
            ffmpeg=os.environ.get("ASTRA_FFMPEG") or None,
            ffprobe=os.environ.get("ASTRA_FFPROBE") or None,
            import_roots=tuple(Path(p).expanduser().resolve() for p in os.environ.get("ASTRA_IMPORT_ROOTS", "").split(os.pathsep) if p.strip()),
            png_template=os.environ.get("ASTRA_PNG_TEMPLATE", "PNG Sequence"),
            ae_result_transport=os.environ.get('ASTRA_AE_RESULT_TRANSPORT', 'artifact-v1'),
            final_max_seconds=float(os.environ.get('ASTRA_FINAL_MAX_SECONDS', '60')),
            final_max_frames=int(os.environ.get('ASTRA_FINAL_MAX_FRAMES', '1800')),
            final_timeout=int(os.environ.get('ASTRA_FINAL_TIMEOUT', '900')),
        )

    def contained_path(self, relative: str) -> Path:
        path = (self.workspace / relative).resolve()
        if not _containment_key(path).is_relative_to(_containment_key(self.workspace.resolve())):
            raise ValueError("Path must remain inside ASTRA_WORKSPACE")
        return path

    def import_path(self, value: str) -> Path:
        """Only workspace files or operator-configured external read roots."""
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self.workspace / path
        path = path.resolve()
        roots = (self.workspace.resolve(), *(root.resolve() for root in self.import_roots))
        if not any(path.is_relative_to(root) for root in roots):
            raise ValueError("Source is outside the workspace and approved ASTRA_IMPORT_ROOTS")
        if path.suffix.lower() != ".aep" or not path.is_file():
            raise ValueError("Source must be an existing .aep file")
        if path.stat().st_size < 64:
            raise ValueError("Source AEP is empty or too small")
        return path

    def read_path(self, value: str, suffixes: set[str]) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute(): path = self.workspace / path
        path = path.resolve()
        if not any(path.is_relative_to(root.resolve()) for root in (self.workspace, *self.import_roots)):
            raise ValueError('Source is outside workspace/approved import roots')
        if not path.is_file() or path.suffix.lower() not in suffixes or path.stat().st_size == 0:
            raise ValueError('Unsupported or missing media source')
        return path
