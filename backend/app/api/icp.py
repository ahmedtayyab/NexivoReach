from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

router = APIRouter(prefix="/api/icp", tags=["icp"])

class ICPRequest(BaseModel):
    target_buyer_types: List[str]
    target_countries: List[str]
    company_size: str = "Medium"
    min_deal_size: Optional[str] = None
    sales_constraints: List[str] = []
    buying_signals: List[Dict[str, Any]] = []

@router.post("/save")
async def save_icp_profile(icp: ICPRequest):
    return {"status": "success", "icp": icp.dict()}
