from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from typing import List, Optional
from sqlmodel import Session
from app.providers.factory import get_ai_provider
from app.database.session import engine
from app.models.schemas import Business, User
from app.api.serializers import business_to_frontend
from app.api.deps import AuthUser, get_current_user, resolve_business_id

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class BusinessExtractRequest(BaseModel):
    description: str


class BusinessProfilePayload(BaseModel):
    id: Optional[str] = None
    name: str
    website: str = ""
    description: str = ""
    targetMarkets: List[str] = []
    primaryCategories: List[str] = []
    extractedByAi: bool = False


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


@router.post("/extract")
async def extract_business_profile(req: BusinessExtractRequest, _user: AuthUser = Depends(get_current_user)):
    provider = get_ai_provider()
    res = await provider.extract_business_profile(req.description)
    return {
        "name": res.get("name", ""),
        "website": res.get("website", ""),
        "description": req.description,
        "targetMarkets": res.get("target_markets") or res.get("targetMarkets") or [],
        "primaryCategories": res.get("primary_categories") or res.get("primaryCategories") or [],
        "extractedByAi": bool(res.get("extracted_by_ai", res.get("extractedByAi", False))),
    }


@router.get("/profile")
def get_business_profile(request: Request, user: AuthUser = Depends(get_current_user)):
    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        biz = session.get(Business, business_id)
        return {"profile": business_to_frontend(biz)}


@router.post("/profile")
def save_business_profile(
    payload: BusinessProfilePayload,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        if payload.id and payload.id != business_id:
            # Allow explicit id only if owned by this user
            candidate = session.get(Business, payload.id)
            if candidate and candidate.user_id == user.id:
                business_id = payload.id
        biz = session.get(Business, business_id) or Business(
            id=business_id, user_id=user.id, name="", website="", description=""
        )
        biz.user_id = user.id
        biz.name = payload.name
        biz.website = payload.website
        biz.description = payload.description
        biz.target_markets = payload.targetMarkets
        biz.primary_categories = payload.primaryCategories
        biz.extracted_by_ai = payload.extractedByAi
        biz.updated_at = _now()
        session.add(biz)
        db_user = session.get(User, user.id)
        if db_user:
            db_user.active_business_id = biz.id
            session.add(db_user)
        session.commit()
        session.refresh(biz)
        return business_to_frontend(biz)
