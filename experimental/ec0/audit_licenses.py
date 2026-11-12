"""Build a source-verified license evidence bundle and a resolved-graph CycloneDX BOM."""
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tomllib
from uuid import uuid4

from jsonschema import Draft7Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.media.ffmpeg import inspect_binary
from check_dependencies import inspect_graph
from run_parity import NO_WINDOW, ROOT, read, require, verified_copy, write


def notice_name(name):
    return bool(re.search(r"(?i)(licen[cs]e|copying|copyright|credits|notice|authors?|attribution|^ofl)", name))


def text_markers(data):
    text = " ".join(data.decode("utf-8-sig", errors="replace").lower().split())
    found = set()
    if "permission is hereby granted, free of charge" in text and "the software is provided" in text:
        found.add("MIT")
    if "apache license" in text and "version 2.0" in text and "end of terms and conditions" in text:
        found.add("Apache-2.0")
    if "redistribution and use in source and binary forms" in text:
        found.add("BSD-3-Clause" if "neither the name" in text else "BSD-2-Clause")
    if "permission to use, copy, modify, and/or distribute" in text and "with or without fee" in text and "provided that" not in text:
        found.add("0BSD")
    if "origin of this software" in text and "altered source versions" in text and "as-is" in text:
        found.add("Zlib")
    if "free and unencumbered software released into the public domain" in text:
        found.add("Unlicense")
    if "unicode license v3" in text:
        found.add("Unicode-3.0")
    if "sil open font license" in text and "version 1.1" in text:
        found.add("OFL-1.1")
    return sorted(found)


def collect_text(directory, label, data):
    require(len(data) <= 2 * 1024 * 1024, "Oversized license/notice candidate")
    sha = hashlib.sha256(data).hexdigest()
    target = directory / "texts" / (sha + ".txt")
    if not target.exists():
        with target.open("xb") as file:
            file.write(data)
    require(digest(target) == sha, "License bundle content changed")
    return {"source_path": label, "sha256": sha, "bytes": len(data), "markers": text_markers(data)}


def registry_package(package, settings, lock, attempt):
    root = settings.contained_path(str(Path(package["manifest_path"]).parent))
    key = (package["name"], package["version"], package["source"])
    row, = [entry for entry in lock["package"] if (entry["name"], entry["version"], entry.get("source")) == key]
    archive = settings.contained_path(
        f"ec0/cargo-home/registry/cache/{root.parent.name}/{package['name']}-{package['version']}.crate"
    )
    require(digest(archive) == row["checksum"], "Registry archive does not match Cargo.lock")
    prefix = f"{package['name']}-{package['version']}/"
    inventory = {}
    texts = []
    with tarfile.open(archive, "r:gz") as source:
        for member in source:
            if member.isdir():
                continue
            require(member.isfile() and member.name.startswith(prefix), "Unexpected registry archive entry")
            relative = member.name.removeprefix(prefix)
            path = (root / relative).resolve()
            require(path.is_relative_to(root) and member.size <= 64 * 1024 * 1024, "Unsafe registry file")
            data = source.extractfile(member).read()
            sha = hashlib.sha256(data).hexdigest()
            require(digest(path) == sha, f"Registry source differs from locked archive: {package['name']}/{relative}")
            inventory[relative] = sha
            if notice_name(Path(relative).name):
                texts.append(collect_text(attempt, relative, data))
    extras = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()} - inventory.keys()
    require(extras <= {".cargo-ok", ".cargo-checksum.json"}, f"Unexpected files in {package['name']}")
    return texts, {"archive_sha256": row["checksum"], "verified_source_files": len(inventory),
                   "source_inventory_sha256": hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()}


