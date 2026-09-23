"""User Google Sheets OAuth helpers — tokens on User, like Gmail."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import httpx
from sqlmodel import Session

from app.config import settings
from app.models.schemas import User

log = logging.getLogger(__name__)

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"
SHEETS_SCOPES = f"{SHEETS_SCOPE} {DRIVE_FILE_SCOPE}"
SHEETS_SCOPES_LIST = [SHEETS_SCOPE, DRIVE_FILE_SCOPE]
TOKEN_URL = "https://oauth2.googleapis.com/token"


def is_connected(user: User | None) -> bool:
    if user is None:
        return False
    if (getattr(user, "sheets_refresh_token", None) or "").strip():
        return True
    return bool((getattr(user, "sheets_access_token", None) or "").strip())


def status_payload(user: User | None) -> Dict[str, Any]:
    connected = is_connected(user)
    return {
        "connected": connected,
        "email": (getattr(user, "sheets_email", None) or "") if connected and user else "",
        "connectedAt": (getattr(user, "sheets_connected_at", None) or "") if connected and user else "",
    }


def store_tokens(
    session: Session,
    user: User,
    *,
    access_token: str,
    refresh_token: Optional[str],
    expires_in: int = 3600,
    email: str = "",
) -> User:
    now = datetime.now(timezone.utc)
    user.sheets_access_token = access_token
    if refresh_token:
        user.sheets_refresh_token = refresh_token
    user.sheets_token_expiry = (now + timedelta(seconds=max(60, expires_in - 60))).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    if email:
        user.sheets_email = email
    user.sheets_connected_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def clear_tokens(session: Session, user: User) -> User:
    user.sheets_access_token = None
    user.sheets_refresh_token = None
    user.sheets_token_expiry = None
    user.sheets_email = None
    user.sheets_connected_at = None
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _expiry_dt(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def get_valid_access_token(session: Session, user: User) -> str:
    """Sync token refresh (Sheets sync paths are synchronous)."""
    token = (getattr(user, "sheets_access_token", None) or "").strip()
    expiry = _expiry_dt(getattr(user, "sheets_token_expiry", None))
    now = datetime.now(timezone.utc)
    refresh = (getattr(user, "sheets_refresh_token", None) or "").strip()
    gmail_refresh = (getattr(user, "gmail_refresh_token", None) or "").strip()
    candidates: list[str] = []
    for rt in (refresh, gmail_refresh):
        if rt and rt not in candidates:
            candidates.append(rt)

    # Known-fresh access token — skip network.
    if token and expiry is not None and expiry > now + timedelta(minutes=1):
        return token

    # Prefer refresh when expiry is missing/expired so create/sync don't use a dead token.
    if candidates:
        last_detail = ""
        with httpx.Client(timeout=20.0) as client:
            for rt in candidates:
                res = client.post(
                    TOKEN_URL,
                    data={
                        "client_id": settings.GOOGLE_CLIENT_ID,
                        "client_secret": settings.GOOGLE_CLIENT_SECRET,
                        "refresh_token": rt,
                        "grant_type": "refresh_token",
                    },
                )
                if res.status_code >= 400:
                    last_detail = (res.text or "")[:200]
                    log.warning("Sheets token refresh failed: %s %s", res.status_code, last_detail)
                    continue
                data = res.json()
                access = data.get("access_token") or ""
                if not access:
                    last_detail = "empty access_token"
                    continue
                store_tokens(
                    session,
                    user,
                    access_token=access,
                    refresh_token=rt if rt != refresh else None,
                    expires_in=int(data.get("expires_in") or 3600),
                    email=getattr(user, "sheets_email", None) or "",
                )
                return access
        if token:
            # Refresh failed but we still have an access token — last resort.
            return token
        raise RuntimeError(
            "Sheets token refresh failed. Disconnect Google in Workspace → Connect and reconnect. "
            f"({last_detail})"
        )

    if token:
        return token
    raise RuntimeError(
        "Google Sheets is not connected. Workspace → Connect → Connect Google again."
    )