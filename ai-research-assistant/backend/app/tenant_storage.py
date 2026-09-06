"""Tenant-owned upload registry used for complete data erasure."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from app.config import UPLOAD_DIR

_lock = Lock()


def _registry_path() -> Path:
    return UPLOAD_DIR / ".tenant-uploads.json"


def _load() -> dict[str, list[str]]:
    path = _registry_path()
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def register_tenant_upload(owner_id: str, stored_filename: str) -> None:
    """Associate an opaque stored filename with its server-derived tenant."""
    with _lock:
        registry = _load()
        filenames = registry.setdefault(owner_id, [])
        if stored_filename not in filenames:
            filenames.append(stored_filename)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        _registry_path().write_text(json.dumps(registry, indent=2), encoding="utf-8")


def delete_tenant_uploads(owner_id: str) -> int:
    """Delete all registered uploads for one tenant and remove its registry entry."""
    with _lock:
        registry = _load()
        filenames = registry.pop(owner_id, [])
        deleted = 0
        for stored_filename in filenames:
            candidate = UPLOAD_DIR / Path(stored_filename).name
            if candidate.exists():
                candidate.unlink()
                deleted += 1
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        _registry_path().write_text(json.dumps(registry, indent=2), encoding="utf-8")
        return deleted
