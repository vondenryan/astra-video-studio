from pathlib import Path, PureWindowsPath
import pytest

from astra_video_studio.config import Settings, _containment_key


def test_configuration_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("ASTRA_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("ASTRA_AE_EXECUTABLE", "custom.exe")
    settings = Settings.from_env()
    assert settings.workspace == tmp_path.resolve()
    assert settings.ae_executable == "custom.exe"


@pytest.mark.parametrize("path", ["../outside", "nested/../../outside"])
def test_escape_rejected(tmp_path, path):
    with pytest.raises(ValueError):
        Settings(tmp_path).contained_path(path)


def test_absolute_escape_rejected(tmp_path):
    with pytest.raises(ValueError):
        Settings(tmp_path / "workspace").contained_path(str(tmp_path / "outside"))


def test_contained_path(tmp_path):
    assert Settings(tmp_path).contained_path("jobs/test") == tmp_path / "jobs/test"


def test_symlink_escape_rejected(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    link = root / "link"
    try:
        link.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("Creating a symlink requires Windows developer mode or privilege")
    with pytest.raises(ValueError):
        Settings(root).contained_path("link/outside")


@pytest.mark.parametrize('candidate,root,expected', [
    (r'\\?\C:\work\responses\hash.json', r'C:\work', True),
    (r'C:\work\responses\hash.json', r'\\?\C:\work', True),
    (r'\\?\UNC\server\share\work\hash.json', r'\\server\share\work', True),
    (r'\\?\C:\work-other\hash.json', r'C:\work', False),
    (r'\\?\D:\work\hash.json', r'C:\work', False),
    (r'\\?\UNC\other\share\work\hash.json', r'\\server\share\work', False),
    (r'\\?\GLOBALROOT\Device\HarddiskVolume1\work', r'C:\work', False),
])
def test_resolved_windows_namespace_comparison(candidate, root, expected):
    assert _containment_key(PureWindowsPath(candidate)).is_relative_to(
        _containment_key(PureWindowsPath(root))) is expected
