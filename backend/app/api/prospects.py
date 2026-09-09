from fastapi import APIRouter, Depends, Request
from typing import Any, Dict
from uuid import uuid4
from sqlmodel import Session, select
from app.database.session import engine
from app.models.schemas import ProspectRecord
from app.api.deps import AuthUser, get_current_user, resolve_business_id
from app.api.serializers import prospect_from_frontend, prospect_to_frontend
from app.integrations import sheets as sheets_mod
import logging

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/prospects", tags=["prospects"])


@router.get("/")
def list_prospects(request: Request, user: AuthUser = Depends(get_current_user)):
    from app.tools.contact_finder import resolve_lead_email

    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        rows = session.exec(
            select(ProspectRecord)
            .where(ProspectRecord.business_id == business_id)
            .order_by(ProspectRecord.discovered_at.desc())
        ).all()
        # Persist empty To:/email from contacts so Outreach stops showing blank buyers
        dirty = False
        for row in rows:
            draft = dict(row.outreach_draft or {}) if row.outreach_draft else {}
            resolved = resolve_lead_email(
                email=row.email or "",
                contacts=row.contacts or [],
                to_email=(draft.get("toEmail") or ""),
            )
            if not resolved:
                continue
            changed = False
            if not (row.email or "").strip():
                row.email = resolved
                changed = True
            if draft and not (draft.get("toEmail") or "").strip():
                draft["toEmail"] = resolved
                row.outreach_draft = draft
                changed = True
            if changed:
                session.add(row)
                dirty = True
        if dirty:
            session.commit()
            for row in rows:
                session.refresh(row)
        return [prospect_to_frontend(r) for r in rows]


@router.delete("/clear")
def clear_prospects(request: Request, user: AuthUser = Depends(get_current_user)):
    """Delete all leads for the active company so Discover can start clean."""
    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        rows = session.exec(
            select(ProspectRecord).where(ProspectRecord.business_id == business_id)
        ).all()
        deleted = 0
        for row in rows:
            session.delete(row)
            deleted += 1
        session.commit()
        return {"ok": True, "deleted": deleted}


@router.delete("/{prospect_id}")
def delete_prospect(prospect_id: str, request: Request, user: AuthUser = Depends(get_current_user)):
    """Delete one lead from Discover / Outreach lists."""
    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        row = session.get(ProspectRecord, prospect_id)
        if not row or row.business_id != business_id:
            return {"ok": True, "deleted": 0}
        session.delete(row)
        session.commit()
        return {"ok": True, "deleted": 1}


@router.post("/save")
def save_prospect(payload: Dict[str, Any], request: Request, user: AuthUser = Depends(get_current_user)):
    data = prospect_from_frontend(payload)
    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        prospect_id = data.get("id") or f"prospect-{uuid4().hex[:8]}"

        existing = session.get(ProspectRecord, prospect_id)
        if existing and existing.business_id == business_id:
            existing.company_name = data["company_name"]
            existing.website = data["website"]
            existing.location = data["location"]
            existing.industry = data["industry"]
            existing.company_size = data["company_size"]
            existing.fit_score = data["fit_score"]
            existing.fit_breakdown = data["fit_breakdown"]
            existing.why_this_prospect = data["why_this_prospect"]
            existing.buying_signals = data["buying_signals"]
            existing.product_fit = data["product_fit"]
            existing.recommended_approach = data["recommended_approach"]
            existing.outreach_draft = data["outreach_draft"]
            existing.stage = data["stage"]
            existing.discovered_at = data["discovered_at"]
            existing.agent_timeline = data["agent_timeline"]
            existing.user_id = user.id
            existing.business_id = business_id
            existing.source = data.get("source") or existing.source
            existing.phone = data.get("phone") or existing.phone
            existing.why_now = data.get("why_now") or existing.why_now
            existing.email = data.get("email") if data.get("email") is not None else existing.email
            existing.contacts = data.get("contacts") if data.get("contacts") is not None else existing.contacts
            if "contact_again" in data:
                existing.contact_again = bool(data.get("contact_again"))
            existing.last_reply_at = data.get("last_reply_at") or existing.last_reply_at
            existing.reply_summary = data.get("reply_summary") or existing.reply_summary
            session.add(existing)
            session.commit()
            session.refresh(existing)
            _maybe_sync_prospect(existing)
            return prospect_to_frontend(existing)

        record = ProspectRecord(
            id=prospect_id,
            company_name=data["company_name"],
            website=data["website"],
            location=data["location"],
            industry=data["industry"],
            company_size=data["company_size"],
            fit_score=data["fit_score"],
            fit_breakdown=data["fit_breakdown"],
            why_this_prospect=data["why_this_prospect"],
            buying_signals=data["buying_signals"],
            product_fit=data["product_fit"],
            recommended_approach=data["recommended_approach"],
            outreach_draft=data["outreach_draft"],
            stage=data["stage"],
            discovered_at=data["discovered_at"],
            agent_timeline=data["agent_timeline"],
            user_id=user.id,
            business_id=business_id,
            source=data.get("source") or "",
            phone=data.get("phone") or "",
            why_now=data.get("why_now") or "",
            email=data.get("email") or "",
            contacts=data.get("contacts") or [],
            contact_again=bool(data.get("contact_again", True)),
            last_reply_at=data.get("last_reply_at") or "",
            reply_summary=data.get("reply_summary") or "",
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        _maybe_sync_prospect(record)
        return prospect_to_frontend(record)


def _maybe_sync_prospect(record: ProspectRecord):
    try:
        if not record.business_id:
            return
        from app.models.schemas import Business
        with Session(engine) as session:
            biz = session.get(Business, record.business_id)
            sheet_id = sheets_mod.business_spreadsheet_id(biz)
            if not sheet_id:
                return
            owner = sheets_mod.owner_user(session, biz)
            if not sheets_mod.is_configured(owner):
                return
            seller = sheets_mod.resolve_company_tab_name(biz, fallback="Company")
            sheets_mod.sync_leads(seller, [{
                "id": record.id,
                "company_name": record.company_name,
                "website": record.website,
                "location": record.location,
                "industry": record.industry,
                "fit_score": record.fit_score,
                "why_this_prospect": record.why_this_prospect,
                "why_now": record.why_now,
                "intent": (record.fit_breakdown or {}).get("intent") or "",
                "stage": record.stage,
                "discovered_at": record.discovered_at,
                "source": record.source,
                "phone": record.phone,
                "email": getattr(record, "email", None) or "",
                "contact_again": bool(getattr(record, "contact_again", True)),
                "reply_summary": getattr(record, "reply_summary", None) or "",
                "seller_name": seller,
            }], spreadsheet_id=sheet_id, session=session, user=owner)
    except Exception as exc:
        log.warning("Sheets prospect sync failed: %s", exc)
