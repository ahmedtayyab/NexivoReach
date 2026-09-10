"""Multi-company CRUD + activate."""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import (
    BUSINESS_COOKIE,
    AuthUser,
    ensure_default_business,
    get_current_user,
    resolve_business_id,
)
from app.api.serializers import business_to_frontend
from app.database.session import engine
from app.integrations import sheets as sheets_mod
from app.models.schemas import Business, ICPConfig, User
import logging

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/companies", tags=["companies"])


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _set_active_cookie(response: Response, business_id: str) -> None:
    response.set_cookie(
        key=BUSINESS_COOKIE,
        value=business_id,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 90,
        path="/",
    )


class CompanyCreate(BaseModel):
    name: str = "New company"
    website: str = ""
    description: str = ""


@router.get("/")
def list_companies(request: Request, user: AuthUser = Depends(get_current_user)):
    with Session(engine) as session:
        ensure_default_business(session, user)
        rows = session.exec(
            select(Business).where(Business.user_id == user.id).order_by(Business.updated_at.desc())
        ).all()
        active_id = resolve_business_id(request, user, session)
        return {
            "companies": [business_to_frontend(b) for b in rows],
            "activeBusinessId": active_id,
        }


@router.post("/")
def create_company(
    payload: CompanyCreate,
    response: Response,
    user: AuthUser = Depends(get_current_user),
):
    with Session(engine) as session:
        biz = Business(
            id=f"biz-{uuid4().hex[:12]}",
            user_id=user.id,
            name=(payload.name or "New company").strip() or "New company",
            website=(payload.website or "").strip(),
            description=(payload.description or "").strip(),
            updated_at=_now(),
        )
        # Reuse the same Google workbook as another company owned by this user,
        # then create identity tabs: "<Name> - Products" / "<Name> - Leads".
        siblings = session.exec(select(Business).where(Business.user_id == user.id)).all()
        for sibling in siblings:
            sid = (sibling.sheets_spreadsheet_id or "").strip()
            if sid:
                biz.sheets_spreadsheet_id = sid
                biz.sheets_spreadsheet_title = sibling.sheets_spreadsheet_title
                break

        session.add(biz)
        session.add(ICPConfig(id=biz.id, business_id=biz.id))
        db_user = session.get(User, user.id)
        if db_user:
            db_user.active_business_id = biz.id
            session.add(db_user)
        session.commit()
        session.refresh(biz)

        # Skip tabs for placeholder names ("New company") — profile save creates them
        # once the company has a real identity.
        if (
            biz.sheets_spreadsheet_id
            and db_user
            and not sheets_mod.is_placeholder_company_name(biz.name)
        ):
            tab_label = sheets_mod.resolve_company_tab_name(biz, fallback=biz.name or "Company")
            ensured = sheets_mod.ensure_company_tabs(
                tab_label,
                spreadsheet_id=biz.sheets_spreadsheet_id,
                session=session,
                user=db_user,
            )
            if not ensured.get("ok"):
                log.warning(
                    "New company %s linked to sheet but tabs not created: %s",
                    biz.id,
                    ensured.get("error"),
                )

        _set_active_cookie(response, biz.id or "")
        return {"company": business_to_frontend(biz), "activeBusinessId": biz.id}


@router.post("/{company_id}/activate")
def activate_company(
    company_id: str,
    response: Response,
    user: AuthUser = Depends(get_current_user),
):
    with Session(engine) as session:
        biz = session.get(Business, company_id)
        if not biz or biz.user_id != user.id:
            raise HTTPException(status_code=404, detail="Company not found")
        # Backfill sheet link from a sibling so older companies join the shared workbook.
        if not (biz.sheets_spreadsheet_id or "").strip():
            siblings = session.exec(select(Business).where(Business.user_id == user.id)).all()
            for sibling in siblings:
                if sibling.id == biz.id:
                    continue
                sid = (sibling.sheets_spreadsheet_id or "").strip()
                if sid:
                    biz.sheets_spreadsheet_id = sid
                    biz.sheets_spreadsheet_title = sibling.sheets_spreadsheet_title
                    biz.updated_at = _now()
                    session.add(biz)
                    break
        db_user = session.get(User, user.id)
        if db_user:
            db_user.active_business_id = biz.id
            session.add(db_user)
        session.commit()
        session.refresh(biz)

        if (
            biz.sheets_spreadsheet_id
            and db_user
            and not sheets_mod.is_placeholder_company_name(biz.name)
        ):
            tab_label = sheets_mod.resolve_company_tab_name(biz, fallback=biz.name or "Company")
            sheets_mod.ensure_company_tabs(
                tab_label,
                spreadsheet_id=biz.sheets_spreadsheet_id,
                session=session,
                user=db_user,
            )

        _set_active_cookie(response, biz.id or "")
        return {"activeBusinessId": biz.id, "company": business_to_frontend(biz)}


@router.delete("/{company_id}")
def delete_company(company_id: str, user: AuthUser = Depends(get_current_user)):
    with Session(engine) as session:
        rows = session.exec(select(Business).where(Business.user_id == user.id)).all()
        if len(rows) <= 1:
            raise HTTPException(status_code=400, detail="Keep at least one company")
        biz = session.get(Business, company_id)
        if not biz or biz.user_id != user.id:
            raise HTTPException(status_code=404, detail="Company not found")
        remaining = [b for b in rows if b.id != company_id]
        session.delete(biz)
        icp = session.get(ICPConfig, company_id)
        if icp:
            session.delete(icp)
        next_id = remaining[0].id if remaining else None
        db_user = session.get(User, user.id)
        if db_user and db_user.active_business_id == company_id:
            db_user.active_business_id = next_id
            session.add(db_user)
        session.commit()
        return {"ok": True, "activeBusinessId": next_id}
