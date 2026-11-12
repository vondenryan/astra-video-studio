"""Run unmodified upstream AEP integration tests with the pinned synthetic corpus."""
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
from uuid import uuid4

from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from run_parity import EFFECTCRAFT, NO_WINDOW, ROOT, git_revision, read, require, verified_copy, write


CORPUS = "97262276f625afdeeb61787e4cbb74b3f17af510"
IGNORED = {
    "container::aepx::every_corpus_pair_gives_the_same_chunk_tree",
    "import::aepx::every_corpus_pair_imports_alike",
    "import::cryptomatte::the_after_effects_sample_arrives_as_after_effects_shows_it",
    "import::versions::copies_saved_as_25x_and_24x_import_like_the_2026_file",
    "import::versions::the_container_of_a_copy_states_its_version_in_head_and_the_writer_in_svap",
}


def source_tests(upstream, destination):
    prefix = "crates/aep/"
    archive = subprocess.run(
        ["git", "-C", str(upstream), "archive", EFFECTCRAFT, prefix + "tests"],
        capture_output=True, check=True, timeout=30, creationflags=NO_WINDOW,
    ).stdout
    inventory = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        for member in source:
            if member.isdir():
                continue
            require(member.isfile() and member.name.startswith(prefix + "tests/"),
                    "Unexpected upstream archive member")
            relative = Path(member.name.removeprefix(prefix))
            target = destination / relative
            require(target.resolve().is_relative_to(destination), "Archive path escaped the test workspace")
            target.parent.mkdir(parents=True, exist_ok=True)
            stream = source.extractfile(member)
            require(stream is not None, "Missing archive bytes")
            with target.open("xb") as output:
                shutil.copyfileobj(stream, output)
            inventory[relative.as_posix()] = digest(target)
    require("tests/it/main.rs" in inventory and "tests/fixtures/corpus.lock" in inventory,
            "Incomplete upstream tests")
    write(destination / "source-files.json", inventory)
    return inventory


def corpus_files(settings, destination, lock):
    corpus = settings.contained_path(f"ec0/corpus-{CORPUS[:8]}")
    require(git_revision(corpus) == CORPUS, "Unexpected corpus revision")
    lines = lock.read_text(encoding="utf-8").splitlines()
    require(f"commit {CORPUS}" in lines, "Unexpected corpus lock")
    inventory = {}
    for line in lines:
        if not line or line.startswith(("#", "repo ", "commit ")):
            continue
        expected, relative = line.split()
        require(re.fullmatch(r"aep/(inputs/)?[\w.-]+\.(aep|aepx|ffx)", relative)
                and re.fullmatch("[0-9a-f]{64}", expected), "Invalid corpus lock entry")
        source = (corpus / relative).resolve()
        require(source.is_relative_to(corpus), "Corpus input escaped its directory")
        target = destination / relative.removeprefix("aep/")
        target.parent.mkdir(parents=True, exist_ok=True)
        verified_copy(source, target, expected)
        inventory[target.relative_to(destination).as_posix()] = expected
    require(len(inventory) == 20, "Incomplete pinned corpus")
    return inventory


def run_suite(settings, attempt, manifest, fixtures):
    base = settings.contained_path("ec0")
    environment = os.environ.copy()
    environment.update(
        CARGO_HOME=str(base / "cargo-home"), RUSTUP_HOME=str(base / "rustup-home"),
        CARGO_TARGET_DIR=str(base / "target"), TEMP=str(base / "temp"), TMP=str(base / "temp"),
        CARGO_NET_OFFLINE="true", EFFECTCRAFT_AEP_FIXTURES=str(fixtures),
        EFFECTCRAFT_AEP_FIXTURES_REQUIRED="1",
    )
    # Ignored upstream version-family, Cryptomatte and exploratory tests have separate inputs.
    # AEP_CORPUS must not silently select the operator's own project directory.
    environment.pop("AEP_CORPUS", None)
    command = [
        str(base / "cargo-home/bin/cargo.exe"), "+1.95.0", "test", "--locked", "--offline",
        "--manifest-path", str(manifest), "--test", "upstream_aep", "-j", "2",
        "--", "--test-threads=2", "--nocapture",
    ]
    write(attempt / "pending.json", {
        "command": command, "fixtures_required": True, "manifest_sha256": digest(manifest),
        "cargo_lock_sha256": digest(manifest.parent / "Cargo.lock"),
    })
    with (attempt / "stdout.log").open("xb") as stdout, (attempt / "stderr.log").open("xb") as stderr:
        process = subprocess.Popen(command, cwd=attempt, env=environment, stdout=stdout, stderr=stderr,
                                   creationflags=NO_WINDOW)
        write(attempt / "process.json", {"pid": process.pid})
        exit_code = process.wait(timeout=600)
    write(attempt / "exit.json", {"exit_code": exit_code})
    result = suite_result(attempt, exit_code)
    # A completed failed suite is evidence too. Keep its dispatch and failure details.
    write(attempt / "suite-result.json", result)
    (attempt / "pending.json").rename(attempt / "dispatch.json")
    return result


