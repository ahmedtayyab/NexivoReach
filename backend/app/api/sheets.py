"""
/api/sheets  — Google Sheets integration endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List

from app.api.deps import AuthUser, get_current_user
from app.integrations import sheets as sheets_mod

router = APIRouter(prefix="/api/sheets", tags=["sheets"])


# ── Status ───────────────────────────────────────────────────────────────────

@router.get("/status")
def get_status(_user: AuthUser = Depends(get_current_user)) -> Dict[str, Any]:
    return sheets_mod.connection_status()


# ── Manual sync endpoints ────────────────────────────────────────────────────

class ProductSyncRequest(BaseModel):
    company_name: str
    products: List[Dict[str, Any]]


class ProspectSyncRequest(BaseModel):
    prospect: Dict[str, Any]


@router.post("/sync-products")
def sync_products(req: ProductSyncRequest, _user: AuthUser = Depends(get_current_user)):
    if not sheets_mod.is_configured():
        raise HTTPException(status_code=400, detail="Google Sheets not configured. Add credentials in Settings → Integrations.")
    return sheets_mod.sync_products(req.company_name, req.products)


@router.post("/sync-prospect")
def sync_prospect(req: ProspectSyncRequest, _user: AuthUser = Depends(get_current_user)):
    if not sheets_mod.is_configured():
        raise HTTPException(status_code=400, detail="Google Sheets not configured.")
    return sheets_mod.sync_prospect(req.prospect)
