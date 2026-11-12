"""Compare archived AE H.264 frames and native inspection with an offline AEP import."""
import math
from pathlib import Path
import subprocess
from uuid import uuid4

from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.media.ffmpeg import inspect_binary
from run_parity import NO_WINDOW, ROOT, read, require, verified_copy, worker, write


def command(args):
    return subprocess.run(args, capture_output=True, check=True, timeout=60, creationflags=NO_WINDOW).stdout


def prepare(settings, case, fonts, directory):
    acceptance_path = settings.contained_path(case["acceptance"])
    acceptance = read(acceptance_path)
    preview = acceptance[case["preview_key"]]
    job_path = settings.contained_path(f"jobs/{case['job_id']}/job.json")
    job = read(job_path)
    data = job["result"]["data"]
    source = settings.contained_path(job["source"])
    version_path = source.parent / "version.json"
    version = read(version_path)
    native_path = settings.contained_path(f"jobs/{case['native_operation']}/result.json")
    native = read(native_path)
    require(
        job["status"] == job["result"]["status"] == native["status"] == version["status"] == "succeeded"
        and preview["job_id"] == data["job_id"] == case["job_id"]
        and native["operation_id"] == version["operation_id"] == case["native_operation"]
        and native["data"]["compositions"] == version["result"]["data"]["compositions"]
        and not native["data"]["project_dirty"]
        and settings.contained_path(native["data"]["project_path"]) == source
        and preview["source_sha256"] == data["source_sha256"] == version["sha256"] == case["source_sha256"]
        and preview["video_sha256"] == data["video_sha256"] == case["video_sha256"],
        "Archived source, acknowledgement and render evidence disagree",
    )
    comp, = native["data"]["compositions"]
    require((comp["name"], comp["width"], comp["height"], comp["fps"], comp["background"])
            == (case["composition"], case["native_width"], case["native_height"], case["fps"], case["background"]),
            "Unexpected archived composition")
    require(data["plan"]["start_time"] == 0 and data["plan"]["fps"] == case["fps"]
            and (data["plan"]["width"], data["plan"]["height"]) == (case["width"], case["height"])
            and all(0 <= frame < data["plan"]["frame_count"] for frame in case["frames"]), "Unexpected render timing")
    verified_copy(source, directory / "reference.aep", case["source_sha256"])
    verified_copy(settings.contained_path(data["video_path"]), directory / "reference.mp4", case["video_sha256"])
    for font in fonts:
        verified_copy(Path("C:/Windows/Fonts") / font["file"], directory / font["file"], font["sha256"])
    samples = next((track["samples"] for layer in comp["layers"] for track in layer["transforms"].values()
                    if track.get("keys")), [])
    times = [row["time"] for row in samples] or [0, comp["duration"] / 2, comp["duration"] - 1 / comp["fps"]]
    config = {**case, "fonts": fonts, "sample_times": times}
    write(directory / "scene.json", config)
    write(directory / "native-composition.json", comp)
    return comp, {
        "acceptance_sha256": digest(acceptance_path), "job_sha256": digest(job_path),
        "version_sha256": digest(version_path), "native_ack_sha256": digest(native_path),
        "source_sha256": case["source_sha256"], "video_sha256": case["video_sha256"],
    }


