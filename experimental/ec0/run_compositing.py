"""Run the fixed compositing probes and check their decoded RGBA pixels."""
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


def main():
    settings = Settings.from_env()
    base = settings.contained_path("ec0")
    if list(base.glob("*/pending.json")):
        raise ValueError("Inspect the pending EC0 job before continuing")
    exe = settings.contained_path("ec0/target/debug/astra-ec0-compositing.exe")
    binary = digest(exe)
    ffmpeg = inspect_binary("ffmpeg", settings.ffmpeg)
    if not ffmpeg.available:
        raise ValueError("FFmpeg unavailable")
    runs = settings.contained_path("ec0/compositing-runs")
    runs.mkdir(exist_ok=True)
    attempt = settings.contained_path("ec0/compositing-" + uuid4().hex)
    attempt.mkdir()
    plan_file = attempt / "plan.json"
    shutil.copyfile(ROOT / "compositing-plan.json", plan_file)
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
        with out.open("xb") as stdout, err.open("xb") as stderr:
            child = subprocess.Popen(
                [str(exe), "--root", str(runs), "--job", job],
                env=dict(os.environ, RAYON_NUM_THREADS=str(threads)),
                stdout=stdout, stderr=stderr, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            write_json(marker, {"job_id": job, "phase": "running", "pid": child.pid, "binary_sha256": binary})
            code = child.wait(timeout=90)
        write_json(attempt / f"{job}-exit.json", {"job_id": job, "exit_code": code})
        if code or out.stat().st_size > 8192:
            raise ValueError(f"Worker exit or receipt failure; inspect {out}")
        receipt = read_json(out)
        if (receipt.get("protocol"), receipt.get("job_id"), receipt.get("status"), receipt.get("revision")) != (
            "astra-ec0-compositing-v1", job, "succeeded", plan["upstream_revision"],
        ) or receipt.get("roundtrip_equal") is not True:
            raise ValueError("Unexpected worker receipt")
        if [row["case"] for row in receipt["dependency_refusals"]] != plan["graph_refusals"]:
            raise ValueError("Incomplete dependency negatives")
        expected = sorted(["project.ecproj", "result.json", *PNG_NAMES])
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
        probes = {}
        for name in PNG_NAMES:
            rgba = subprocess.run(
                [ffmpeg.path, "-v", "error", "-i", str(directory / name), "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
                check=True, capture_output=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout
            probes[name] = check_pixels(name, rgba, plan["pixel_channel_tolerance"])
        reports.append({"job_id": job, "threads": threads, "receipt": receipt, "pixel_checks": probes,
                        "files": {name: digest(directory / name) for name in expected}})
    stable_files = ["project.ecproj", *PNG_NAMES]
    if any(row["files"][name] != reports[0]["files"][name] for row in reports for name in stable_files):
        raise ValueError("Outputs differ across CPU thread counts")
    if digest(exe) != binary or any(digest(Path(path)) != sha for path, sha in baseline.items()):
        raise ValueError("Worker or prior project hash changed")
    record = {
        "scope": plan["scope"], "runs": reports, "binary_sha256": binary, "plan_sha256": digest(plan_file),
        "dependency_closure_sha256": digest(attempt / "dependency-closure.json"),
        "prior_aep_files_verified": len(baseline), "pending": plan["pending"],
    }
    proof = attempt / "verification.json"
    write_json(proof, record)
    write_json(base / "compositing-current.json", {"directory": str(attempt), "verification_sha256": digest(proof)})
    print(json.dumps({"directory": str(attempt), "runs": len(reports), "pngs_per_run": len(PNG_NAMES),
                      "negative_graph_cases": len(plan["graph_refusals"]), "prior_aep_files_verified": len(baseline)}))


if __name__ == "__main__":
    main()
