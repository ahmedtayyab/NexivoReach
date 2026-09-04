from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from app.config import settings

ALGORITHM = "HS256"


def create_session_token(user_id: str, hours: int = 24 * 14) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=hours)).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def decode_session_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])


def create_oauth_state(purpose: str = "oauth", user_id: Optional[str] = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "typ": purpose,
        "exp": int((now + timedelta(minutes=10)).timestamp()),
    }
    if user_id:
        payload["uid"] = user_id
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def verify_oauth_state(state: str, purpose: str = "oauth") -> bool:
    try:
        payload = jwt.decode(state, settings.JWT_SECRET, algorithms=[ALGORITHM])
        return payload.get("typ") == purpose
    except Exception:
        return False


def decode_oauth_state(state: str) -> dict:
    return jwt.decode(state, settings.JWT_SECRET, algorithms=[ALGORITHM])