def compare_semantics(native, imported, limits):
    differences = []
    checks = 0

    def check(label, expected, actual, spatial=False):
        nonlocal checks
        checks += 1
        if isinstance(expected, list):
            require(isinstance(actual, list) and len(expected) == len(actual), "Unexpected vector dimensions")
            for index, (left, right) in enumerate(zip(expected, actual)):
                check(f"{label}.{index}", left, right, spatial)
            return
        if isinstance(expected, (str, bool)) or expected is None:
            matches = expected == actual
        else:
            tolerance = limits["position_error_px"] if spatial else limits["scalar_absolute_relative"]
            matches = math.isclose(expected, actual, rel_tol=limits["scalar_absolute_relative"], abs_tol=tolerance)
        if not matches:
            differences.append({"field": label, "ae": expected, "effectcraft": actual})

    layers = {layer["name"]: layer for layer in imported["layers"]}
    require(len(layers) == len(native["layers"]), "Layer count changed during import")
    key_count = sample_count = 0
    for layer in native["layers"]:
        ec = layers[layer["name"]]
        for name, track in layer["transforms"].items():
            candidate = ec["tracks"][name]
            prefix = layer["name"] + "." + name
            spatial = name in {"position", "anchor"}
            if not track["keys"]:
                check(prefix + ".value", track["value"], candidate["value"]["v"], spatial)
                continue
            check(prefix + ".key_count", len(track["keys"]), len(candidate["keys"]))
            require(len(track["keys"]) == len(candidate["keys"]), "Key count mismatch")
            for index, (left, right) in enumerate(zip(track["keys"], candidate["keys"])):
                key_count += 1
                label = f"{prefix}.key.{index}"
                check(label + ".time", left["time"], right["time"] / 254_016_000_000)
                check(label + ".value", left["value"], right["value"]["v"], spatial)
                for a, b in (("temporal_auto", "auto_bezier"), ("temporal_continuous", "continuous"), ("roving", "roving")):
                    check(label + "." + a, left[a], right[b])
                for side in ("in", "out"):
                    check(label + "." + side, left[side + "_type"], right[side + "_interp"].lower())
                    if left[side + "_type"] == "bezier":
                        require(len(left[side + "_ease"]) == len(right[side + "_ease"]), "Ease dimensions changed")
                        for a, b in zip(left[side + "_ease"], right[side + "_ease"]):
                            check(label + "." + side + ".speed", a["speed"], b["speed"])
                            check(label + "." + side + ".influence", a["influence"], b["influence"] * 100)
                    if track["spatial"]:
                        check(label + "." + side + ".spatial", left[side + "_spatial"], right["spatial_" + side], True)
                if track["spatial"]:
                    check(label + ".spatial_auto", left["spatial_auto"], right["spatial_auto"])
                    check(label + ".spatial_continuous", left["spatial_continuous"], right["spatial_continuous"])
            for sample in track["samples"]:
                matching, = [row for row in candidate["samples"] if math.isclose(sample["time"], row["time"], abs_tol=1e-8)]
                check(prefix + ".sample." + str(sample["time"]), sample["value"], matching["value"]["v"], spatial)
                sample_count += 1
    return {"checks": checks, "keys": key_count, "samples": sample_count,
            "pass": not differences, "differences": differences}


def metrics(left, right, width, height, roi, limits):
    require(len(left) == len(right) == width * height * 4, "Unexpected decoded frame bytes")
    x0, y0, x1, y1 = roi
    require(0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height, "Invalid diagnostic ROI")
    scores = []
    error = 0
    c1, c2 = (0.01 * 255)**2, (0.03 * 255)**2
    for y in range(y0, y1, 8):
        for x in range(x0, x1, 8):
            pairs = [([], []) for _ in range(3)]
            for row in range(y, min(y + 8, y1)):
                for column in range(x, min(x + 8, x1)):
                    at = (row * width + column) * 4
                    for channel, (a, b) in enumerate(pairs):
                        a.append(left[at + channel])
                        b.append(right[at + channel])
            for a, b in pairs:
                count = len(a)
                mean_a, mean_b = sum(a) / count, sum(b) / count
                var_a = sum((value - mean_a)**2 for value in a) / max(count - 1, 1)
                var_b = sum((value - mean_b)**2 for value in b) / max(count - 1, 1)
                cov = sum((p - mean_a) * (q - mean_b) for p, q in zip(a, b)) / max(count - 1, 1)
                scores.append(((2 * mean_a * mean_b + c1) * (2 * cov + c2))
                              / ((mean_a**2 + mean_b**2 + c1) * (var_a + var_b + c2)))
                error += sum(abs(p - q) for p, q in zip(a, b))
    ssim = sum(scores) / len(scores)
    mae = error / ((x1 - x0) * (y1 - y0) * 3)
    return {"ssim": ssim, "rgb_mae_bytes": mae,
            "diagnostic_threshold_pass": ssim >= limits["ssim_min"] and mae <= limits["mae_bytes_max"]}


