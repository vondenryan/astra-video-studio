"""Measure the fixed CPU stress fixtures while preserving all prior evidence."""
import ctypes
from ctypes import wintypes
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import time
from uuid import uuid4

from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.media.ffmpeg import inspect_binary
from run_parity import NO_WINDOW, ROOT, read, require, verified_copy, write


class MemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD), ("page_faults", wintypes.DWORD),
        ("peak_working_set", ctypes.c_size_t), ("working_set", ctypes.c_size_t),
        ("quota_peak_paged_pool", ctypes.c_size_t), ("quota_paged_pool", ctypes.c_size_t),
        ("quota_peak_nonpaged_pool", ctypes.c_size_t), ("quota_nonpaged_pool", ctypes.c_size_t),
        ("pagefile_usage", ctypes.c_size_t), ("peak_pagefile_usage", ctypes.c_size_t),
    ]


def measured_process(command, directory, environment, plan):
    require(os.name == "nt", "This resource probe uses Windows process counters")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(MemoryCounters), wintypes.DWORD]
    write(directory / "pending.json", {"command": command})
    start = time.perf_counter()
    with (directory / "stdout.log").open("xb") as stdout, (directory / "stderr.log").open("xb") as stderr:
        process = subprocess.Popen(command, cwd=directory, env=environment, stdout=stdout, stderr=stderr,
                                   creationflags=NO_WINDOW)
        write(directory / "pid.json", {"pid": process.pid})
        handle = kernel.OpenProcess(0x0400 | 0x0010, False, process.pid)
        require(bool(handle), "Cannot open owned process counters; retain pending for inspection")
        try:
            times = [wintypes.FILETIME() for _ in range(4)]
            require(kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)),
                    "Cannot read owned process identity")
            creation = times[0].dwLowDateTime | (times[0].dwHighDateTime << 32)
            write(directory / "process.json", {"pid": process.pid, "creation_filetime": creation})
            peak = samples = last_current = 0
            while True:
                counters = MemoryCounters()
                counters.cb = ctypes.sizeof(counters)
                if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                    samples += 1
                    peak = max(peak, counters.peak_working_set)
                    last_current = counters.working_set
                if process.poll() is not None:
                    break
                require(time.perf_counter() - start < plan["worker_timeout_seconds"],
                        "Owned process timed out; retain pending and inspect without replay")
                time.sleep(plan["memory_poll_seconds"])
            exit_code = process.wait()
            final_counters = MemoryCounters()
            final_counters.cb = ctypes.sizeof(final_counters)
            post_exit_query = bool(psapi.GetProcessMemoryInfo(handle, ctypes.byref(final_counters), final_counters.cb))
            if post_exit_query:
                peak = max(peak, final_counters.peak_working_set)
        finally:
            kernel.CloseHandle(handle)
    result = {
        "exit_code": exit_code, "wall_ms": (time.perf_counter() - start) * 1000,
        "peak_working_set_bytes": peak, "memory_samples": samples,
        "last_working_set_bytes": last_current, "pid": process.pid, "creation_filetime": creation,
        "post_exit_memory_query_succeeded": post_exit_query,
        "memory_method": "Maximum queried Windows PeakWorkingSetSize, sampled while running and queried after exit",
        "stdout_sha256": digest(directory / "stdout.log"), "stderr_sha256": digest(directory / "stderr.log"),
    }
    write(directory / "exit.json", result)
    require(exit_code == 0 and samples > 0 and peak > 0, f"Process failed; inspect {directory}")
    return result


def close_attempt(directory):
    (directory / "pending.json").rename(directory / "dispatch.json")


def run_worker(exe, parent, mode, layers, threads, number, plan):
    directory = parent / f"{layers}-{mode}-{number}"
    directory.mkdir()
    environment = dict(os.environ, RAYON_NUM_THREADS=str(threads))
    process = measured_process([str(exe), mode, str(layers), str(directory)], directory, environment, plan)
    report_path = directory / "worker-report.json"
    require(report_path.stat().st_size <= 1024 * 1024, "Oversized stress report")
    report = read(report_path)
    expected_frames = list(range(900)) if mode == "sequence" else plan["sample_frames"]
    require((report["mode"], report["root_layers"], report["nested_layers"], report["width"],
             report["height"], report["fps"], report["duration_frames"])
            == (mode, layers, 3, 1920, 1080, 30, 900)
            and report["frames"] == expected_frames and report["project_roundtrip_equal"]
            and report["pixel_probes_passed"], "Unexpected stress report identity")
    expected_runs = 11 if mode == "warm" else 1
    require(len(report["runs"]) == expected_runs, "Incomplete stress repetitions")
    for index, row in enumerate(report["runs"]):
        require(row["iteration"] == index and row["excluded_warmup"] == (mode == "warm" and index == 0)
                and len(row["frame_rgba_sha256"]) == len(expected_frames)
                and all(math.isfinite(row[field]) and row[field] >= 0
                        for field in ("render_ms", "rgba_hash_ms", "png_write_ms")),
                "Invalid stress timing record")
    require(process["peak_working_set_bytes"] <= plan["rss_bytes_max"], "Worker exceeded the fixed RSS budget")
    require(process["post_exit_memory_query_succeeded"], "Complete lifetime memory counter unavailable")
    require(digest(directory / "project.ecproj") == report["project_sha256"], "Stress project hash mismatch")
    close_attempt(directory)
    return directory, report, {"directory": directory.name, "threads": threads, **process,
                              "report_sha256": digest(report_path)}


