from fastapi import APIRouter, HTTPException
from typing import List
from sqlmodel import Session, select
from app.database.session import engine
from app.models.schemas import ProspectRecord

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
            # update
            existing = session.get(ProspectRecord, payload.id)
            for k, v in payload.dict().items():
                setattr(existing, k, v)
            session.add(existing)
            session.commit()
            session.refresh(existing)
            return existing

        session.add(payload)
        session.commit()
        session.refresh(payload)
        return payload
