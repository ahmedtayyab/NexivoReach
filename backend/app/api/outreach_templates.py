"""CRUD for per-company outreach email templates."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.api.deps import AuthUser, get_current_user, resolve_business_id
from app.database.session import engine
from app.models.schemas import Business, OutreachTemplate

router = APIRouter(prefix="/api/outreach-templates", tags=["outreach-templates"])


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def template_to_frontend(row: OutreachTemplate) -> Dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name or "",
        "category": row.category or "",
        "tags": list(row.tags or []),
        "subject": row.subject or "",
        "body": row.body or "",
        "specializeLines": list(row.specialize_lines or []),
        "sortOrder": int(row.sort_order or 0),
        "updatedAt": row.updated_at or "",
    }


def normalize_template(raw: Dict[str, Any], index: int = 0) -> Dict[str, Any]:
    tags = raw.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.replace(";", ",").split(",") if t.strip()]
    lines = raw.get("specializeLines") or raw.get("specialize_lines") or []
    if isinstance(lines, str):
        lines = [ln.strip() for ln in lines.splitlines() if ln.strip()]
    return {
        "id": (raw.get("id") or "").strip() or f"tpl-{uuid4().hex[:10]}",
        "name": (raw.get("name") or "").strip() or f"Template {index + 1}",
        "category": (raw.get("category") or "").strip(),
        "tags": [str(t).strip() for t in tags if str(t).strip()][:24],
        "subject": (raw.get("subject") or "").strip(),
        "body": (raw.get("body") or "").strip(),
        "specialize_lines": [str(x).strip() for x in lines if str(x).strip()][:20],
        "sort_order": int(raw.get("sortOrder") or raw.get("sort_order") or index),
        "updated_at": _now(),
    }


class TemplateSaveRequest(BaseModel):
    templates: List[Dict[str, Any]] = Field(default_factory=list)
    outreachMode: Optional[str] = None  # ai | templates


@router.get("/")
def list_templates(request: Request, user: AuthUser = Depends(get_current_user)):
    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        rows = session.exec(
            select(OutreachTemplate)
            .where(OutreachTemplate.business_id == business_id)
            .order_by(OutreachTemplate.sort_order, OutreachTemplate.name)
        ).all()
        biz = session.get(Business, business_id)
        mode = (getattr(biz, "outreach_mode", None) or "ai").strip().lower()
        if mode not in ("ai", "templates"):
            mode = "ai"
        return {
            "outreachMode": mode,
            "templates": [template_to_frontend(r) for r in rows],
        }


@router.post("/save")
def save_templates(
    req: TemplateSaveRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        biz = session.get(Business, business_id)
        if biz and req.outreachMode is not None:
            mode = (req.outreachMode or "ai").strip().lower()
            biz.outreach_mode = mode if mode in ("ai", "templates") else "ai"
            session.add(biz)

        existing = session.exec(
            select(OutreachTemplate).where(OutreachTemplate.business_id == business_id)
        ).all()
        for row in existing:
            session.delete(row)
        session.flush()

        saved = []
        for i, raw in enumerate(req.templates or []):
            data = normalize_template(raw, i)
            if not data["body"] and not data["subject"]:
                continue
            row = OutreachTemplate(
                id=data["id"],
                business_id=business_id,
                user_id=user.id,
                name=data["name"],
                category=data["category"],
                tags=data["tags"],
                subject=data["subject"],
                body=data["body"],
                specialize_lines=data["specialize_lines"],
                sort_order=data["sort_order"],
                updated_at=data["updated_at"],
            )
            session.add(row)
            saved.append(row)

        session.commit()
        for row in saved:
            session.refresh(row)

        mode = (getattr(biz, "outreach_mode", None) or "ai") if biz else "ai"
        return {
            "outreachMode": mode,
            "templates": [template_to_frontend(r) for r in saved],
        }
