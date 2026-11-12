"""Compare preserved native TIFF RGB/alpha with the hash-bound offline EC renderer."""
import argparse
import math
import re

from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.media.ffmpeg import inspect_binary
from run_codec_control import bounds
from run_parity import read, require, verified_copy, worker, write
from run_visual_diagnostic import command, compare_semantics, metrics


def compare_channels(native, composite, straight, width, height, roi, background, limits):
    require(len(native) == len(composite) == len(straight) == width * height * 4, "Decoded dimensions disagree")
    result = metrics(native, composite, width, height, roi, limits)
    result["rgb_pass"] = result.pop("diagnostic_threshold_pass")
    x0, y0, x1, y1 = roi
    alpha_max = alpha_total = transparent = 0
    matte_max = 0
    matte = [math.floor(value * 255 + 0.5) for value in background]
    for y in range(y0, y1):
        for x in range(x0, x1):
            at = (y * width + x) * 4
            error = abs(native[at + 3] - straight[at + 3])
            alpha_max = max(alpha_max, error)
            alpha_total += error
            if native[at + 3] == 0:
                transparent += 1
                matte_max = max(matte_max, *(abs(native[at + channel] - matte[channel]) for channel in range(3)))
    left = bounds(native, width, height, roi, 24)
    right = bounds(composite, width, height, roi, 24)
    delta = max(abs(a - b) for a, b in zip(left, right)) if left and right else None
    result.update(
        alpha_max_error_bytes=alpha_max, alpha_mae_bytes=alpha_total / ((x1 - x0) * (y1 - y0)),
        alpha_pass=alpha_max <= limits["alpha_max_error_bytes"],
        transparent_pixels_checked=transparent, transparent_matte_max_error_bytes=matte_max,
        native_matte_matches_acknowledged_background=matte_max <= 1,
        ae_bounds=left, ec_bounds=right, bounds_max_delta_native_px=delta,
        bounds_pass=(left is None and right is None) or (delta is not None and delta <= limits["bounds_native_pixels_max"]),
    )
    result["pass"] = all(result[key] for key in
                         ("rgb_pass", "alpha_pass", "bounds_pass", "native_matte_matches_acknowledged_background"))
    return result


def analyze(settings, attempt):
    capture_path = attempt / "capture-summary.json"
    captured = read(capture_path)
    plan = read(attempt / "plan.json")
    require(digest(attempt / "plan.json") == captured["plan_sha256"], "Capture plan changed")
    require(captured["font_bindings_before"] == captured["font_bindings_after"], "Unstable native font bindings")
    output = attempt / "comparison"
    output.mkdir()
    ffmpeg = inspect_binary("ffmpeg", settings.ffmpeg)
    require(ffmpeg.available, "FFmpeg unavailable")
    executable = settings.contained_path("ec0/target/debug/astra-ec0-aep.exe")
    reports = []
    for case in plan["cases"]:
        reference, = [row for row in captured["references"] if row["name"] == case["name"]]
        native = reference["native_composition"]
        sequence_path = settings.contained_path(reference["sequence_manifest"])
        require(digest(sequence_path) == reference["sequence_manifest_sha256"], "Native sequence manifest changed")
        sequence = read(sequence_path)
        require(sequence["source_pixel_format"] == "rgba" and sequence["depth_bits"] == 8
                and sequence["native_bytes_preserved"] and sequence["alpha_verified"]
                and sequence["alpha_association"] == "Premultiplied (Matted)",
                "Native alpha association is outside this comparison contract")
        color = sequence["source_color"]
        require(color["bits_per_channel"] == 8 and color["linearized"] is False
                and color["working_space"] in ("", "None", "sRGB IEC61966-2.1"),
                "Native color policy is outside this comparison contract")
        directory = output / case["name"]
        directory.mkdir()
        verified_copy(attempt / case["source_file"], directory / "reference.aep", case["source_sha256"])
        for font in plan["fonts"]:
            verified_copy(attempt / font["file"], directory / font["file"], font["sha256"])
        samples = next((track["samples"] for layer in native["layers"] for track in layer["transforms"].values()
                        if track.get("keys")), [])
        times = [row["time"] for row in samples] or [0, native["duration"] / 2, native["duration"] - 1 / native["fps"]]
        write(directory / "scene.json", {**case, "background": sequence["composition_background"],
                                         "fonts": plan["fonts"], "sample_times": times})
        rendered = worker(executable, "compare", directory)
        require(rendered["status"] == "rendered" and not rendered["font_system_scanned"], "EC render did not verify")
        semantics = compare_semantics(native, rendered, plan["thresholds"])
        frames = []
        ratio_x, ratio_y = case["native_width"] / case["width"], case["native_height"] / case["height"]
        require(ratio_x.is_integer() and ratio_y.is_integer(), "Comparison needs a declared integer ROI scaling")
        regions = {name: [int(x0 * ratio_x), int(y0 * ratio_y), int(x1 * ratio_x), int(y1 * ratio_y)]
                   for name, (x0, y0, x1, y1) in case["rois"].items()}
        for frame in case["frames"]:
            info = sequence["frames"][frame]
            require(info["path"] == f"frame_{frame:05d}.tif", "Incorrect native frame index")
            source = sequence_path.parent / "frames" / info["path"]
            verified_copy(source, directory / info["path"], info["sha256"])
            require(source.stat().st_size == info["bytes"], "Native TIFF size changed")
            inputs = [directory / info["path"], directory / f"ec-{frame}.png", directory / f"ec-rgba-{frame}.png"]
            pixels = [command([ffmpeg.path, "-nostdin", "-v", "error", "-i", str(path),
                               "-frames:v", "1", "-pix_fmt", "rgba", "-f", "rawvideo", "-"]) for path in inputs]
            measured = {name: compare_channels(*pixels, case["native_width"], case["native_height"], roi,
                                               sequence["composition_background"], plan["thresholds"])
                        for name, roi in regions.items()}
            frames.append({"frame": frame, "inputs_sha256": [digest(path) for path in inputs], "regions": measured})
        reports.append({"name": case["name"], "semantics": semantics, "frames": frames,
                        "worker_report_sha256": digest(directory / "worker-report.json"),
                        "native_sequence_sha256": reference["sequence_manifest_sha256"]})
    passed = all(case["semantics"]["pass"] and all(region["pass"] for frame in case["frames"]
                                                  for region in frame["regions"].values()) for case in reports)
    report = {
        "capture_summary_sha256": digest(capture_path), "plan_sha256": digest(attempt / "plan.json"),
        "scope": "Native-resolution preserved TIFF RGB/alpha compared separately with EC output using the same current font files",
        "worker_sha256": digest(executable), "cases": reports,
        "status": "passed" if passed else "measured_with_outliers",
        "limits": "Applies to the captured typography/vector/animation cases. Native TIFF bytes are unchanged.",
    }
    write(output / "summary.json", report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("attempt")
    args = parser.parse_args()
    require(re.fullmatch(r"lossless-[0-9a-f]{32}", args.attempt), "Unexpected lossless capture directory")
    settings = Settings.from_env()
    report = analyze(settings, settings.contained_path("ec0/" + args.attempt))
    print(report["status"])


if __name__ == "__main__":
    main()
