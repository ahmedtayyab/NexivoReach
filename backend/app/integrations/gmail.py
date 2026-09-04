"""User Gmail API helpers — send + reply poll. Uses OAuth tokens on User, not Sheets SA."""

from __future__ import annotations

import base64
import logging
import re
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

import httpx
from sqlmodel import Session

from app.config import settings
from app.models.schemas import User

log = logging.getLogger(__name__)

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_SCOPES = f"{GMAIL_SEND_SCOPE} {GMAIL_READONLY_SCOPE}"
TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"


def is_connected(user: User) -> bool:
    return bool((getattr(user, "gmail_refresh_token", None) or "").strip())


def status_payload(user: User) -> Dict[str, Any]:
    connected = is_connected(user)
    return {
        "connected": connected,
        "email": (getattr(user, "gmail_email", None) or "") if connected else "",
        "connectedAt": (getattr(user, "gmail_connected_at", None) or "") if connected else "",
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
    user.gmail_access_token = access_token
    if refresh_token:
        user.gmail_refresh_token = refresh_token
    user.gmail_token_expiry = (now + timedelta(seconds=max(60, expires_in - 60))).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    if email:
        user.gmail_email = email
    user.gmail_connected_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def clear_tokens(session: Session, user: User) -> User:
    user.gmail_access_token = None
    user.gmail_refresh_token = None
    user.gmail_token_expiry = None
    user.gmail_email = None
    user.gmail_connected_at = None
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


async def get_valid_access_token(session: Session, user: User) -> str:
    token = (getattr(user, "gmail_access_token", None) or "").strip()
    expiry = _expiry_dt(getattr(user, "gmail_token_expiry", None))
    now = datetime.now(timezone.utc)
    if token and expiry and expiry > now + timedelta(minutes=1):
        return token
    refresh = (getattr(user, "gmail_refresh_token", None) or "").strip()
    if not refresh:
        raise RuntimeError("Gmail is not connected. Connect Gmail in Settings → Integrations.")
    async with httpx.AsyncClient(timeout=20.0) as client:
        res = await client.post(
            TOKEN_URL,
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            },
        )
        if res.status_code >= 400:
            raise RuntimeError(f"Gmail token refresh failed ({res.status_code})")
        data = res.json()
        access = data.get("access_token") or ""
        if not access:
            raise RuntimeError("Gmail token refresh returned no access token")
        store_tokens(
            session,
            user,
            access_token=access,
            refresh_token=None,
            expires_in=int(data.get("expires_in") or 3600),
            email=getattr(user, "gmail_email", None) or "",
        )
        return access


def _mime_message(*, to: str, subject: str, body: str, from_email: str = "") -> str:
    msg = MIMEText(body or "", "plain", "utf-8")
    msg["To"] = to
    msg["Subject"] = subject or "(no subject)"
    if from_email:
        msg["From"] = from_email
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    return raw


async def send_email(
    session: Session,
    user: User,
    *,
    to: str,
    subject: str,
    body: str,
) -> Dict[str, str]:
    if not to.strip():
        raise RuntimeError("No recipient email on this lead")
    access = await get_valid_access_token(session, user)
    raw = _mime_message(
        to=to.strip(),
        subject=subject,
        body=body,
        from_email=getattr(user, "gmail_email", None) or "",
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            f"{GMAIL_API}/messages/send",
            headers={"Authorization": f"Bearer {access}"},
            json={"raw": raw},
        )
        if res.status_code >= 400:
            raise RuntimeError(f"Gmail send failed ({res.status_code}): {res.text[:200]}")
        data = res.json()
        return {
            "messageId": data.get("id") or "",
            "threadId": data.get("threadId") or "",
        }


def _strip_html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text or "")
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:2000]


async def _get_message(client: httpx.AsyncClient, access: str, msg_id: str) -> Dict[str, Any]:
    res = await client.get(
        f"{GMAIL_API}/messages/{msg_id}",
        headers={"Authorization": f"Bearer {access}"},
        params={"format": "full"},
    )
    if res.status_code >= 400:
        return {}
    return res.json()


def _header(payload: Dict[str, Any], name: str) -> str:
    for h in (payload.get("payload") or {}).get("headers") or []:
        if (h.get("name") or "").lower() == name.lower():
            return h.get("value") or ""
    return ""


def _body_text(payload: Dict[str, Any]) -> str:
    root = payload.get("payload") or {}
    parts = [root] + list(root.get("parts") or [])
    # Flatten one more level for multipart/alternative
    extra = []
    for p in list(parts):
        extra.extend(p.get("parts") or [])
    parts.extend(extra)
    plain = ""
    html = ""
    for part in parts:
        mime = (part.get("mimeType") or "").lower()
        data = ((part.get("body") or {}).get("data")) or ""
        if not data:
            continue
        try:
            decoded = base64.urlsafe_b64decode(data.encode("ascii")).decode("utf-8", errors="ignore")
        except Exception:
            continue
        if mime == "text/plain" and not plain:
            plain = decoded
        elif mime == "text/html" and not html:
            html = decoded
    if plain:
        return re.sub(r"\s+", " ", plain).strip()[:2000]
    if html:
        return _strip_html(html)
    return (payload.get("snippet") or "")[:2000]


async def find_replies_for_leads(
    session: Session,
    user: User,
    leads: List[Dict[str, str]],
) -> List[Dict[str, Any]]:
    """
    leads: [{prospectId, email, threadId?}]
    Returns reply hits with summary text.
    """
    if not leads:
        return []
    access = await get_valid_access_token(session, user)
    hits: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for lead in leads:
            email = (lead.get("email") or "").strip()
            thread_id = (lead.get("threadId") or "").strip()
            prospect_id = lead.get("prospectId") or ""
            if not email and not thread_id:
                continue
            try:
                if thread_id:
                    tres = await client.get(
                        f"{GMAIL_API}/threads/{thread_id}",
                        headers={"Authorization": f"Bearer {access}"},
                        params={"format": "full"},
                    )
                    if tres.status_code >= 400:
                        continue
                    messages = (tres.json().get("messages") or [])
                    # Skip our outbound (first); look for later messages from prospect
                    for msg in messages[1:]:
                        payload = msg
                        frm = _header(payload, "From").lower()
                        if email and email.lower() not in frm:
                            # Still accept any non-self reply in thread
                            self_email = (getattr(user, "gmail_email", None) or "").lower()
                            if self_email and self_email in frm:
                                continue
                        body = _body_text(payload)
                        if not body:
                            continue
                        hits.append({
                            "prospectId": prospect_id,
                            "email": email,
                            "summary": body,
                            "messageId": msg.get("id") or "",
                            "threadId": thread_id,
                            "from": _header(payload, "From"),
                        })
                        break
                else:
                    q = f"from:{email} newer_than:30d"
                    sres = await client.get(
                        f"{GMAIL_API}/messages",
                        headers={"Authorization": f"Bearer {access}"},
                        params={"q": q, "maxResults": 3},
                    )
                    if sres.status_code >= 400:
                        continue
                    for item in (sres.json().get("messages") or [])[:1]:
                        msg = await _get_message(client, access, item.get("id") or "")
                        if not msg:
                            continue
                        body = _body_text(msg)
                        if not body:
                            continue
                        hits.append({
                            "prospectId": prospect_id,
                            "email": email,
                            "summary": body,
                            "messageId": msg.get("id") or "",
                            "threadId": msg.get("threadId") or "",
                            "from": _header(msg, "From"),
                        })
            except Exception as exc:
                log.warning("Gmail reply search failed for %s: %s", email, exc)
    return hits
