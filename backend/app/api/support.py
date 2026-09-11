"""Customer support tickets."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from app.api.deps import AuthUser, get_current_user
from app.database.session import engine
from app.models.schemas import SupportTicket, User
from app.services import notifications as notif_mod

router = APIRouter(prefix="/api/support", tags=["support"])

VALID_STATUS = {"open", "in_progress", "resolved", "closed"}
VALID_CATEGORY = {"general", "billing", "limits", "bug"}
VALID_PRIORITY = {"low", "normal", "high"}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class TicketCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)
    category: str = "general"
    priority: str = "normal"


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
        "createdAt": row.created_at,
        "updatedAt": row.updated_at,
        "resolvedAt": row.resolved_at,
    }


def _user_label(session: Session, user_id: str) -> tuple[str, str]:
    u = session.get(User, user_id)
    if not u:
        return "", ""
    return u.email or "", u.name or ""


@router.get("/tickets")
def list_my_tickets(user: AuthUser = Depends(get_current_user)):
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
def create_ticket(payload: TicketCreate, user: AuthUser = Depends(get_current_user)):
    category = (payload.category or "general").strip().lower()
    priority = (payload.priority or "normal").strip().lower()
    if category not in VALID_CATEGORY:
        raise HTTPException(status_code=400, detail="Invalid category")
    if priority not in VALID_PRIORITY:
        raise HTTPException(status_code=400, detail="Invalid priority")
    subject = payload.subject.strip()
    body = payload.body.strip()
    if not subject or not body:
        raise HTTPException(status_code=400, detail="Subject and body required")

    now = _now()
    row = SupportTicket(
        id=f"tkt-{uuid4().hex[:12]}",
        user_id=user.id,
        subject=subject[:200],
        body=body[:5000],
        status="open",
        priority=priority,
        category=category,
        created_at=now,
        updated_at=now,
    )
    with Session(engine) as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        # Confirm to the customer.
        notif_mod.notify_user(
            session,
            user.id,
            kind="ticket",
            title="Support ticket submitted",
            body=f"We received “{row.subject}”. We'll reply here when there's an update.",
            href=f"#support",
            meta={"ticketId": row.id},
        )
        return serialize_ticket(row, email=user.email, name=user.name)


@router.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: str, user: AuthUser = Depends(get_current_user)):
    with Session(engine) as session:
        row = session.get(SupportTicket, ticket_id)
        if not row or row.user_id != user.id:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return serialize_ticket(row, email=user.email, name=user.name)
