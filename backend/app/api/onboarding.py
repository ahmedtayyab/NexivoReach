from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Optional
from app.providers.factory import get_ai_provider

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

class BusinessExtractRequest(BaseModel):
    description: str

class BusinessProfileResponse(BaseModel):
    name: str
    website: str
    description: str
    target_markets: List[str]
    primary_categories: List[str]
    extracted_by_ai: bool = True

@router.post("/extract", response_model=BusinessProfileResponse)
async def extract_business_profile(req: BusinessExtractRequest):
    provider = get_ai_provider()
    res = await provider.extract_business_profile(req.description)
    return BusinessProfileResponse(
        name=res.get("name", "Apex Fitness Equipment"),
        website=res.get("website", "https://apexfitnessequipment.example.com"),
        description=req.description,
        target_markets=res.get("target_markets", ["United Arab Emirates", "Saudi Arabia", "Qatar"]),
        primary_categories=res.get("primary_categories", ["Commercial Strength", "Free Weights", "Cardio Equipment"]),
        extracted_by_ai=True
    )
