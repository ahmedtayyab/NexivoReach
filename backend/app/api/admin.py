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
from app.models.schemas import Business, InviteAllowlist, ProspectRecord, UsageDaily, User
from app.services import access as access_mod

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


@router.patch("/users/{user_id}")
def patch_user(user_id: str, payload: UserPatch, admin: AuthUser = Depends(_require_admin)):
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if payload.clearRestrictions:
            user.is_suspended = False
            user.usage_unlimited = False
            user.daily_hunt_limit = None
            user.daily_extract_limit = None
            user.daily_prepare_limit = None
            user.daily_send_limit = None
        elif payload.liftAllCaps:
            user.is_suspended = False
            user.usage_unlimited = True
            user.daily_hunt_limit = None
            user.daily_extract_limit = None
            user.daily_prepare_limit = None
            user.daily_send_limit = None
        else:
            if payload.isSuspended is not None:
                if user.id == admin.id and payload.isSuspended:
                    raise HTTPException(status_code=400, detail="Cannot suspend yourself")
                user.is_suspended = payload.isSuspended
            if payload.isAdmin is not None:
                if user.id == admin.id and not payload.isAdmin:
                    raise HTTPException(status_code=400, detail="Cannot remove your own admin flag")
                user.is_admin = payload.isAdmin
            if payload.plan is not None:
                plan = payload.plan.strip().lower()
                if plan not in {"pilot", "free", "pro", "growth"}:
                    raise HTTPException(status_code=400, detail="Invalid plan")
                user.plan = plan
            if payload.usageUnlimited is not None:
                user.usage_unlimited = payload.usageUnlimited
                if payload.usageUnlimited:
                    # Custom per-action caps are irrelevant while unlimited.
                    user.daily_hunt_limit = None
                    user.daily_extract_limit = None
                    user.daily_prepare_limit = None
                    user.daily_send_limit = None
            if payload.dailyHuntLimit is not None:
                user.daily_hunt_limit = payload.dailyHuntLimit if payload.dailyHuntLimit >= 0 else None
            if payload.dailyExtractLimit is not None:
                user.daily_extract_limit = payload.dailyExtractLimit if payload.dailyExtractLimit >= 0 else None
            if payload.dailyPrepareLimit is not None:
                user.daily_prepare_limit = payload.dailyPrepareLimit if payload.dailyPrepareLimit >= 0 else None
            if payload.dailySendLimit is not None:
                user.daily_send_limit = payload.dailySendLimit if payload.dailySendLimit >= 0 else None

        session.add(user)
        session.commit()
        session.refresh(user)
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
def create_invite(payload: InviteCreate, admin: AuthUser = Depends(_require_admin)):
    with Session(engine) as session:
        row = access_mod.add_invite(
            session, payload.email, payload.note, created_by=admin.email or admin.id
        )
        return {
            "email": row.email,
            "note": row.note,
            "createdAt": row.created_at,
            "createdBy": row.created_by,
        }


@router.delete("/allowlist/{email}")
def delete_invite(email: str, _admin: AuthUser = Depends(_require_admin)):
    with Session(engine) as session:
        ok = access_mod.remove_invite(session, email)
        if not ok:
            raise HTTPException(status_code=404, detail="Invite not found")
        return {"ok": True}
