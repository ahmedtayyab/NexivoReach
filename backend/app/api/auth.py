from datetime import datetime, timezone
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from app.config import settings, effective_app_url, effective_google_redirect_uri
from app.database.session import engine
from app.models.schemas import User
from app.api.deps import (
    SESSION_COOKIE,
    auth_required,
    get_current_user,
    google_configured,
    local_user,
    AuthUser,
)
from app.api.tokens import (
    create_oauth_state,
    create_session_token,
    decode_oauth_state,
    verify_oauth_state,
)
from app.integrations import gmail as gmail_mod

router = APIRouter(prefix="/api/auth", tags=["auth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def _user_payload(user) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "gmail": gmail_mod.status_payload(user),
    }


@router.get("/me")
def auth_me(request: Request):
    if not auth_required():
        u = local_user()
        return {"configured": False, "user": {**_user_payload(u), "gmail": {"connected": False, "email": "", "connectedAt": ""}}}
    try:
        user = get_current_user(request)
        with Session(engine) as session:
            row = session.get(User, user.id)
            if row:
                return {"configured": True, "user": _user_payload(row)}
        return {"configured": True, "user": _user_payload(user)}
    except HTTPException:
        return {"configured": True, "user": None}


@router.get("/google")
def google_login():
    if not google_configured():
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")
    state = create_oauth_state("oauth")
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": effective_google_redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    response = RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}")
    response.set_cookie(
        "nr_oauth_state",
        state,
        httponly=True,
        samesite="lax",
        secure=_secure_cookies(),
        max_age=600,
        path="/",
    )
    return response


@router.get("/gmail")
def gmail_connect(request: Request, user: AuthUser = Depends(get_current_user)):
    """Separate consent for Gmail send + read. Reuses the same OAuth redirect URI."""
    if not google_configured():
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    if not auth_required():
        raise HTTPException(status_code=400, detail="Connect Gmail after signing in with Google")
    state = create_oauth_state("gmail", user_id=user.id)
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": effective_google_redirect_uri(),
        "response_type": "code",
        "scope": f"openid email profile {gmail_mod.GMAIL_SCOPES}",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    response = RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}")
    response.set_cookie(
        "nr_oauth_state",
        state,
        httponly=True,
        samesite="lax",
        secure=_secure_cookies(),
        max_age=600,
        path="/",
    )
    return response


@router.get("/gmail/status")
def gmail_status(request: Request, user: AuthUser = Depends(get_current_user)):
    with Session(engine) as session:
        row = session.get(User, user.id)
        if not row:
            return {"connected": False, "email": "", "connectedAt": ""}
        return gmail_mod.status_payload(row)


@router.post("/gmail/disconnect")
def gmail_disconnect(request: Request, user: AuthUser = Depends(get_current_user)):
    with Session(engine) as session:
        row = session.get(User, user.id)
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        gmail_mod.clear_tokens(session, row)
        return {"ok": True, **gmail_mod.status_payload(row)}


@router.get("/google/callback")
def google_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    app_url = effective_app_url()
    if error:
        return RedirectResponse(f"{app_url}/?auth=error")
    cookie_state = request.cookies.get("nr_oauth_state", "")
    if not code or not state or state != cookie_state:
        return RedirectResponse(f"{app_url}/?auth=error")

    try:
        state_payload = decode_oauth_state(state)
        purpose = state_payload.get("typ") or "oauth"
    except Exception:
        return RedirectResponse(f"{app_url}/?auth=error")

    if purpose == "gmail":
        return _gmail_callback(code, state_payload, app_url)

    if not verify_oauth_state(state, "oauth"):
        return RedirectResponse(f"{app_url}/?auth=error")

    with httpx.Client(timeout=20.0) as client:
        token_res = client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": effective_google_redirect_uri(),
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
        )
        if token_res.status_code >= 400:
            return RedirectResponse(f"{app_url}/?auth=error")
        access_token = token_res.json().get("access_token")
        if not access_token:
            return RedirectResponse(f"{app_url}/?auth=error")
        info_res = client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if info_res.status_code >= 400:
            return RedirectResponse(f"{app_url}/?auth=error")
        info = info_res.json()

    google_id = info.get("sub")
    email = info.get("email")
    if not google_id or not email:
        return RedirectResponse(f"{app_url}/?auth=error")

    with Session(engine) as session:
        user = session.exec(select(User).where(User.google_id == google_id)).first()
        if not user:
            user = User(
                id=f"user-{uuid4().hex[:12]}",
                google_id=google_id,
                email=email,
                name=info.get("name") or email.split("@")[0],
                picture=info.get("picture") or "",
                created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
        else:
            user.email = email
            user.name = info.get("name") or user.name
            user.picture = info.get("picture") or user.picture
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id

    response = HTMLResponse(
        """<!DOCTYPE html><html><head><meta charset="utf-8"></head>"""
        """<body><script>sessionStorage.setItem('nr_post_login','1');window.location.replace('/#queue');</script></body></html>"""
    )
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(user_id),
        httponly=True,
        samesite="lax",
        secure=_secure_cookies(),
        max_age=60 * 60 * 24 * 14,
        path="/",
    )
    response.delete_cookie("nr_oauth_state", path="/")
    return response


def _gmail_callback(code: str, state_payload: dict, app_url: str):
    user_id = state_payload.get("uid") or ""
    if state_payload.get("typ") != "gmail" or not user_id:
        return RedirectResponse(f"{app_url}/?gmail=error#settings/integrations")

    with httpx.Client(timeout=20.0) as client:
        token_res = client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": effective_google_redirect_uri(),
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
        )
        if token_res.status_code >= 400:
            return RedirectResponse(f"{app_url}/?gmail=error#settings/integrations")
        token_data = token_res.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        if not access_token:
            return RedirectResponse(f"{app_url}/?gmail=error#settings/integrations")
        info_res = client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        gmail_email = ""
        if info_res.status_code < 400:
            gmail_email = info_res.json().get("email") or ""

    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            return RedirectResponse(f"{app_url}/?gmail=error#settings/integrations")
        # Refresh token only returned on first consent; keep existing if missing
        if not refresh_token and not (user.gmail_refresh_token or "").strip():
            return RedirectResponse(f"{app_url}/?gmail=error#settings/integrations")
        gmail_mod.store_tokens(
            session,
            user,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=int(token_data.get("expires_in") or 3600),
            email=gmail_email or user.email,
        )

    response = HTMLResponse(
        """<!DOCTYPE html><html><head><meta charset="utf-8"></head>"""
        """<body><script>window.location.replace('/?gmail=connected#settings/integrations');</script></body></html>"""
    )
    response.delete_cookie("nr_oauth_state", path="/")
    return response


@router.post("/logout")
def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


def _secure_cookies() -> bool:
    return effective_app_url().startswith("https://")
