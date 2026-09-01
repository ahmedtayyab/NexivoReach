from datetime import datetime, timedelta, timezone
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


def create_oauth_state() -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "typ": "oauth",
        "exp": int((now + timedelta(minutes=10)).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def verify_oauth_state(state: str) -> bool:
    try:
        payload = jwt.decode(state, settings.JWT_SECRET, algorithms=[ALGORITHM])
        return payload.get("typ") == "oauth"
    except Exception:
        return False
