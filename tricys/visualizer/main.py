# tricys/visualizer/main.py
import argparse
import json
import logging
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from threading import Timer
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import urlopen

from tricys.visualizer.context import (
    build_viewer_context,
    create_context_reference,
    get_default_context_dir,
    issue_context_token,
)

from .app import create_app

logger = logging.getLogger(__name__)
DEFAULT_SHARED_PORT = 8050
DEFAULT_CONTEXT_TTL_SECONDS = int(os.getenv("HDF5_VISUALIZER_TOKEN_TTL_SECONDS", "900"))
DEFAULT_SECRET = os.getenv(
    "HDF5_VISUALIZER_SECRET",
    os.getenv("SECRET_KEY", "your-super-secret-key-change-in-production"),
)


def _configure_logging():
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def _normalize_base_path(base_pathname: str) -> str:
    normalized = base_pathname or "/"
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    if not normalized.endswith("/"):
        normalized = f"{normalized}/"
    return normalized


def _resolve_client_host(host: str) -> str:
    if host in {"0.0.0.0", "::", ""}:
        return "127.0.0.1"
    return host


def _build_service_url(
    host: str, port: int, base_pathname: str, token: str = None
) -> str:
    client_host = _resolve_client_host(host)
    base = _normalize_base_path(base_pathname)
    url = f"http://{client_host}:{port}{base}"
    if token:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}token={quote(token)}"
    return url


def _is_running_in_container() -> bool:
    return (
        Path("/.dockerenv").exists() or os.getenv("container", "").lower() == "docker"
    )


def _resolve_display_host(host: str) -> str:
    client_host = _resolve_client_host(host)
    if _is_running_in_container() and client_host in {"127.0.0.1", "localhost"}:
        return "localhost"
    return client_host


def _build_display_url(
    host: str, port: int, base_pathname: str, token: str = None
) -> str:
    display_host = _resolve_display_host(host)
    base = _normalize_base_path(base_pathname)
    url = f"http://{display_host}:{port}{base}"
    if token:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}token={quote(token)}"
    return url


def _build_healthcheck_url(host: str, port: int, base_pathname: str) -> str:
    base = _normalize_base_path(base_pathname)
    return f"http://{_resolve_client_host(host)}:{port}{base.rstrip('/')}/health"


def _probe_shared_service(host: str, port: int, base_pathname: str) -> dict:
    healthcheck_url = _build_healthcheck_url(host, port, base_pathname)
    try:
        with urlopen(healthcheck_url, timeout=2) as response:
            payload = json.loads(
                response.read().decode("utf-8", errors="replace") or "{}"
            )
            return {
                "running": 200 <= response.status < 300,
                "server_mode": bool(payload.get("server_mode")),
                "status_code": response.status,
            }
    except (URLError, json.JSONDecodeError, TimeoutError, ValueError):
        return {"running": False, "server_mode": False, "status_code": None}


def _is_port_in_use(host: str, port: int) -> bool:
    client_host = _resolve_client_host(host)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((client_host, port)) == 0


