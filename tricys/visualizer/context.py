import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, Optional


def get_default_context_dir() -> str:
    configured = os.getenv("HDF5_CONTEXTS_DIR")
    if configured:
        return configured
    return str(Path.home() / ".tricys" / "hdf5_contexts")


def _urlsafe_b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _urlsafe_b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def build_viewer_context(
    file_path: str,
    display_path: Optional[str] = None,
    task_id: Optional[str] = None,
    project_id: Optional[str] = None,
    mode: str = "server",
) -> Dict[str, Any]:
    resolved_path = str(Path(file_path).expanduser().resolve())
    return {
        "file_path": resolved_path,
        "display_path": display_path or resolved_path,
        "task_id": task_id,
        "project_id": project_id,
        "mode": mode,
    }


def _ensure_context_dir(context_dir: str) -> Path:
    resolved = Path(context_dir).expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def create_context_reference(
    context: Dict[str, Any],
    context_dir: str,
    expires_in_seconds: int = 900,
) -> Dict[str, Any]:
    issued_at = int(time.time())
    payload = dict(context)
    payload["iat"] = issued_at
    payload["exp"] = issued_at + max(int(expires_in_seconds), 1)

    context_id = secrets.token_urlsafe(24)
    target_dir = _ensure_context_dir(context_dir)
    context_path = target_dir / f"{context_id}.json"
    context_path.write_text(
        json.dumps(payload, separators=(",", ":")), encoding="utf-8"
    )
    return {
        "context_id": context_id,
        "exp": payload["exp"],
    }


def load_context_reference(context_id: str, context_dir: str) -> Dict[str, Any]:
    if not context_id:
        raise ValueError("Missing viewer context id")

    context_path = _ensure_context_dir(context_dir) / f"{context_id}.json"
    if not context_path.exists():
        raise ValueError("Viewer context not found")

    try:
        payload = json.loads(context_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Viewer context payload is invalid") from exc

    if int(payload.get("exp", 0)) < int(time.time()):
        try:
            context_path.unlink()
        except OSError:
            pass
        raise ValueError("Viewer context expired")

    file_path = payload.get("file_path")
    if not file_path:
        raise ValueError("Viewer context missing file path")

    resolved_path = Path(file_path).expanduser().resolve()
    if resolved_path.suffix.lower() != ".h5":
        raise ValueError("Viewer context points to an unsupported file")
    if not resolved_path.exists():
        raise ValueError("Requested HDF5 file is no longer available")

    payload["file_path"] = str(resolved_path)
    payload.setdefault("display_path", str(resolved_path))
    payload.setdefault("mode", "server")
    payload["context_id"] = context_id
    return payload


def issue_context_token(
    context: Dict[str, Any],
    secret: str,
    expires_in_seconds: int = 900,
) -> str:
    issued_at = int(time.time())
    payload = dict(context)
    payload["iat"] = issued_at
    payload["exp"] = issued_at + max(int(expires_in_seconds), 1)

    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return f"{_urlsafe_b64encode(body)}.{_urlsafe_b64encode(signature)}"


def decode_context_token(token: str, secret: str) -> Dict[str, Any]:
    try:
        body_b64, sig_b64 = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("Malformed viewer token") from exc

    body = _urlsafe_b64decode(body_b64)
    provided_signature = _urlsafe_b64decode(sig_b64)
    expected_signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()

    if not hmac.compare_digest(provided_signature, expected_signature):
        raise ValueError("Invalid viewer token signature")

    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Malformed viewer token payload") from exc

    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("Viewer token expired")

    if not payload.get("context_id"):
        raise ValueError("Viewer token missing context id")

    return payload


def resolve_context_token(token: str, secret: str, context_dir: str) -> Dict[str, Any]:
    payload = decode_context_token(token, secret)
    return load_context_reference(payload["context_id"], context_dir)
