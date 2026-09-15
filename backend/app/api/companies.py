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
from app.models.schemas import Business, BusinessMember, ICPConfig, User
import logging

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/companies", tags=["companies"])


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _accessible_companies(session: Session, user: AuthUser) -> list[Business]:
    owned = session.exec(
        select(Business).where(Business.user_id == user.id).order_by(Business.updated_at.desc())
    ).all()
    by_id = {b.id: b for b in owned if b.id}
    email = (user.email or "").strip().lower()
    memberships = session.exec(
        select(BusinessMember).where(BusinessMember.status == "active")
    ).all()
    for m in memberships:
        if m.user_id == user.id or (email and (m.email or "").strip().lower() == email):
            if m.business_id and m.business_id not in by_id:
                biz = session.get(Business, m.business_id)
                if biz:
                    by_id[biz.id] = biz
    return list(by_id.values())


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
        rows = _accessible_companies(session, user)
        rows = sorted(rows, key=lambda b: b.updated_at or "", reverse=True)
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


class MemberInvite(BaseModel):
    email: str
    role: str = "member"


@router.get("/{company_id}/members")
def list_members(company_id: str, user: AuthUser = Depends(get_current_user)):
    with Session(engine) as session:
        biz = session.get(Business, company_id)
        if not biz:
            raise HTTPException(status_code=404, detail="Company not found")
        from app.api.deps import user_can_access_business

        if not user_can_access_business(session, user, biz):
            raise HTTPException(status_code=404, detail="Company not found")
        owner = session.get(User, biz.user_id) if biz.user_id else None
        members = session.exec(
            select(BusinessMember).where(BusinessMember.business_id == company_id)
        ).all()
        return {
            "owner": {
                "userId": biz.user_id,
                "email": owner.email if owner else "",
                "name": owner.name if owner else "",
                "role": "owner",
            },
            "members": [
                {
                    "id": m.id,
                    "email": m.email,
                    "userId": m.user_id,
                    "role": m.role,
                    "status": m.status,
                    "createdAt": m.created_at,
                }
                for m in members
            ],
        }


@router.post("/{company_id}/members")
def invite_member(company_id: str, payload: MemberInvite, user: AuthUser = Depends(get_current_user)):
    email = (payload.email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Enter a valid email")
    role = (payload.role or "member").strip().lower()
    if role not in ("member", "admin"):
        role = "member"
    with Session(engine) as session:
        biz = session.get(Business, company_id)
        if not biz or biz.user_id != user.id:
            raise HTTPException(status_code=403, detail="Only the company owner can invite seats")
        existing = session.exec(
            select(BusinessMember).where(
                BusinessMember.business_id == company_id,
                BusinessMember.email == email,
            )
        ).first()
        if existing:
            return {
                "id": existing.id,
                "email": existing.email,
                "role": existing.role,
                "status": existing.status,
                "alreadyInvited": True,
            }
        # If they already have an account, activate immediately
        invitee = session.exec(select(User).where(User.email == email)).first()
        row = BusinessMember(
            id=f"mem-{uuid4().hex[:12]}",
            business_id=company_id,
            user_id=invitee.id if invitee else None,
            email=email,
            role=role,
            status="active" if invitee else "pending",
            invited_by=user.id,
            created_at=_now(),
            accepted_at=_now() if invitee else None,
        )
        session.add(row)
        # Also allowlist them so invite-only signup works
        from app.services import access as access_mod

        try:
            access_mod.add_invite(session, email, note=f"Seat on {biz.name}", created_by=user.email)
        except Exception:
            pass
        session.commit()
        session.refresh(row)
        return {
            "id": row.id,
            "email": row.email,
            "role": row.role,
            "status": row.status,
            "alreadyInvited": False,
        }


@router.delete("/{company_id}/members/{member_id}")
def remove_member(company_id: str, member_id: str, user: AuthUser = Depends(get_current_user)):
    with Session(engine) as session:
        biz = session.get(Business, company_id)
        if not biz or biz.user_id != user.id:
            raise HTTPException(status_code=403, detail="Only the owner can remove seats")
        row = session.get(BusinessMember, member_id)
        if not row or row.business_id != company_id:
            raise HTTPException(status_code=404, detail="Member not found")
        session.delete(row)
        session.commit()
        return {"ok": True}


@router.post("/{company_id}/members/accept")
def accept_member_invite(company_id: str, user: AuthUser = Depends(get_current_user)):
    email = (user.email or "").strip().lower()
    with Session(engine) as session:
        row = session.exec(
            select(BusinessMember).where(
                BusinessMember.business_id == company_id,
                BusinessMember.email == email,
                BusinessMember.status == "pending",
            )
        ).first()
        if not row:
            raise HTTPException(status_code=404, detail="No pending invite for this company")
        row.user_id = user.id
        row.status = "active"
        row.accepted_at = _now()
        session.add(row)
        db_user = session.get(User, user.id)
        if db_user:
            db_user.active_business_id = company_id
            session.add(db_user)
        session.commit()
        return {"ok": True, "businessId": company_id}
