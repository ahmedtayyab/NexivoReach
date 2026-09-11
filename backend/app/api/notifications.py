"""Customer in-app notifications."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.api.deps import AuthUser, get_current_user
from app.database.session import engine
from app.services import notifications as notif_mod

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
def list_notifications(user: AuthUser = Depends(get_current_user), limit: int = 40):
    with Session(engine) as session:
        rows = notif_mod.list_for_user(session, user.id, limit=limit)
        return {
            "unreadCount": notif_mod.unread_count(session, user.id),
            "notifications": [notif_mod.serialize(r) for r in rows],
        }


@router.post("/read-all")
def read_all(user: AuthUser = Depends(get_current_user)):
    with Session(engine) as session:
        n = notif_mod.mark_all_read(session, user.id)
        return {"ok": True, "marked": n, "unreadCount": 0}


@router.post("/{notification_id}/read")
def read_one(notification_id: str, user: AuthUser = Depends(get_current_user)):
    with Session(engine) as session:
        row = notif_mod.mark_read(session, user.id, notification_id)
        if not row:
            raise HTTPException(status_code=404, detail="Notification not found")
        return {
            "ok": True,
            "notification": notif_mod.serialize(row),
            "unreadCount": notif_mod.unread_count(session, user.id),
        }
