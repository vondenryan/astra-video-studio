"""Process identity and durable cross-process render admission. Never launches work."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import time
from uuid import uuid4

INSTANCE = uuid4().hex


def process_identity(pid):
    """PID plus OS creation time prevents treating a reused PID as our worker."""
    if type(pid) is not int or pid <= 0: return {'state':'unknown'}
    if os.name != 'nt':
        try:
            fields=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
            return {'pid':pid,'created':fields[19],'state':'alive'}
        except FileNotFoundError: return {'pid':pid,'state':'dead'}
        except OSError: return {'pid':pid,'state':'unknown'}
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];api.OpenProcess.restype=wintypes.HANDLE
    api.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)]
    api.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    api.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=api.OpenProcess(0x1000,False,pid)
    if not handle:return {'pid':pid,'state':'dead' if ctypes.get_last_error()==87 else 'unknown'}
    try:
        times=[wintypes.FILETIME() for _ in range(4)];code=wintypes.DWORD()
        if not api.GetProcessTimes(handle,*(ctypes.byref(t) for t in times)) or not api.GetExitCodeProcess(handle,ctypes.byref(code)):
            return {'pid':pid,'state':'unknown'}
        return {'pid':pid,'created':str((times[0].dwHighDateTime<<32)|times[0].dwLowDateTime),
                'state':'alive' if code.value==259 else 'dead'}
    finally:api.CloseHandle(handle)


def owner_identity():
    return process_identity(os.getpid())|{'instance_id':INSTANCE}


def owner_state(owner):
    if (not isinstance(owner,dict) or type(owner.get('pid')) is not int or owner['pid']<=0
        or not isinstance(owner.get('created'),str) or not owner['created'].isdigit()):return 'unknown'
    current=process_identity(owner.get('pid'))
    if current['state']=='dead':return 'dead'
    if current['state']!='alive':return 'unknown'
    return 'alive' if current['created']==owner['created'] else 'dead'


class WorkspaceLock:
    """Kernel-backed file lock: crash releases lock, never implies job completion."""
    def __init__(self,path,wait=5,cancel=None):self.path,self.wait,self.cancel=path,wait,cancel
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.stream=self.path.open('a+b');self.stream.seek(0,2)
        if self.stream.tell()==0:self.stream.write(b'0');self.stream.flush()
        deadline=time.monotonic()+self.wait
        while True:
            try:
                self.stream.seek(0)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(self.stream.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(self.stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                return self
            except OSError:
                if (self.cancel and self.cancel()) or time.monotonic()>=deadline:
                    self.stream.close();raise BlockingIOError('Workspace queue lock busy; work was not dispatched')
                time.sleep(.05)
    def __exit__(self,*args):
        try:
            self.stream.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(),fcntl.LOCK_UN)
        finally:self.stream.close()


class RenderRegistry:
    def __init__(self,settings):
        self.settings=settings
        self.directory=settings.contained_path('queue/claims');self.directory.mkdir(parents=True,exist_ok=True)
    def lock(self):return WorkspaceLock(self.settings.contained_path('queue/admission.lock'))
    def worker_lock(self,cancel=None):return WorkspaceLock(self.settings.contained_path('queue/worker.lock'),wait=3600,cancel=cancel)
    def path(self,identifier):
        from astra_video_studio.project_manager import valid_id
        return self.settings.contained_path('queue/claims/'+valid_id(identifier)+'.json')
    @staticmethod
    def validate(value,identifier):
        if (not isinstance(value,dict) or type(value.get('schema_version')) is not int or value['schema_version']!=1 or value.get('job_id')!=identifier
            or type(value.get('released')) is not bool or type(value.get('worker_started')) is not bool
            or not isinstance(value.get('owner'),dict) or not isinstance(value['owner'].get('created'),str)
            or not value['owner']['created'].isdigit() or type(value['owner'].get('pid')) is not int or value['owner']['pid']<=0):
            raise ValueError('Invalid durable render claim; inspect before further admission')
        return value
    def claims(self):
        from astra_video_studio.jobs import read_json
        paths=list(self.directory.glob('*.json'))
        if len(paths)>10000:raise ValueError('Queue claim inventory exceeds diagnostic bound')
        result=[]
        for path in paths:
            checked=self.path(path.stem);value=read_json(checked)
            self.validate(value,path.stem)
            result.append(value)
        return result
    def admit(self,job):
        from astra_video_studio.jobs import write_json,timestamp
        with self.lock():
            path=self.path(job.id)
            if path.exists():raise ValueError('Render job was already admitted')
            if sum(not c.get('released') for c in self.claims())>=4:raise BlockingIOError('Durable workspace render queue full (4 outstanding jobs)')
            write_json(path,dict(schema_version=1,job_id=job.id,owner=job.journal['owner'],admitted_at=timestamp(),worker_started=False,released=False))
    def start(self,job):
        from astra_video_studio.jobs import read_json,write_json,timestamp
        with self.lock():
            claim=self.validate(read_json(self.path(job.id)),job.id)
            if claim.get('released') or claim.get('worker_started') or claim['owner']!=job.journal['owner']:
                raise ValueError('Render claim ownership/start conflict; no replay')
            claim.update(worker_started=True,started_at=timestamp());write_json(self.path(job.id),claim)
    def release(self,job,reason='worker_finished'):
        from astra_video_studio.jobs import read_json,write_json,timestamp
        with self.lock():
            path=self.path(job.id)
            if not path.exists():return
            claim=self.validate(read_json(path),job.id)
            if claim['owner']!=job.journal['owner']:raise ValueError('Cannot release another worker claim')
            claim.update(released=True,released_at=timestamp(),release_reason=reason);write_json(path,claim)
