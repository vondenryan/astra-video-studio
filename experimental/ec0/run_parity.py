"""Compare a pinned offline importer with retained AE evidence and dry-run the corpus."""
from collections import Counter
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
from uuid import uuid4

from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.media.ffmpeg import inspect_binary


ROOT = Path(__file__).resolve().parent
EFFECTCRAFT = "a41ff5015c6687db15a6f074a47b870b8f09fece"
WIDTH, HEIGHT = 1920, 1080
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(value, indent=2, allow_nan=False) + "\n")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verified_copy(source, destination, expected):
    require(digest(source) == expected, f"Input hash mismatch for {source.name}")
    shutil.copyfile(source, destination)
    require(digest(destination) == expected, f"Copy hash mismatch for {source.name}")


def worker(executable, mode, directory):
    pending = directory / "pending.json"
    executable_sha = digest(executable)
    write(pending, {"mode": mode, "executable_sha256": executable_sha})
    with (directory / "stdout.log").open("xb") as stdout, (directory / "stderr.log").open("xb") as stderr:
        process = subprocess.Popen(
            [str(executable), mode, str(directory)], cwd=directory,
            stdout=stdout, stderr=stderr, creationflags=NO_WINDOW,
        )
        write(directory / "process.json", {"pid": process.pid})
        exit_code = process.wait(timeout=180)
    require(exit_code == 0 and digest(executable) == executable_sha, f"Worker failed; inspect {directory}")
    report_path = directory / "worker-report.json"
    report = read(report_path)
    require(report["mode"] == mode, "Unexpected worker report")
    write(directory / "completed.json", {"exit_code": exit_code, "report_sha256": digest(report_path)})
    pending.rename(directory / "dispatch.json")
    return report


def prepare_reference(settings, plan, directory):
    path = settings.contained_path
    root = path(plan["reference"])
    source = read(root / "source.json")
    source_path = path(source["source"])
    verified_copy(source_path, directory / "reference.aep", plan["source_sha256"])
    packaged_mark = path(f"{plan['reference']}/package/media/14.png")
    require(digest(packaged_mark) == plan["source_asset_sha256"], "Archived package asset mismatch")
    verified_copy(root / "mark.png", directory / "mark.png", plan["source_asset_sha256"])

    job = path(f"jobs/{plan['native_operation']}")
    ack = read(job / "result.json")
    native = job / "native-result.json"
    evidence = ack["evidence"]
    require(
        (ack["operation_id"], ack["status"], ack["protocol"], evidence["file"])
        == (plan["native_operation"], "succeeded", "artifact-v1", native.name)
        and native.stat().st_size == evidence["bytes"] and digest(native) == evidence["sha256"],
        "Invalid archived AE acknowledgement",
    )
    native_result = read(native)["result"]
    require((native_result["operation_id"], native_result["status"])
            == (plan["native_operation"], "succeeded"), "Mismatched AE result")
    inspection = native_result["data"]
    require(path(inspection["project_path"]) == source_path and not inspection["project_dirty"],
            "Inspection is for a different or unsaved project")
    comp, = inspection["compositions"]
    require(comp["composition_id"] == f"astra:composition:{source['composition_id']}",
            "Unexpected composition identity")
    mark, = (layer for layer in comp["layers"] if layer["name"] == "Collected mark")
    footage, = (item for item in inspection["footage"] if item["ae_id"] == mark["source_ae_id"])
    require(digest(path(footage["path"])) == plan["source_asset_sha256"],
            "Inspected mark asset mismatch")

    render_path = path(f"jobs/{plan['render_job']}/job.json")
    render = read(render_path)
    data = render["result"]["data"]
    sequence_path = root / "alpha" / "sequence.json"
    sequence_sha = digest(sequence_path)
    request = read(root / "intermediate-submitted.json")
    require(
        render["status"] == "succeeded" and render["job_id"] == request["job_id"] == plan["render_job"]
        and data["source_sha256"] == source["source_sha256"] == plan["source_sha256"]
        and request["request"]["composition_id"] == source["composition_id"]
        and request["request"]["base_aep_sha256"] == plan["source_sha256"]
        and request["request"]["start_time"] == 3
        and data["sequence_manifest_sha256"] == sequence_sha,
        "Invalid archived render provenance",
    )
    sequence = read(sequence_path)
    require(
        (sequence["width"], sequence["height"], sequence["fps"], sequence["depth_bits"],
         sequence["source_pixel_format"]) == (WIDTH, HEIGHT, 24, 8, "rgba")
        and sequence["alpha_verified"] and sequence["native_bytes_preserved"]
        and sequence["source_color"] == {"bits_per_channel": 8, "working_space": "None", "linearized": False}
        and sequence["alpha_association"] == "Premultiplied (Matted)", "Unexpected TIFF format",
    )
    frames = {}
    for index, frame in zip(plan["frame_indices"], plan["composition_frames"], strict=True):
        row = sequence["frames"][index]
        name = f"frame_{index:05}.tif"
        require(row["path"] == name and frame == 72 + index, "Invalid TIFF frame mapping")
        verified_copy(root / "alpha" / "frames" / name, directory / name, row["sha256"])
        require((directory / name).stat().st_size == row["bytes"], "TIFF size mismatch")
        frames[str(index)] = row["sha256"]
    provenance = {
        "ae_version": inspection["ae_version"], "ack_sha256": digest(job / "result.json"),
        "inspection_sha256": evidence["sha256"], "render_job_sha256": digest(render_path),
        "sequence_sha256": sequence_sha, "native_frame_sha256": frames,
        "source_sha256": plan["source_sha256"], "mark_sha256": plan["source_asset_sha256"],
    }
    return comp, provenance


