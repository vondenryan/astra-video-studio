"""Technical local reference inspection; semantic/visual judgements stay explicit."""
import json
from pathlib import Path
import subprocess
from uuid import uuid4
from pydantic import Field

from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import write_json
from astra_video_studio.media.ffmpeg import inspect_binary
from astra_video_studio.motion_engine.schemas import StrictModel


class ReferenceRequest(StrictModel):
    source_path: str = Field(min_length=1,max_length=32767)
    sample_times: list[float] | None = Field(default=None,min_length=1,max_length=8)


class ReferenceReport(StrictModel):
    reference_id: str
    source_path: str
    source_sha256: str
    metadata: dict
    samples: list[str]
    visual_analysis_performed: bool = False
    limitations: list[str]


def analyze(settings: Settings,request: ReferenceRequest) -> ReferenceReport:
    source=settings.read_path(request.source_path,{'.mp4','.mov','.webm','.png','.jpg','.jpeg','.tif','.tiff'})
    if source.stat().st_size>2_000_000_000: raise ValueError('Reference exceeds 2 GB limit')
    ffmpeg,ffprobe=inspect_binary('ffmpeg',settings.ffmpeg),inspect_binary('ffprobe',settings.ffprobe)
    if not ffmpeg.available or not ffprobe.available: raise ValueError(ffmpeg.error or ffprobe.error)
    identifier=uuid4().hex; directory=settings.contained_path('references/'+identifier); directory.mkdir(parents=True,exist_ok=False)
    def run(command,timeout):
        result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout,shell=False,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode: raise ValueError('Reference media inspection failed: '+result.stderr[-1000:])
        return result.stdout
    data=json.loads(run([ffprobe.path,'-v','error','-protocol_whitelist','file,pipe','-show_streams','-show_format','-of','json',str(source)],15))
    videos=[v for v in data.get('streams',[]) if v.get('codec_type')=='video']
    if not videos or videos[0].get('width',0)*videos[0].get('height',0)>16_000_000: raise ValueError('Reference has no bounded image/video stream')
    duration=float(data.get('format',{}).get('duration',0))
    samples=[]
    times=request.sample_times or ([0] if duration<=0 else [0,duration*0.5,max(0,duration-0.1)])
    if any(t<0 or (duration>0 and t>=duration) or (duration<=0 and t!=0) for t in times): raise ValueError('Reference sample time outside media duration')
    for i,t in enumerate(times):
        target=directory/f'sample-{i}.png'
        run([ffmpeg.path,'-nostdin','-v','error','-n','-protocol_whitelist','file,pipe','-i',str(source),'-ss',str(t),'-vf','scale=960:-2','-frames:v','1','-update','1',str(target)],30)
        if not target.is_file(): raise ValueError('Reference frame extraction failed')
        samples.append(str(target))
    report=ReferenceReport(reference_id=identifier,source_path=str(source),source_sha256=digest(source),metadata={'width':videos[0].get('width'),'height':videos[0].get('height'),'codec':videos[0].get('codec_name'),'fps':videos[0].get('avg_frame_rate'),'duration':duration},samples=samples,limitations=['Technical metadata and sampled images only; no automatic shot/style/semantic similarity claim.','Codex/operator must actually inspect samples before recording visual observations.'])
    write_json(directory/'report.json',report.model_dump()); return report
