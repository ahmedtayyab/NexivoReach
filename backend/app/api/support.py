"""Customer support tickets."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from app.api.deps import AuthUser, get_current_user, get_session_user
from app.database.session import engine
from app.models.schemas import SupportTicket, User
from app.services import access as access_mod
from app.services import notifications as notif_mod
from app.services import support_attachments as att_mod

router = APIRouter(prefix="/api/support", tags=["support"])

VALID_STATUS = {"open", "in_progress", "resolved", "closed"}
VALID_CATEGORY = {"general", "billing", "limits", "bug", "appeal"}
VALID_PRIORITY = {"low", "normal", "high"}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class TicketCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)
    category: str = "general"
    priority: str = "normal"


def _attachments_meta(row: SupportTicket) -> list:
    attachments = getattr(row, "attachments", None) or []
    if isinstance(attachments, str):
        try:
            attachments = json.loads(attachments) or []
        except Exception:
            attachments = []
    return attachments if isinstance(attachments, list) else []


def serialize_ticket(row: SupportTicket, email: str = "", name: str = "") -> dict:
    return {
        "id": row.id,
        "userId": row.user_id,
        "email": email,
        "name": name,
        "subject": row.subject,
        "body": row.body,
        "status": row.status,
        "priority": row.priority,
        "category": row.category,
        "adminReply": row.admin_reply or "",
        "attachments": att_mod.attachment_public(_attachments_meta(row), row.id or ""),
        "createdAt": row.created_at,
        "updatedAt": row.updated_at,
        "resolvedAt": row.resolved_at,
    }


def _user_label(session: Session, user_id: str) -> tuple[str, str]:
    u = session.get(User, user_id)
    if not u:
        return "", ""
    return u.email or "", u.name or ""


def _can_view_ticket(user: AuthUser, row: SupportTicket) -> bool:
    if row.user_id == user.id:
        return True
    return bool(getattr(user, "is_admin", False) or access_mod.is_admin_email(user.email))


@router.get("/tickets")
def list_my_tickets(user: AuthUser = Depends(get_session_user)):
    with Session(engine) as session:
        rows = session.exec(
            select(SupportTicket)
            .where(SupportTicket.user_id == user.id)
            .order_by(col(SupportTicket.created_at).desc())
        ).all()
        return {
            "tickets": [
                serialize_ticket(r, email=user.email, name=user.name) for r in rows
            ]
        }


@router.post("/tickets")
async def create_ticket(
    subject: str = Form(...),
    body: str = Form(...),
    category: str = Form("general"),
    priority: str = Form("normal"),
    files: List[UploadFile] | None = File(None),
    user: AuthUser = Depends(get_current_user),
):
    category_n = (category or "general").strip().lower()
    priority_n = (priority or "normal").strip().lower()
    if category_n not in VALID_CATEGORY:
        raise HTTPException(status_code=400, detail="Invalid category")
    if priority_n not in VALID_PRIORITY:
        raise HTTPException(status_code=400, detail="Invalid priority")
    subject_n = (subject or "").strip()
    body_n = (body or "").strip()
    if not subject_n or not body_n:
        raise HTTPException(status_code=400, detail="Subject and body required")

    file_list = [f for f in (files or []) if f and (f.filename or "").strip()]
    if len(file_list) > att_mod.MAX_FILES:
        raise HTTPException(status_code=400, detail=f"At most {att_mod.MAX_FILES} images allowed")

    now = _now()
    ticket_id = f"tkt-{uuid4().hex[:12]}"
    try:
        attachments = await att_mod.save_uploads(ticket_id, file_list)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not save attachments: {exc}") from exc

    row = SupportTicket(
        id=ticket_id,
        user_id=user.id,
        subject=subject_n[:200],
        body=body_n[:5000],
        status="open",
        priority=priority_n,
        category=category_n,
        attachments=attachments,
        created_at=now,
        updated_at=now,
    )
    with Session(engine) as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        notif_mod.notify_user(
            session,
            user.id,
            kind="ticket",
            title="Support ticket submitted",
            body=f"We received “{row.subject}”. We'll reply here when there's an update.",
            href="#support",
            meta={"ticketId": row.id},
        )
        return serialize_ticket(row, email=user.email, name=user.name)


class AppealCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    subject: str = Field(default="Account suspension appeal", max_length=200)


@router.post("/appeal")
def create_appeal(payload: AppealCreate, user: AuthUser = Depends(get_session_user)):
    """Suspended users may submit an appeal without full app access."""
    subject = (payload.subject or "Account suspension appeal").strip() or "Account suspension appeal"
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="Please explain what happened")

    now = _now()
    row = SupportTicket(
        id=f"tkt-{uuid4().hex[:12]}",
        user_id=user.id,
        subject=subject[:200],
        body=body[:5000],
        status="open",
        priority="high",
        category="appeal",
        attachments=[],
        created_at=now,
        updated_at=now,
    )
    with Session(engine) as session:
        open_appeals = session.exec(
            select(SupportTicket).where(
                SupportTicket.user_id == user.id,
                SupportTicket.category == "appeal",
            )
        ).all()
        existing = next((t for t in open_appeals if t.status in {"open", "in_progress"}), None)
        if existing:
            return {
                **serialize_ticket(existing, email=user.email, name=user.name),
                "alreadyOpen": True,
            }
        session.add(row)
        session.commit()
        session.refresh(row)
        notif_mod.notify_user(
            session,
            user.id,
            kind="ticket",
            title="Appeal submitted",
            body="We received your suspension appeal. An admin will review it.",
            href="#suspended",
            meta={"ticketId": row.id, "appeal": True},
        )
        return {**serialize_ticket(row, email=user.email, name=user.name), "alreadyOpen": False}


@router.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: str, user: AuthUser = Depends(get_session_user)):
    with Session(engine) as session:
        row = session.get(SupportTicket, ticket_id)
        if not row or not _can_view_ticket(user, row):
            raise HTTPException(status_code=404, detail="Ticket not found")
        email, name = _user_label(session, row.user_id)
        return serialize_ticket(row, email=email or user.email, name=name or user.name)


@router.get("/tickets/{ticket_id}/attachments/{attachment_id}")
def get_ticket_attachment(
    ticket_id: str,
    attachment_id: str,
    user: AuthUser = Depends(get_session_user),
):
    with Session(engine) as session:
        row = session.get(SupportTicket, ticket_id)
        if not row or not _can_view_ticket(user, row):
            raise HTTPException(status_code=404, detail="Ticket not found")
        path, mime, name = att_mod.resolve_file(ticket_id, attachment_id, _attachments_meta(row))
        return FileResponse(path, media_type=mime, filename=name)
