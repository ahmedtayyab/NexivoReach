from dataclasses import dataclass
import os
from fastapi import Depends, HTTPException, Request
from sqlmodel import Session
from app.config import settings
from app.database.session import engine
from app.models.schemas import User
from app.api.tokens import decode_session_token

SESSION_COOKIE = "nr_session"
LOCAL_USER_ID = "local"


@dataclass
class AuthUser:
    id: str
    email: str
    name: str
    picture: str
    google_id: str


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
    )


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
        )


CurrentUser = Depends(get_current_user)
