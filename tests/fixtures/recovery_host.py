"""Controlled host/child interruption fixture. Never starts Adobe or executes JSX."""
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

from astra_video_studio.ae_bridge.runner import BridgeRunner
from astra_video_studio.ae_bridge.idle_transport import IdleTransport
from astra_video_studio.config import Settings
from astra_video_studio.jobs import Job,write_json
from astra_video_studio.lifecycle import RenderRegistry
from astra_video_studio.media.preview import PreviewService
from astra_video_studio.schemas import ComponentStatus

mode=sys.argv[1];root=Path(sys.argv[2]);root.mkdir(parents=True,exist_ok=True);s=Settings(root)

if mode=='real_read':
    original=IdleTransport.publish
    def pause(transport,job):
        original(transport,job)
        write_json(Path(sys.argv[4]),{'job_id':job.id,'pid':os.getpid()})
        time.sleep(30)  # Test kills this owned Python host after the real AE ack.
    with patch.object(IdleTransport,'publish',pause):
        BridgeRunner(s).run('inspect',{'project_path':Path(sys.argv[3]).as_posix()})
elif mode=='late_ack_child':
    identifier=sys.argv[3];time.sleep(2)
    directory=root/'jobs'/identifier
    result=dict(operation_id=identifier,status='succeeded',data={'fixture_only':True,'no_ae_execution':True})
    raw=json.dumps(dict(schema_version=1,protocol='artifact-v1',result=result)).encode()
    (directory/'native-result.json').write_bytes(raw)
    write_json(directory/'result.json',dict(operation_id=identifier,status='succeeded',protocol='artifact-v1',
        evidence=dict(file='native-result.json',bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())))
elif mode in ('native_child','encoder_child'):
    write_json(root/'child-alive.json',{'pid':os.getpid()});time.sleep(3)
    (root/'partial-output.fixture').write_bytes(b'isolated fixture output, not an AE frame');sys.exit(0)
elif mode=='bridge':
    def publish(job):
        child=subprocess.Popen([sys.executable,__file__,'late_ack_child',str(root),job.id],
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        write_json(root/'control.json',{'job_id':job.id,'child_pid':child.pid})
    with patch('astra_video_studio.ae_bridge.runner.AELock',side_effect=nullcontext),\
        patch('astra_video_studio.ae_bridge.runner.discover_ae',return_value=ComponentStatus(available=True,path='fixture.exe')),\
        patch('astra_video_studio.ae_bridge.runner.IdleTransport.ensure_ready',return_value={'transport':'fixture_only'}),\
        patch('astra_video_studio.ae_bridge.runner.IdleTransport.publish',side_effect=publish):
        BridgeRunner(s).run('inspect',{'project_path':str(root/'fixture.aep')})
else:
    job=Job(s,'preview_render');registry=RenderRegistry(s)
    try:registry.admit(job)
    except BlockingIOError:sys.exit(9)
    job.record('queued');write_json(root/(str(os.getpid())+'-control.json'),{'job_id':job.id,'pid':os.getpid()})
    if mode=='queued':
        while True:time.sleep(.2)
    elif mode in ('render','encode'):
        registry.start(job)
        write_json(root/'control.json',{'job_id':job.id})
        PreviewService(s)._process(job,[sys.executable,__file__,'native_child' if mode=='render' else 'encoder_child',str(root)],
            'aerender' if mode=='render' else 'encode',30,native=mode=='render')