def distribution(values):
    ordered = sorted(values)
    return {"count": len(ordered), "median_ms": statistics.median(ordered),
            "p95_ms": ordered[math.ceil(0.95 * len(ordered)) - 1], "values_ms": values}


def render_video(settings, attempt, full, plan, expected_hashes):
    ffmpeg = inspect_binary("ffmpeg", settings.ffmpeg)
    ffprobe = inspect_binary("ffprobe", settings.ffprobe)
    require(ffmpeg.available and ffprobe.available, "FFmpeg/FFprobe unavailable")
    frames = attempt / "png-decode"
    frames.mkdir()
    frame_decode = measured_process([
        ffmpeg.path, "-v", "error", "-framerate", "30", "-i", str(full / "frame-%04d.png"),
        "-frames:v", "900", "-pix_fmt", "rgba", "-f", "framehash", "-hash", "sha256", "-",
    ], frames, os.environ.copy(), plan)
    decoded_hashes = []
    for line in (frames / "stdout.log").read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line:
            continue
        fields = [field.strip() for field in line.split(",")]
        index = len(decoded_hashes)
        require(len(fields) == 6 and fields[:5] == ["0", str(index), str(index), "1", "8294400"],
                "Unexpected PNG sequence frame")
        decoded_hashes.append(fields[-1])
    require(decoded_hashes == expected_hashes, "Decoded PNG sequence differs from the worker RGBA hashes")
    close_attempt(frames)
    directory = attempt / "encode"
    directory.mkdir()
    video = directory / "stress.mp4"
    process = measured_process([
        ffmpeg.path, "-v", "error", "-framerate", "30", "-i", str(full / "frame-%04d.png"),
        "-frames:v", "900", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", str(video),
    ], directory, os.environ.copy(), plan)
    probe = subprocess.run([
        ffprobe.path, "-v", "error", "-count_frames", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,avg_frame_rate,nb_read_frames,duration,codec_name,pix_fmt",
        "-of", "json", str(video),
    ], capture_output=True, check=True, timeout=60, creationflags=NO_WINDOW)
    with (directory / "probe.json").open("xb") as file:
        file.write(probe.stdout)
    stream, = read(directory / "probe.json")["streams"]
    require((stream["width"], stream["height"], stream["avg_frame_rate"], stream["nb_read_frames"],
             stream["codec_name"], stream["pix_fmt"]) == (1920, 1080, "30/1", "900", "h264", "yuv420p")
            and abs(float(stream["duration"]) - 30) <= 1 / 30, "Distribution video does not match the plan")
    close_attempt(directory)
    decode = attempt / "decode"
    decode.mkdir()
    decoded = measured_process([ffmpeg.path, "-v", "error", "-xerror", "-i", str(video), "-f", "null", "-"],
                               decode, os.environ.copy(), plan)
    close_attempt(decode)
    return {"png_decode": frame_decode, "encode": process, "full_decode": decoded,
            "stream": stream, "sha256": digest(video),
            "ffmpeg_version": ffmpeg.version, "ffprobe_version": ffprobe.version}