def suite_result(attempt, exit_code):
    output = (attempt / "stdout.log").read_text(encoding="utf-8", errors="strict")
    matches = re.findall(
        r"test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out;",
        output,
    )
    require(len(matches) == 1 and "SKIPPED:" not in output, "Incomplete or skipped upstream test result")
    status, passed, failed, ignored, measured, filtered = matches[0]
    result = {
        "status": status, "passed": int(passed), "failed": int(failed), "ignored": int(ignored),
        "measured": int(measured), "filtered": int(filtered), "exit_code": exit_code,
        "ignored_cases": re.findall(r"^test (.+) \.\.\. ignored(?:,.*)?$", output, re.MULTILINE),
        "stdout_sha256": digest(attempt / "stdout.log"), "stderr_sha256": digest(attempt / "stderr.log"),
    }
    require(result["passed"] + result["failed"] == 602 and result["ignored"] == len(IGNORED)
            and set(result["ignored_cases"]) == IGNORED and result["filtered"] == 0
            and result["measured"] == 0, "Unexpected upstream integration test selection")
    return result


def main():
    settings = Settings.from_env()
    base = settings.contained_path("ec0")
    require(not any(base.glob("aep-suite-*/pending.json")), "Inspect the unresolved upstream suite first")
    upstream = base / f"cargo-home/git/checkouts/effectcraft-f03e2ef0951e8587/{EFFECTCRAFT[:7]}"
    require(git_revision(upstream) == EFFECTCRAFT, "Unexpected upstream revision")
    attempt = base / ("aep-suite-" + uuid4().hex)
    attempt.mkdir()
    print(attempt, flush=True)
    package = attempt / "package"
    package.mkdir()
    sources = source_tests(upstream, package)
    fixtures = attempt / "fixtures"
    corpus = corpus_files(settings, fixtures, package / "tests/fixtures/corpus.lock")
    manifest_source = ROOT / "worker/Cargo.toml"
    manifest = package / "Cargo.toml"
    with manifest.open("x", encoding="utf-8", newline="\n") as file:
        file.write(manifest_source.read_text(encoding="utf-8")
                   + '\n[[test]]\nname = "upstream_aep"\npath = "tests/it/main.rs"\n')
    lock = ROOT / "worker/Cargo.lock"
    verified_copy(lock, package / "Cargo.lock", digest(lock))
    baseline = {path: digest(path) for path in settings.contained_path("projects").rglob("*.aep")}
    write(attempt / "aep-baseline.json", {str(path): sha for path, sha in baseline.items()})
    result = run_suite(settings, attempt, manifest, fixtures)
    record_summary(attempt, sources, corpus, baseline, result)
    print(result, flush=True)
    return 0 if result["exit_code"] == 0 and result["failed"] == 0 and result["status"] == "ok" else 1


def record_summary(attempt, sources, corpus, baseline, result):
    package = attempt / "package"
    fixtures = attempt / "fixtures"
    require(all(path.is_file() and digest(path) == sha for path, sha in baseline.items()),
            "A preexisting managed AEP changed")
    require(all(digest(package / name) == sha for name, sha in sources.items()), "Upstream test sources changed")
    require(all(digest(fixtures / name) == sha for name, sha in corpus.items()), "Corpus bytes changed")
    report = {
        "scope": "Unmodified pinned upstream AEP integration target, hosted by the isolated Astra probe dependency graph",
        "effectcraft_revision": EFFECTCRAFT, "corpus_revision": CORPUS,
        "source_files": len(sources), "source_inventory_sha256": digest(package / "source-files.json"),
        "corpus_files": corpus, "cargo_lock_sha256": digest(package / "Cargo.lock"),
        "manifest_sha256": digest(package / "Cargo.toml"),
        "fixtures_required": True, "preexisting_managed_aeps_preserved": len(baseline),
        "suite": result,
        "pending": ["Upstream library unit tests and example tests",
                    "Five upstream ignored exploratory/version-family/Cryptomatte tests"],
    }
    write(attempt / "summary.json", report)
    return report


if __name__ == "__main__":
    raise SystemExit(main())
