from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Optional
from sqlmodel import Session
from app.providers.factory import get_ai_provider
from app.database.session import engine
from app.models.schemas import Business
from app.api.serializers import business_to_frontend
from app.api.deps import AuthUser, get_current_user

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
def get_business_profile(user: AuthUser = Depends(get_current_user)):
    with Session(engine) as session:
        biz = session.get(Business, user.id)
        payload = business_to_frontend(biz)
        return {"profile": payload}


@router.post("/profile")
def save_business_profile(payload: BusinessProfilePayload, user: AuthUser = Depends(get_current_user)):
    with Session(engine) as session:
        biz = session.get(Business, user.id) or Business(id=user.id, name="", website="", description="")
        biz.id = user.id
        biz.name = payload.name
        biz.website = payload.website
        biz.description = payload.description
        biz.target_markets = payload.targetMarkets
        biz.primary_categories = payload.primaryCategories
        biz.extracted_by_ai = payload.extractedByAi
        session.add(biz)
        session.commit()
        session.refresh(biz)
        return business_to_frontend(biz)