def frames(ffmpeg, directory, case):
    rows = []
    for frame in case["frames"]:
        native_png = directory / f"ae-{frame}.png"
        ec_png = directory / f"ec-scaled-{frame}.png"
        command([ffmpeg, "-nostdin", "-v", "error", "-i", str(directory / "reference.mp4"),
                 "-vf", f"select=eq(n\\,{frame})", "-frames:v", "1", str(native_png)])
        command([ffmpeg, "-nostdin", "-v", "error", "-i", str(directory / f"ec-{frame}.png"),
                 "-vf", f"scale={case['width']}:{case['height']}", "-frames:v", "1", str(ec_png)])
        raw = []
        for path in (native_png, ec_png):
            raw.append(command([ffmpeg, "-nostdin", "-v", "error", "-i", str(path),
                                "-frames:v", "1", "-pix_fmt", "rgba", "-f", "rawvideo", "-"]))
        rows.append((frame, raw, {"ae_png_sha256": digest(native_png), "ec_png_sha256": digest(ec_png)}))
    return rows


def main():
    settings = Settings.from_env()
    base = settings.contained_path("ec0")
    require(not any(base.glob("visual-diagnostic-*/*/pending.json")), "Inspect the retained diagnostic worker first")
    plan_path = ROOT / "visual-diagnostic-plan.json"
    plan = read(plan_path)
    attempt = base / ("visual-diagnostic-" + uuid4().hex)
    attempt.mkdir()
    print(attempt, flush=True)
    verified_copy(plan_path, attempt / "plan.json", digest(plan_path))
    baseline = {path: digest(path) for path in settings.contained_path("projects").rglob("*.aep")}
    write(attempt / "aep-baseline.json", {str(path): sha for path, sha in baseline.items()})
    executable = base / "target/debug/astra-ec0-aep.exe"
    ffmpeg = inspect_binary("ffmpeg", settings.ffmpeg)
    require(ffmpeg.available, "FFmpeg unavailable")
    reports = []
    for case in plan["cases"]:
        directory = attempt / case["name"]
        directory.mkdir()
        native, provenance = prepare(settings, case, plan["fonts"], directory)
        result = worker(executable, "compare", directory)
        if result["status"] == "refused":
            reports.append({"name": case["name"], "status": "refused", "provenance": provenance,
                            "import_report": result["import_report"], "worker_report_sha256": digest(directory / "worker-report.json")})
            continue
        require(not result["font_system_scanned"], "Unexpected system font scan")
        semantic = compare_semantics(native, result, plan["thresholds"])
        measurements = []
        for frame, raw, hashes in frames(ffmpeg.path, directory, case):
            regions = {name: metrics(*raw, case["width"], case["height"], roi, plan["thresholds"])
                       for name, roi in case["rois"].items()}
            measurements.append({"frame": frame, "regions": regions, **hashes})
        reports.append({"name": case["name"], "status": "diagnosed", "provenance": provenance,
                        "semantics": semantic, "frames": measurements, "import_report": result["import_report"],
                        "worker_report_sha256": digest(directory / "worker-report.json")})
    require(all(path.is_file() and digest(path) == sha for path, sha in baseline.items()), "A preexisting AEP changed")
    report = {"scope": plan["scope"], "plan_sha256": digest(plan_path), "worker_sha256": digest(executable),
              "font_policy": plan["font_policy"], "fonts": plan["fonts"], "cases": reports,
              "preexisting_managed_aeps_preserved": len(baseline),
              "acceptance": "Lossless AE visual parity and historical font identity remain pending"}
    write(attempt / "summary.json", report)
    print([(row["name"], row["status"]) for row in reports], flush=True)


if __name__ == "__main__":
    main()
