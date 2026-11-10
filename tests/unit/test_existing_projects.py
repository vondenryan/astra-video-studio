import copy
import json
from unittest.mock import Mock

import pytest

from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import ExistingProjectService
from astra_video_studio.motion_engine.service import verify_edit
from astra_video_studio.project_identity import build_id_map, mapped_state, extend_project_ids
from astra_video_studio.schemas import ProjectOpenCopyRequest


def source_file(path):
    path.write_bytes(b"test fixture data, not a real AEP" * 4)
    return path


def test_relative_source_is_workspace_relative(tmp_path):
    source = source_file(tmp_path / "source.aep")
    assert Settings(tmp_path).import_path("source.aep") == source.resolve()


def test_external_sources_need_operator_configured_root(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    external = source_file(tmp_path / "external.aep")
    with pytest.raises(ValueError, match="approved"):
        Settings(workspace).import_path(str(external))
    assert Settings(workspace, import_roots=(tmp_path,)).import_path(str(external)) == external


@pytest.mark.parametrize("name,content", [("movie.mp4", b"x" * 200), ("empty.aep", b""), ("tiny.aep", b"x")])
def test_invalid_source_files(tmp_path, name, content):
    (tmp_path / name).write_bytes(content)
    with pytest.raises(ValueError):
        Settings(tmp_path).import_path(name)


def test_invalid_source_never_submits(tmp_path):
    service = ExistingProjectService(Settings(tmp_path))
    service.projects.runner = Mock()
    with pytest.raises(ValueError):
        service.open_copy(ProjectOpenCopyRequest(source_path="missing.aep"))
    service.projects.runner.run.assert_not_called()


def sample():
    return {"compositions": [{"ae_id": 1, "composition_id": "Client notes", "layers": [{"ae_id": 10, "layer_id": "same comment", "name": "same"}, {"ae_id": 11, "layer_id": "same comment", "name": "same"}]}]}


def test_sidecar_ids_preserve_comments_and_survive_reordering():
    original = sample()
    baseline = copy.deepcopy(original)
    mapping = build_id_map(original)
    normalized = mapped_state(original, mapping)
    assert original == baseline
    assert normalized["compositions"][0]["layers"][0]["layer_id"] != normalized["compositions"][0]["layers"][1]["layer_id"]
    original["compositions"][0]["layers"].reverse()
    assert build_id_map(original, mapping) == mapping


def test_new_manual_duplicate_gets_new_uuid():
    data = sample()
    data["compositions"][0]["layers"] = [{"ae_id": 10, "layer_id": "astra:layer:" + "a" * 32}]
    mapping = build_id_map(data, preserve_comments=True)
    data["compositions"][0]["layers"].append({"ae_id": 12, "layer_id": "astra:layer:" + "a" * 32})
    updated = build_id_map(data, mapping, preserve_comments=True)
    assert updated["layers"]["10"] == "a" * 32
    assert updated["layers"]["12"] != "a" * 32


def test_duplicate_before_original_cannot_steal_verified_id():
    saved = sample()
    saved["compositions"][0]["layers"] = [{"ae_id": 10, "layer_id": "astra:layer:" + "a" * 32}]
    current = copy.deepcopy(saved)
    current["compositions"][0]["layers"].insert(0, {"ae_id": 12, "layer_id": "astra:layer:" + "a" * 32})
    mapping = extend_project_ids({"result": {"data": saved}}, current)
    assert mapping["layers"]["10"] == "a" * 32
    assert mapping["layers"]["12"] != "a" * 32


def test_duplicate_native_ids_rejected():
    data = sample()
    data["compositions"][0]["layers"][1]["ae_id"] = 10
    with pytest.raises(ValueError, match="duplicate"):
        build_id_map(data)


def test_import_roots_are_environment_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("ASTRA_IMPORT_ROOTS", str(tmp_path))
    assert Settings.from_env().import_roots == (tmp_path.resolve(),)


def test_saved_source_mutation_is_blocked_before_ae(tmp_path):
    from astra_video_studio.motion_engine.service import MotionService
    from astra_video_studio.motion_engine.schemas import TransformRequest
    import hashlib
    pid = "1" * 32
    directory = tmp_path / "projects" / pid
    directory.mkdir(parents=True)
    source = source_file(directory / "project.aep")
    manifest = {"project_id": pid, "status": "succeeded", "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
    (directory / "project.json").write_text(json.dumps(manifest))
    source.write_bytes(b"modified outside Astra" * 10)
    service = MotionService(Settings(tmp_path))
    service.projects.runner = Mock()
    with pytest.raises(ValueError, match="changed outside"):
        service.transform(TransformRequest(project_id=pid, composition_id="2" * 32, layer_id="3" * 32, values={"opacity": 50}))
    service.projects.runner.run.assert_not_called()


def test_edit_verifier_protects_other_layers():
    target_id, comp_id = "a" * 32, "b" * 32
    target = {"layer_id": "astra:layer:" + target_id, "text": "title", "transforms": {"opacity": {"value": 100, "keys": []}}}
    other = {"layer_id": "astra:layer:" + "c" * 32, "text": "keep", "transforms": {"opacity": {"value": 37, "keys": []}}}
    before = {"compositions": [{"composition_id": "astra:composition:" + comp_id, "width": 1920, "height": 1080, "fps": 30, "duration": 5, "layers": [target, other]}]}
    after = copy.deepcopy(before)
    after["compositions"][0]["layers"][1]["transforms"]["opacity"]["value"] = 50
    with pytest.raises(ValueError, match="Unrelated layer"):
        verify_edit(before, after, comp_id, target_id, {"opacity": 50}, False)
