"""Append a hash-bound H.264 control and foreground bounds to an existing diagnostic."""
import argparse
from pathlib import Path
import re

from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.media.ffmpeg import inspect_binary
from run_parity import ROOT, read, require, verified_copy, write
from run_visual_diagnostic import command, metrics


def bounds(pixels, width, height, roi, distance):
    background = pixels[:3]
    x0, y0, x1, y1 = roi
    xs, ys = [], []
    for y in range(y0, y1):
        for x in range(x0, x1):
            at = (y * width + x) * 4
            if any(abs(pixels[at + channel] - background[channel]) > distance for channel in range(3)):
                xs.append(x)
                ys.append(y)
    return [min(xs), min(ys), max(xs) + 1, max(ys) + 1] if xs else None


def analyze(attempt, settings):
    original_path = attempt / "summary.json"
    original = read(original_path)
    original_plan = read(attempt / "plan.json")
    require(digest(attempt / "plan.json") == original["plan_sha256"], "Diagnostic plan changed")
    plan_path = ROOT / "visual-codec-control-plan.json"
    plan = read(plan_path)
    directory = attempt / "codec-control"
    directory.mkdir()
    verified_copy(plan_path, directory / "plan.json", digest(plan_path))
    ffmpeg = inspect_binary("ffmpeg", settings.ffmpeg)
    require(ffmpeg.available, "FFmpeg unavailable")
    cases = []
    for case in original["cases"]:
        if case["status"] != "diagnosed":
            continue
        config, = [item for item in original_plan["cases"] if item["name"] == case["name"]]
        source = attempt / case["name"]
        require(digest(source / "worker-report.json") == case["worker_report_sha256"], "Worker evidence changed")
        frames = []
        for frame in case["frames"]:
            index = frame["frame"]
            candidate = source / f"ec-scaled-{index}.png"
            native = source / f"ae-{index}.png"
            require(digest(candidate) == frame["ec_png_sha256"] and digest(native) == frame["ae_png_sha256"],
                    "Diagnostic frame changed")
            video = directory / f"{case['name']}-{index}.mp4"
            decoded = directory / f"{case['name']}-{index}.png"
            command([ffmpeg.path, "-nostdin", "-v", "error", "-n", "-i", str(candidate),
                     "-frames:v", "1", "-c:v", plan["codec"], "-preset", plan["preset"],
                     "-crf", str(plan["crf"]), "-vf", f"format={plan['pixel_format']}", str(video)])
            command([ffmpeg.path, "-nostdin", "-v", "error", "-n", "-i", str(video),
                     "-frames:v", "1", str(decoded)])
            pixels = [command([ffmpeg.path, "-nostdin", "-v", "error", "-i", str(path),
                               "-frames:v", "1", "-pix_fmt", "rgba", "-f", "rawvideo", "-"])
                      for path in (native, decoded)]
            regions = {}
            for name, roi in config["rois"].items():
                result = metrics(*pixels, config["width"], config["height"], roi, plan["thresholds"])
                left, right = [bounds(value, config["width"], config["height"], roi,
                                      plan["foreground_channel_distance"]) for value in pixels]
                error = max(abs(a - b) for a, b in zip(left, right)) if left and right else None
                result.update(ae_bounds=left, ec_bounds=right, bounds_max_delta_reference_px=error,
                              diagnostic_bounds_pass=(left is None and right is None)
                              or (error is not None and error <= plan["bounds_reference_pixels_max"]))
                regions[name] = result
            frames.append({"frame": index, "regions": regions, "control_mp4_sha256": digest(video),
                           "control_png_sha256": digest(decoded),
                           "ae_background_rgb": list(pixels[0][:3]), "ec_background_rgb": list(pixels[1][:3])})
        cases.append({"name": case["name"], "frames": frames})
    report = {"scope": plan["scope"], "limits": plan["limits"], "plan_sha256": digest(plan_path),
              "original_summary_sha256": digest(original_path), "ffmpeg_version": ffmpeg.version,
              "cases": cases}
    write(directory / "summary.json", report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("attempt", help="The visual-diagnostic UUID directory name")
    args = parser.parse_args()
    require(re.fullmatch(r"visual-diagnostic-[0-9a-f]{32}", args.attempt), "Unexpected diagnostic directory name")
    settings = Settings.from_env()
    report = analyze(settings.contained_path("ec0/" + args.attempt), settings)
    print([(case["name"], len(case["frames"])) for case in report["cases"]])


if __name__ == "__main__":
    main()
