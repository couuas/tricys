import logging
from pathlib import Path

from tricys.visualizer.callbacks import _build_viewer_error_copy
from tricys.visualizer.context import (
    decode_context_token,
    get_default_context_dir,
    load_context_reference,
)
from tricys.visualizer.main import (
    _build_display_url,
    _build_service_url,
    _create_viewer_token,
    _handle_close_shared_service,
    _log_visualizer_available,
    _normalize_base_path,
)


def test_normalize_base_path_adds_slashes():
    assert _normalize_base_path("hdf5") == "/hdf5/"
    assert _normalize_base_path("/hdf5") == "/hdf5/"
    assert _normalize_base_path("/hdf5/") == "/hdf5/"


def test_build_service_url_uses_localhost_for_wildcard_host():
    assert (
        _build_service_url("0.0.0.0", 8050, "/hdf5/") == "http://127.0.0.1:8050/hdf5/"
    )
    assert (
        _build_service_url("0.0.0.0", 8050, "/hdf5/", token="abc")
        == "http://127.0.0.1:8050/hdf5/?token=abc"
    )


def test_build_display_url_prefers_localhost_inside_container(monkeypatch):
    monkeypatch.setattr("tricys.visualizer.main._is_running_in_container", lambda: True)

    assert (
        _build_display_url("0.0.0.0", 8050, "/hdf5/", token="abc")
        == "http://localhost:8050/hdf5/?token=abc"
    )


def test_create_viewer_token_persists_context(tmp_path):
    h5_file = tmp_path / "sample.h5"
    h5_file.write_text("placeholder", encoding="utf-8")
    context_dir = tmp_path / "contexts"

    token = _create_viewer_token(str(h5_file), "secret-key", str(context_dir))
    payload = decode_context_token(token, "secret-key")
    context = load_context_reference(payload["context_id"], str(context_dir))

    assert Path(context["file_path"]) == h5_file.resolve()
    assert context["mode"] == "server"


def test_get_default_context_dir_uses_stable_user_path(monkeypatch, tmp_path):
    monkeypatch.delenv("HDF5_CONTEXTS_DIR", raising=False)
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))

    assert Path(get_default_context_dir()) == tmp_path / ".tricys" / "hdf5_contexts"


def test_get_default_context_dir_prefers_environment_override(monkeypatch, tmp_path):
    custom_dir = tmp_path / "custom-contexts"
    monkeypatch.setenv("HDF5_CONTEXTS_DIR", str(custom_dir))

    assert get_default_context_dir() == str(custom_dir)


def test_build_viewer_error_copy_for_missing_token():
    title, message, detail = _build_viewer_error_copy("Missing viewer token")

    assert title == "Missing viewer token"
    assert "signed token" in message
    assert "token query parameter" in detail


def test_build_viewer_error_copy_for_missing_context():
    title, message, detail = _build_viewer_error_copy("Viewer context not found")

    assert title == "Viewer context not found"
    assert "could not find" in message
    assert "Reopen the file" in detail


def test_build_viewer_error_copy_for_invalid_signature():
    title, message, detail = _build_viewer_error_copy("Invalid viewer token signature")

    assert title == "Invalid viewer token signature"
    assert "does not match" in message
    assert "HDF5_VISUALIZER_SECRET" in detail


def test_build_viewer_error_copy_for_missing_file():
    title, message, detail = _build_viewer_error_copy(
        "Requested HDF5 file is no longer available"
    )

    assert title == "HDF5 file no longer available"
    assert "no longer exists" in message
    assert "Restore the file" in detail


def test_build_viewer_error_copy_for_invalid_context_payload():
    title, message, detail = _build_viewer_error_copy(
        "Viewer context payload is invalid"
    )

    assert title == "Viewer context payload is invalid"
    assert "could not be parsed" in message
    assert "context file" in detail


def test_handle_close_shared_service_noop_when_port_is_free(monkeypatch):
    args = type(
        "Args", (), {"host": "127.0.0.1", "port": None, "base_pathname": "/hdf5/"}
    )()

    monkeypatch.setattr(
        "tricys.visualizer.main._probe_shared_service",
        lambda *args, **kwargs: {
            "running": False,
            "server_mode": False,
            "status_code": None,
        },
    )
    monkeypatch.setattr(
        "tricys.visualizer.main._is_port_in_use", lambda *args, **kwargs: False
    )

    _handle_close_shared_service(args)


def test_handle_close_shared_service_refuses_non_tricys_service(monkeypatch):
    args = type(
        "Args", (), {"host": "127.0.0.1", "port": 8050, "base_pathname": "/hdf5/"}
    )()

    monkeypatch.setattr(
        "tricys.visualizer.main._probe_shared_service",
        lambda *args, **kwargs: {
            "running": False,
            "server_mode": False,
            "status_code": None,
        },
    )
    monkeypatch.setattr(
        "tricys.visualizer.main._is_port_in_use", lambda *args, **kwargs: True
    )

    try:
        _handle_close_shared_service(args)
    except RuntimeError as exc:
        assert "Refusing to terminate" in str(exc)
        return

    raise AssertionError("Expected RuntimeError for non-TRICYS service")


def test_handle_close_shared_service_terminates_running_shared_service(monkeypatch):
    args = type(
        "Args", (), {"host": "127.0.0.1", "port": 8050, "base_pathname": "/hdf5/"}
    )()
    terminated = {"pid": None}
    port_states = iter([True, False])

    monkeypatch.setattr(
        "tricys.visualizer.main._probe_shared_service",
        lambda *args, **kwargs: {
            "running": True,
            "server_mode": True,
            "status_code": 200,
        },
    )
    monkeypatch.setattr(
        "tricys.visualizer.main._find_listening_pid", lambda *args, **kwargs: 43210
    )
    monkeypatch.setattr(
        "tricys.visualizer.main._terminate_process",
        lambda pid: terminated.update(pid=pid),
    )
    monkeypatch.setattr(
        "tricys.visualizer.main._is_port_in_use",
        lambda *args, **kwargs: next(port_states),
    )

    _handle_close_shared_service(args)

    assert terminated["pid"] == 43210


def test_log_visualizer_available_includes_url(caplog):
    with caplog.at_level(logging.INFO, logger="tricys.visualizer.main"):
        _log_visualizer_available("http://127.0.0.1:8050/hdf5/?token=abc")

    assert (
        "HDF5 visualizer available: http://127.0.0.1:8050/hdf5/?token=abc"
        in caplog.text
    )