def git_revision(root):
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True,
        check=True, timeout=20, creationflags=NO_WINDOW,
    ).stdout.strip()


def prepare_corpus(settings, plan, directory):
    upstream = settings.contained_path(f"ec0/cargo-home/git/checkouts/effectcraft-f03e2ef0951e8587/{EFFECTCRAFT[:7]}")
    corpus = settings.contained_path(f"ec0/corpus-{plan['corpus_commit'][:8]}")
    require(git_revision(upstream) == EFFECTCRAFT and git_revision(corpus) == plan["corpus_commit"],
            "Unexpected corpus or upstream revision")
    lock_name = "crates/aep/tests/fixtures/corpus.lock"
    lock = upstream / lock_name
    committed_lock = subprocess.run(
        ["git", "-C", str(upstream), "show", f"{EFFECTCRAFT}:{lock_name}"],
        capture_output=True, check=True, timeout=20, creationflags=NO_WINDOW,
    ).stdout
    require(lock.read_bytes().replace(b"\r\n", b"\n") == committed_lock, "Modified upstream corpus lock")
    inputs = directory / "inputs"
    inputs.mkdir()
    names = set()
    count = 0
    for line in committed_lock.decode("utf-8").splitlines():
        if not line or line.startswith("#") or line.startswith(("repo ", "commit ")):
            continue
        expected, relative = line.split()
        require(re.fullmatch(r"aep/(inputs/)?[\w.-]+\.(aep|aepx|ffx)", relative),
                "Unexpected corpus path")
        source = (corpus / relative).resolve()
        require(source.is_relative_to(corpus) and re.fullmatch("[0-9a-f]{64}", expected),
                "Unexpected corpus hash entry")
        require(digest(source) == expected, f"Corpus hash mismatch for {relative}")
        count += 1
        if source.suffix in {".aep", ".aepx"}:
            require(source.name not in names, "Duplicate corpus project")
            verified_copy(source, inputs / source.name, expected)
            names.add(source.name)
    require(f"commit {plan['corpus_commit']}" in committed_lock.decode().splitlines() and names,
            "Corpus lock does not match the plan")
    return names, count, digest(lock)


