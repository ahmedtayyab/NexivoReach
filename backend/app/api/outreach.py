"""Prospect outreach actions: prepare drafts, Gmail send, reply sync, follow-ups."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

from app.api.deps import AuthUser, get_current_user, resolve_business_id
from app.api.serializers import prospect_to_frontend
from app.database.session import engine
from app.integrations import gmail as gmail_mod
from app.models.schemas import Business, ProspectRecord, User
from app.providers.factory import get_ai_provider
from app.tools.contact_finder import discover_contacts
from app.tools.web_search import WebSearchTool
import logging

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/prospects", tags=["prospects-outreach"])


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ")


def _clock() -> str:
    return time.strftime("%H:%M")


def _get_owned(session: Session, prospect_id: str, business_id: str) -> ProspectRecord:
    row = session.get(ProspectRecord, prospect_id)
    if not row or row.business_id != business_id:
        raise HTTPException(status_code=404, detail="Prospect not found")
    return row


def _seller_name(session: Session, business_id: str) -> str:
    biz = session.get(Business, business_id) if business_id else None
    return ((biz.name if biz else "") or "Sales Team").strip() or "Sales Team"


def _fit_summary(row: ProspectRecord) -> str:
    fb = row.fit_breakdown or {}
    return (fb.get("fitSummary") or fb.get("fit_summary") or "").lower()


def _priority(row: ProspectRecord) -> str:
    fb = row.fit_breakdown or {}
    return (fb.get("priority") or "").lower()


def _is_outreach_ready(row: ProspectRecord) -> bool:
    """Best-fit only: high fit, priority/nurture, or strong score (+ intent boost)."""
    if _fit_summary(row) == "high":
        return True
    if _priority(row) in ("priority", "nurture"):
        return True
    score = int(row.fit_score or 0)
    intent = ((row.fit_breakdown or {}).get("intent") or "none").lower()
    if score >= 75:
        return True
    if score >= 65 and intent in ("high", "low"):
        return True
    return False


async def _prepare_one(
    session: Session,
    row: ProspectRecord,
    seller: str,
    *,
    force: bool = False,
) -> ProspectRecord:
    if row.outreach_draft and not force:
        return row

    email = (row.email or "").strip()
    contacts = list(row.contacts or [])
    phone = (row.phone or "").strip()
    site_text = ""

    if row.website:
        try:
            page = await WebSearchTool().scrape_homepage(row.website)
            site_text = (page.get("text") or "") if isinstance(page, dict) else ""
        except Exception:
            site_text = ""
        try:
            found = await discover_contacts(
                website=row.website,
                homepage_text=site_text,
                homepage_url=row.website,
                seed_phone=phone,
            )
            contacts = found.get("contacts") or contacts
            email = found.get("email") or email
            phone = found.get("phone") or phone
        except Exception as exc:
            log.warning("Contact discover failed for %s: %s", row.id, exc)

    provider = get_ai_provider()
    draft = await provider.generate_personalized_outreach(
        company_name=row.company_name or "there",
        why_prospect=row.why_this_prospect or "",
        signals=row.buying_signals or [],
        matched_products=row.product_fit or [],
        seller_name=seller,
    )
    now = _now()
    outreach = {
        "id": f"draft-{uuid4().hex[:8]}",
        "subject": draft.get("subject") or f"Introduction — {seller}",
        "body": draft.get("body") or "",
        "personalizedReason": draft.get("personalizedReason") or "",
        "status": "Draft",
        "createdAt": now,
        "toEmail": email or "",
    }
    timeline = list(row.agent_timeline or [])
    timeline.append({"time": _clock(), "action": "Prepared outreach draft (human review before send)"})
    if email:
        timeline.append({"time": _clock(), "action": f"Contact email {email}"})

    row.email = email or row.email
    row.phone = phone or row.phone
    row.contacts = contacts
    row.outreach_draft = outreach
    row.agent_timeline = timeline
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@router.post("/prepare-outreach-batch")
async def prepare_outreach_batch(
    payload: Dict[str, Any],
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """Prepare drafts for high-fit leads that lack outreach (or force regenerate)."""
    force = bool(payload.get("force"))
    ids = payload.get("ids") or []
    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        seller = _seller_name(session, business_id)
        rows = session.exec(
            select(ProspectRecord).where(ProspectRecord.business_id == business_id)
        ).all()
        targets: List[ProspectRecord] = []
        id_set = set(ids) if ids else None
        for row in rows:
            if id_set is not None and row.id not in id_set:
                continue
            if row.outreach_draft and not force:
                continue
            if id_set is None and not _is_outreach_ready(row):
                continue
            targets.append(row)

        updated = []
        for row in targets[:40]:
            try:
                updated.append(await _prepare_one(session, row, seller, force=force))
            except Exception as exc:
                log.warning("Prepare outreach failed for %s: %s", row.id, exc)

        return {
            "ok": True,
            "prepared": len(updated),
            "prospects": [prospect_to_frontend(r) for r in updated],
        }


@router.post("/{prospect_id}/prepare-outreach")
async def prepare_outreach(
    prospect_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    force: bool = False,
):
    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        row = _get_owned(session, prospect_id, business_id)
        seller = _seller_name(session, business_id)
        row = await _prepare_one(session, row, seller, force=force or not row.outreach_draft)
        return prospect_to_frontend(row)


@router.post("/{prospect_id}/prepare-follow-up")
async def prepare_follow_up(
    prospect_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        row = _get_owned(session, prospect_id, business_id)
        seller = _seller_name(session, business_id)
        prior = row.outreach_draft or {}
        provider = get_ai_provider()
        draft = await provider.generate_follow_up_outreach(
            company_name=row.company_name or "there",
            why_prospect=row.why_this_prospect or "",
            prior_subject=prior.get("subject") or "",
            prior_body=prior.get("body") or "",
            reply_summary=row.reply_summary or "",
            seller_name=seller,
        )
        now = _now()
        outreach = {
            "id": f"draft-{uuid4().hex[:8]}",
            "subject": draft.get("subject") or f"Re: {prior.get('subject') or row.company_name}",
            "body": draft.get("body") or "",
            "personalizedReason": draft.get("personalizedReason") or "Follow-up draft",
            "status": "Draft",
            "createdAt": now,
            "toEmail": prior.get("toEmail") or row.email or "",
            "kind": "follow_up",
            "priorMessageId": prior.get("gmailMessageId") or "",
            "priorThreadId": prior.get("gmailThreadId") or "",
        }
        timeline = list(row.agent_timeline or [])
        timeline.append({"time": _clock(), "action": "Prepared follow-up draft"})
        if row.stage in ("Contacted", "Replied"):
            row.stage = "Re-contact"
        row.outreach_draft = outreach
        row.contact_again = True
        row.agent_timeline = timeline
        session.add(row)
        session.commit()
        session.refresh(row)
        return prospect_to_frontend(row)


@router.post("/{prospect_id}/send")
async def send_outreach(
    prospect_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """Send via Gmail when connected; otherwise returns mailto fallback payload."""
    body_in: Dict[str, Any] = {}
    try:
        body_in = await request.json()
    except Exception:
        body_in = {}

    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        row = _get_owned(session, prospect_id, business_id)
        draft = dict(row.outreach_draft or {})
        if not draft:
            raise HTTPException(status_code=400, detail="No outreach draft — prepare outreach first")

        subject = (body_in.get("subject") or draft.get("subject") or "").strip()
        body = (body_in.get("body") or draft.get("body") or "").strip()
        to = (body_in.get("toEmail") or draft.get("toEmail") or row.email or "").strip()
        if subject:
            draft["subject"] = subject
        if body:
            draft["body"] = body
        if to:
            draft["toEmail"] = to

        db_user = session.get(User, user.id)
        use_gmail = bool(db_user and gmail_mod.is_connected(db_user))

        if use_gmail:
            try:
                sent = await gmail_mod.send_email(
                    session,
                    db_user,
                    to=to,
                    subject=draft.get("subject") or "",
                    body=draft.get("body") or "",
                )
            except Exception as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            draft["status"] = "Sent"
            draft["gmailMessageId"] = sent.get("messageId") or ""
            draft["gmailThreadId"] = sent.get("threadId") or ""
            draft["sentAt"] = _now()
            draft["sentVia"] = "gmail"
            row.stage = "Contacted"
            timeline = list(row.agent_timeline or [])
            timeline.append({"time": _clock(), "action": f"Sent via Gmail to {to or '(no to)'}"})
            row.outreach_draft = draft
            row.agent_timeline = timeline
            session.add(row)
            session.commit()
            session.refresh(row)
            return {
                "ok": True,
                "via": "gmail",
                "prospect": prospect_to_frontend(row),
            }

        # Mailto fallback — client opens mail app; we still mark Sent like before
        draft["status"] = "Sent"
        draft["sentAt"] = _now()
        draft["sentVia"] = "mailto"
        row.stage = "Contacted"
        timeline = list(row.agent_timeline or [])
        timeline.append({"time": _clock(), "action": "Opened mailto for human send"})
        row.outreach_draft = draft
        row.agent_timeline = timeline
        session.add(row)
        session.commit()
        session.refresh(row)
        return {
            "ok": True,
            "via": "mailto",
            "mailto": {
                "to": to,
                "subject": draft.get("subject") or "",
                "body": draft.get("body") or "",
            },
            "prospect": prospect_to_frontend(row),
        }


@router.post("/sync-replies")
async def sync_replies(
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        db_user = session.get(User, user.id)
        if not db_user or not gmail_mod.is_connected(db_user):
            raise HTTPException(status_code=400, detail="Connect Gmail in Settings → Integrations first")

        rows = session.exec(
            select(ProspectRecord).where(ProspectRecord.business_id == business_id)
        ).all()
        leads = []
        for row in rows:
            draft = row.outreach_draft or {}
            if (draft.get("status") or "") not in ("Sent", "Approved", "Draft"):
                if row.stage not in ("Contacted", "Replied", "Re-contact"):
                    continue
            email = (draft.get("toEmail") or row.email or "").strip()
            thread_id = (draft.get("gmailThreadId") or "").strip()
            if not email and not thread_id:
                continue
            if row.reply_summary and draft.get("status") == "Replied":
                continue
            leads.append({
                "prospectId": row.id or "",
                "email": email,
                "threadId": thread_id,
            })

        hits = await gmail_mod.find_replies_for_leads(session, db_user, leads[:40])
        by_id = {h["prospectId"]: h for h in hits}
        updated = []
        now = _now()
        for row in rows:
            hit = by_id.get(row.id or "")
            if not hit:
                continue
            summary = (hit.get("summary") or "").strip()
            if not summary:
                continue
            draft = dict(row.outreach_draft or {})
            draft["status"] = "Replied"
            row.reply_summary = summary[:2000]
            row.last_reply_at = now
            row.contact_again = True
            row.stage = "Re-contact"
            timeline = list(row.agent_timeline or [])
            timeline.append({
                "time": _clock(),
                "action": "Gmail reply detected — marked Re-contact",
                "details": summary[:200],
            })
            row.outreach_draft = draft
            row.agent_timeline = timeline
            session.add(row)
            updated.append(row)
        session.commit()
        for row in updated:
            session.refresh(row)

        return {
            "ok": True,
            "synced": len(updated),
            "prospects": [prospect_to_frontend(r) for r in updated],
        }