def main():
    settings = Settings.from_env()
    base = settings.contained_path("ec0")
    require(not any(base.glob("stress-*/*/pending.json")), "Inspect the retained stress process before a new run")
    plan_path = ROOT / "stress-plan.json"
    plan = read(plan_path)
    require((plan["fresh_process_runs"], plan["warm_runs"], plan["sample_frames"],
             plan["root_layer_counts"]) == (5, 10, [0, 225, 450, 675, 899], [3, 40, 80]),
            "Unsupported stress plan")
    exe = base / "target/release/astra-ec0-stress.exe"
    executable_sha = digest(exe)
    attempt = base / ("stress-" + uuid4().hex)
    attempt.mkdir()
    print(attempt, flush=True)
    verified_copy(plan_path, attempt / "plan.json", digest(plan_path))
    dependencies = read(base / "dependencies-current.json")
    closure_path = settings.contained_path(dependencies["closure_path"])
    closure = read(closure_path)
    require(closure["cargo_lock_sha256"] == digest(ROOT / "worker/Cargo.lock")
            and not closure["gui_packages"], "Dependency evidence does not match the stress build")
    verified_copy(closure_path, attempt / "dependency-closure.json", dependencies["closure_sha256"])
    verified_copy(settings.contained_path(dependencies["metadata_path"]), attempt / "cargo-metadata.json",
                  closure["metadata_sha256"])
    baseline = {path: digest(path) for path in settings.contained_path("projects").rglob("*.aep")}
    write(attempt / "aep-baseline.json", {str(path): sha for path, sha in baseline.items()})
    scenes = []
    processes = []
    hashes_80 = None
    for layers in plan["root_layer_counts"]:
        cold = []
        reference = None
        project_sha = None
        for number, threads in enumerate(plan["fresh_process_threads"]):
            directory, report, process = run_worker(exe, attempt, "fresh", layers, threads, number, plan)
            row, = report["runs"]
            if reference is None:
                reference, project_sha = row["frame_rgba_sha256"], report["project_sha256"]
            require(reference == row["frame_rgba_sha256"] and project_sha == report["project_sha256"],
                    "Fresh-process renders are nondeterministic")
            cold.append(row)
            processes.append(process)
        directory, report, process = run_worker(exe, attempt, "warm", layers, plan["warm_threads"], 0, plan)
        processes.append(process)
        require(report["project_sha256"] == project_sha, "Warm fixture differs from fresh fixture")
        require(all(row["frame_rgba_sha256"] == reference for row in report["runs"]),
                "Warm renders differ from fresh renders")
        require(len(set(reference)) > 1, "Stress fixture did not exercise animation")
        warm = [row for row in report["runs"] if not row["excluded_warmup"]]
        scenes.append({
            "root_layers": layers, "nested_layers": 3, "project_sha256": project_sha,
            "sample_rgba_sha256": reference,
            "fresh": {field: distribution([row[field] for row in cold])
                      for field in ("render_ms", "rgba_hash_ms", "png_write_ms")},
            "warm": {field: distribution([row[field] for row in warm])
                     for field in ("render_ms", "rgba_hash_ms")},
            "fresh_process_wall": distribution([row["wall_ms"] for row in processes if row["directory"].startswith(f"{layers}-fresh-")]),
        })
        if layers == 80:
            hashes_80 = reference
        print(f"{layers} root layers completed", flush=True)
    determinism = []
    for number, threads in enumerate(plan["determinism_threads"], start=10):
        directory, report, process = run_worker(exe, attempt, "fresh", 80, threads, number, plan)
        processes.append(process)
        row, = report["runs"]
        require(row["frame_rgba_sha256"] == hashes_80 and report["project_sha256"] == scenes[-1]["project_sha256"],
                "Changing thread counts changed the stress fixture")
        determinism.append({"threads": threads, "directory": directory.name, "report_sha256": process["report_sha256"]})
    full, report, process = run_worker(exe, attempt, "sequence", 80, plan["full_sequence_threads"], 0, plan)
    processes.append(process)
    row, = report["runs"]
    require([row["frame_rgba_sha256"][frame] for frame in plan["sample_frames"]] == hashes_80,
            "Full sequence differs from the repeated sample frames")
    require(len(list(full.glob("frame-*.png"))) == 900, "Incomplete 900-frame sequence")
    video = render_video(settings, attempt, full, plan, row["frame_rgba_sha256"])
    require(digest(exe) == executable_sha and digest(plan_path) == digest(attempt / "plan.json"),
            "Stress executable or plan changed")
    require(all(path.is_file() and digest(path) == sha for path, sha in baseline.items()), "A prior managed AEP changed")
    report = {
        "scope": plan["scope"], "plan_sha256": digest(plan_path), "worker_sha256": executable_sha,
        "cargo_lock_sha256": digest(ROOT / "worker/Cargo.lock"), "profile": "release",
        "environment": {"windows": platform.version(), "machine": platform.machine(), "logical_cpus": os.cpu_count()},
        "scenes": scenes, "processes": processes, "determinism": determinism,
        "full_sequence": {key: value for key, value in row.items() if key != "frame_rgba_sha256"},
        "full_sequence_report_sha256": process["report_sha256"], "video": video,
        "rss_budget_bytes": plan["rss_bytes_max"], "preexisting_managed_aeps_preserved": len(baseline),
        "limits": plan["limits"],
    }
    write(attempt / "summary.json", report)
    print("Full 900-frame sequence and decode completed", flush=True)


if __name__ == "__main__":
    main()
