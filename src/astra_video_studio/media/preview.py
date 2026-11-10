"""Bounded local preview queue: isolated AE render copy → PNG → verified MP4."""
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import math
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from fractions import Fraction
from typing import Literal

from pydantic import BaseModel, Field

from astra_video_studio.ae_bridge.discovery import discover_ae
from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import Job, write_json
from astra_video_studio.lifecycle import RenderRegistry, process_identity
from astra_video_studio.media.ffmpeg import inspect_binary
from astra_video_studio.motion_engine.schemas import StrictModel
from astra_video_studio.motion_engine.timeline import frame
from astra_video_studio.project_manager import ProjectManager, valid_id
from astra_video_studio.schemas import OperationResult

log = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="astra-preview")
_slots = threading.BoundedSemaphore(4)


class PreviewRequest(StrictModel):
    project_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    composition_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    start_time: float = Field(default=0, ge=0, le=300)
    duration: float = Field(default=3, ge=0.1, le=15)
    max_width: int = Field(default=1280, ge=64, le=1920)


class AudioPreviewRequest(PreviewRequest):
    """Separate opt-in 20-second audio contract; silent preview limits are unchanged."""
    duration: float = Field(default=3, ge=0.1, le=20)
    audio_state_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    base_aep_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class PreviewSubmission(BaseModel):
    job_id: str
    status: Literal["queued", "busy"]
    error: str | None = None


class Cancelled(Exception):
    pass


