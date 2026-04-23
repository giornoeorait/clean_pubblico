"""Object storage integration (Emergent).

Wraps the Emergent storage API with a simple helper:
- init_storage() — call once on startup
- put_object(path, data, content_type) — upload bytes
- get_object(path) — download bytes
- upload_bytes(data, ext, folder, content_type) — returns {path, size, url}
"""
import os
import uuid
import base64
import logging
import requests
from typing import Tuple, Optional

logger = logging.getLogger("cleantec.storage")

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
APP_NAME = "cleantec"

_storage_key: Optional[str] = None


def init_storage() -> Optional[str]:
    """Initialize once; returns storage_key. Safe to call many times."""
    global _storage_key
    if _storage_key:
        return _storage_key
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        logger.warning("EMERGENT_LLM_KEY missing — object storage disabled")
        return None
    try:
        resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": key}, timeout=30)
        resp.raise_for_status()
        _storage_key = resp.json()["storage_key"]
        logger.info("Object storage initialized")
        return _storage_key
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
        return None


def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    if not key:
        raise RuntimeError("Object storage not initialized")
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def get_object(path: str) -> Tuple[bytes, str]:
    key = init_storage()
    if not key:
        raise RuntimeError("Object storage not initialized")
    resp = requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


MIME_TYPES = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "gif": "image/gif", "webp": "image/webp", "pdf": "application/pdf",
}


def upload_bytes(data: bytes, ext: str, folder: str = "misc", content_type: Optional[str] = None) -> dict:
    """Upload raw bytes; returns {path, size, url}."""
    ext = (ext or "bin").lower().strip(".")
    ctype = content_type or MIME_TYPES.get(ext, "application/octet-stream")
    path = f"{APP_NAME}/{folder}/{uuid.uuid4()}.{ext}"
    result = put_object(path, data, ctype)
    return {
        "path": result["path"],
        "size": result.get("size", len(data)),
        "content_type": ctype,
        "url": f"/api/files/{result['path']}",
    }


def decode_data_url(data_url: str) -> Tuple[bytes, str]:
    """Decode a base64 data URL → (bytes, ext). Used for signature capture."""
    if "," not in data_url:
        raise ValueError("Invalid data URL")
    header, b64 = data_url.split(",", 1)
    ext = "png"
    if "image/jpeg" in header: ext = "jpg"
    elif "image/webp" in header: ext = "webp"
    elif "image/png" in header: ext = "png"
    return base64.b64decode(b64), ext
