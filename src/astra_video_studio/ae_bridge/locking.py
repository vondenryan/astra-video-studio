"""One Windows-session mutex for all Astra AE operations, across processes."""
import ctypes
from ctypes import wintypes
import os


class AELock:
    def __enter__(self):
        if os.name != "nt":
            raise OSError("The AE bridge requires Windows")
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self.api.CreateMutexW.restype = wintypes.HANDLE
        self.api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.api.WaitForSingleObject.restype = wintypes.DWORD
        self.api.ReleaseMutex.argtypes = [wintypes.HANDLE]
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.api.CreateMutexW(None, False, "Local\\AstraVideoStudio.AE2025")
        if not self.handle:
            raise OSError("Could not create the AE instance mutex")
        code = self.api.WaitForSingleObject(self.handle, 0)
        if code != 0:
            if code == 0x80:
                self.api.ReleaseMutex(self.handle)
            self.api.CloseHandle(self.handle)
            raise BlockingIOError("AE bridge busy or prior mutex owner exited unexpectedly; inspect AE before retrying")
        return self

    def __exit__(self, *args):
        self.api.ReleaseMutex(self.handle)
        self.api.CloseHandle(self.handle)