def git_package(package, settings, attempt):
    root = settings.contained_path(str(Path(package["manifest_path"]).parent))
    repo = root
    while not (repo / ".git").exists():
        require(repo != settings.workspace, "Missing Git checkout for dependency")
        repo = repo.parent
    source_url, commit = package["source"].removeprefix("git+").rsplit("#", 1)
    require(re.fullmatch("[0-9a-f]{40}", commit), "Unpinned Git dependency")
    relative = root.relative_to(repo).as_posix()
    top_files = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", "--name-only", commit], capture_output=True, text=True,
        check=True, timeout=30, creationflags=NO_WINDOW,
    ).stdout.splitlines()
    inherited = [name for name in top_files if notice_name(name)]
    archive = subprocess.run(
        ["git", "-C", str(repo), "archive", commit, relative, *inherited],
        capture_output=True, check=True, timeout=30, creationflags=NO_WINDOW,
    ).stdout
    inventory = {}
    texts = []
    normalized = 0
    with tarfile.open(fileobj=io.BytesIO(archive)) as tree:
        for member in tree:
            if member.isdir():
                continue
            require(member.isfile() and member.size <= 64 * 1024 * 1024, "Unexpected Git archive entry")
            path = (repo / member.name).resolve()
            require(path.is_relative_to(repo), "Git file escaped checkout")
            data = tree.extractfile(member).read()
            actual = path.read_bytes()
            if actual != data:
                require(b"\0" not in data and actual.replace(b"\r\n", b"\n") == data.replace(b"\r\n", b"\n"),
                        f"Git source differs from pinned commit: {member.name}")
                normalized += 1
            inventory[member.name] = hashlib.sha256(data).hexdigest()
            if notice_name(Path(member.name).name):
                # Preserve exact committed bytes in the evidence bundle.
                texts.append(collect_text(attempt, member.name, data))
    return texts, {"git_commit": commit, "source_url": source_url, "verified_source_files": len(inventory),
                   "crlf_equivalent_files": normalized,
                   "source_inventory_sha256": hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()}


def component_ref(package):
    identity = "|".join((package["name"], package["version"], package["source"] or "workspace"))
    return "urn:sha256:" + hashlib.sha256(identity.encode()).hexdigest()


def validate_bom(bom, settings, plan):
    store = {}
    for row in plan["schemas"]:
        source = settings.contained_path(f"ec0/schemas/{row['file']}")
        require(digest(source) == row["sha256"], "CycloneDX schema changed")
        schema = read(source)
        store[schema["$id"]] = schema
        store["http://cyclonedx.org/schema/" + row["file"]] = schema
        store["https://cyclonedx.org/schema/" + row["file"]] = schema
    schema = store["http://cyclonedx.org/schema/bom-1.6.schema.json"]
    registry = Registry().with_resources(
        (uri, Resource.from_contents(value, default_specification=DRAFT7)) for uri, value in store.items()
    )
    Draft7Validator(schema, registry=registry).validate(bom)
    refs = {bom["metadata"]["component"]["bom-ref"]} | {item["bom-ref"] for item in bom["components"]}
    require(len(refs) == len(bom["components"]) + 1, "Duplicate BOM component identity")
    require({row["ref"] for row in bom["dependencies"]} == refs, "Incomplete BOM dependency nodes")
    require(all(set(row["dependsOn"]) <= refs for row in bom["dependencies"]), "Dangling BOM dependency edge")


