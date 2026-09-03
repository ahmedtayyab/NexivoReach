from dataclasses import dataclass
import os
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session, select

from app.config import settings
from app.database.session import engine
from app.models.schemas import Business, User
from app.api.tokens import decode_session_token

SESSION_COOKIE = "nr_session"
BUSINESS_COOKIE = "nr_business"
LOCAL_USER_ID = "local"


@dataclass
class AuthUser:
    id: str
    email: str
    name: str
    picture: str
    google_id: str
    active_business_id: Optional[str] = None


def google_configured() -> bool:
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)


def auth_required() -> bool:
    if os.getenv("AUTH_DISABLED", "").lower() in ("1", "true", "yes"):
        return False
    return google_configured()


def local_user() -> AuthUser:
    return AuthUser(
        id=LOCAL_USER_ID,
        email="local@nexivoreach.local",
        name="Local user",
        picture="",
        google_id="local",
        active_business_id=None,
    )


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def get_current_user(request: Request) -> AuthUser:
    if not auth_required():
        return local_user()
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_session_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid session")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid session")
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return AuthUser(
            id=user.id or user_id,
            email=user.email,
            name=user.name,
            picture=user.picture,
            google_id=user.google_id,
            active_business_id=user.active_business_id,
        )


def ensure_default_business(session: Session, user: AuthUser) -> Business:
    """Return the user's active company, creating a blank one if they have none."""
    businesses = session.exec(
        select(Business).where(Business.user_id == user.id).order_by(Business.updated_at.desc())
    ).all()
    if businesses:
        preferred = None
        if user.active_business_id:
            preferred = next((b for b in businesses if b.id == user.active_business_id), None)
        biz = preferred or businesses[0]
        db_user = session.get(User, user.id)
        if db_user and db_user.active_business_id != biz.id:
            db_user.active_business_id = biz.id
            session.add(db_user)
            session.commit()
        return biz

    biz = Business(
        id=f"biz-{uuid4().hex[:12]}",
        user_id=user.id,
        name="",
        website="",
        description="",
        updated_at=_now(),
    )
    session.add(biz)
    db_user = session.get(User, user.id)
    if db_user:
        db_user.active_business_id = biz.id
        session.add(db_user)
    elif not auth_required():
        session.add(User(
            id=user.id,
            google_id=user.google_id,
            email=user.email,
            name=user.name,
            picture=user.picture,
            created_at=_now(),
            active_business_id=biz.id,
        ))
    session.commit()
    session.refresh(biz)
    return biz


def resolve_business_id(request: Request, user: AuthUser, session: Session) -> str:
    header = (request.headers.get("X-Business-Id") or "").strip()
    cookie = (request.cookies.get(BUSINESS_COOKIE) or "").strip()
    candidate = header or cookie or (user.active_business_id or "")

    if candidate:
        biz = session.get(Business, candidate)
        if biz and biz.user_id == user.id:
            return biz.id or candidate

    biz = ensure_default_business(session, user)
    return biz.id or ""


CurrentUser = Depends(get_current_user)
