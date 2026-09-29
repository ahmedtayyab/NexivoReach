"""User-facing admin message popups (acknowledge / dismiss / reply)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.api.deps import AuthUser, get_current_user
from app.database.session import engine
from app.services import admin_messages as msg_mod

router = APIRouter(prefix="/api/messages", tags=["messages"])


class MessageAction(BaseModel):
    action: str  # acknowledge | dismiss | reply
    replyBody: str = ""


@router.get("/pending-popup")
def pending_popup(user: AuthUser = Depends(get_current_user)):
    with Session(engine) as session:
        pending = msg_mod.pending_popup_for_user(session, user.id)
        return {"message": pending}


@router.post("/{delivery_id}/action")
def act_on_message(
    delivery_id: str,
    payload: MessageAction,
    user: AuthUser = Depends(get_current_user),
):
    with Session(engine) as session:
        try:
            result = msg_mod.resolve_delivery(
                session,
                user.id,
                delivery_id,
                action=payload.action,
                reply_body=payload.replyBody or "",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"delivery": result}
