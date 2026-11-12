"""Prepare or explicitly collect lossless AE references through the guarded services."""
import argparse
from pathlib import Path
import re
import time
from urllib.parse import unquote, urlparse
from uuid import uuid4

from astra_video_studio.ae_bridge.idle_transport import IdleTransport
from astra_video_studio.ae_bridge.runner import BridgeRunner
from astra_video_studio.config import Settings
from astra_video_studio.design import DesignService, FontsQuery
from astra_video_studio.existing_projects import ExistingProjectService, digest
from astra_video_studio.media.final_render import FinalRenderRequest, RenderService
from astra_video_studio.project_manager import ProjectManager
from astra_video_studio.schemas import ProjectOpenCopyRequest
from run_parity import ROOT, read, require, verified_copy, write


def ready(settings):
    state = IdleTransport(settings).state()
    require(state and not state.get("active_job"), "Bridge stale or busy; no automatic launch")
    require(not any(settings.contained_path(name).exists() for name in
                    ("ae-pending.json", "preview-pending.json", "bridge/inbox.txt")),
            "Native work is pending; inspect before continuing")
    startup = settings.contained_path("bridge/startup-pending.json")
    if startup.exists():
        require(read(startup)["instance_id"] == state["instance_id"], "Bootstrap acknowledgement does not match the session")


def font_evidence(settings, plan, directory, label):
    ready(settings)
    result = DesignService(settings).fonts(FontsQuery(query="Arial", limit=100, include_locations=True,
                                                     include_project_context=True))
    write(directory / (label + ".json"), result.model_dump(mode="json"))
    require(result.status == "succeeded", result.error or "Native font query did not succeed")
    require(not result.data["truncated"], "Ambiguous/truncated font query")
    selected = []
    for expected in plan["fonts"]:
        font, = [row for row in result.data["fonts"] if row["postscript_name"] == expected["postscript"]]
        require(not font["substitute"] and bool(font["location"]), "Font binding is unavailable")
        location = font["location"]
        if location.startswith("file:"):
            location = unquote(urlparse(location).path).lstrip("/")
        path = Path(location).resolve()
        configured = (Path("C:/Windows/Fonts") / expected["file"]).resolve()
        require(path == configured and digest(path) == expected["sha256"], "Native font path or bytes differ from the plan")
        selected.append({**font, "sha256": expected["sha256"]})
    return selected, result.data["project_context"]


def prepare(settings):
    plan_path = ROOT / "visual-diagnostic-plan.json"
    original = read(plan_path)
    attempt = settings.contained_path("ec0/lossless-" + uuid4().hex)
    attempt.mkdir()
    cases = []
    for case in original["cases"]:
        job = read(settings.contained_path(f"jobs/{case['job_id']}/job.json"))
        source = settings.contained_path(job["source"])
        verified_copy(source, attempt / (case["name"] + ".aep"), case["source_sha256"])
        cases.append({**case, "source_file": case["name"] + ".aep",
                      "native_frame_count": max(case["frames"]) + 1})
    for font in original["fonts"]:
        verified_copy(Path("C:/Windows/Fonts") / font["file"], attempt / font["file"], font["sha256"])
    plan = {
        "scope": "New acknowledged TIFF RGBA8 references, explicit current AE font paths and offline EC comparison",
        "cases": cases, "fonts": original["fonts"], "source_plan_sha256": digest(plan_path),
        "thresholds": {**original["thresholds"], "alpha_max_error_bytes": 1, "bounds_native_pixels_max": 1},
        "rules": ["Use existing protected project-copy and render services.",
                  "One collection attempt per prepared directory. Retain failed or unknown work.",
                  "Preserve existing AEPs, snapshot the checked-clean active source, restore its saved path.",
                  "Native TIFF bytes and association remain unchanged.",
                  "Compare stored native RGB to EC composited over the acknowledged background.",
                  "Compare native alpha independently to the straight-alpha EC output."],
    }
    write(attempt / "plan.json", plan)
    return attempt