def compare_semantics(native, ec, limits):
    mismatches = []
    tolerance = limits["scalar_absolute_relative"]

    def check(label, expected, actual, absolute=tolerance):
        if isinstance(expected, bool) or isinstance(expected, str):
            matches = expected == actual
        else:
            matches = math.isclose(expected, actual, rel_tol=tolerance, abs_tol=absolute)
        if not matches:
            mismatches.append({"field": label, "ae": expected, "effectcraft": actual})

    for field in ("width", "height", "fps", "duration"):
        check(field, native[field], ec[field])
    layers = {layer["name"]: layer["transforms"] for layer in native["layers"]}
    for field in ("position", "anchor", "scale", "opacity"):
        expected = layers["Collected mark"][field]["value"]
        actual = ec[f"mark_{field}"]["v"]
        if isinstance(expected, list):
            for index, (left, right) in enumerate(zip(expected, actual, strict=True)):
                absolute = limits["position_error_px"] if field in {"position", "anchor"} else tolerance
                check(f"mark.{field}.{index}", left, right, absolute)
        else:
            check(f"mark.{field}", expected, actual)
    opacity = layers["Title"]["opacity"]
    check("key_count", len(opacity["keys"]), len(ec["opacity_keys"]))
    for index, (left, right) in enumerate(zip(opacity["keys"], ec["opacity_keys"])):
        check(f"key.{index}.time", left["time"], right["time"] / 254_016_000_000)
        check(f"key.{index}.value", left["value"], right["value"]["v"])
        for a, b in (("temporal_auto", "auto_bezier"), ("temporal_continuous", "continuous"), ("roving", "roving")):
            check(f"key.{index}.{a}", left[a], right[b])
        # AE identifies opacity as non-spatial. Spatial flags have no meaning on this track.
        for side in ("in", "out"):
            kind = left[f"{side}_type"]
            prefix = f"key.{index}.{side}"
            check(prefix, kind, right[f"{side}_interp"].lower())
            if kind == "bezier":
                a, = left[f"{side}_ease"]
                b, = right[f"{side}_ease"]
                check(prefix + ".speed", a["speed"], b["speed"])
                check(prefix + ".influence", a["influence"], b["influence"] * 100)
    for index, (left, right) in enumerate(zip(opacity["samples"], ec["opacity_samples"], strict=True)):
        for field in ("time", "value"):
            check(f"sample.{index}.{field}", left[field], right[field])
    return {"pass": not mismatches, "key_count": len(ec["opacity_keys"]),
            "sample_count": len(ec["opacity_samples"]), "mismatches": mismatches}


def rgba(ffmpeg, path):
    result = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
        capture_output=True, check=True, timeout=30, creationflags=NO_WINDOW,
    ).stdout
    require(len(result) == WIDTH * HEIGHT * 4, "Unexpected decoded frame size")
    return result


def compare_pixels(left, right, region, limits):
    x0, y0, x1, y1 = region
    require(0 <= x0 < x1 <= WIDTH and 0 <= y0 < y1 <= HEIGHT
            and (x1 - x0) % 8 == (y1 - y0) % 8 == 0, "Invalid pixel region")
    scores = []
    rgb_error = alpha_error = native_opaque = 0
    c1, c2 = (0.01 * 255)**2, (0.03 * 255)**2
    for y in range(y0, y1, 8):
        for x in range(x0, x1, 8):
            channels = [([], []) for _ in range(3)]
            for row in range(y, y + 8):
                for col in range(x, x + 8):
                    index = (row * WIDTH + col) * 4
                    a, b = left[index + 3], right[index + 3]
                    require(a in {0, 255} and b in {0, 255}, "Nonbinary alpha in reference region")
                    native_opaque += a == 255
                    alpha_error = max(alpha_error, abs(a - b))
                    for channel, (values_a, values_b) in enumerate(channels):
                        values_a.append(left[index + channel] if a else 0)
                        values_b.append(right[index + channel] if b else 0)
            for a, b in channels:
                mean_a, mean_b = sum(a) / 64, sum(b) / 64
                var_a = sum((value - mean_a)**2 for value in a) / 63
                var_b = sum((value - mean_b)**2 for value in b) / 63
                covariance = sum((p - mean_a) * (q - mean_b) for p, q in zip(a, b)) / 63
                scores.append(((2 * mean_a * mean_b + c1) * (2 * covariance + c2))
                              / ((mean_a**2 + mean_b**2 + c1) * (var_a + var_b + c2)))
                rgb_error += sum(abs(p - q) for p, q in zip(a, b))
    require(native_opaque == 64 * 64, "Native reference does not contain the expected mark")
    ssim = sum(scores) / len(scores)
    mae = rgb_error / ((x1 - x0) * (y1 - y0) * 3)
    return {"ssim": ssim, "rgb_mae_bytes": mae, "alpha_max_error_bytes": alpha_error,
            "pass": ssim >= limits["ssim_min"] and mae <= limits["mae_bytes_max"]
            and alpha_error <= limits["alpha_error_bytes_max"]}


