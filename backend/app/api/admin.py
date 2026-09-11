"""Admin console: users, usage, invite allowlist, suspend."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, col, func, select

from app.api.deps import AuthUser, get_current_user
from app.config import settings
from app.database.session import engine
from app.models.schemas import Business, InviteAllowlist, ProspectRecord, SupportTicket, UsageDaily, User
from app.services import access as access_mod
from app.services import notifications as notif_mod
from app.api.support import (
    VALID_PRIORITY,
    VALID_STATUS,
    _now as ticket_now,
    _user_label,
    serialize_ticket,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _require_admin(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    # Local AUTH_DISABLED operator is always admin for ops.
    if user.id == "local":
        return user
    with Session(engine) as session:
        row = session.get(User, user.id)
        if row and access_mod.user_is_admin(row):
            return user
    if access_mod.is_admin_email(user.email):
        return user
    raise HTTPException(status_code=403, detail="Admin only")


class UserPatch(BaseModel):
    isSuspended: Optional[bool] = None
    isAdmin: Optional[bool] = None
    plan: Optional[str] = None
    usageUnlimited: Optional[bool] = None
    # -1 clears override (back to global default). Omit to leave unchanged.
    dailyHuntLimit: Optional[int] = None
    dailyExtractLimit: Optional[int] = None
    dailyPrepareLimit: Optional[int] = None
    dailySendLimit: Optional[int] = None
    # Unsuspend + wipe custom caps → global defaults (still capped).
    clearRestrictions: Optional[bool] = None
    # Unsuspend + no daily caps at all.
    liftAllCaps: Optional[bool] = None


class InviteCreate(BaseModel):
    email: str
    note: str = ""
    sendEmail: bool = True


def _invite_email_body(*, invitee: str, app_url: str, from_name: str) -> str:
    return (
        f"Hi,\n\n"
        f"You've been invited to NexivoReach (private beta).\n\n"
        f"1. Open {app_url}\n"
        f"2. Sign in with Google using this exact address: {invitee}\n\n"
        f"If Google still shows “access blocked”, ask the operator to also add you as an "
        f"OAuth test user in Google Cloud Console while the app is in Testing mode.\n\n"
        f"— {from_name or 'NexivoReach'}\n"
    )


def _user_card(session: Session, user: User, day: str) -> dict:
    usage = session.exec(
        select(UsageDaily).where(UsageDaily.user_id == user.id, UsageDaily.day == day)
    ).first()
    companies = session.exec(select(Business).where(Business.user_id == user.id)).all()
    leads = session.exec(
        select(func.count()).select_from(ProspectRecord).where(ProspectRecord.user_id == user.id)
    ).one()
    limits = {
        "hunt": access_mod._limit_for(user, "hunt"),
        "extract": access_mod._limit_for(user, "extract"),
        "prepare": access_mod._limit_for(user, "prepare"),
        "send": access_mod._limit_for(user, "send"),
    }
    used = {
        "hunt": usage.hunts if usage else 0,
        "extract": usage.extracts if usage else 0,
        "prepare": usage.prepares if usage else 0,
        "send": usage.sends if usage else 0,
    }
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "createdAt": user.created_at,
        "isAdmin": access_mod.user_is_admin(user),
        "isSuspended": bool(user.is_suspended),
        "usageUnlimited": bool(getattr(user, "usage_unlimited", False)),
        "plan": user.plan or "pilot",
        "companyCount": len(companies),
        "leadCount": int(leads or 0),
        "companies": [{"id": c.id, "name": c.name or "Untitled"} for c in companies[:8]],
        "usageToday": {
            "day": day,
            "used": used,
            "limits": limits,
            "bypassed": access_mod.user_bypasses_caps(user),
        },
        "limitOverrides": {
            "hunt": user.daily_hunt_limit,
            "extract": user.daily_extract_limit,
            "prepare": user.daily_prepare_limit,
            "send": user.daily_send_limit,
        },
    }


@router.get("/overview")
def admin_overview(_admin: AuthUser = Depends(_require_admin)):
    day = access_mod.utc_day()
    with Session(engine) as session:
        users = session.exec(select(User)).all()
        usage_rows = session.exec(select(UsageDaily).where(UsageDaily.day == day)).all()
        invites = session.exec(select(InviteAllowlist)).all()
        by_user = {u.id: u for u in users}
        totals = {"hunt": 0, "extract": 0, "prepare": 0, "send": 0}
        for row in usage_rows:
            totals["hunt"] += row.hunts
            totals["extract"] += row.extracts
            totals["prepare"] += row.prepares
            totals["send"] += row.sends

        series = []
        for i in range(6, -1, -1):
            d = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
            rows = session.exec(select(UsageDaily).where(UsageDaily.day == d)).all()
            series.append({
                "day": d,
                "hunts": sum(r.hunts for r in rows),
                "extracts": sum(r.extracts for r in rows),
                "prepares": sum(r.prepares for r in rows),
                "sends": sum(r.sends for r in rows),
                "activeUsers": len({
                    r.user_id for r in rows
                    if (r.hunts + r.extracts + r.prepares + r.sends) > 0
                }),
            })

        active_today = len({
            r.user_id for r in usage_rows
            if (r.hunts + r.extracts + r.prepares + r.sends) > 0
        })
        suspended = sum(1 for u in users if u.is_suspended)
        return {
            "day": day,
            "inviteOnly": bool(settings.INVITE_ONLY),
            "defaults": {
                "hunt": settings.DAILY_HUNT_LIMIT,
                "extract": settings.DAILY_EXTRACT_LIMIT,
                "prepare": settings.DAILY_PREPARE_LIMIT,
                "send": settings.DAILY_SEND_LIMIT,
            },
            "stats": {
                "users": len(users),
                "suspended": suspended,
                "invites": len(invites),
                "activeToday": active_today,
                "usageToday": totals,
            },
            "series": series,
            "topUsersToday": sorted(
                [
                    {
                        "id": r.user_id,
                        "email": (by_user[r.user_id].email if r.user_id in by_user else r.user_id),
                        "name": (by_user[r.user_id].name if r.user_id in by_user else ""),
                        "hunts": r.hunts,
                        "extracts": r.extracts,
                        "prepares": r.prepares,
                        "sends": r.sends,
                        "total": r.hunts + r.extracts + r.prepares + r.sends,
                    }
                    for r in usage_rows
                    if (r.hunts + r.extracts + r.prepares + r.sends) > 0
                ],
                key=lambda x: x["total"],
                reverse=True,
            )[:8],
        }


@router.get("/users")
def list_users(_admin: AuthUser = Depends(_require_admin)):
    day = access_mod.utc_day()
    with Session(engine) as session:
        users = session.exec(select(User).order_by(col(User.created_at).desc())).all()
        return {"users": [_user_card(session, u, day) for u in users], "day": day}


def _notify_account_change(session: Session, user: User, title: str, body: str, kind: str = "system") -> None:
    if not user.id:
        return
    notif_mod.notify_user(
        session,
        user.id,
        kind=kind,
        title=title,
        body=body,
        href="#support",
        meta={"source": "admin"},
    )


@router.patch("/users/{user_id}")
def patch_user(user_id: str, payload: UserPatch, admin: AuthUser = Depends(_require_admin)):
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        notices: list[tuple[str, str, str]] = []

        if payload.clearRestrictions:
            user.is_suspended = False
            user.usage_unlimited = False
            user.daily_hunt_limit = None
            user.daily_extract_limit = None
            user.daily_prepare_limit = None
            user.daily_send_limit = None
            notices.append(
                (
                    "system",
                    "Account restrictions cleared",
                    "Your suspension was lifted and custom daily caps were reset to the default plan limits.",
                )
            )
        elif payload.liftAllCaps:
            user.is_suspended = False
            user.usage_unlimited = True
            user.daily_hunt_limit = None
            user.daily_extract_limit = None
            user.daily_prepare_limit = None
            user.daily_send_limit = None
            notices.append(
                (
                    "system",
                    "Daily usage caps lifted",
                    "An admin removed your daily hunt/extract/prepare/send limits. You can keep working without hitting caps.",
                )
            )
        else:
            if payload.isSuspended is not None:
                if user.id == admin.id and payload.isSuspended:
                    raise HTTPException(status_code=400, detail="Cannot suspend yourself")
                user.is_suspended = payload.isSuspended
                if payload.isSuspended:
                    notices.append(
                        (
                            "warn",
                            "Account suspended",
                            "An admin suspended your account. Open Support if you believe this is a mistake.",
                        )
                    )
                else:
                    notices.append(
                        (
                            "system",
                            "Account unsuspended",
                            "An admin restored access to your account. You can sign in and continue.",
                        )
                    )
            if payload.isAdmin is not None:
                if user.id == admin.id and not payload.isAdmin:
                    raise HTTPException(status_code=400, detail="Cannot remove your own admin flag")
                user.is_admin = payload.isAdmin
            if payload.plan is not None:
                plan = payload.plan.strip().lower()
                if plan not in {"pilot", "free", "pro", "growth"}:
                    raise HTTPException(status_code=400, detail="Invalid plan")
                user.plan = plan
                notices.append(
                    (
                        "info",
                        f"Plan updated to {plan}",
                        f"Your NexivoReach plan is now “{plan}”. Limits may change with your package.",
                    )
                )
            if payload.usageUnlimited is not None:
                user.usage_unlimited = payload.usageUnlimited
                if payload.usageUnlimited:
                    user.daily_hunt_limit = None
                    user.daily_extract_limit = None
                    user.daily_prepare_limit = None
                    user.daily_send_limit = None
                    notices.append(
                        (
                            "system",
                            "Unlimited usage enabled",
                            "An admin enabled unlimited daily usage on your account.",
                        )
                    )
                else:
                    notices.append(
                        (
                            "warn",
                            "Unlimited usage turned off",
                            "Daily caps apply again on your account. Check Notifications for remaining usage.",
                        )
                    )
            limit_bits: list[str] = []
            if payload.dailyHuntLimit is not None:
                user.daily_hunt_limit = payload.dailyHuntLimit if payload.dailyHuntLimit >= 0 else None
                limit_bits.append(
                    f"hunt → {user.daily_hunt_limit if user.daily_hunt_limit is not None else 'default'}"
                )
            if payload.dailyExtractLimit is not None:
                user.daily_extract_limit = payload.dailyExtractLimit if payload.dailyExtractLimit >= 0 else None
                limit_bits.append(
                    f"extract → {user.daily_extract_limit if user.daily_extract_limit is not None else 'default'}"
                )
            if payload.dailyPrepareLimit is not None:
                user.daily_prepare_limit = payload.dailyPrepareLimit if payload.dailyPrepareLimit >= 0 else None
                limit_bits.append(
                    f"prepare → {user.daily_prepare_limit if user.daily_prepare_limit is not None else 'default'}"
                )
            if payload.dailySendLimit is not None:
                user.daily_send_limit = payload.dailySendLimit if payload.dailySendLimit >= 0 else None
                limit_bits.append(
                    f"send → {user.daily_send_limit if user.daily_send_limit is not None else 'default'}"
                )
            if limit_bits:
                notices.append(
                    (
                        "info",
                        "Daily limits updated",
                        "An admin changed your caps: " + "; ".join(limit_bits) + ".",
                    )
                )

        session.add(user)
        session.commit()
        session.refresh(user)
        for kind, title, body in notices:
            _notify_account_change(session, user, title, body, kind=kind)
        return _user_card(session, user, access_mod.utc_day())


@router.get("/allowlist")
def list_allowlist(_admin: AuthUser = Depends(_require_admin)):
    with Session(engine) as session:
        rows = session.exec(
            select(InviteAllowlist).order_by(col(InviteAllowlist.created_at).desc())
        ).all()
        return {
            "inviteOnly": bool(settings.INVITE_ONLY),
            "invites": [
                {
                    "email": r.email,
                    "note": r.note,
                    "createdAt": r.created_at,
                    "createdBy": r.created_by,
                }
                for r in rows
            ],
        }


@router.post("/allowlist")
async def create_invite(payload: InviteCreate, admin: AuthUser = Depends(_require_admin)):
    from app.config import effective_app_url
    from app.integrations import gmail as gmail_mod

    with Session(engine) as session:
        row = access_mod.add_invite(
            session, payload.email, payload.note, created_by=admin.email or admin.id
        )
        invite_link = effective_app_url().rstrip("/")
        result = {
            "email": row.email,
            "note": row.note,
            "createdAt": row.created_at,
            "createdBy": row.created_by,
            "inviteLink": invite_link,
            "emailSent": False,
            "emailError": "",
        }

        if not payload.sendEmail:
            return result

        db_admin = session.get(User, admin.id)
        if not db_admin or not gmail_mod.is_connected(db_admin):
            result["emailError"] = (
                "Invite saved, but Gmail isn’t connected on this admin account — "
                "connect Gmail in Workspace → Connect, or copy the invite link and email them manually."
            )
            return result

        try:
            await gmail_mod.send_email(
                session,
                db_admin,
                to=row.email,
                subject="You're invited to NexivoReach",
                body=_invite_email_body(
                    invitee=row.email,
                    app_url=invite_link,
                    from_name=db_admin.name or db_admin.gmail_email or admin.email,
                ),
            )
            result["emailSent"] = True
        except Exception as exc:
            result["emailError"] = f"Invite saved, but email failed: {str(exc)[:180]}"
        return result


@router.delete("/allowlist")
def delete_invite(email: str, _admin: AuthUser = Depends(_require_admin)):
    """Remove an invite. Email is a query param so addresses with @ work reliably."""
    with Session(engine) as session:
        ok = access_mod.remove_invite(session, email)
        if not ok:
            raise HTTPException(status_code=404, detail="Invite not found")
        return {"ok": True, "email": access_mod.normalize_email(email)}


# Keep old path working for any cached clients
@router.delete("/allowlist/{email}")
def delete_invite_path(email: str, _admin: AuthUser = Depends(_require_admin)):
    with Session(engine) as session:
        ok = access_mod.remove_invite(session, email)
        if not ok:
            raise HTTPException(status_code=404, detail="Invite not found")
        return {"ok": True, "email": access_mod.normalize_email(email)}


class TicketPatch(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    adminReply: Optional[str] = None


@router.get("/tickets")
def list_tickets(_admin: AuthUser = Depends(_require_admin), status: Optional[str] = None):
    with Session(engine) as session:
        all_rows = session.exec(
            select(SupportTicket).order_by(col(SupportTicket.updated_at).desc())
        ).all()
        open_count = sum(1 for r in all_rows if r.status in {"open", "in_progress"})
        rows = all_rows
        if status:
            want = status.strip().lower()
            rows = [r for r in all_rows if r.status == want]
        out = []
        for r in rows:
            email, name = _user_label(session, r.user_id)
            out.append(serialize_ticket(r, email=email, name=name))
        return {"tickets": out, "openCount": open_count}


@router.patch("/tickets/{ticket_id}")
def patch_ticket(ticket_id: str, payload: TicketPatch, _admin: AuthUser = Depends(_require_admin)):
    with Session(engine) as session:
        row = session.get(SupportTicket, ticket_id)
        if not row:
            raise HTTPException(status_code=404, detail="Ticket not found")

        reply_changed = False
        if payload.status is not None:
            status = payload.status.strip().lower()
            if status not in VALID_STATUS:
                raise HTTPException(status_code=400, detail="Invalid status")
            row.status = status
            if status in {"resolved", "closed"} and not row.resolved_at:
                row.resolved_at = ticket_now()
            if status in {"open", "in_progress"}:
                row.resolved_at = None
        if payload.priority is not None:
            priority = payload.priority.strip().lower()
            if priority not in VALID_PRIORITY:
                raise HTTPException(status_code=400, detail="Invalid priority")
            row.priority = priority
        if payload.adminReply is not None:
            reply = payload.adminReply.strip()
            if reply != (row.admin_reply or ""):
                reply_changed = True
            row.admin_reply = reply[:5000]

        row.updated_at = ticket_now()
        session.add(row)
        session.commit()
        session.refresh(row)

        if reply_changed and row.admin_reply:
            notif_mod.notify_user(
                session,
                row.user_id,
                kind="ticket",
                title="Support replied to your ticket",
                body=f"Update on “{row.subject}”: {row.admin_reply[:240]}",
                href="#support",
                meta={"ticketId": row.id, "status": row.status},
            )
        elif payload.status is not None:
            notif_mod.notify_user(
                session,
                row.user_id,
                kind="ticket",
                title=f"Ticket marked {row.status.replace('_', ' ')}",
                body=f"“{row.subject}” is now {row.status.replace('_', ' ')}.",
                href="#support",
                meta={"ticketId": row.id, "status": row.status},
            )

        email, name = _user_label(session, row.user_id)
        return serialize_ticket(row, email=email, name=name)
