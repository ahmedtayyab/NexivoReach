"""In-app notifications for usage warnings and admin-targeted changes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlmodel import Session, select

from app.models.schemas import Notification, User
from app.services.access import UsageKind, utc_day


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def notify_user(
    session: Session,
    user_id: str,
    *,
    kind: str = "info",
    title: str,
    body: str = "",
    href: Optional[str] = None,
    meta: Optional[dict[str, Any]] = None,
    dedupe_key: Optional[str] = None,
) -> Optional[Notification]:
    """Create a notification. If dedupe_key is set, skip when an unread-or-same-day match exists."""
    if not user_id:
        return None
    meta = dict(meta or {})
    if dedupe_key:
        meta["dedupeKey"] = dedupe_key
        existing = session.exec(
            select(Notification).where(Notification.user_id == user_id)
        ).all()
        for row in existing:
            row_meta = row.meta or {}
            if row_meta.get("dedupeKey") != dedupe_key:
                continue
            # Same-day usage alerts: one per key.
            if kind == "usage" and (row.created_at or "").startswith(utc_day()):
                return row
            if kind != "usage" and not row.read_at:
                return row

    row = Notification(
        id=f"ntf-{uuid4().hex[:12]}",
        user_id=user_id,
        kind=kind,
        title=(title or "").strip()[:200],
        body=(body or "").strip()[:2000],
        href=href,
        created_at=_now(),
        meta=meta,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def notify_usage_if_low(session: Session, user: User, snapshot: dict) -> None:
    """Emit usage notifications when any action is ≥80% of daily limit (once per day/kind)."""
    if not user or not user.id:
        return
    if snapshot.get("bypassed"):
        return
    used = snapshot.get("used") or {}
    limits = snapshot.get("limits") or {}
    day = snapshot.get("day") or utc_day()
    kinds: list[UsageKind] = ["hunt", "extract", "prepare", "send"]
    for kind in kinds:
        limit = int(limits.get(kind) or 0)
        count = int(used.get(kind) or 0)
        if limit <= 0:
            continue
        pct = count / limit
        if pct < 0.8:
            continue
        pct_i = min(100, int(round(pct * 100)))
        exhausted = count >= limit
        title = (
            f"Daily {kind} limit reached"
            if exhausted
            else f"Running low on {kind}s ({pct_i}%)"
        )
        body = (
            f"You've used {count} of {limit} {kind}s today ({day} UTC). "
            + (
                "Ask support if you need a higher cap."
                if exhausted
                else "Consider pacing usage or ask an admin to raise your limit."
            )
        )
        notify_user(
            session,
            user.id,
            kind="usage",
            title=title,
            body=body,
            href="#support",
            meta={"action": kind, "used": count, "limit": limit, "pct": pct_i},
            dedupe_key=f"usage:{day}:{kind}:{'full' if exhausted else 'low'}",
        )


def notify_limit_reached(session: Session, user: User, kind: UsageKind, limit: int) -> None:
    day = utc_day()
    if not user or not user.id:
        return
    notify_user(
        session,
        user.id,
        kind="usage",
        title=f"Daily {kind} limit reached",
        body=(
            f"You've hit your daily {kind} cap ({limit}/day, {day} UTC). "
            "Try again tomorrow or open Support to request a raise."
        ),
        href="#support",
        meta={"action": kind, "limit": limit, "pct": 100},
        dedupe_key=f"usage:{day}:{kind}:full",
    )


def list_for_user(session: Session, user_id: str, limit: int = 40) -> list[Notification]:
    rows = session.exec(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
    ).all()
    return list(rows)[: max(1, min(limit, 100))]


def unread_count(session: Session, user_id: str) -> int:
    rows = session.exec(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.read_at == None,  # noqa: E711
        )
    ).all()
    return len(rows)


def mark_read(session: Session, user_id: str, notification_id: str) -> Optional[Notification]:
    row = session.get(Notification, notification_id)
    if not row or row.user_id != user_id:
        return None
    if not row.read_at:
        row.read_at = _now()
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def mark_all_read(session: Session, user_id: str) -> int:
    rows = session.exec(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.read_at == None,  # noqa: E711
        )
    ).all()
    now = _now()
    for row in rows:
        row.read_at = now
        session.add(row)
    session.commit()
    return len(rows)


def serialize(row: Notification) -> dict:
    return {
        "id": row.id,
        "kind": row.kind,
        "title": row.title,
        "body": row.body,
        "href": row.href,
        "readAt": row.read_at,
        "createdAt": row.created_at,
        "meta": row.meta or {},
    }
