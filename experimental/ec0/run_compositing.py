"""Run the fixed compositing probes and check their decoded RGBA pixels."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import read_json, write_json
from astra_video_studio.media.ffmpeg import inspect_binary
from astra_video_studio.svg import parse_svg

ROOT = Path(__file__).resolve().parent
WIDTH, HEIGHT = 160, 120
CLEAR = (0, 0, 0, 0)
GREEN = (0, 255, 0, 255)
CYAN = (0, 255, 255, 255)
PROBES = {
    "fill-0.png": [(80, 60, GREEN), (10, 10, CLEAR)],
    "vectors-0.png": [(44, 60, GREEN), (80, 60, (255, 0, 0, 255)), (112, 60, (255, 0, 0, 255)), (10, 60, CLEAR)],
    "trim-0.png": [(40, 60, (255,) * 4), (72, 60, (255,) * 4), (104, 60, CLEAR)],
    "morph-0.png": [(48, 60, (0, 0, 255, 255)), (80, 60, CLEAR), (112, 60, CLEAR)],
    "morph-15.png": [(48, 60, CLEAR), (80, 60, (0, 0, 255, 255)), (112, 60, CLEAR)],
    "morph-30.png": [(48, 60, CLEAR), (80, 60, CLEAR), (112, 60, (0, 0, 255, 255))],
    "mask-0.png": [(50, 60, (255, 255, 0, 255)), (80, 60, CLEAR), (10, 60, CLEAR)],
    "alpha-matte-0.png": [(80, 60, CYAN), (10, 60, CLEAR)],
    "luma-control-0.png": [(80, 60, CYAN), (10, 60, CLEAR)],
    "precomp-parent-0.png": [(112, 60, (255, 0, 255, 255)), (80, 60, CLEAR)],
}
PNG_NAMES = sorted([*PROBES, "blur-0.png", "luma-matte-0.png"])
SVG_PROBES = [(10, 10), (40, 60), (80, 60), (120, 60), (40, 102), (74, 110)]


def svg_input(attempt):
    source = attempt / "input.svg"
    shutil.copyfile(ROOT / "svg-fixture.svg", source)
    groups = parse_svg(source.read_bytes())
    for group in groups:
        del group["group_id"]  # The production parser allocates AE identities per call.
    write_json(attempt / "normalized-svg.json", groups)
    refused = []
    for case, fragment in {
        "gradient": '<rect width="50" height="50" fill="url(#paint)"/>',
        "transform": '<rect width="50" height="50" transform="translate(10 10)"/>',
        "image": '<image href="unsupported.png"/>',
    }.items():
        data = f'<svg viewBox="0 0 160 120">{fragment}</svg>'.encode()
        try:
            parse_svg(data)
        except ValueError as error:
            refused.append({"case": case, "error": str(error)})
        else:
            raise ValueError(f"Unsupported SVG feature accepted: {case}")
    write_json(attempt / "svg-refusals.json", refused)
    return groups


def check_native_paths(actual, groups):
    def paint(style, stroke=False):
        if style is None:
            return None
        result = {"rgba": [*style["color"], 1], "opacity": style["opacity"]}
        if stroke:
            result.update(width=style["width"], cap=0, join=0)
        return result

    expected = [{"path": g["path"], "fill": paint(g["fill"]), "stroke": paint(g["stroke"], True)} for g in groups]
    if actual != expected:
        raise ValueError("Reopened SVG paths or paint parameters differ from the normalized SVG")


def check_svg_pixels(before, after, tolerance):
    if len(before) != WIDTH * HEIGHT * 4 or len(after) != len(before):
        raise ValueError("Incorrect SVG raster dimensions")
    before_targets = [CLEAR, GREEN, (128, 127, 0, 255), (255, 0, 0, 128), (255,) * 4, (255,) * 4]
    after_targets = [CLEAR, GREEN, (0, 127, 128, 255), (0, 0, 255, 128), (255,) * 4, (255,) * 4]
    observed = []
    for (x, y), first, second in zip(SVG_PROBES, before_targets, after_targets):
        offset = (y * WIDTH + x) * 4
        pair = (tuple(before[offset:offset + 4]), tuple(after[offset:offset + 4]))
        if any(abs(a - b) > tolerance for actual, expected in zip(pair, (first, second)) for a, b in zip(actual, expected)):
            raise ValueError(f"SVG paint or geometry mismatch at {(x, y)}: {pair}")
        observed.append({"point": [x, y], "before": pair[0], "after": pair[1]})
    changed = 0
    for offset in range(0, len(before), 4):
        if before[offset:offset + 4] != after[offset:offset + 4]:
            y, x = divmod(offset // 4, WIDTH)
            if not (64 <= x < 136 and 40 <= y < 96):
                raise ValueError("SVG edit changed pixels outside the target rectangle")
            changed += 1
    if changed != 72 * 56:
        raise ValueError(f"SVG edit affected {changed} pixels instead of the rectangle's full area")
    return {"probes": observed, "changed_pixels": changed}


def check_selector_pixels(decoded):
    def regions(rgba):
        if len(rgba) != WIDTH * HEIGHT * 4:
            raise ValueError("Incorrect text selector raster dimensions")
        return tuple(bytes(
            rgba[(y * WIDTH + x) * 4 + 3]
            for y in range(HEIGHT) for x in range(start, stop)
        ) for start, stop in ((0, 60), (60, WIDTH)))

    first, middle, last = (regions(decoded[f"selector-{frame}.png"]) for frame in (0, 15, 30))
    if any(first[0]) or any(first[1]) or any(middle[0]) or middle[1] != last[1]:
        raise ValueError("Character reveal did not preserve the visible character at midpoint")
    if not all(max(region) == 255 for region in last):
        raise ValueError("Final frame must reveal both characters")
    return {"visible_alpha_pixels_by_character_region": {
        str(frame): [sum(value > 0 for value in region) for region in samples]
        for frame, samples in zip((0, 15, 30), (first, middle, last))
    }}


def check_pixels(name, rgba, tolerance):
    if len(rgba) != WIDTH * HEIGHT * 4:
        raise ValueError("Incorrect raster dimensions")

    def pixel(x, y):
        offset = (y * WIDTH + x) * 4
        return tuple(rgba[offset:offset + 4])

    if name == "luma-matte-0.png":
        if any(rgba[3::4]):
            raise ValueError("Black luma matte should hide the entire target")
        return {"transparent_pixels": WIDTH * HEIGHT}
    if name == "blur-0.png":
        positions = [40, 45, 48, 52, 60, 80]
        alpha = [pixel(x, 60)[3] for x in positions]
        mirror = [pixel(WIDTH - 1 - x, 60)[3] for x in positions]
        if not 0 < alpha[1] < alpha[2] < alpha[3] < alpha[4] <= alpha[5] or alpha[-1] < 254:
            raise ValueError(f"Blur edge or halo mismatch: {alpha}")
        if any(abs(a - b) > tolerance for a, b in zip(alpha, mirror)):
            raise ValueError(f"Asymmetric blur edge: {alpha}, {mirror}")
        return {"edge_alpha": alpha, "mirrored_alpha": mirror}
    samples = []
    for x, y, expected in PROBES[name]:
        actual = pixel(x, y)
        if any(abs(a - b) > tolerance for a, b in zip(actual, expected)):
            raise ValueError(f"{name} pixel {(x, y)}: got {actual}, expected {expected}")
        samples.append({"point": [x, y], "rgba": actual})
    return samples


def main(suite="compositing"):
    settings = Settings.from_env()
    base = settings.contained_path("ec0")
    if list(base.glob("*/pending.json")):
        raise ValueError("Inspect the pending EC0 job before continuing")
    exe = settings.contained_path("ec0/target/debug/astra-ec0-compositing.exe")
    binary = digest(exe)
    ffmpeg = inspect_binary("ffmpeg", settings.ffmpeg)
    if not ffmpeg.available:
        raise ValueError("FFmpeg unavailable")
    svg = suite == "svg"
    selector = suite == "text-selector"
    runs = settings.contained_path(f"ec0/{suite}-runs")
    runs.mkdir(exist_ok=True)
    attempt = settings.contained_path(f"ec0/{suite}-" + uuid4().hex)
    attempt.mkdir()
    plan_file = attempt / "plan.json"
    shutil.copyfile(ROOT / f"{suite}-plan.json", plan_file)
    plan = read_json(plan_file)
    ref = read_json(base / "dependencies-current.json")
    closure = settings.contained_path(ref["closure_path"])
    metadata = settings.contained_path(ref["metadata_path"])
    closure_data = read_json(closure)
    if (digest(closure) != ref["closure_sha256"]
            or digest(metadata) != closure_data["metadata_sha256"]
            or digest(ROOT / "worker/Cargo.lock") != closure_data["cargo_lock_sha256"]
            or closure_data["gui_packages"]):
        raise ValueError("Dependency evidence does not match the locked build")
    shutil.copyfile(closure, attempt / "dependency-closure.json")
    shutil.copyfile(metadata, attempt / "cargo-metadata.json")
    baseline = {str(path): digest(path) for path in settings.contained_path("projects").rglob("*.aep")}
    write_json(attempt / "aep-baseline.json", baseline)
    groups = svg_input(attempt) if svg else None
    if svg:
        png_names = ["svg-before.png", "svg-after.png"]
    elif selector:
        png_names = [f"selector-{frame}.png" for frame in plan["frames"]]
    else:
        png_names = PNG_NAMES
    extra_outputs = ["edited.ecproj", "paths.json"] if svg else []
    expected = sorted(["project.ecproj", "result.json", *png_names, *extra_outputs])
    protocol = f"astra-ec0-{suite}-v1"
    reports = []
    for threads in plan["threads"]:
        job = uuid4().hex
        directory = runs / job
        out = attempt / f"{job}-stdout.json"
        err = attempt / f"{job}-stderr.log"
        marker = attempt / "pending.json"
        if digest(exe) != binary:
            raise ValueError("Worker changed before dispatch")
        write_json(marker, {"job_id": job, "phase": "dispatch_intent", "binary_sha256": binary})
        input_path = attempt / "normalized-svg.json" if svg else os.devnull
        with out.open("xb") as stdout, err.open("xb") as stderr, open(input_path, "rb") as stdin:
            args = [str(exe), "--root", str(runs), "--job", job]
            if suite != "compositing":
                args.append(f"--{suite}")
            child = subprocess.Popen(
                args,
                env=dict(os.environ, RAYON_NUM_THREADS=str(threads)),
                stdin=stdin, stdout=stdout, stderr=stderr, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            write_json(marker, {"job_id": job, "phase": "running", "pid": child.pid, "binary_sha256": binary})
            code = child.wait(timeout=90)
        write_json(attempt / f"{job}-exit.json", {"job_id": job, "exit_code": code})
        if code or out.stat().st_size > 8192:
            raise ValueError(f"Worker exit or receipt failure; inspect {out}")
        receipt = read_json(out)
        if (receipt.get("protocol"), receipt.get("job_id"), receipt.get("status"), receipt.get("revision")) != (
            protocol, job, "succeeded", plan["upstream_revision"],
        ) or receipt.get("roundtrip_equal") is not True:
            raise ValueError("Unexpected worker receipt")
        if suite == "compositing" and [row["case"] for row in receipt["dependency_refusals"]] != plan["graph_refusals"]:
            raise ValueError("Incomplete dependency negatives")
        if svg and receipt.get("native_paths") != len(groups):
            raise ValueError("Incorrect native SVG path count")
        if selector and (
            receipt.get("font_postscript") != plan["font"]["postscript"]
            or receipt.get("font_sha256") != plan["font"]["sha256"]
            or receipt.get("system_fonts_scanned") is not False
        ):
            raise ValueError("Text selector used an unexpected font")
        if sorted(p.name for p in directory.iterdir()) != expected:
            raise ValueError("Missing or unexpected output")
        for name in expected:
            path = directory / name
            if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()) or path.stat().st_size > 16777216:
                raise ValueError("Invalid output path or size")
        if read_json(directory / "result.json") != receipt:
            raise ValueError("Persisted receipt mismatch")
        shutil.copyfile(marker, attempt / f"{job}-completed-pending.json")
        marker.unlink()
        decoded = {}
        for name in png_names:
            decoded[name] = subprocess.run(
                [ffmpeg.path, "-v", "error", "-i", str(directory / name), "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
                check=True, capture_output=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout
        if svg:
            check_native_paths(read_json(directory / "paths.json"), groups)
            probes = check_svg_pixels(decoded["svg-before.png"], decoded["svg-after.png"], plan["pixel_channel_tolerance"])
        elif selector:
            probes = check_selector_pixels(decoded)
        else:
            probes = {name: check_pixels(name, rgba, plan["pixel_channel_tolerance"]) for name, rgba in decoded.items()}
        reports.append({"job_id": job, "threads": threads, "receipt": receipt, "pixel_checks": probes,
                        "files": {name: digest(directory / name) for name in expected}})
    stable_files = ["project.ecproj", *png_names, *extra_outputs]
    if any(row["files"][name] != reports[0]["files"][name] for row in reports for name in stable_files):
        raise ValueError("Outputs differ across CPU thread counts")
    if digest(exe) != binary or any(digest(Path(path)) != sha for path, sha in baseline.items()):
        raise ValueError("Worker or prior project hash changed")
    record = {
        "scope": plan["scope"], "runs": reports, "binary_sha256": binary, "plan_sha256": digest(plan_file),
        "dependency_closure_sha256": digest(attempt / "dependency-closure.json"),
        "prior_aep_files_verified": len(baseline), "pending": plan["pending"],
    }
    if svg:
        record.update(svg_sha256=digest(attempt / "input.svg"), native_paths=len(groups),
                      svg_refusals=read_json(attempt / "svg-refusals.json"))
    proof = attempt / "verification.json"
    write_json(proof, record)
    write_json(base / f"{suite}-current.json", {"directory": str(attempt), "verification_sha256": digest(proof)})
    print(json.dumps({"directory": str(attempt), "runs": len(reports), "pngs_per_run": len(png_names),
                      "prior_aep_files_verified": len(baseline)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    cases = parser.add_mutually_exclusive_group()
    cases.add_argument("--svg", dest="suite", action="store_const", const="svg", help="Run the editable SVG import fixture")
    cases.add_argument("--text-selector", dest="suite", action="store_const", const="text-selector", help="Run the text animation fixture")
    main(suite=parser.parse_args().suite or "compositing")