def preview_plan(request: PreviewRequest, comp: dict) -> dict:
    fps = comp["fps"]
    start = frame(request.start_time, fps)
    end = frame(request.start_time + request.duration, fps)
    count = end - start
    if count < 1 or end / fps > comp["duration"] + 1e-6:
        raise ValueError("Preview interval is outside the composition or spans no frames")
    if comp["width"] > 3840 or comp["height"] > 2160 or count > 900:
        raise ValueError("Preview source exceeds 4K/900-frame local limits")
    ratio = min(1, request.max_width / comp["width"])
    width = max(2, int(comp["width"] * ratio) // 2 * 2)
    height = max(2, int(comp["height"] * ratio) // 2 * 2)
    return {"start_time": start / fps, "duration": count / fps, "fps": fps, "frame_count": count, "width": width, "height": height, "source_width": comp["width"], "source_height": comp["height"]}


def frame_sequence(directory: Path, expected_count: int) -> tuple[int, str]:
    files = [p for p in directory.iterdir() if p.is_file()]
    numbers, extensions = [], set()
    for path in files:
        match = re.fullmatch(r"frame_(\d{5,})\.(png|tif|tiff)", path.name, flags=re.IGNORECASE)
        if not match or path.stat().st_size == 0:
            raise ValueError("Unexpected/empty render frame")
        numbers.append(int(match.group(1)))
        extensions.add(path.suffix)
    numbers.sort()
    if len(extensions) != 1 or len(numbers) != expected_count or not numbers or numbers != list(range(numbers[0], numbers[0] + expected_count)):
        raise ValueError("Rendered frame sequence is missing, discontinuous or has the wrong count")
    # AE uses five-digit sequence placeholders for this trusted output template.
    return numbers[0], str(directory / ("frame_%05d" + next(iter(extensions))))


def verify_probe(data: dict, plan: dict) -> dict:
    streams = [stream for stream in data.get("streams", []) if stream.get("codec_type") == "video"]
    if len(streams) != 1:
        raise ValueError("Expected one video stream")
    stream = streams[0]
    if stream.get("codec_name") != "h264" or stream.get("pix_fmt") != "yuv420p":
        raise ValueError("Unexpected MP4 codec/pixel format")
    if stream.get("width") != plan["width"] or stream.get("height") != plan["height"]:
        raise ValueError("Preview resolution mismatch")
    duration = float(data.get("format", {}).get("duration", 0))
    fps = float(Fraction(stream.get("avg_frame_rate", "0/1")))
    if not math.isfinite(duration) or not math.isfinite(fps) or abs(duration - plan["duration"]) > max(0.05, 1 / plan["fps"]):
        raise ValueError("Preview duration mismatch")
    if abs(fps - plan["fps"]) > 0.01 or int(stream.get("nb_read_frames", -1)) != plan["frame_count"]:
        raise ValueError("Preview FPS/decoded frame count mismatch")
    return {"duration": duration, "fps": fps, "frame_count": int(stream["nb_read_frames"]), "width": stream["width"], "height": stream["height"], "codec": stream["codec_name"], "pixel_format": stream["pix_fmt"]}


class PreviewService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.projects = ProjectManager(settings)

    def make_plan(self, request, comp):
        return preview_plan(request, comp)

    def output_directory(self, job, request):
        return job.directory

    def submit(self, request: PreviewRequest) -> PreviewSubmission:
        manifest, source = self.projects.load(request.project_id)
        saved = json.loads((source.parent / "version.json").read_text(encoding="utf-8")) if manifest.get("current_version") else manifest
        if digest(source) != saved.get("sha256"):
            raise ValueError("Saved source changed outside Astra; save a reviewed version first")
        comps = [c for c in saved["result"]["data"]["compositions"] if c["composition_id"] == "astra:composition:" + request.composition_id]
        if len(comps) != 1:
            raise ValueError("Composition ID is absent or ambiguous")
        plan = self.make_plan(request, comps[0])
        if plan.get('purpose') == 'final' and request.base_aep_sha256 != saved['sha256']:
            raise ValueError('Final render base AEP hash conflict')
        if getattr(request, 'audio_state_sha256', None):
            from astra_video_studio.audio import AudioService, AudioTarget
            target = AudioTarget.model_validate(request.model_dump(include={'project_id', 'composition_id', 'base_aep_sha256', 'audio_state_sha256'}))
            audio = AudioService(self.settings)
            _, _, state = audio.state(target)
            if not state['audio_clips']: raise ValueError('Audio preview requires clips')
            audio.assets(state)
        job = Job(self.settings, 'render_final' if plan.get('purpose') == 'final' else 'preview_render')
        if not _slots.acquire(blocking=False):
            job.record("busy", error="Preview queue capacity reached")
            return PreviewSubmission(job_id=job.id, status="busy", error="Preview queue capacity reached (4 outstanding jobs)")
        try:
            RenderRegistry(self.settings).admit(job)
        except (OSError,ValueError) as exc:
            _slots.release()
            job.record('busy',error=str(exc))
            return PreviewSubmission(job_id=job.id,status='busy',error=str(exc))
        job.record("queued", job_id=job.id, request=request.model_dump(), plan=plan, owner_pid=os.getpid(), source=str(source),source_sha256=saved['sha256'])
        try:
            future = _executor.submit(self._work, job, request, source, saved["sha256"], manifest.get("id_map"), plan)
            future.add_done_callback(lambda completed: self._worker_completed(job, completed))
        except Exception:
            _slots.release()
            RenderRegistry(self.settings).release(job,'executor_start_failed')
            job.record("failed", error="Could not start preview worker")
            raise
        return PreviewSubmission(job_id=job.id, status="queued")

    @staticmethod
    def _worker_completed(job, future):
        """Surface uncaught/final-journal errors instead of leaving polling running forever."""
        if future.cancelled():
            _slots.release()  # A cancelled Future never entered _work/finally.
            RenderRegistry(job.settings).release(job,'future_cancelled_before_worker')
            error = RuntimeError('Preview worker was cancelled before committing its result')
        else:
            error = future.exception()
        if error is None:
            return
        log.error('preview=%s worker/completion failure', job.id, exc_info=(type(error), error, error.__traceback__))
        result = OperationResult(operation_id=job.id, status='failed', error='Preview worker could not commit completion: ' + type(error).__name__ + ': ' + str(error), artifacts=[str(job.directory)])
        try:
            write_json(job.directory / 'worker-failure.json', {'operation_id': job.id, 'status': 'failed', 'result': result.model_dump()})
            job.record('failed', result=result.model_dump(), stage='worker_completion_failure')
        except Exception:
            log.exception('preview=%s could not update its main journal; inspect worker-failure.json and native pending markers', job.id)

    def cancel(self, job_id: str) -> dict:
        job_id = valid_id(job_id)
        state = self.projects.job_status(job_id)
        if state["action"] not in ("preview_render", 'render_final'):
            raise ValueError("Only preview jobs support cancellation requests")
        if state["status"] in ("queued", "running"):
            self.settings.contained_path(f"jobs/{job_id}/cancel-requested").touch(exist_ok=True)
        state = self.projects.job_status(job_id)
        state["cancel_requested"] = self.settings.contained_path(f"jobs/{job_id}/cancel-requested").exists()
        return state

    @staticmethod
    def _cancelled(job: Job) -> bool:
        return (job.directory / "cancel-requested").exists()

    def _check_cancel(self, job: Job):
        if self._cancelled(job):
            raise Cancelled("Cancellation requested; no further stages will run")

    def _process(self, job: Job, command: list[str], name: str, timeout: float, native: bool = False):
        job.record("running", stage=name, last_command=command, process_launch_intent=True, process_exit_confirmed=False, process_identity=None,
                   cancellation_policy='wait_native_exit_preserve_on_timeout' if native else 'terminate_owned_child_on_request')
        log.info("preview=%s stage=%s", job.id, name)
        log_path = job.directory / (name + ".log")
        native_pending = self.settings.contained_path("preview-pending.json")
        with log_path.open("w", encoding="utf-8") as output:
            if native:
                try:
                    with native_pending.open("x", encoding="utf-8") as marker:
                        json.dump({"job_id": job.id, "owner_pid": os.getpid(), "status": "starting", "command": command}, marker)
                        marker.flush()
                        os.fsync(marker.fileno())
                except FileExistsError as exc:
                    raise BlockingIOError("Another native renderer is active or unresolved") from exc
            try:
                process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except OSError:
                if native:
                    native_pending.unlink(missing_ok=True)
                raise
            if native:
                write_json(native_pending, {"job_id": job.id, "owner_pid": os.getpid(), "pid": process.pid, "status": "running", "command": command})
            child=process_identity(process.pid)
            job.record("running", stage=name, process_pid=process.pid, process_identity=child, last_command=command)
            deadline = time.monotonic() + timeout
            while process.poll() is None:
                if not native and self._cancelled(job):
                    process.terminate()
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill();process.wait(timeout=5)
                    job.record('running',process_exit_confirmed=True,process_returncode=process.returncode)
                    raise Cancelled('Owned encoder cancelled; partial outputs retained')
                if time.monotonic() > deadline:
                    # Do not kill AE or assume killing the aerender launcher stops
                    # its child engine. Retain isolated outputs and block more renders.
                    if native:
                        write_json(native_pending, {"job_id": job.id, "pid": process.pid, "status": "timeout", "reason": "Native render timeout; inspect renderer before another preview"})
                    else:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=5)
                    raise TimeoutError(f"{name} timed out; see {log_path}")
                time.sleep(0.2)
            if native:
                native_pending.unlink(missing_ok=True)  # Only after confirmed process exit.
            job.record('running',process_exit_confirmed=True,process_returncode=process.returncode)
            if process.returncode:
                raise ValueError(f"{name} failed (exit {process.returncode}); see {log_path}")
        self._check_cancel(job)

    def _work(self, job, request, source, source_hash, mapping, plan):
        registry=RenderRegistry(self.settings)
        try:
            if self._cancelled(job):
                job.record('cancelled',result=OperationResult(operation_id=job.id,status='cancelled',error='Cancelled before worker start').model_dump())
                return
            job.record('queued',stage='waiting_workspace_worker')
            with registry.worker_lock(lambda:self._cancelled(job)):
                registry.start(job)
                job.record('running',stage='worker_started')
                self._work_run(job,request,source,source_hash,mapping,plan)
        except BlockingIOError as exc:
            status='cancelled' if self._cancelled(job) else 'blocked'
            job.record(status,result=OperationResult(operation_id=job.id,status=status,error=str(exc)).model_dump())
        finally:
            try:registry.release(job)
            finally:_slots.release()

    def _work_run(self, job: Job, request: PreviewRequest, source: Path, source_hash: str, mapping: dict | None, plan: dict):
        result = OperationResult(operation_id=job.id, status="running", project_id=request.project_id, project_path=str(source))
        try:
            self._check_cancel(job)
            if self.settings.contained_path("preview-pending.json").exists():
                result.status, result.error = "blocked", "Unresolved native renderer; inspect preview-pending.json"
                return
            if digest(source) != source_hash:
                raise ValueError("Source changed while preview was queued")
            output_directory = self.output_directory(job, request)
            ae = discover_ae(self.settings.ae_executable)
            if not ae.available or ae.error:
                raise ValueError(ae.error or "AE unavailable")
            aerender = Path(ae.path).parent / "aerender.exe"
            if not aerender.is_file():
                raise ValueError("aerender.exe not found beside AfterFX.exe")
            ffmpeg = inspect_binary("ffmpeg", self.settings.ffmpeg)
            ffprobe = inspect_binary("ffprobe", self.settings.ffprobe)
            if not ffmpeg.available or not ffprobe.available:
                raise ValueError(ffmpeg.error or ffprobe.error)
            audio_mix, audio_measurement = None, None
            if getattr(request, 'audio_state_sha256', None):
                from astra_video_studio.audio import AudioService, AudioTarget
                target = AudioTarget.model_validate(request.model_dump(include={'project_id', 'composition_id', 'base_aep_sha256', 'audio_state_sha256'}))
                job.record('running', stage='audio_mix')
                audio_mix, audio_measurement = AudioService(self.settings).render(target,
                    frame(plan['start_time'], plan['fps']), plan['frame_count'], job.directory)
                self._check_cancel(job)
            frames = job.directory / "frames"
            frames.mkdir(exist_ok=False)
            import shutil
            estimated_bytes = plan.get('estimated_bytes', plan["source_width"] * plan["source_height"] * plan["frame_count"] * 16)
            if shutil.disk_usage(job.directory).free < estimated_bytes + 256 * 1024 * 1024:
                raise ValueError("Insufficient disk space for worst-case PNG sequence")
            render_copy = job.directory / "render-copy.aep"
            shutil.copyfile(source, render_copy)
            if digest(render_copy) != source_hash:
                raise ValueError("Render copy hash mismatch")
            job.record("running", stage="preparing_ae", native_preparation_intent=True, result=result.model_dump())
            prepared = self.projects.runner.run("preview_prepare", {"project_path": render_copy.as_posix(), "managed_paths": self.projects.managed_paths(), "id_map": mapping, "composition_id": request.composition_id, "plan": plan, "output_template": self.settings.png_template, "frame_pattern": (frames / "frame_[#####].png").as_posix()})
            job.journal["preparation_operation_id"] = prepared.operation_id
            if prepared.status != "succeeded":
                result.status, result.error = prepared.status, prepared.error
                return
            info = prepared.data
            if info.get("queue_items") != 1 or info.get("width") != plan["source_width"] or info.get("height") != plan["source_height"] or not math.isclose(info.get("duration", -1), plan["duration"], abs_tol=1e-5) or not math.isclose(info.get("start_time", -1), plan["start_time"], abs_tol=1e-5) or not math.isclose(info.get("fps", -1), plan["fps"], abs_tol=1e-5):
                raise ValueError("AE prepared the wrong queue/composition interval")
            if digest(source) != source_hash:
                raise ValueError("Original AEP changed during preview preparation")
            if plan.get('purpose') == 'final':
                self.check_color(info)
                if plan.get('preset') == 'tiff_rgba8':
                    output_settings = info.get('output_settings', {})
                    if output_settings.get('Format') != 'TIFF Sequence' or output_settings.get('Channels') != 'RGB + Alpha' or output_settings.get('Depth') != 'Millions of Colors+':
                        raise ValueError('Intermediate requires acknowledged native 8-bit RGBA TIFF settings')
            self._check_cancel(job)
            self._process(job, [str(aerender), "-project", str(render_copy), "-rqindex", "1", "-close", "DO_NOT_SAVE_CHANGES"], "aerender", self.settings.final_timeout if plan.get('purpose') == 'final' else 300, native=True)
            first, pattern = frame_sequence(frames, plan["frame_count"])
            if plan.get('preset') == 'tiff_rgba8':
                result = self.finish_sequence(job, request, source, source_hash, render_copy, plan, prepared,
                    first, pattern, output_directory, ffmpeg.path, ffprobe.path, audio_mix, audio_measurement)
                return
            video = output_directory / ('final.mp4' if plan.get('purpose') == 'final' else 'preview.mp4')
            picture = output_directory/'picture.mp4' if audio_mix else video
            vf = f"scale={plan['width']}:{plan['height']},format=yuv420p"
            tags = []
            if plan.get('purpose') == 'final':
                vf = (f"scale={plan['width']}:{plan['height']}:force_original_aspect_ratio=decrease:in_range=pc:out_range=tv:out_color_matrix=bt709,"
                    f"pad={plan['width']}:{plan['height']}:(ow-iw)/2:(oh-ih)/2,format=yuv420p,"
                    "setparams=range=limited:color_primaries=bt709:color_trc=iec61966-2-1:colorspace=bt709")
                tags = ['-color_range', 'tv', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'iec61966-2-1']
            self._process(job, [ffmpeg.path, "-nostdin", "-hide_banner", "-v", "error", "-n", "-framerate", str(plan["fps"]), "-start_number", str(first), "-i", pattern, "-vf", vf, "-frames:v", str(plan["frame_count"]), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", *tags, "-movflags", "+faststart", str(picture)], "encode", 300 if plan.get('purpose') == 'final' else 120)
            if audio_mix:
                self._process(job, [ffmpeg.path, '-nostdin', '-v', 'error', '-n', '-i', str(picture), '-i', str(audio_mix),
                    '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
                    '-t', str(plan['duration']), '-movflags', '+faststart', str(video)], 'audio_mux', 120)
            self._process(job, [ffprobe.path, "-v", "error", "-count_frames", "-show_streams", "-show_format", "-of", "json", str(video)], "ffprobe", 60)
            probe = json.loads((job.directory / "ffprobe.log").read_text(encoding="utf-8-sig"))
            verified = verify_probe(probe, plan)
            if plan.get('purpose') == 'final':
                stream = next(s for s in probe['streams'] if s.get('codec_type') == 'video')
                if any(stream.get(k) != v for k,v in {'color_range':'tv','color_space':'bt709','color_primaries':'bt709','color_transfer':'iec61966-2-1'}.items()):
                    raise ValueError('Final render color tags differ from declared policy')
                verified['color'] = {k:stream.get(k) for k in ('color_range','color_space','color_primaries','color_transfer')}
            if audio_mix:
                from astra_video_studio.media import audio as audio_media
                audio_measurement['encoded_stream'] = audio_media.verify_audio_probe(probe, plan['duration'], plan['fps'])
                decoded = job.directory/'audio-decoded.wav'
                audio_media.decode(ffmpeg.path, video, decoded, job.directory/'audio-decode.log')
                decoded_measurement = audio_media.analyze_pcm(decoded)
                if abs(decoded_measurement['sample_count']/audio_media.RATE-plan['duration']) > 1/plan['fps']:
                    raise ValueError('Decoded audio duration exceeds one-frame tolerance')
                if decoded_measurement['peak_linear'] > 10**(-0.1/20):
                    raise ValueError('Decoded AAC exceeds -0.1dBFS sample-peak ceiling')
                audio_measurement['decoded'] = {k:v for k,v in decoded_measurement.items() if k != 'energy_onsets'}
            self._process(job, [ffmpeg.path, "-nostdin", "-v", "error", "-xerror", "-i", str(video), "-map", "0:v:0",
                *(['-map', '0:a:0'] if audio_mix else []), "-f", "null", "-"], "decode", 60)
            samples = []
            for index, timepoint in enumerate([0, plan["duration"] / 2, max(0, plan["duration"] - 1.5 / plan["fps"])]):
                sample = job.directory / f"sample-{index}.png"
                self._process(job, [ffmpeg.path, "-nostdin", "-v", "error", "-n", "-i", str(video), "-ss", str(timepoint), "-frames:v", "1", "-update", "1", str(sample)], f"sample-{index}", 30)
                if not sample.is_file() or not sample.stat().st_size:
                    raise ValueError("Sample frame extraction produced no image")
                samples.append(str(sample))
            if digest(source) != source_hash:
                raise ValueError("Source hash changed while rendering")
            result.status = "succeeded"
            result.data = {"job_id": job.id, "video_path": str(video), "render_copy": str(render_copy), "plan": plan, "verification": verified, "samples": samples, "source_sha256": source_hash, "video_sha256": digest(video), "ae_preparation": prepared.data}
            if plan.get('purpose') == 'final':
                result.data.update(purpose='final', preset=request.preset, destination_path=str(output_directory),
                    source_color=info.get('source_color'), color_policy=request.color_policy)
            if audio_mix:
                _, _, final_state = AudioService(self.settings).state(target)
                AudioService(self.settings).assets(final_state)
                result.data.update(audio_state_sha256=request.audio_state_sha256, audio_backend='ffmpeg_postproduction',
                    audio_verification=audio_measurement, audio_mix_sha256=digest(audio_mix))
            result.artifacts = [str(video), str(render_copy), *samples, str(job.directory / "job.json"), *[str(p) for p in job.directory.glob("*.log")]]
            if audio_mix: result.artifacts += [str(audio_mix), str(decoded)]
            # Remove only the exact PNG files validated above, after native render
            # completed and the MP4 decoded. Retain logs, copy, MP4 and samples.
            for path in frames.iterdir():
                path.unlink()
            frames.rmdir()
        except Cancelled as exc:
            result.status, result.error = "cancelled", str(exc)
        except TimeoutError as exc:
            result.status, result.error = "timeout", str(exc)
        except BlockingIOError as exc:
            result.status, result.error = "blocked", str(exc)
        except Exception as exc:
            result.status, result.error = "failed", f"{type(exc).__name__}: {exc}"
            log.exception("preview=%s failed", job.id)
        finally:
            if not result.artifacts:
                result.artifacts = [str(job.directory / "job.json"), *[str(p) for p in job.directory.glob("*.log")]]
                if (job.directory / "render-copy.aep").is_file():
                    result.artifacts.append(str(job.directory / "render-copy.aep"))
            job.record(result.status, result=result.model_dump(), cancel_requested=self._cancelled(job))
