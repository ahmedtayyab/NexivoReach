"""
/api/sheets  — Google Sheets integration endpoints.

Users connect Google Sheets via OAuth (their Drive). Each company links its own
spreadsheet ID — never shared across users/companies.
"""

from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import AuthUser, get_current_user, resolve_business_id
from app.api.serializers import product_to_frontend, prospect_to_frontend
from app.database.session import engine
from app.integrations import sheets as sheets_mod
from app.integrations import sheets_oauth as sheets_oauth_mod
from app.models.schemas import Business, ICPConfig, ProductItem, ProspectRecord, User
from app.tools.web_search import _registrable_domain
import logging

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sheets", tags=["sheets"])


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _active_business(session: Session, request: Request, user: AuthUser) -> Business:
    business_id = resolve_business_id(request, user, session)
    if not business_id:
        raise HTTPException(status_code=400, detail="Select or create a company first.")
    biz = session.get(Business, business_id)
    if not biz or biz.user_id != user.id:
        raise HTTPException(status_code=404, detail="Company not found.")
    return biz


def _db_user(session: Session, user: AuthUser) -> User:
    row = session.get(User, user.id)
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return row


def _require_sheets_oauth(db_user: User) -> None:
    if sheets_oauth_mod.is_connected(db_user):
        return
    if sheets_mod.oauth_available():
        raise HTTPException(
            status_code=400,
            detail="Connect Google Sheets first (Settings → Integrations).",
        )
    if not sheets_mod.is_configured(db_user):
        raise HTTPException(
            status_code=400,
            detail="Google Sheets is not available. Connect Google Sheets in Settings.",
        )


@router.get("/status")
def get_status(request: Request, user: AuthUser = Depends(get_current_user)) -> Dict[str, Any]:
    with Session(engine) as session:
        db_user = session.get(User, user.id)
        try:
            biz = _active_business(session, request, user)
            sid = sheets_mod.business_spreadsheet_id(biz)
            title = (biz.sheets_spreadsheet_title or "").strip()
            company_name = biz.name or ""
            company_id = biz.id
        except HTTPException:
            status = sheets_mod.connection_status("", session=session, user=db_user)
            status["companyName"] = ""
            return status
        status = sheets_mod.connection_status(sid, session=session, user=db_user)
        if status.get("connected") and title and not status.get("spreadsheet_title"):
            status["spreadsheet_title"] = title
        status["companyName"] = company_name
        status["companyId"] = company_id
        return status


class ConnectRequest(BaseModel):
    spreadsheet: str  # ID or full docs.google.com URL