def main():
    settings = Settings.from_env()
    base = settings.contained_path("ec0")
    plan_path = ROOT / "license-audit-plan.json"
    plan = read(plan_path)
    pointer = read(base / "dependencies-current.json")
    closure_path = settings.contained_path(pointer["closure_path"])
    closure = read(closure_path)
    require(digest(closure_path) == pointer["closure_sha256"]
            and closure["cargo_lock_sha256"] == digest(ROOT / "worker/Cargo.lock"), "Stale dependency inventory")
    metadata_path = settings.contained_path(pointer["metadata_path"])
    require(digest(metadata_path) == closure["metadata_sha256"], "Metadata evidence changed")
    metadata = read(metadata_path)
    graph = inspect_graph(metadata)
    require(graph["packages"] == closure["packages"] and not graph["gui_packages"], "Unexpected resolved graph")
    names = {(row["name"], row["version"], row["source"]) for row in graph["packages"]}
    packages = [row for row in metadata["packages"] if (row["name"], row["version"], row["source"]) in names]
    attempt = base / ("license-audit-" + uuid4().hex)
    attempt.mkdir()
    (attempt / "texts").mkdir()
    print(attempt, flush=True)
    verified_copy(plan_path, attempt / "plan.json", digest(plan_path))
    verified_copy(closure_path, attempt / "dependency-closure.json", pointer["closure_sha256"])
    verified_copy(metadata_path, attempt / "cargo-metadata.json", closure["metadata_sha256"])
    lock = tomllib.loads((ROOT / "worker/Cargo.lock").read_text(encoding="utf-8"))
    baseline = {path: digest(path) for path in settings.contained_path("projects").rglob("*.aep")}
    write(attempt / "aep-baseline.json", {str(path): sha for path, sha in baseline.items()})
    components = []
    evidence = []
    notes = []
    refs = {package["id"]: component_ref(package) for package in packages}
    for package in packages:
        raw = package["license"]
        require(bool(raw), "A package has no license declaration")
        expression = plan["legacy_license_expressions"].get(raw, raw)
        if package["source"] and package["source"].startswith("registry+"):
            texts, integrity = registry_package(package, settings, lock, attempt)
        elif package["source"] and package["source"].startswith("git+"):
            texts, integrity = git_package(package, settings, attempt)
        else:
            require(package["id"] == metadata["resolve"]["root"], "Unexpected local package")
            license_path = ROOT.parent.parent / "LICENSE"
            texts = [collect_text(attempt, "LICENSE", license_path.read_bytes())]
            integrity = {"workspace_manifest_sha256": digest(Path(package["manifest_path"]))}
        markers = {item for text in texts for item in text["markers"]}
        identifiers = set(re.findall(r"[A-Za-z0-9][A-Za-z0-9.+-]*", expression)) - {"AND", "OR", "WITH"}
        missing = sorted(identifiers - markers)
        if missing:
            notes.append({"package": package["name"], "version": package["version"], "unmatched_text_markers": missing})
        evidence.append({"name": package["name"], "version": package["version"], "source": package["source"],
                         "declared_license": raw, "bom_expression": expression,
                         "texts": texts, "unmatched_text_markers": missing, "integrity": integrity})
        component = {
            "type": "application" if package["id"] == metadata["resolve"]["root"] else "library",
            "bom-ref": refs[package["id"]], "name": package["name"], "version": package["version"],
            "licenses": [{"expression": expression}],
            "properties": [{"name": "astra:cargo:features", "value": json.dumps(
                next(row["features"] for row in graph["packages"] if row["name"] == package["name"] and row["version"] == package["version"]))},
                           {"name": "astra:cargo:declared-license", "value": raw}],
        }
        if package["source"]:
            component["properties"].append({"name": "astra:cargo:source", "value": package["source"]})
        if "archive_sha256" in integrity:
            component["purl"] = f"pkg:cargo/{package['name']}@{package['version']}"
            component["hashes"] = [{"alg": "SHA-256", "content": integrity["archive_sha256"]}]
        components.append(component)
    fonts = read(ROOT / "font-assets-manifest.json")
    text_package = next(package for package in packages if package["name"] == "effectcraft-text")
    text_root = settings.contained_path(str(Path(text_package["manifest_path"]).parent))
    font_root = text_root.parent.parent
    included = re.findall(r'include_bytes!\("../../../(assets/fonts/[^"]+)"\)',
                          (text_root / "src/fonts.rs").read_text(encoding="utf-8"))
    require(set(included) == {font["file"] for font in fonts["fonts"]}, "Embedded font inventory is incomplete")
    font_components = []
    font_evidence = []
    for font in fonts["fonts"]:
        asset = (font_root / font["file"]).resolve()
        license_file = (font_root / font["license_file"]).resolve()
        attribution = Path(str(asset) + ".attribution")
        require(asset.is_relative_to(font_root) and license_file.is_relative_to(font_root), "Font path escaped checkout")
        require(digest(asset) == font["sha256"] and asset.stat().st_size == font["bytes"]
                and digest(license_file) == font["license_sha256"]
                and digest(attribution) == font["attribution_sha256"], "Font identity, license or attribution changed")
        commit = text_package["source"].rsplit("#", 1)[1]
        for path in (asset, license_file, attribution):
            committed = subprocess.run(
                ["git", "-C", str(font_root), "show", f"{commit}:{path.relative_to(font_root).as_posix()}"],
                capture_output=True, check=True, timeout=30, creationflags=NO_WINDOW,
            ).stdout
            actual = path.read_bytes()
            require(actual == committed or (b"\0" not in committed
                    and actual.replace(b"\r\n", b"\n") == committed.replace(b"\r\n", b"\n")),
                    "Font asset or accompanying text differs from the pinned Git commit")
        text = collect_text(attempt, font["license_file"], license_file.read_bytes())
        attribution_text = collect_text(attempt, attribution.relative_to(font_root).as_posix(), attribution.read_bytes())
        require("OFL-1.1" in text["markers"], "Font license marker missing")
        font_evidence.append({**font, "license_text": text, "attribution_text": attribution_text})
        font_components.append({
            "type": "file", "bom-ref": "urn:sha256:" + font["sha256"], "name": Path(font["file"]).name,
            "hashes": [{"alg": "SHA-256", "content": font["sha256"]}], "licenses": [{"license": {"id": "OFL-1.1"}}],
            "properties": [{"name": "astra:font:author", "value": font["author"]},
                           {"name": "astra:font:license-sha256", "value": font["license_sha256"]}],
        })
    root_component = next(item for item in components if item["bom-ref"] == refs[metadata["resolve"]["root"]])
    nodes = {row["id"]: row for row in metadata["resolve"]["nodes"]}
    dependencies = [{"ref": refs[package["id"]], "dependsOn": sorted(
        {refs[edge["pkg"]] for edge in nodes[package["id"]]["deps"]})} for package in packages]
    text_deps = next(row for row in dependencies if row["ref"] == refs[text_package["id"]])
    text_deps["dependsOn"].extend(item["bom-ref"] for item in font_components)
    dependencies.extend({"ref": item["bom-ref"], "dependsOn": []} for item in font_components)
    bom = {"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
           "metadata": {"component": root_component, "properties": [
               {"name": "astra:scope", "value": plan["scope"]},
               {"name": "astra:target", "value": graph["target"]},
               {"name": "astra:cargo-lock-sha256", "value": closure["cargo_lock_sha256"]}]},
           "components": [item for item in components if item != root_component] + font_components,
           "dependencies": dependencies}
    validate_bom(bom, settings, plan)
    write(attempt / "bom.cdx.json", bom)
    write(attempt / "license-evidence.json", evidence)
    write(attempt / "font-evidence.json", font_evidence)
    with (attempt / "THIRD-PARTY-NOTICES.txt").open("x", encoding="utf-8", newline="\n") as file:
        file.write("EC-0 collected license and notice evidence\n\n")
        file.write("Resolved Windows Cargo graph and seven embedded fonts. Manual release review remains pending.\n\n")
        for row in evidence:
            file.write(f"{row['name']} {row['version']}\nDeclared license {row['declared_license']}\n")
            for text in row["texts"]:
                file.write(f"  {text['source_path']} -> texts/{text['sha256']}.txt\n")
            file.write("\n")
        for row in font_evidence:
            file.write(f"{row['file']}\n{row['author']}\n")
            file.write(f"  License texts/{row['license_sha256']}.txt\n")
            file.write(f"  Attribution texts/{row['attribution_sha256']}.txt\n\n")
        for path in sorted((attempt / "texts").glob("*.txt")):
            file.write(f"\n===== texts/{path.name} =====\n")
            file.write(path.read_text(encoding="utf-8-sig", errors="replace"))
            file.write("\n")
    tools = {}
    for name in ("ffmpeg", "ffprobe"):
        info = inspect_binary(name, getattr(settings, name))
        tools[name] = {"available": info.available, "version": info.version,
                       "executable_sha256": digest(Path(info.path)) if info.available else None}
    require(all(path.is_file() and digest(path) == sha for path, sha in baseline.items()), "A prior AEP changed")
    summary = {
        "scope": plan["scope"], "plan_sha256": digest(plan_path), "cargo_lock_sha256": closure["cargo_lock_sha256"],
        "dependency_closure_sha256": pointer["closure_sha256"], "packages": len(packages),
        "embedded_font_components": len(font_components), "bom_components_including_root": len(packages) + len(font_components),
        "license_texts_deduplicated": len(list((attempt / "texts").glob("*.txt"))),
        "source_files_verified": sum(row["integrity"].get("verified_source_files", 0) for row in evidence),
        "bom_schema_validation": "passed", "bom_sha256": digest(attempt / "bom.cdx.json"),
        "license_evidence_sha256": digest(attempt / "license-evidence.json"),
        "font_evidence_sha256": digest(attempt / "font-evidence.json"),
        "notices_sha256": digest(attempt / "THIRD-PARTY-NOTICES.txt"),
        "unmatched_text_markers": notes, "external_tools": tools,
        "preexisting_managed_aeps_preserved": len(baseline),
        "pending": [plan["release_approval"], plan["external_tools_scope"],
                    "Embedded data and source-level copyright obligations require manual review.",
                    "Resolved graph inventory is not an attestation of linked binary contents."],
    }
    write(attempt / "summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
