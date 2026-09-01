from datetime import datetime, timezone
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException, Request
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
)
from app.api.tokens import create_oauth_state, create_session_token, verify_oauth_state

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
    }


@router.get("/me")
def auth_me(request: Request):
    if not auth_required():
        return {"configured": False, "user": _user_payload(local_user())}
    try:
        user = get_current_user(request)
        return {"configured": True, "user": _user_payload(user)}
    except HTTPException:
        return {"configured": True, "user": None}


@router.get("/google")
def google_login():
    if not google_configured():
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")
    state = create_oauth_state()
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


@router.get("/google/callback")
def google_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    app_url = effective_app_url()
    if error:
        return RedirectResponse(f"{app_url}/?auth=error")
    cookie_state = request.cookies.get("nr_oauth_state", "")
    if not code or not state or state != cookie_state or not verify_oauth_state(state):
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
        """<body><script>window.location.replace("/#queue");</script></body></html>"""
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


@router.post("/logout")
def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


def _secure_cookies() -> bool:
    return effective_app_url().startswith("https://")
