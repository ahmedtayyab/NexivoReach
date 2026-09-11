"""Invite allowlist, admin recognition, and daily usage caps."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException
from sqlmodel import Session, select

from app.config import settings
from app.models.schemas import InviteAllowlist, UsageDaily, User

UsageKind = Literal["hunt", "extract", "prepare", "send"]


def utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def admin_emails() -> set[str]:
    raw = settings.ADMIN_EMAILS or ""
    return {normalize_email(part) for part in raw.split(",") if part.strip()}


def is_admin_email(email: str | None) -> bool:
    return normalize_email(email) in admin_emails()


def user_is_admin(user: User | None) -> bool:
    if user is None:
        return False
    if getattr(user, "is_admin", False):
        return True
    return is_admin_email(user.email)


def sync_admin_flag(session: Session, user: User) -> User:
    """Promote ADMIN_EMAILS on login; bootstrap first user if no admins configured."""
    changed = False
    if is_admin_email(user.email) and not user.is_admin:
        user.is_admin = True
        changed = True
    elif not admin_emails() and not user.is_admin:
        existing_admin = session.exec(select(User).where(User.is_admin == True)).first()  # noqa: E712
        if existing_admin is None:
            user.is_admin = True
            changed = True
    if changed:
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


def is_email_invited(session: Session, email: str) -> bool:
    addr = normalize_email(email)
    if not addr:
        return False
    if is_admin_email(addr):
        return True
    row = session.get(InviteAllowlist, addr)
    return row is not None


def assert_can_signup(session: Session, email: str) -> None:
    if not settings.INVITE_ONLY:
        return
    if is_email_invited(session, email):
        return
    raise HTTPException(
        status_code=403,
        detail="Invite only — ask the operator to add your email to the allowlist.",
    )


def assert_not_suspended(user: User | None) -> None:
    if user is not None and getattr(user, "is_suspended", False):
        raise HTTPException(status_code=403, detail="Account suspended. Contact support.")


def user_bypasses_caps(user: User | None) -> bool:
    if user is None:
        return False
    if user_is_admin(user):
        return True
    return bool(getattr(user, "usage_unlimited", False))


def _limit_for(user: User, kind: UsageKind) -> int:
    if user_bypasses_caps(user):
        return 999999
    overrides = {
        "hunt": user.daily_hunt_limit,
        "extract": user.daily_extract_limit,
        "prepare": user.daily_prepare_limit,
        "send": user.daily_send_limit,
    }
    override = overrides[kind]
    if override is not None and int(override) >= 0:
        return int(override)
    defaults = {
        "hunt": settings.DAILY_HUNT_LIMIT,
        "extract": settings.DAILY_EXTRACT_LIMIT,
        "prepare": settings.DAILY_PREPARE_LIMIT,
        "send": settings.DAILY_SEND_LIMIT,
    }
    return max(0, int(defaults[kind]))


def _get_or_create_usage(session: Session, user_id: str, day: str | None = None) -> UsageDaily:
    day = day or utc_day()
    row = session.exec(
        select(UsageDaily).where(UsageDaily.user_id == user_id, UsageDaily.day == day)
    ).first()
    if row:
        return row
    row = UsageDaily(id=f"usage-{uuid4().hex[:12]}", user_id=user_id, day=day)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def usage_snapshot(session: Session, user: User) -> dict:
    row = _get_or_create_usage(session, user.id or "")
    kinds: list[UsageKind] = ["hunt", "extract", "prepare", "send"]
    used = {
        "hunt": row.hunts,
        "extract": row.extracts,
        "prepare": row.prepares,
        "send": row.sends,
    }
    limits = {k: _limit_for(user, k) for k in kinds}
    bypassed = user_bypasses_caps(user)
    return {
        "day": row.day,
        "used": used,
        "limits": limits,
        "remaining": {
            k: (999999 if bypassed else max(0, limits[k] - used[k])) for k in kinds
        },
        "bypassed": bypassed,
        "usageUnlimited": bool(getattr(user, "usage_unlimited", False)),
    }


def consume_usage(session: Session, user: User, kind: UsageKind, amount: int = 1) -> dict:
    """Raise 429 if over daily cap; otherwise increment and return snapshot."""
    from app.services import notifications as notif_mod

    assert_not_suspended(user)
    amount = max(1, int(amount))
    if user_bypasses_caps(user):
        # Still record for visibility, but never block.
        row = _get_or_create_usage(session, user.id or "")
        if kind == "hunt":
            row.hunts += amount
        elif kind == "extract":
            row.extracts += amount
        elif kind == "prepare":
            row.prepares += amount
        else:
            row.sends += amount
        session.add(row)
        session.commit()
        return usage_snapshot(session, user)

    limit = _limit_for(user, kind)
    row = _get_or_create_usage(session, user.id or "")
    current = {
        "hunt": row.hunts,
        "extract": row.extracts,
        "prepare": row.prepares,
        "send": row.sends,
    }[kind]
    if current + amount > limit:
        notif_mod.notify_limit_reached(session, user, kind, limit)
        raise HTTPException(
            status_code=429,
            detail=(
                f"Daily {kind} limit reached ({limit}/day). "
                "Try again tomorrow or ask an admin to raise your cap."
            ),
        )
    if kind == "hunt":
        row.hunts += amount
    elif kind == "extract":
        row.extracts += amount
    elif kind == "prepare":
        row.prepares += amount
    else:
        row.sends += amount
    session.add(row)
    session.commit()
    snap = usage_snapshot(session, user)
    notif_mod.notify_usage_if_low(session, user, snap)
    return snap


def add_invite(session: Session, email: str, note: str = "", created_by: str = "") -> InviteAllowlist:
    addr = normalize_email(email)
    if not addr or "@" not in addr:
        raise HTTPException(status_code=400, detail="Valid email required")
    existing = session.get(InviteAllowlist, addr)
    if existing:
        existing.note = note or existing.note
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing
    row = InviteAllowlist(
        email=addr,
        note=(note or "").strip(),
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        created_by=created_by or "",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def remove_invite(session: Session, email: str) -> bool:
    row = session.get(InviteAllowlist, normalize_email(email))
    if not row:
        return False
    session.delete(row)
    session.commit()
    return True
