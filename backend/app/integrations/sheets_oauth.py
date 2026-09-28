"""User Google Sheets OAuth helpers — tokens on User, like Gmail."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Set

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
TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


def _scopes_include_sheets(scope_blob: str | Set[str] | None) -> bool:
    if isinstance(scope_blob, set):
        granted = scope_blob
    else:
        granted = {s for s in str(scope_blob or "").split() if s}
    return SHEETS_SCOPE in granted


def access_token_scopes(access_token: str) -> Set[str]:
    token = (access_token or "").strip()
    if not token:
        return set()
    try:
        with httpx.Client(timeout=8.0) as client:
            res = client.get(TOKENINFO_URL, params={"access_token": token})
            if res.status_code >= 400:
                return set()
            scope = (res.json() or {}).get("scope") or ""
            return {s for s in scope.split() if s}
    except Exception as exc:
        log.warning("sheets tokeninfo failed: %r", exc)
        return set()


def token_has_sheets_scopes(access_token: str, scope_hint: str = "") -> bool:
    """True when tokeninfo or an OAuth scope hint includes spreadsheets."""
    if _scopes_include_sheets(scope_hint):
        return True
    return _scopes_include_sheets(access_token_scopes(access_token))


# Back-compat alias used by auth callbacks
_token_has_sheets_scopes = token_has_sheets_scopes


def is_connected(user: User | None) -> bool:
    if user is None:
        return False
    if (getattr(user, "sheets_refresh_token", None) or "").strip():
        return True
    if (getattr(user, "sheets_access_token", None) or "").strip():
        return True
    return False


def sanitize_sheets_tokens(session: Session, user: User) -> User:
    """
    Drop Sheets tokens that cannot actually call Sheets (e.g. Gmail-only access
    accidentally stored on sheets_* fields). Returns the refreshed user row.
    """
    access = (getattr(user, "sheets_access_token", None) or "").strip()
    refresh = (getattr(user, "sheets_refresh_token", None) or "").strip()
    if not access and not refresh:
        return user

    if access and token_has_sheets_scopes(access):
        return user

    # Access is missing or Gmail-only — try refresh candidates before giving up.
    gmail_refresh = (getattr(user, "gmail_refresh_token", None) or "").strip()
    candidates = [rt for rt in (refresh, gmail_refresh) if rt]
    if candidates:
        try:
            get_valid_access_token(session, user)
            session.refresh(user)
            access2 = (getattr(user, "sheets_access_token", None) or "").strip()
            if access2 and token_has_sheets_scopes(access2):
                return user
        except Exception as exc:
            log.info("sheets sanitize refresh failed: %r", exc)

    # Still unusable — clear so UI shows Connect Sheets again.
    log.warning("Clearing unusable Sheets tokens for user %s", getattr(user, "id", "?"))
    return clear_tokens(session, user)


def ensure_sheets_tokens_from_gmail(session: Session, user: User) -> User:
    """
    If Sheets looks disconnected but Gmail's refresh/access already has Sheets scopes
    (typical after Workspace → Connect Google), copy those tokens onto the Sheets fields.
    """
    user = sanitize_sheets_tokens(session, user) if is_connected(user) else user
    if is_connected(user):
        access = (getattr(user, "sheets_access_token", None) or "").strip()
        if access and token_has_sheets_scopes(access):
            return user
        if (getattr(user, "sheets_refresh_token", None) or "").strip():
            return user

    gmail_refresh = (getattr(user, "gmail_refresh_token", None) or "").strip()
    gmail_access = (getattr(user, "gmail_access_token", None) or "").strip()
    if not gmail_refresh and not gmail_access:
        return user

    email = (
        getattr(user, "sheets_email", None)
        or getattr(user, "gmail_email", None)
        or user.email
        or ""
    )

    if gmail_access and token_has_sheets_scopes(gmail_access):
        return store_tokens(
            session,
            user,
            access_token=gmail_access,
            refresh_token=gmail_refresh or None,
            expires_in=3600,
            email=email,
        )

    if not gmail_refresh:
        return user

    try:
        with httpx.Client(timeout=20.0) as client:
            res = client.post(
                TOKEN_URL,
                data={
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "refresh_token": gmail_refresh,
                    "grant_type": "refresh_token",
                },
            )
            if res.status_code >= 400:
                log.warning(
                    "sheets backfill refresh failed: %s %s",
                    res.status_code,
                    (res.text or "")[:200],
                )
                return user
            data = res.json() or {}
            cand = (data.get("access_token") or "").strip()
            scope_hint = data.get("scope") or ""
            if not cand:
                return user
            if not token_has_sheets_scopes(cand, scope_hint):
                log.info("gmail refresh lacks Sheets scopes — user must Connect Sheets")
                return user
            return store_tokens(
                session,
                user,
                access_token=cand,
                refresh_token=gmail_refresh,
                expires_in=int(data.get("expires_in") or 3600),
                email=email,
            )
    except Exception as exc:
        log.warning("sheets backfill from gmail failed: %r", exc)
        return user


def status_payload(user: User | None) -> Dict[str, Any]:
    connected = is_connected(user)
    # Treat Gmail-only poison access as disconnected for UI.
    if connected and user:
        access = (getattr(user, "sheets_access_token", None) or "").strip()
        refresh = (getattr(user, "sheets_refresh_token", None) or "").strip()
        if access and not token_has_sheets_scopes(access) and not refresh:
            connected = False
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
                data = res.json() or {}
                access = (data.get("access_token") or "").strip()
                if not access:
                    last_detail = "empty access_token"
                    continue
                scope_hint = data.get("scope") or ""
                # Never store a Gmail-only token onto Sheets fields.
                if not token_has_sheets_scopes(access, scope_hint):
                    last_detail = "refresh token missing spreadsheets scope"
                    log.warning("Skipping Sheets refresh candidate without Sheets scopes")
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
            return token
        raise RuntimeError(
            "Sheets token refresh failed. Connect Google → Connect Sheets and allow access. "
            f"({last_detail})"
        )

    if token:
        return token
    raise RuntimeError(
        "Google Sheets is not connected. Workspace → Connect → Connect Sheets."
    )
