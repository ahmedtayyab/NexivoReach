"""Store and serve support ticket image attachments."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from app.config import _BACKEND_DIR

UPLOAD_ROOT = (_BACKEND_DIR / "data" / "support_uploads").resolve()
MAX_FILES = 4
MAX_BYTES = 2_500_000  # ~2.5 MB each
ALLOWED_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _safe_name(name: str) -> str:
    base = Path(name or "image").name
    base = re.sub(r"[^\w.\-]+", "_", base).strip("._") or "image"
    return base[:80]


def ensure_upload_root() -> Path:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    return UPLOAD_ROOT


def ticket_dir(ticket_id: str) -> Path:
    ensure_upload_root()
    path = (UPLOAD_ROOT / ticket_id).resolve()
    if UPLOAD_ROOT not in path.parents and path != UPLOAD_ROOT:
        raise HTTPException(status_code=400, detail="Invalid ticket id")
    path.mkdir(parents=True, exist_ok=True)
    return path


async def save_uploads(ticket_id: str, files: List[UploadFile]) -> List[Dict[str, Any]]:
    """Persist up to MAX_FILES image uploads; return metadata list."""
    if not files:
        return []
    saved: List[Dict[str, Any]] = []
    for raw in files[:MAX_FILES]:
        if not raw or not (raw.filename or "").strip():
            continue
        mime = (raw.content_type or "").split(";")[0].strip().lower()
        if mime not in ALLOWED_MIME:
            raise HTTPException(
                status_code=400,
                detail="Only image attachments are allowed (JPEG, PNG, WebP, GIF).",
            )
        data = await raw.read()
        if not data:
            continue
        if len(data) > MAX_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"Each image must be under {MAX_BYTES // 1_000_000}MB.",
            )
        att_id = uuid4().hex[:12]
        ext = ALLOWED_MIME[mime]
        filename = _safe_name(raw.filename or f"screenshot{ext}")
        if not filename.lower().endswith(ext):
            filename = f"{Path(filename).stem}{ext}"
        dest = ticket_dir(ticket_id) / f"{att_id}{ext}"
        dest.write_bytes(data)
        saved.append(
            {
                "id": att_id,
                "name": filename,
                "mime": mime,
                "size": len(data),
                "ext": ext.lstrip("."),
            }
        )
    return saved


def resolve_file(ticket_id: str, attachment_id: str, meta: List[Dict[str, Any]]) -> Tuple[Path, str, str]:
    """Return (path, mime, download_name) for an attachment id."""
    att_id = (attachment_id or "").strip()
    item = next((a for a in (meta or []) if str(a.get("id") or "") == att_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Attachment not found")
    ext = (item.get("ext") or ALLOWED_MIME.get(item.get("mime") or "", ".bin").lstrip(".")).lstrip(".")
    path = (UPLOAD_ROOT / ticket_id / f"{att_id}.{ext}").resolve()
    if UPLOAD_ROOT not in path.parents:
        raise HTTPException(status_code=404, detail="Attachment not found")
    if not path.is_file():
        # Fallback: any matching att_id.*
        folder = UPLOAD_ROOT / ticket_id
        matches = list(folder.glob(f"{att_id}.*")) if folder.is_dir() else []
        if not matches:
            raise HTTPException(status_code=404, detail="Attachment file missing")
        path = matches[0]
    mime = str(item.get("mime") or "application/octet-stream")
    name = str(item.get("name") or path.name)
    return path, mime, name


def attachment_public(meta: Optional[List[Any]], ticket_id: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for a in meta or []:
        if not isinstance(a, dict) or not a.get("id"):
            continue
        att_id = str(a["id"])
        out.append(
            {
                "id": att_id,
                "name": a.get("name") or "image",
                "mime": a.get("mime") or "image/jpeg",
                "size": int(a.get("size") or 0),
                "url": f"/api/support/tickets/{ticket_id}/attachments/{att_id}",
            }
        )
    return out
