"""Admin → user messages: popup once, then live in notifications; reply opens Support."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlmodel import Session, col, select

from app.models.schemas import (
    AdminMessage,
    AdminMessageDelivery,
    Notification,
    SupportTicket,
    User,
)
from app.services import notifications as notif_mod

VALID_SEVERITY = {"info", "warn", "action_required"}
VALID_AUDIENCE = {"all", "user"}
VALID_STATUS = {"pending_popup", "acknowledged", "dismissed", "replied"}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def serialize_message(row: AdminMessage, *, delivery_count: int = 0, pending: int = 0) -> Dict[str, Any]:
    return {
        "id": row.id,
        "fromAdminId": row.from_admin_id,
        "title": row.title,
        "body": row.body,
        "severity": row.severity,
        "audience": row.audience,
        "targetUserId": row.target_user_id,
        "createdAt": row.created_at,
        "expiresAt": row.expires_at,
        "deliveryCount": delivery_count,
        "pendingPopupCount": pending,
    }


def serialize_delivery(
    delivery: AdminMessageDelivery,
    message: AdminMessage,
) -> Dict[str, Any]:
    return {
        "id": delivery.id,
        "messageId": message.id,
        "status": delivery.status,
        "ticketId": delivery.ticket_id,
        "createdAt": delivery.created_at,
        "resolvedAt": delivery.resolved_at,
        "title": message.title,
        "body": message.body,
        "severity": message.severity,
        "requiresAck": message.severity == "action_required",
        "notificationId": delivery.notification_id,
    }


def _recipient_ids(session: Session, audience: str, target_user_id: Optional[str]) -> List[str]:
    if audience == "user":
        uid = (target_user_id or "").strip()
        if not uid:
            return []
        row = session.get(User, uid)
        return [uid] if row else []
    rows = session.exec(select(User)).all()
    return [u.id for u in rows if u.id]


def create_and_deliver(
    session: Session,
    *,
    admin_id: str,
    title: str,
    body: str,
    severity: str = "info",
    audience: str = "all",
    target_user_id: Optional[str] = None,
) -> AdminMessage:
    sev = (severity or "info").strip().lower()
    if sev not in VALID_SEVERITY:
        sev = "info"
    aud = (audience or "all").strip().lower()
    if aud not in VALID_AUDIENCE:
        aud = "all"

    msg = AdminMessage(
        id=f"amsg-{uuid4().hex[:12]}",
        from_admin_id=admin_id,
        title=(title or "").strip()[:200],
        body=(body or "").strip()[:4000],
        severity=sev,
        audience=aud,
        target_user_id=(target_user_id or None) if aud == "user" else None,
        created_at=_now(),
    )
    session.add(msg)
    session.commit()
    session.refresh(msg)

    recipients = _recipient_ids(session, aud, target_user_id)
    now = _now()
    for uid in recipients:
        if uid == admin_id and aud == "all":
            # Still deliver to admin so they can preview the popup path if desired;
            # keep delivery — admins are users too.
            pass
        ntf = notif_mod.notify_user(
            session,
            uid,
            kind="admin_message",
            title=msg.title,
            body=msg.body,
            href="#notifications",
            meta={
                "adminMessageId": msg.id,
                "severity": sev,
                "popup": True,
            },
        )
        delivery = AdminMessageDelivery(
            id=f"amd-{uuid4().hex[:12]}",
            message_id=msg.id or "",
            user_id=uid,
            notification_id=ntf.id if ntf else None,
            status="pending_popup",
            created_at=now,
        )
        session.add(delivery)
    session.commit()
    return msg


def list_messages(session: Session, limit: int = 40) -> List[Dict[str, Any]]:
    rows = session.exec(
        select(AdminMessage).order_by(col(AdminMessage.created_at).desc())
    ).all()
    out: List[Dict[str, Any]] = []
    for row in rows[: max(1, min(limit, 100))]:
        deliveries = session.exec(
            select(AdminMessageDelivery).where(AdminMessageDelivery.message_id == row.id)
        ).all()
        pending = sum(1 for d in deliveries if d.status == "pending_popup")
        out.append(serialize_message(row, delivery_count=len(deliveries), pending=pending))
    return out


def pending_popup_for_user(session: Session, user_id: str) -> Optional[Dict[str, Any]]:
    deliveries = session.exec(
        select(AdminMessageDelivery)
        .where(
            AdminMessageDelivery.user_id == user_id,
            AdminMessageDelivery.status == "pending_popup",
        )
        .order_by(col(AdminMessageDelivery.created_at).asc())
    ).all()
    for d in deliveries:
        msg = session.get(AdminMessage, d.message_id)
        if not msg:
            continue
        if msg.expires_at and msg.expires_at < _now():
            d.status = "dismissed"
            d.resolved_at = _now()
            session.add(d)
            session.commit()
            continue
        return serialize_delivery(d, msg)
    return None


def _get_owned_delivery(
    session: Session, user_id: str, delivery_id: str
) -> Optional[tuple[AdminMessageDelivery, AdminMessage]]:
    d = session.get(AdminMessageDelivery, delivery_id)
    if not d or d.user_id != user_id:
        return None
    msg = session.get(AdminMessage, d.message_id)
    if not msg:
        return None
    return d, msg


def resolve_delivery(
    session: Session,
    user_id: str,
    delivery_id: str,
    *,
    action: str,
    reply_body: str = "",
) -> Dict[str, Any]:
    """action: acknowledge | dismiss | reply"""
    owned = _get_owned_delivery(session, user_id, delivery_id)
    if not owned:
        raise ValueError("Message not found")
    delivery, msg = owned

    act = (action or "").strip().lower()
    if act not in {"acknowledge", "dismiss", "reply"}:
        raise ValueError("Invalid action")

    if delivery.status != "pending_popup" and act != "reply":
        return serialize_delivery(delivery, msg)

    ticket_id = delivery.ticket_id
    if act == "reply":
        text = (reply_body or "").strip()
        if len(text) < 2:
            raise ValueError("Reply is too short")
        now = _now()
        ticket = SupportTicket(
            id=f"tkt-{uuid4().hex[:10]}",
            user_id=user_id,
            subject=f"Re: {msg.title}"[:200],
            body=(
                f"{text}\n\n---\nIn reply to admin message:\n{msg.title}\n\n{msg.body}"
            )[:8000],
            status="open",
            priority="normal",
            category="general",
            created_at=now,
            updated_at=now,
        )
        session.add(ticket)
        session.commit()
        session.refresh(ticket)
        ticket_id = ticket.id
        delivery.status = "replied"
        delivery.ticket_id = ticket_id
        delivery.resolved_at = now
    elif act == "acknowledge":
        delivery.status = "acknowledged"
        delivery.resolved_at = _now()
    else:
        if msg.severity == "action_required":
            raise ValueError("This message requires acknowledgement or a reply")
        delivery.status = "dismissed"
        delivery.resolved_at = _now()

    session.add(delivery)
    # Keep notification in the inbox; clear popup flag so it lives as a normal alert
    if delivery.notification_id:
        ntf = session.get(Notification, delivery.notification_id)
        if ntf and ntf.user_id == user_id:
            meta = dict(ntf.meta or {})
            meta["popup"] = False
            meta["userAction"] = delivery.status
            ntf.meta = meta
            ntf.read_at = None
            session.add(ntf)
    session.commit()
    session.refresh(delivery)
    result = serialize_delivery(delivery, msg)
    if ticket_id:
        result["ticketId"] = ticket_id
    return result
