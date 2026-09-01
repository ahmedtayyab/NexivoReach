from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from sqlmodel import Session
from app.database.session import engine
from app.models.schemas import ICPConfig
from app.api.serializers import icp_to_frontend
from app.api.deps import AuthUser, get_current_user

router = APIRouter(prefix="/api/icp", tags=["icp"])


class ICPRequest(BaseModel):
    targetBuyerTypes: List[str] = []
    targetCountries: List[str] = []
    companySize: str = "Medium"
    minDealSize: Optional[str] = None
    shippingMarkets: List[str] = []
    salesConstraints: List[str] = []
    buyingSignals: List[Dict[str, Any]] = []


@router.get("/")
def get_icp_profile(user: AuthUser = Depends(get_current_user)):
    with Session(engine) as session:
        icp = session.get(ICPConfig, user.id)
        return {"icp": icp_to_frontend(icp)}


@router.post("/save")
def save_icp_profile(payload: ICPRequest, user: AuthUser = Depends(get_current_user)):
    with Session(engine) as session:
        icp = session.get(ICPConfig, user.id) or ICPConfig(id=user.id)
        icp.id = user.id
        icp.target_buyer_types = payload.targetBuyerTypes
        icp.target_countries = payload.targetCountries
        icp.company_size = payload.companySize
        icp.min_deal_size = payload.minDealSize
        icp.shipping_markets = payload.shippingMarkets
        icp.sales_constraints = payload.salesConstraints
        icp.buying_signals = payload.buyingSignals
        session.add(icp)
        session.commit()
        session.refresh(icp)
        return {"status": "success", "icp": icp_to_frontend(icp)}
