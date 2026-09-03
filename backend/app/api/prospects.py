from fastapi import APIRouter, Depends, HTTPException
from typing import List
from sqlmodel import Session, select
from app.database.session import engine
from app.models.schemas import ProspectRecord
from app.api.deps import AuthUser, get_current_user
from app.integrations import sheets as sheets_mod
import logging

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/prospects", tags=["prospects"])


@router.get("/", response_model=List[ProspectRecord])
def list_prospects():
    with Session(engine) as session:
        stmt = select(ProspectRecord).order_by(ProspectRecord.discovered_at.desc())
        results = session.exec(stmt).all()
        return results


@router.get("/{prospect_id}", response_model=ProspectRecord)
def get_prospect(prospect_id: str):
    with Session(engine) as session:
        prospect = session.get(ProspectRecord, prospect_id)
        if not prospect:
            raise HTTPException(status_code=404, detail="Prospect not found")
        return prospect


@router.post("/save", response_model=ProspectRecord)
def save_prospect(payload: ProspectRecord):
    with Session(engine) as session:
        if payload.id and session.get(ProspectRecord, payload.id):
            existing = session.get(ProspectRecord, payload.id)
            old_stage = existing.stage
            for k, v in payload.dict().items():
                setattr(existing, k, v)
            session.add(existing)
            session.commit()
            session.refresh(existing)
            _maybe_sync_prospect(existing, stage_changed=(existing.stage != old_stage))
            return existing

        session.add(payload)
        session.commit()
        session.refresh(payload)
        _maybe_sync_prospect(payload, stage_changed=True)
        return payload


def _maybe_sync_prospect(record: ProspectRecord, stage_changed: bool = False):
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