@router.post("/connect")
def connect_spreadsheet(
    req: ConnectRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    with Session(engine) as session:
        db_user = _db_user(session, user)
        _require_sheets_oauth(db_user)
        verified = sheets_mod.verify_spreadsheet_access(
            req.spreadsheet, session=session, user=db_user
        )
        if not verified.get("ok"):
            raise HTTPException(status_code=400, detail=verified.get("error") or "Cannot access spreadsheet")

        biz = _active_business(session, request, user)
        biz.sheets_spreadsheet_id = verified["spreadsheetId"]
        biz.sheets_spreadsheet_title = verified.get("spreadsheet_title") or ""
        biz.updated_at = _now()
        session.add(biz)
        session.commit()
        return {
            "ok": True,
            "connected": True,
            "spreadsheetId": biz.sheets_spreadsheet_id,
            "spreadsheet_title": biz.sheets_spreadsheet_title,
            "url": verified.get("url") or "",
            "companyId": biz.id,
            "companyName": biz.name,
        }


@router.post("/create")
def create_spreadsheet(request: Request, user: AuthUser = Depends(get_current_user)):
    """Create a spreadsheet in the user's Google Drive for the active company."""
    with Session(engine) as session:
        db_user = _db_user(session, user)
        _require_sheets_oauth(db_user)
        biz = _active_business(session, request, user)
        title = sheets_mod.resolve_company_tab_name(biz, fallback=biz.name or "Company")
        created = sheets_mod.create_business_spreadsheet(
            title,
            session=session,
            user=db_user,
            share_with_email=user.email or "",
        )
        if not created.get("ok"):
            raise HTTPException(status_code=400, detail=created.get("error") or "Could not create spreadsheet")
        biz.sheets_spreadsheet_id = created["spreadsheetId"]
        biz.sheets_spreadsheet_title = created.get("spreadsheet_title") or ""
        biz.updated_at = _now()
        session.add(biz)
        session.commit()
        return {
            "ok": True,
            "connected": True,
            "spreadsheetId": biz.sheets_spreadsheet_id,
            "spreadsheet_title": biz.sheets_spreadsheet_title,
            "url": created.get("url") or "",
            "companyId": biz.id,
            "companyName": biz.name,
        }


@router.post("/disconnect")
def disconnect_spreadsheet(request: Request, user: AuthUser = Depends(get_current_user)):
    """Unlink spreadsheet from this company (does not delete the Google file)."""
    with Session(engine) as session:
        biz = _active_business(session, request, user)
        biz.sheets_spreadsheet_id = None
        biz.sheets_spreadsheet_title = None
        biz.updated_at = _now()
        session.add(biz)
        session.commit()
        return {"ok": True, "connected": False, "companyId": biz.id}


@router.post("/sync-leads")
def sync_leads_now(request: Request, user: AuthUser = Depends(get_current_user)):
    """Push all company leads to Sheets and re-apply status row colors."""
    with Session(engine) as session:
        db_user = _db_user(session, user)
        _require_sheets_oauth(db_user)
        biz = _active_business(session, request, user)
        sheet_id = sheets_mod.business_spreadsheet_id(biz)
        if not sheet_id:
            raise HTTPException(
                status_code=400,
                detail="Create or link a spreadsheet for this company first.",
            )
        seller = sheets_mod.resolve_company_tab_name(biz, fallback="Company")
        rows = session.exec(
            select(ProspectRecord).where(ProspectRecord.business_id == biz.id)
        ).all()
        payload = []
        dirty = False
        for record in rows:
            stage = (record.stage or "To contact").strip()
            draft = record.outreach_draft or {}
            draft_status = (draft.get("status") or "").strip() if isinstance(draft, dict) else ""
            if draft_status == "Sent" and stage in ("To contact", "Qualified", "New", "Researched", ""):
                stage = "Contacted"
                record.stage = stage
                session.add(record)
                dirty = True
            elif draft_status == "Replied" and stage not in ("Re-contact", "Won", "Meeting", "Denied", "Avoid"):
                stage = "Re-contact"
                record.stage = stage
                session.add(record)
                dirty = True
            payload.append({
                "id": record.id,
                "company_name": record.company_name,
                "website": record.website,
                "location": record.location,
                "industry": record.industry,
                "fit_score": record.fit_score,
                "why_this_prospect": record.why_this_prospect,
                "why_now": getattr(record, "why_now", None) or "",
                "intent": (record.fit_breakdown or {}).get("intent") or "",
                "stage": stage,
                "discovered_at": record.discovered_at,
                "source": record.source,
                "phone": record.phone,
                "email": getattr(record, "email", None) or "",
                "contact_again": bool(getattr(record, "contact_again", True)),
                "reply_summary": getattr(record, "reply_summary", None) or "",
                "seller_name": seller,
            })
        if dirty:
            session.commit()
        if not payload:
            return {"ok": True, "written": 0, "message": "No leads to sync"}
        try:
            result = sheets_mod.sync_leads(
                seller, payload, spreadsheet_id=sheet_id, session=session, user=db_user
            )
        except Exception as exc:
            log.warning("Manual Sheets lead sync failed: %s", exc)
            raise HTTPException(status_code=400, detail=f"Sheets sync failed: {exc}") from exc
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        return {
            "ok": True,
            "written": result.get("written") or 0,
            "tab": result.get("tab") or "",
            "url": result.get("url") or "",
        }


@router.get("/restore-options")
def restore_options(request: Request, user: AuthUser = Depends(get_current_user)):
    with Session(engine) as session:
        db_user = _db_user(session, user)
        _require_sheets_oauth(db_user)
        biz = _active_business(session, request, user)
        sheet_id = sheets_mod.business_spreadsheet_id(biz)
        if not sheet_id:
            raise HTTPException(status_code=400, detail="Create or link a spreadsheet for this company first.")
        return {
            "companies": sheets_mod.list_restore_tabs(
                spreadsheet_id=sheet_id, session=session, user=db_user
            )
        }


class RestoreRequest(BaseModel):
    company_name: str
    include_products: bool = True
    include_leads: bool = False
    replace_products: bool = True
    replace_leads: bool = False


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
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """Recreate catalog/leads from this company's linked Google Sheets tabs."""
    company_name = (req.company_name or "").strip()
    if not company_name or sheets_mod.is_placeholder_company_name(company_name):
        raise HTTPException(status_code=400, detail="Pick a real company tab to restore.")

    with Session(engine) as session:
        db_user = _db_user(session, user)
        _require_sheets_oauth(db_user)
        biz = _active_business(session, request, user)
        sheet_id = sheets_mod.business_spreadsheet_id(biz)
        if not sheet_id:
            raise HTTPException(status_code=400, detail="Create or link a spreadsheet for this company first.")

        options = {
            c["companyName"]: c
            for c in sheets_mod.list_restore_tabs(
                spreadsheet_id=sheet_id, session=session, user=db_user
            )
        }
        match = options.get(company_name)
        if not match:
            raise HTTPException(status_code=404, detail=f"No Sheets tabs found for {company_name}")

        products: list[dict] = []
        if req.include_products and match.get("productsTab"):
            products = sheets_mod.fetch_products_from_tab(
                match["productsTab"], spreadsheet_id=sheet_id, session=session, user=db_user
            )

        leads: list[dict] = []
        if req.include_leads and match.get("leadsTab"):
            leads = sheets_mod.fetch_leads_from_tab(
                match["leadsTab"], spreadsheet_id=sheet_id, session=session, user=db_user
            )

        website = _guess_website(products)
        business_id = biz.id or ""
        if company_name and (
            sheets_mod.is_placeholder_company_name(biz.name) or not (biz.name or "").strip()
        ):
            biz.name = company_name
        if website:
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