def main():
    settings = Settings.from_env()
    base = settings.contained_path("ec0")
    require(not any(base.glob("parity-*/*/pending.json")), "Inspect the unresolved parity worker first")
    plan_path = ROOT / "parity-plan.json"
    plan = read(plan_path)
    exe = settings.contained_path("ec0/target/debug/astra-ec0-aep.exe")
    attempt = settings.contained_path("ec0/parity-" + uuid4().hex)
    attempt.mkdir()
    print(attempt, flush=True)
    plan_sha = digest(plan_path)
    verified_copy(plan_path, attempt / plan_path.name, plan_sha)
    baseline = {path: digest(path) for path in settings.contained_path("projects").rglob("*.aep")}
    write(attempt / "aep-baseline.json", {str(path): sha for path, sha in baseline.items()})
    dependencies = read(base / "dependencies-current.json")
    closure_path = settings.contained_path(dependencies["closure_path"])
    closure = read(closure_path)
    lock_sha = digest(ROOT / "worker" / "Cargo.lock")
    require(closure["cargo_lock_sha256"] == lock_sha and not closure["gui_packages"],
            "Dependency inventory does not match the locked worker")
    verified_copy(closure_path, attempt / "dependency-closure.json", dependencies["closure_sha256"])
    verified_copy(settings.contained_path(dependencies["metadata_path"]), attempt / "cargo-metadata.json",
                  closure["metadata_sha256"])
    ffmpeg = inspect_binary("ffmpeg", settings.ffmpeg)
    require(ffmpeg.available, "FFmpeg is unavailable")
    reference, corpus = attempt / "reference", attempt / "corpus"
    reference.mkdir()
    corpus.mkdir()
    comp, provenance = prepare_reference(settings, plan, reference)
    names, count, corpus_lock_sha = prepare_corpus(settings, plan, corpus)
    ec = worker(exe, "reference", reference)
    corpus_report = worker(exe, "corpus", corpus)["files"]
    require(len(corpus_report) == len(names) and {row["name"] for row in corpus_report} == names,
            "Incomplete corpus report")
    pixel_results = []
    for index, frame in zip(plan["frame_indices"], plan["composition_frames"], strict=True):
        native = rgba(ffmpeg.path, reference / f"frame_{index:05}.tif")
        ec_path = reference / f"ec-{index}.png"
        candidate = rgba(ffmpeg.path, ec_path)
        pixel_results.append({"frame": frame, "effectcraft_sha256": digest(ec_path), "regions": {
            name: compare_pixels(native, candidate, region, plan["thresholds"])
            for name, region in plan["rois"].items()
        }})
    require(all(path.is_file() and digest(path) == sha for path, sha in baseline.items()),
            "A preexisting managed AEP changed during the probe")
    semantics = compare_semantics(comp, ec["semantics"], plan["thresholds"])
    files = []
    for row in corpus_report:
        details = row.get("report", {})
        entry = {key: row[key] for key in ("name", "status", "strict", "loss_count", "error") if key in row}
        entry.update(missing_fonts=len(details.get("missingFonts", [])),
                     missing_footage=len(details.get("missingFootage", [])))
        if details.get("losses"):
            entry["losses"] = details["losses"]
        files.append(entry)
    report = {
        "plan_sha256": plan_sha, "effectcraft_revision": EFFECTCRAFT, "worker_sha256": digest(exe),
        "cargo_lock_sha256": lock_sha, "dependency_closure_sha256": dependencies["closure_sha256"],
        "reachable_packages": closure["reachable_package_count"], "ffmpeg_version": ffmpeg.version,
        "preexisting_managed_aeps_preserved": len(baseline), "provenance": provenance,
        "pixels": pixel_results, "semantics": semantics, "reference_import_report": ec["import_report"],
        "corpus": {"commit": plan["corpus_commit"], "lock_sha256": corpus_lock_sha, "locked_files_verified": count,
                   "statuses": dict(Counter(row.get("strict", row["status"]) for row in files)), "files": files},
        "worker_reports": {path.name: digest(path / "worker-report.json") for path in (reference, corpus)},
    }
    write(attempt / "summary.json", report)
    return 0 if semantics["pass"] and all(row["status"] == "analyzed" for row in files) and all(
        region["pass"] for row in pixel_results for region in row["regions"].values()
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
