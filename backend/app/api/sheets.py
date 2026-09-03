"""
/api/sheets  — Google Sheets integration endpoints.
"""

from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import AuthUser, get_current_user
from app.api.serializers import product_to_frontend, prospect_to_frontend
from app.database.session import engine
from app.integrations import sheets as sheets_mod
from app.models.schemas import Business, ICPConfig, ProductItem, ProspectRecord
from app.tools.web_search import _registrable_domain

router = APIRouter(prefix="/api/sheets", tags=["sheets"])


@router.get("/status")
def get_status(_user: AuthUser = Depends(get_current_user)) -> Dict[str, Any]:
    return sheets_mod.connection_status()


@router.get("/restore-options")
def restore_options(_user: AuthUser = Depends(get_current_user)):
    if not sheets_mod.is_configured():
        raise HTTPException(status_code=400, detail="Google Sheets not configured.")
    return {"companies": sheets_mod.list_restore_tabs()}


class RestoreRequest(BaseModel):
    company_name: str
    include_products: bool = True
    include_leads: bool = False
    replace_products: bool = True
    replace_leads: bool = False


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _guess_website(products: list[dict]) -> str:
    for p in products:
        for key in ("sourceUrl", "productUrl"):
            url = (p.get(key) or "").strip()
            if not url:
                continue
            domain = _registrable_domain(url)
            if domain:
                return f"https://{domain}"
    return ""


@router.post("/restore")
def restore_from_sheets(
    req: RestoreRequest,
    user: AuthUser = Depends(get_current_user),
):
    """Recreate a company (+ catalog, optionally leads) from Google Sheets tabs."""
    if not sheets_mod.is_configured():
        raise HTTPException(status_code=400, detail="Google Sheets not configured.")

    company_name = (req.company_name or "").strip()
    if not company_name or sheets_mod.is_placeholder_company_name(company_name):
        raise HTTPException(status_code=400, detail="Pick a real company tab to restore.")

    options = {c["companyName"]: c for c in sheets_mod.list_restore_tabs()}
    match = options.get(company_name)
    if not match:
        raise HTTPException(status_code=404, detail=f"No Sheets tabs found for {company_name}")

    products: list[dict] = []
    if req.include_products and match.get("productsTab"):
        products = sheets_mod.fetch_products_from_tab(match["productsTab"])

    leads: list[dict] = []
    if req.include_leads and match.get("leadsTab"):
        leads = sheets_mod.fetch_leads_from_tab(match["leadsTab"])

    website = _guess_website(products)

    with Session(engine) as session:
        from app.models.schemas import User

        # Ensure the Google/local user row exists so company ownership sticks.
        db_user = session.get(User, user.id)
        if not db_user:
            db_user = User(
                id=user.id,
                google_id=user.google_id or user.id,
                email=user.email,
                name=user.name,
                picture=user.picture or "",
                created_at=_now(),
            )
            session.add(db_user)
            session.flush()

        owned = session.exec(select(Business).where(Business.user_id == user.id)).all()
        named = next(
            (b for b in owned if (b.name or "").strip().lower() == company_name.lower()),
            None,
        )

        # Claim an orphan company with the same name (e.g. left behind after auth/db reset).
        if not named:
            orphans = session.exec(select(Business)).all()
            orphan = next(
                (
                    b for b in orphans
                    if (b.name or "").strip().lower() == company_name.lower()
                    and (not b.user_id or b.user_id != user.id)
                ),
                None,
            )
            if orphan:
                orphan.user_id = user.id
                named = orphan

        if named:
            biz = named
        else:
            # Always create a real company record — do not only rename a blank one.
            biz = Business(
                id=f"biz-{uuid4().hex[:12]}",
                user_id=user.id,
                name=company_name,
                website=website,
                description="",
                updated_at=_now(),
            )
            session.add(biz)
            session.flush()

        business_id = biz.id or ""
        biz.user_id = user.id
        biz.name = company_name
        if website:
            biz.website = website
        elif not (biz.website or "").strip():
            biz.website = website
        biz.updated_at = _now()
        session.add(biz)

        icp = session.get(ICPConfig, business_id) or session.exec(
            select(ICPConfig).where(ICPConfig.business_id == business_id)
        ).first()
        if not icp:
            session.add(ICPConfig(id=business_id, business_id=business_id))
        else:
            icp.business_id = business_id
            session.add(icp)

        products_saved = 0
        if req.include_products:
            if req.replace_products:
                for row in session.exec(
                    select(ProductItem).where(ProductItem.business_id == business_id)
                ).all():
                    session.delete(row)
            for index, raw in enumerate(products):
                item = ProductItem(
                    id=raw.get("id") or f"prod-restored-{uuid4().hex[:8]}",
                    name=raw.get("name") or f"Product {index + 1}",
                    category=raw.get("category") or "Uncategorized",
                    description=raw.get("description") or "",
                    price=raw.get("price"),
                    moq=raw.get("moq"),
                    product_url=raw.get("productUrl"),
                    image_url=raw.get("imageUrl"),
                    source_url=raw.get("sourceUrl"),
                    in_stock=raw.get("inStock"),
                    user_id=user.id,
                    business_id=business_id,
                )
                session.add(item)
                products_saved += 1

        leads_saved = 0
        if req.include_leads:
            if req.replace_leads:
                for row in session.exec(
                    select(ProspectRecord).where(ProspectRecord.business_id == business_id)
                ).all():
                    session.delete(row)
            known = set()
            for raw in leads:
                site = (raw.get("website") or "").strip()
                name = (raw.get("companyName") or "").strip()
                key = site.lower() or name.lower()
                if not key or key in known:
                    continue
                known.add(key)
                pr = ProspectRecord(
                    id=f"prospect-{uuid4().hex[:10]}",
                    company_name=name,
                    website=site,
                    location=raw.get("location") or "",
                    industry=raw.get("industry") or "",
                    company_size="",
                    fit_score=int(raw.get("fitScore") or 0),
                    fit_breakdown={
                        "intent": raw.get("intent") or "",
                        "whyNow": raw.get("whyNow") or "",
                    },
                    why_this_prospect=raw.get("whyThisProspect") or "",
                    why_now=raw.get("whyNow") or "",
                    buying_signals=[],
                    product_fit=[],
                    recommended_approach="",
                    outreach_draft=None,
                    stage=raw.get("stage") or "To contact",
                    discovered_at=raw.get("discoveredAt") or _now(),
                    agent_timeline=[],
                    user_id=user.id,
                    business_id=business_id,
                    source=raw.get("source") or "web",
                    phone=raw.get("phone") or "",
                )
                session.add(pr)
                leads_saved += 1

        db_user.active_business_id = business_id
        session.add(db_user)
        session.commit()
        session.refresh(biz)

        product_rows = session.exec(
            select(ProductItem).where(ProductItem.business_id == business_id)
        ).all()
        prospect_rows = session.exec(
            select(ProspectRecord).where(ProspectRecord.business_id == business_id)
        ).all()

        return {
            "ok": True,
            "company": {
                "id": biz.id,
                "name": biz.name,
                "website": biz.website,
                "description": biz.description,
                "targetMarkets": biz.target_markets or [],
                "primaryCategories": biz.primary_categories or [],
            },
            "productsRestored": products_saved,
            "leadsRestored": leads_saved,
            "products": [product_to_frontend(p) for p in product_rows],
            "prospects": [prospect_to_frontend(p) for p in prospect_rows],
            "activeBusinessId": business_id,
        }
