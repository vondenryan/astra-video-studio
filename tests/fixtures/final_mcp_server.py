"""Test-only fake native picture provider. Real MCP/FFmpeg; never launches AE."""
from pathlib import Path
from uuid import uuid4

from astra_video_studio import mcp_server
from astra_video_studio.ae_bridge.runner import BridgeRunner
from astra_video_studio.config import Settings
from astra_video_studio.media import preview
from astra_video_studio.media.audio import binaries,run
from astra_video_studio.schemas import ComponentStatus,OperationResult

settings=Settings.from_env()
for name in ('AfterFX.exe','aerender.exe'): (settings.workspace/name).write_bytes(b'never executed fixture')
preview.discover_ae=lambda *args:ComponentStatus(available=True,path=str(settings.workspace/'AfterFX.exe'),version='25.5')
prepared={}


def native(self,action,payload):
    if action!='preview_prepare': raise AssertionError('Native calls forbidden in final-render fixture')
    prepared.update(payload)
    plan=payload['plan']
    if plan['preset']=='tiff_rgba8':prepared['frame_pattern']=payload['frame_pattern'].replace('.png','.tif')
    return OperationResult(operation_id=uuid4().hex,status='succeeded',data={
        'fixture_only':True,'queue_items':1,'fps':plan['fps'],'width':plan['source_width'],'height':plan['source_height'],
        'duration':plan['duration'],'start_time':plan['start_time'],
        'source_color':{'bits_per_channel':8,'linearized':False,'working_space':''},
        'output_settings':{'Color':'Premultiplied (Matted)','Format':'TIFF Sequence','Channels':'RGB + Alpha','Depth':'Millions of Colors+'}})


process=preview.PreviewService._process
def synthetic(self,job,command,name,timeout,native=False):
    if not native: return process(self,job,command,name,timeout,native=False)
    ffmpeg,_=binaries(settings);plan=prepared['plan']
    target=str(Path(prepared['frame_pattern'].replace('[#####]','%05d')))
    run([ffmpeg,'-nostdin','-v','error','-n','-f','lavfi','-i',
        f"color=c=black@0:s={plan['source_width']}x{plan['source_height']}:r={plan['fps']},format=rgba,drawbox=x=20:y=20:w=80:h=60:color=red:t=fill:replace=1",
        '-frames:v',str(plan['frame_count']),'-pix_fmt','rgba',target],job.directory/'fixture-frames.log')


BridgeRunner.run=native
preview.PreviewService._process=synthetic
mcp_server.main()