def _find_listening_pid(host: str, port: int):
    client_host = _resolve_client_host(host)

    if os.name == "nt":
        result = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None

        host_candidates = {client_host, "0.0.0.0", "127.0.0.1", "::", "[::]"}
        port_suffix = f":{port}"
        for line in result.stdout.splitlines():
            parts = re.split(r"\s+", line.strip())
            if len(parts) < 5 or parts[0].upper() != "TCP":
                continue
            local_address = parts[1]
            state = parts[3].upper()
            pid = parts[4]
            if state != "LISTENING" or not local_address.endswith(port_suffix):
                continue
            local_host = local_address[: -len(port_suffix)] or "0.0.0.0"
            if local_host in host_candidates:
                try:
                    return int(pid)
                except ValueError:
                    return None
        return None

    if shutil.which("lsof"):
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                line = line.strip()
                if line:
                    try:
                        return int(line)
                    except ValueError:
                        continue
        return None

    if shutil.which("ss"):
        result = subprocess.run(
            ["ss", "-ltnp"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None

        port_suffix = f":{port}"
        for line in result.stdout.splitlines():
            if port_suffix not in line:
                continue
            match = re.search(r"pid=(\d+)", line)
            if match:
                return int(match.group(1))
        return None

    return None


def _terminate_process(pid: int) -> None:
    if os.name == "nt":
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip()
                or result.stdout.strip()
                or f"Failed to terminate process {pid}"
            )
        return

    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        raise RuntimeError(f"Failed to terminate process {pid}") from exc


def _handle_close_shared_service(args) -> None:
    port = args.port if args.port is not None else DEFAULT_SHARED_PORT
    base_pathname = _normalize_base_path(args.base_pathname)
    probe = _probe_shared_service(args.host, port, base_pathname)

    if not probe["running"]:
        if _is_port_in_use(args.host, port):
            raise RuntimeError(
                f"Port {port} is occupied by a non-TRICYS-HDF5 service. Refusing to terminate it with --close."
            )
        logger.info("No running shared HDF5 service found", extra={"port": port})
        return

    if not probe["server_mode"]:
        raise RuntimeError(
            f"Port {port} is occupied by a non-shared TRICYS HDF5 service. Refusing to terminate it with --close."
        )

    pid = _find_listening_pid(args.host, port)
    if pid is None:
        raise RuntimeError(
            f"Could not determine the PID for the shared HDF5 service on port {port}."
        )

    _terminate_process(pid)

    deadline = time.time() + 5
    while time.time() < deadline:
        if not _is_port_in_use(args.host, port):
            logger.info("Closed shared HDF5 service", extra={"port": port, "pid": pid})
            return
        time.sleep(0.1)

    raise RuntimeError(
        f"Shared HDF5 service on port {port} did not stop cleanly after terminating PID {pid}."
    )


def _ensure_context_dir_writable(context_dir: str) -> Path:
    resolved = Path(context_dir).expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    probe_file = resolved / f".tricys_write_test_{os.getpid()}"
    try:
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink()
    except OSError as exc:
        raise RuntimeError(
            f"Context directory '{resolved}' is not writable. "
            "If you are inside the tricys-hdf5 container, /data may be mounted read-only. "
            "Use a writable context dir or run the command from a container that can write viewer contexts."
        ) from exc
    return resolved


def _create_viewer_token(h5_file_path: str, secret: str, context_dir: str) -> str:
    resolved_file = Path(h5_file_path).expanduser().resolve()
    if resolved_file.suffix.lower() != ".h5":
        raise RuntimeError("Only .h5 files are supported")
    if not resolved_file.exists():
        raise RuntimeError(f"HDF5 file not found: {resolved_file}")

    writable_context_dir = _ensure_context_dir_writable(context_dir)
    viewer_context = build_viewer_context(
        str(resolved_file),
        display_path=str(resolved_file),
        mode="server",
    )
    context_reference = create_context_reference(
        viewer_context,
        str(writable_context_dir),
        DEFAULT_CONTEXT_TTL_SECONDS,
    )
    return issue_context_token(
        {"context_id": context_reference["context_id"]},
        secret,
        DEFAULT_CONTEXT_TTL_SECONDS,
    )


def _start_shared_service_process(
    host: str, port: int, base_pathname: str, secret: str, context_dir: str
) -> subprocess.Popen:
    command = [
        sys.executable,
        "-m",
        "tricys.main",
        "hdf5",
        "--server-mode",
        "--host",
        host,
        "--port",
        str(port),
        "--base-pathname",
        _normalize_base_path(base_pathname),
        "--secret",
        secret,
        "--context-dir",
        str(Path(context_dir).expanduser().resolve()),
        "--no-browser",
    ]

    kwargs = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs["start_new_session"] = True

    return subprocess.Popen(command, **kwargs)


def _wait_for_shared_service(
    host: str, port: int, base_pathname: str, timeout_seconds: int = 10
) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        probe = _probe_shared_service(host, port, base_pathname)
        if probe["running"] and probe["server_mode"]:
            return True
        time.sleep(0.25)
    return False


def _open_url(url: str, no_browser: bool) -> None:
    if not no_browser:
        Timer(1, lambda: webbrowser.open(url)).start()


def _log_visualizer_available(url: str) -> None:
    logger.info("HDF5 visualizer available: %s", url)


def _handle_shared_file_open(args) -> None:
    secret = args.secret or DEFAULT_SECRET
    port = args.port if args.port is not None else DEFAULT_SHARED_PORT
    base_pathname = _normalize_base_path(args.base_pathname)

    probe = _probe_shared_service(args.host, port, base_pathname)
    if probe["running"] and probe["server_mode"]:
        token = _create_viewer_token(args.h5file, secret, args.context_dir)
        url = _build_service_url(args.host, port, base_pathname, token=token)
        display_url = _build_display_url(args.host, port, base_pathname, token=token)
        logger.info("Reusing running shared HDF5 service on port %s", port)
        _log_visualizer_available(display_url)
        _open_url(url, args.no_browser)
        return

    if _is_port_in_use(args.host, port):
        raise RuntimeError(
            f"Port {port} is already occupied by a non-TRICYS-HDF5 service. "
            f"Please choose another port with --port <port>."
        )

    token = _create_viewer_token(args.h5file, secret, args.context_dir)
    process = _start_shared_service_process(
        args.host,
        port,
        base_pathname,
        secret,
        args.context_dir,
    )
    if not _wait_for_shared_service(args.host, port, base_pathname):
        raise RuntimeError(
            f"Failed to start shared HDF5 service on port {port}. "
            f"Spawned PID: {process.pid}."
        )

    url = _build_service_url(args.host, port, base_pathname, token=token)
    display_url = _build_display_url(args.host, port, base_pathname, token=token)
    logger.info("Started shared HDF5 service on port %s (PID %s)", port, process.pid)
    _log_visualizer_available(display_url)
    _open_url(url, args.no_browser)


def start():
    """
    Parses command-line arguments and starts the Dash server.
    """
    _configure_logging()
    parser = argparse.ArgumentParser(description="Launch the Tricys HDF5 Visualizer.")
    parser.add_argument(
        "h5file", type=str, nargs="?", help="Path to the HDF5 results file."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Shared service port. Defaults to 8050. If that port is occupied by another service, rerun with --port.",
    )
    parser.add_argument(
        "--host", type=str, default="127.0.0.1", help="Host to bind the web server to."
    )
    parser.add_argument(
        "--server-mode",
        action="store_true",
        help="Run a fixed-port multi-session viewer that resolves files from signed tokens.",
    )
    parser.add_argument(
        "--close",
        action="store_true",
        help="Force-close the running shared HDF5 service on the target port.",
    )
    parser.add_argument(
        "--base-pathname",
        type=str,
        default=os.getenv("HDF5_VISUALIZER_BASE_URL", "/"),
        help="Base URL pathname prefix, e.g. /hdf5/ when running behind a reverse proxy.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open a browser window.",
    )
    parser.add_argument(
        "--context-dir",
        type=str,
        default=get_default_context_dir(),
        help="Directory used by the shared service to store and resolve opaque HDF5 viewer contexts.",
    )
    parser.add_argument(
        "--secret",
        type=str,
        default=DEFAULT_SECRET,
        help="Shared secret used to validate viewer tokens in shared service mode.",
    )
    args = parser.parse_args()

    if args.close and args.h5file:
        parser.error("h5file positional argument is not supported with --close")
    if args.close and args.server_mode:
        parser.error("--server-mode cannot be combined with --close")
    if args.server_mode and args.h5file:
        parser.error("h5file positional argument is not supported in --server-mode")
    if not args.close and not args.server_mode and not args.h5file:
        parser.error("h5file is required unless --server-mode is enabled")
    if args.server_mode and not args.secret:
        parser.error("--secret is required in --server-mode")

    if args.close:
        try:
            _handle_close_shared_service(args)
        except RuntimeError as exc:
            parser.exit(1, f"Error: {exc}\n")
        return

    if not args.server_mode and args.h5file:
        try:
            _handle_shared_file_open(args)
        except RuntimeError as exc:
            parser.exit(1, f"Error: {exc}\n")
        return

    port = args.port if args.port is not None else DEFAULT_SHARED_PORT
    normalized_base_path = _normalize_base_path(args.base_pathname)

    app = create_app(
        h5_file_path=args.h5file,
        server_mode=args.server_mode,
        context_secret=args.secret,
        base_pathname=normalized_base_path,
        context_dir=args.context_dir,
    )

    url = _build_service_url(args.host, port, normalized_base_path)
    display_url = _build_display_url(args.host, port, normalized_base_path)
    _open_url(url, args.no_browser)

    logger.info("Starting Tricys HDF5 Visualizer on %s:%s", args.host, port)
    _log_visualizer_available(display_url)

    app.run(port=port, host=args.host, debug=False)


if __name__ == "__main__":
    start()
