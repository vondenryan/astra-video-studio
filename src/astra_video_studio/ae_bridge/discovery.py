import ctypes
import os
from pathlib import Path
import shutil

from astra_video_studio.schemas import ComponentStatus


def executable_version(path: Path) -> str | None:
    """Read PE fixed version metadata without launching the executable."""
    if os.name != "nt":
        return None
    from ctypes import wintypes

    lib = ctypes.WinDLL("version", use_last_error=True)
    lib.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    lib.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    lib.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    lib.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
    size = lib.GetFileVersionInfoSizeW(str(path), None)
    if not size:
        return None
    data = ctypes.create_string_buffer(size)
    if not lib.GetFileVersionInfoW(str(path), 0, size, data):
        return None
    ptr, length = ctypes.c_void_p(), wintypes.UINT()
    if not lib.VerQueryValueW(data, "\\", ctypes.byref(ptr), ctypes.byref(length)) or length.value < 52:
        return None
    info = ctypes.cast(ptr, ctypes.POINTER(wintypes.DWORD))
    if info[0] != 0xFEEF04BD:
        return None
    return ".".join(str(x) for x in (info[2] >> 16, info[2] & 65535, info[3] >> 16, info[3] & 65535))


def discover_ae(override: str | None = None) -> ComponentStatus:
    if override:
        path = Path(override).expanduser().resolve()
    else:
        root = Path(os.environ.get("ProgramFiles", "C:/Program Files"))
        path = root / "Adobe/Adobe After Effects 2025/Support Files/AfterFX.exe"
        if not path.is_file():
            found = shutil.which("AfterFX.exe")
            if found:
                path = Path(found).resolve()
    if not path.is_file():
        return ComponentStatus(path=str(path), error="After Effects executable not found; set ASTRA_AE_EXECUTABLE.")
    version = executable_version(path)
    compatible = bool(version and version.split(".")[0] == "25")
    return ComponentStatus(
        available=True, path=str(path), version=version,
        error=None if compatible else "AE 2025 (25.x) could not be confirmed from executable metadata.",
    )
