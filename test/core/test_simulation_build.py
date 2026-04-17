import os

from tricys.simulation.simulation import _resolve_built_model_paths


def test_resolve_built_model_paths_linux_keeps_executable_without_exe(monkeypatch):
    monkeypatch.setattr("tricys.simulation.simulation.sys.platform", "linux")

    exe_path, xml_path = _resolve_built_model_paths(
        ["MyModel", "MyModel_init.xml"], "/tmp/build"
    )

    assert os.path.normpath(exe_path) == os.path.normpath("/tmp/build/MyModel")
    assert os.path.normpath(xml_path) == os.path.normpath("/tmp/build/MyModel_init.xml")


def test_resolve_built_model_paths_windows_adds_exe_suffix(monkeypatch):
    monkeypatch.setattr("tricys.simulation.simulation.sys.platform", "win32")

    exe_path, xml_path = _resolve_built_model_paths(
        ["MyModel", "MyModel_init.xml"], "C:/temp/build"
    )

    assert os.path.normpath(exe_path) == os.path.normpath("C:/temp/build/MyModel.exe")
    assert os.path.normpath(xml_path) == os.path.normpath(
        "C:/temp/build/MyModel_init.xml"
    )


def test_resolve_built_model_paths_rejects_empty_executable_name(monkeypatch):
    monkeypatch.setattr("tricys.simulation.simulation.sys.platform", "linux")

    try:
        _resolve_built_model_paths(["", "MyModel_init.xml"], "/tmp/build")
    except RuntimeError as exc:
        assert "invalid artifacts" in str(exc)
        return

    raise AssertionError("Expected RuntimeError for empty executable artifact")
