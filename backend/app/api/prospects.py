from fastapi import APIRouter, Depends, HTTPException, Request
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
    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        rows = session.exec(
            select(ProspectRecord)
            .where(ProspectRecord.business_id == business_id)
            .order_by(ProspectRecord.discovered_at.desc())
        ).all()
        return [prospect_to_frontend(r) for r in rows]


@router.get("/{prospect_id}")
def get_prospect(prospect_id: str, request: Request, user: AuthUser = Depends(get_current_user)):
    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        prospect = session.get(ProspectRecord, prospect_id)
        if not prospect or prospect.business_id != business_id:
            raise HTTPException(status_code=404, detail="Prospect not found")
        return prospect_to_frontend(prospect)


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
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        _maybe_sync_prospect(record)
        return prospect_to_frontend(record)


def _maybe_sync_prospect(record: ProspectRecord):
    if not sheets_mod.is_configured():
        return
    try:
        sheets_mod.sync_prospect({
            "id": record.id,
            "company_name": record.company_name,
            "website": record.website,
            "location": record.location,
            "industry": record.industry,
            "company_size": record.company_size,
            "fit_score": record.fit_score,
            "why_this_prospect": record.why_this_prospect,
            "recommended_approach": record.recommended_approach,
            "stage": record.stage,
            "discovered_at": record.discovered_at,
        })
    except Exception as exc:
        log.warning("Sheets prospect sync failed: %s", exc)