def capture(settings, attempt):
    require(not (attempt / "capture-intent.json").exists(), "This collection was already attempted; inspect its records")
    plan_path = attempt / "plan.json"
    plan = read(plan_path)
    ready(settings)
    projects = ProjectManager(settings)
    managed = {Path(path) for path in projects.managed_paths()}
    baseline = {path: digest(path) for path in settings.contained_path("projects").rglob("*.aep")}
    write(attempt / "aep-baseline.json", {str(path): sha for path, sha in baseline.items()})
    fonts, context = font_evidence(settings, plan, attempt, "fonts-before")
    original_path = settings.contained_path(context["project_path"]) if context["project_path"] else None
    require(context["dirty"] is False and (original_path in managed if original_path else context["item_count"] == 0),
            "Active project must be a checked-clean managed source or an empty project")
    if original_path:
        verified_copy(original_path, attempt / "active-source-backup.aep", baseline[original_path])
    write(attempt / "capture-intent.json", {"plan_sha256": digest(plan_path),
                                           "original_context": context, "font_bindings": fonts})
    references = []
    service = RenderService(settings)
    for case in plan["cases"]:
        name = case["name"]
        source = attempt / case["source_file"]
        require(digest(source) == case["source_sha256"], "Prepared source changed")
        ready(settings)
        opened = ExistingProjectService(settings).open_copy(ProjectOpenCopyRequest(source_path=str(source)))
        write(attempt / (name + "-open.json"), opened.model_dump(mode="json"))
        require(opened.status == "succeeded", opened.error or "Reference copy was not opened")
        comp, = opened.data["compositions"]
        require((comp["name"], comp["width"], comp["height"], comp["fps"])
                == (case["composition"], case["native_width"], case["native_height"], case["fps"]),
                "Native copy composition changed")
        bindings, current = font_evidence(settings, plan, attempt, name + "-fonts")
        require(current["dirty"] is False and settings.contained_path(current["project_path"]) == Path(opened.project_path),
                "Reference copy is no longer active and clean")
        required_fonts = {run["style"]["font"] for layer in comp["layers"] if layer.get("text_style")
                          for run in layer["text_style"]["style_runs"]}
        require(required_fonts <= {font["postscript_name"] for font in bindings}, "Reference uses an unverified font")
        require(all(not layer["text_style"]["font_missing"] for layer in comp["layers"] if layer.get("text_style")),
                "Native reference substituted a font")
        request = FinalRenderRequest(
            project_id=opened.project_id, composition_id=comp["composition_id"].removeprefix("astra:composition:"),
            base_aep_sha256=case["source_sha256"], preset="tiff_rgba8", start_time=0,
            duration=case["native_frame_count"] / case["fps"], width=case["native_width"],
            height=case["native_height"], fps=case["fps"],
            destination=attempt.relative_to(settings.workspace).as_posix() + "/" + name + "-tiff",
            color_policy="interpret_native_rgb_as_srgb",
        )
        write(attempt / (name + "-render-request.json"), request.model_dump(mode="json"))
        submission = service.submit(request)
        write(attempt / (name + "-submission.json"), submission.model_dump(mode="json"))
        require(submission.status in {"queued", "running"}, submission.error or "Render was not admitted")
        deadline = time.monotonic() + 1800
        while True:
            status = projects.job_status(submission.job_id)
            if status["status"] in {"succeeded", "failed", "timeout", "blocked", "cancelled", "busy"}:
                break
            require(time.monotonic() < deadline, "Render unresolved; inspect retained job before doing anything else")
            time.sleep(0.5)
        write(attempt / (name + "-render-status.json"), status)
        require(status["status"] == status["result"]["status"] == "succeeded", "Native render did not succeed")
        data = status["result"]["data"]
        sequence_path = settings.contained_path(data["sequence_manifest_path"])
        require(digest(sequence_path) == data["sequence_manifest_sha256"]
                and data["source_sha256"] == case["source_sha256"], "Native sequence source or evidence mismatch")
        sequence = read(sequence_path)
        require(sequence["native_bytes_preserved"] and sequence["frame_count"] == case["native_frame_count"],
                "Incomplete native sequence")
        for row in sequence["frames"]:
            require(re.fullmatch(r"frame_[0-9]{5}\.tif", row["path"]), "Unexpected native frame path")
            frame = sequence_path.parent / "frames" / row["path"]
            require(digest(frame) == row["sha256"] and frame.stat().st_size == row["bytes"], "Native frame changed")
        references.append({"name": name, "project_id": opened.project_id, "project_path": opened.project_path,
                           "open_operation_id": opened.operation_id, "render_job_id": submission.job_id,
                           "source_sha256": case["source_sha256"], "sequence_manifest": str(sequence_path),
                           "sequence_manifest_sha256": data["sequence_manifest_sha256"],
                           "native_composition": comp, "font_bindings": bindings})
        write(attempt / (name + "-reference.json"), references[-1])
        print(name + " native TIFF reference completed", flush=True)
    after_fonts, after_context = font_evidence(settings, plan, attempt, "fonts-after")
    require(after_fonts == fonts, "Font bindings changed during native rendering")
    restored = None
    if original_path:
        require(digest(original_path) == baseline[original_path], "Original active source changed")
        restored = BridgeRunner(settings).run("open_copy", {
            "project_path": original_path.as_posix(), "source_path": original_path.as_posix(),
            "managed_paths": projects.managed_paths(),
        })
        write(attempt / "restore.json", restored.model_dump(mode="json"))
        require(restored.status == "succeeded" and settings.contained_path(restored.data["project_path"]) == original_path,
                "Original saved project was not restored")
    require(all(path.is_file() and digest(path) == sha for path, sha in baseline.items()), "A preexisting managed AEP changed")
    summary = {"plan_sha256": digest(plan_path), "references": references,
               "original_project_restored": original_path is not None and restored.status == "succeeded",
               "initial_empty_project": original_path is None, "preexisting_managed_aeps_preserved": len(baseline),
               "font_bindings_before": fonts, "font_bindings_after": after_fonts}
    write(attempt / "capture-summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", help="Prepared lossless-UUID directory. Requires exclusive operator coordination.")
    args = parser.parse_args()
    settings = Settings.from_env()
    if args.capture:
        require(re.fullmatch(r"lossless-[0-9a-f]{32}", args.capture), "Unexpected capture directory name")
        attempt = settings.contained_path("ec0/" + args.capture)
        try:
            capture(settings, attempt)
        except Exception as error:
            write(attempt / "capture-failure.json", {"error": str(error)})
            intent = attempt / "capture-intent.json"
            if intent.exists() and not (attempt / "restore.json").exists():
                try:
                    ready(settings)
                    context = read(intent)["original_context"]
                    if context["project_path"]:
                        original = settings.contained_path(context["project_path"])
                        require(digest(original) == read(attempt / "aep-baseline.json")[str(original)],
                                "Original source changed; restoration deferred")
                        restored = BridgeRunner(settings).run("open_copy", {
                            "project_path": original.as_posix(), "source_path": original.as_posix(),
                            "managed_paths": ProjectManager(settings).managed_paths(),
                        })
                        write(attempt / "restore.json", restored.model_dump(mode="json"))
                except Exception as restore_error:
                    write(attempt / "restore-deferred.json", {"reason": str(restore_error)})
            raise
    else:
        print(prepare(settings))


if __name__ == "__main__":
    main()
