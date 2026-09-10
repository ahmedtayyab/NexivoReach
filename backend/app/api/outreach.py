"""Prospect outreach actions: prepare drafts, Gmail send, reply sync, follow-ups."""

from __future__ import annotations

import time
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

from app.api.deps import AuthUser, get_current_user, resolve_business_id
from app.api.serializers import prospect_to_frontend
from app.database.session import engine
from app.integrations import gmail as gmail_mod
from app.integrations import sheets as sheets_mod
from app.models.schemas import Business, ProspectRecord, User
from app.providers.factory import get_ai_provider
from app.tools.contact_finder import discover_contacts, resolve_lead_email, email_from_contacts
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


def _recipient_email(row: ProspectRecord) -> str:
    """Resolve who to email — draft To: → lead.email → contacts[]."""
    draft = row.outreach_draft or {}
    return resolve_lead_email(
        email=row.email or "",
        contacts=row.contacts or [],
        to_email=(draft.get("toEmail") or "") if isinstance(draft, dict) else "",
    )


def _sync_leads_to_sheets(session: Session, business_id: str, rows: List[ProspectRecord]) -> None:
    """Push stage/status to Sheets so emailed rows get Contacted coloring."""
    if not rows:
        return
    try:
        biz = session.get(Business, business_id) if business_id else None
        sheet_id = sheets_mod.business_spreadsheet_id(biz)
        if not sheet_id:
            return
        owner = sheets_mod.owner_user(session, biz)
        if not sheets_mod.is_configured(owner):
            return
        seller = sheets_mod.resolve_company_tab_name(biz, fallback="Company")
        payload = []
        dirty = False
        for record in rows:
            stage = (record.stage or "To contact").strip()
            draft = record.outreach_draft or {}
            draft_status = (draft.get("status") or "").strip() if isinstance(draft, dict) else ""
            # Emailed drafts must show Contacted even if stage lagged behind
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
        sheets_mod.sync_leads(
            seller, payload, spreadsheet_id=sheet_id, session=session, user=owner
        )
    except Exception as exc:
        log.warning("Sheets sync after outreach failed: %s", exc)


async def _ensure_recipient(session: Session, row: ProspectRecord) -> str:
    """
    Make sure the lead has a recipient email before send.
    Uses stored email/contacts first; if empty, re-scrapes the company site.
    """
    existing = _recipient_email(row)
    if existing:
        # Keep draft.toEmail + row.email in sync so UI/send stay consistent
        draft = dict(row.outreach_draft or {})
        dirty = False
        if draft and not (draft.get("toEmail") or "").strip():
            draft["toEmail"] = existing
            row.outreach_draft = draft
            dirty = True
        if not (row.email or "").strip():
            row.email = existing
            dirty = True
        if dirty:
            session.add(row)
            session.commit()
            session.refresh(row)
        return existing

    website = (row.website or "").strip()
    if not website:
        return ""

    phone = (row.phone or "").strip()
    page: Dict[str, Any] = {}
    try:
        page = await WebSearchTool().scrape_homepage(website)
    except Exception as exc:
        log.warning("Recipient scrape homepage failed for %s: %s", row.id, exc)
    site_text = (page.get("text") or "") if isinstance(page, dict) else ""
    try:
        found = await discover_contacts(
            website=website,
            homepage_html=(page.get("html") or "")[:400000] if isinstance(page, dict) else "",
            homepage_text=site_text,
            homepage_url=(page.get("url") if isinstance(page, dict) else None) or website,
            seed_phone=phone,
            seed_emails=list((page.get("emails") or []) if isinstance(page, dict) else []),
        )
    except Exception as exc:
        log.warning("Recipient contact discover failed for %s: %s", row.id, exc)
        return ""

    email = (found.get("email") or "").strip()
    contacts = found.get("contacts") or list(row.contacts or [])
    if not email:
        email = email_from_contacts(contacts)
    if not email:
        return ""

    if email and not any(
        isinstance(c, dict)
        and (c.get("type") or "").lower() == "email"
        and (c.get("value") or "").lower() == email.lower()
        for c in contacts
    ):
        contacts = [{
            "type": "email",
            "value": email,
            "label": "Email",
            "source": "site",
            "role": "general",
        }, *contacts]

    row.email = email
    row.phone = found.get("phone") or row.phone
    row.contacts = contacts
    draft = dict(row.outreach_draft or {})
    if draft:
        draft["toEmail"] = email
        row.outreach_draft = draft
    timeline = list(row.agent_timeline or [])
    timeline.append({"time": _clock(), "action": f"Resolved recipient email {email}"})
    row.agent_timeline = timeline
    session.add(row)
    session.commit()
    session.refresh(row)
    return email


async def _prepare_one(
    session: Session,
    row: ProspectRecord,
    seller: str,
    *,
    force: bool = False,
) -> ProspectRecord:
    # Always try to resolve recipient — even when a draft already exists
    email = await _ensure_recipient(session, row)
    contacts = list(row.contacts or [])
    phone = (row.phone or "").strip()

    if row.outreach_draft and not force:
        # Patch empty To: on existing drafts so one-click send works
        draft = dict(row.outreach_draft)
        if email and not (draft.get("toEmail") or "").strip():
            draft["toEmail"] = email
            row.outreach_draft = draft
            if not (row.email or "").strip():
                row.email = email
            session.add(row)
            session.commit()
            session.refresh(row)
        return row

    # If still no email, scrape again as part of prepare (website may have been empty earlier)
    if not email and (row.website or "").strip():
        email = await _ensure_recipient(session, row)
        contacts = list(row.contacts or [])
        phone = (row.phone or "").strip()

    provider = get_ai_provider()
    fb = row.fit_breakdown or {}
    draft = await provider.generate_personalized_outreach(
        company_name=row.company_name or "there",
        why_prospect=row.why_this_prospect or "",
        signals=row.buying_signals or [],
        matched_products=row.product_fit or [],
        seller_name=seller,
        why_now=getattr(row, "why_now", None) or fb.get("whyNow") or "",
        evidence=fb.get("evidence") or [],
        location=row.location or "",
        industry=row.industry or "",
        recommended_approach=row.recommended_approach or "",
        fit_summary=fb.get("fitSummary") or "",
        intent=fb.get("intent") or "",
    )
    now = _now()
    to_addr = email or _recipient_email(row)
    outreach = {
        "id": f"draft-{uuid4().hex[:8]}",
        "subject": draft.get("subject") or f"Introduction — {seller}",
        "body": draft.get("body") or "",
        "personalizedReason": draft.get("personalizedReason") or "",
        "outreachRationale": draft.get("outreachRationale") or None,
        "status": "Draft",
        "createdAt": now,
        "toEmail": to_addr or "",
    }
    timeline = list(row.agent_timeline or [])
    timeline.append({"time": _clock(), "action": "Prepared outreach draft (human review before send)"})
    if to_addr:
        timeline.append({"time": _clock(), "action": f"Contact email {to_addr}"})
    else:
        timeline.append({"time": _clock(), "action": "No public email found — draft saved without To:"})

    row.email = to_addr or row.email
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
                # Still include if draft exists but To: is empty — patch recipient
                if _recipient_email(row) and (row.outreach_draft or {}).get("toEmail"):
                    continue
                if not row.website and not _recipient_email(row):
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


def _draft_ready_to_send(row: ProspectRecord) -> bool:
    draft = row.outreach_draft or {}
    if not draft:
        return False
    status = (draft.get("status") or "").strip()
    if status not in ("Draft", "Approved"):
        return False
    # Recipient may live on lead.email / contacts even if draft.toEmail is empty
    to = _recipient_email(row)
    if not to:
        return False
    if not (draft.get("subject") or "").strip():
        return False
    if not (draft.get("body") or "").strip():
        return False
    return True


def _draft_sendable_after_resolve(row: ProspectRecord) -> bool:
    """Draft has subject/body and status — recipient may still need a scrape."""
    draft = row.outreach_draft or {}
    if not draft:
        return False
    if (draft.get("status") or "").strip() not in ("Draft", "Approved"):
        return False
    if not (draft.get("subject") or "").strip():
        return False
    if not (draft.get("body") or "").strip():
        return False
    return True


async def _send_one_gmail(
    session: Session,
    row: ProspectRecord,
    db_user: User,
    *,
    to: str = "",
    subject: str = "",
    body: str = "",
) -> ProspectRecord:
    draft = dict(row.outreach_draft or {})
    if not draft:
        raise HTTPException(status_code=400, detail="No outreach draft")

    to_addr = (to or "").strip() or await _ensure_recipient(session, row)
    if not to_addr:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No recipient email for {row.company_name or 'lead'} — "
                "no public address found on their website/contact page"
            ),
        )

    subj = (subject or draft.get("subject") or "").strip()
    body_text = (body or draft.get("body") or "").strip()
    if not subj or not body_text:
        raise HTTPException(status_code=400, detail=f"Incomplete draft for {row.company_name}")

    sent = await gmail_mod.send_email(
        session,
        db_user,
        to=to_addr,
        subject=subj,
        body=body_text,
    )
    draft["toEmail"] = to_addr
    draft["subject"] = subj
    draft["body"] = body_text
    draft["status"] = "Sent"
    draft["gmailMessageId"] = sent.get("messageId") or ""
    draft["gmailThreadId"] = sent.get("threadId") or ""
    draft["sentAt"] = _now()
    draft["sentVia"] = "gmail"
    row.email = to_addr or row.email
    row.stage = "Contacted"
    timeline = list(row.agent_timeline or [])
    timeline.append({"time": _clock(), "action": f"Sent via Gmail to {to_addr}"})
    row.outreach_draft = draft
    row.agent_timeline = timeline
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@router.post("/send-batch")
async def send_batch(
    payload: Dict[str, Any],
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """
    One-click: send ready outreach drafts via Gmail.
    Resolves recipient from lead email/contacts (and re-scrapes if needed).
    """
    ids = payload.get("ids") or []
    best_fit_only = payload.get("bestFitOnly", True) if not ids else False
    limit = min(40, max(1, int(payload.get("limit") or 25)))

    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        db_user = session.get(User, user.id)
        if not db_user or not gmail_mod.is_connected(db_user):
            raise HTTPException(
                status_code=400,
                detail="Connect Gmail in Settings → Integrations to send in one click",
            )

        rows = session.exec(
            select(ProspectRecord).where(ProspectRecord.business_id == business_id)
        ).all()
        id_set = set(ids) if ids else None
        targets: List[ProspectRecord] = []
        for row in rows:
            if id_set is not None and row.id not in id_set:
                continue
            if not _draft_sendable_after_resolve(row):
                continue
            if best_fit_only and not _is_outreach_ready(row):
                continue
            targets.append(row)

        targets.sort(key=lambda r: int(r.fit_score or 0), reverse=True)
        targets = targets[:limit]

        sent_rows: List[ProspectRecord] = []
        errors: List[Dict[str, str]] = []
        skipped_no_email = 0
        for row in targets:
            try:
                recipient = await _ensure_recipient(session, row)
                if not recipient:
                    skipped_no_email += 1
                    errors.append({
                        "id": row.id or "",
                        "company": row.company_name or "",
                        "error": "No public email on website/contact page",
                    })
                    continue
                if sent_rows:
                    time.sleep(0.35)
                sent_rows.append(await _send_one_gmail(session, row, db_user, to=recipient))
            except Exception as exc:
                log.warning("Batch send failed for %s: %s", row.id, exc)
                errors.append({
                    "id": row.id or "",
                    "company": row.company_name or "",
                    "error": str(exc)[:200],
                })

        if sent_rows:
            _sync_leads_to_sheets(session, business_id, sent_rows)

        return {
            "ok": True,
            "sent": len(sent_rows),
            "failed": len(errors),
            "skippedNoEmail": skipped_no_email,
            "errors": errors[:20],
            "prospects": [prospect_to_frontend(r) for r in sent_rows],
        }


@router.post("/send-ready")
async def send_ready(
    payload: Dict[str, Any],
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """
    Full one-click: resolve emails → prepare drafts → send via Gmail.
    """
    limit = min(25, max(1, int(payload.get("limit") or 15)))
    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        db_user = session.get(User, user.id)
        if not db_user or not gmail_mod.is_connected(db_user):
            raise HTTPException(
                status_code=400,
                detail="Connect Gmail in Settings → Integrations to send in one click",
            )
        seller = _seller_name(session, business_id)
        rows = session.exec(
            select(ProspectRecord).where(ProspectRecord.business_id == business_id)
        ).all()

        prepared = 0
        resolved = 0
        for row in sorted(rows, key=lambda r: int(r.fit_score or 0), reverse=True):
            if prepared >= limit:
                break
            if not _is_outreach_ready(row):
                continue
            if row.outreach_draft and (row.outreach_draft or {}).get("status") in ("Sent", "Replied"):
                continue
            # Resolve / scrape email first — this is the product core
            try:
                email = await _ensure_recipient(session, row)
            except Exception:
                email = ""
            if email:
                resolved += 1
            if not email and not (row.website or "").strip():
                continue
            try:
                await _prepare_one(session, row, seller, force=False)
                prepared += 1
            except Exception as exc:
                log.warning("Prepare before send failed for %s: %s", row.id, exc)

        rows = session.exec(
            select(ProspectRecord).where(ProspectRecord.business_id == business_id)
        ).all()
        targets = [
            r for r in rows
            if _draft_sendable_after_resolve(r) and _is_outreach_ready(r)
        ]
        targets.sort(key=lambda r: int(r.fit_score or 0), reverse=True)
        targets = targets[:limit]

        sent_rows: List[ProspectRecord] = []
        errors: List[Dict[str, str]] = []
        for row in targets:
            try:
                recipient = await _ensure_recipient(session, row)
                if not recipient:
                    errors.append({
                        "id": row.id or "",
                        "company": row.company_name or "",
                        "error": "No public email on website/contact page",
                    })
                    continue
                if sent_rows:
                    time.sleep(0.35)
                sent_rows.append(await _send_one_gmail(session, row, db_user, to=recipient))
            except Exception as exc:
                log.warning("Send-ready failed for %s: %s", row.id, exc)
                errors.append({
                    "id": row.id or "",
                    "company": row.company_name or "",
                    "error": str(exc)[:200],
                })

        if sent_rows:
            _sync_leads_to_sheets(session, business_id, sent_rows)

        return {
            "ok": True,
            "prepared": prepared,
            "resolvedEmails": resolved,
            "sent": len(sent_rows),
            "failed": len(errors),
            "errors": errors[:20],
            "prospects": [prospect_to_frontend(r) for r in sent_rows],
        }


@router.post("/backfill-recipients")
async def backfill_recipients(
    payload: Dict[str, Any],
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """
    Fill empty Outreach To: fields from contacts, then re-scrape sites still missing email.
    Called when opening Outreach so buyer addresses aren't blank.
    """
    limit = min(30, max(1, int(payload.get("limit") or 20)))
    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        rows = session.exec(
            select(ProspectRecord).where(ProspectRecord.business_id == business_id)
        ).all()
        targets: List[ProspectRecord] = []
        for row in rows:
            draft = row.outreach_draft or {}
            if not draft:
                continue
            if (draft.get("status") or "").strip() in ("Sent", "Replied"):
                continue
            existing = _recipient_email(row)
            if existing:
                # Sync empty To: / email from contacts without re-scraping
                dirty = False
                draft_dict = dict(draft)
                if not (draft_dict.get("toEmail") or "").strip():
                    draft_dict["toEmail"] = existing
                    row.outreach_draft = draft_dict
                    dirty = True
                if not (row.email or "").strip():
                    row.email = existing
                    dirty = True
                if dirty:
                    session.add(row)
                continue
            if not (row.website or "").strip():
                continue
            targets.append(row)

        session.commit()

        targets.sort(key=lambda r: int(r.fit_score or 0), reverse=True)
        filled: List[ProspectRecord] = []
        for row in targets[:limit]:
            try:
                email = await _ensure_recipient(session, row)
                if email:
                    filled.append(row)
            except Exception as exc:
                log.warning("Backfill recipient failed for %s: %s", row.id, exc)

        # Reload business rows so response includes synced To: fields
        rows = session.exec(
            select(ProspectRecord).where(ProspectRecord.business_id == business_id)
        ).all()
        updated = [
            r for r in rows
            if r.outreach_draft and _recipient_email(r)
            and (r.outreach_draft or {}).get("status") not in ("Sent", "Replied")
        ]

        return {
            "ok": True,
            "filled": len(filled),
            "prospects": [prospect_to_frontend(r) for r in updated],
        }


@router.post("/{prospect_id}/refresh-contacts")
async def refresh_contacts(
    prospect_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """Re-scrape the company site for public emails/phones and save onto the lead."""
    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        row = _get_owned(session, prospect_id, business_id)
        if not (row.website or "").strip():
            raise HTTPException(status_code=400, detail="Lead has no website to scrape")
        phone = (row.phone or "").strip()
        page: Dict[str, Any] = {}
        try:
            page = await WebSearchTool().scrape_homepage(row.website)
        except Exception as exc:
            log.warning("Homepage scrape failed for %s: %s", prospect_id, exc)
        site_text = (page.get("text") or "") if isinstance(page, dict) else ""
        found = await discover_contacts(
            website=row.website,
            homepage_html=(page.get("html") or "")[:400000] if isinstance(page, dict) else "",
            homepage_text=site_text,
            homepage_url=(page.get("url") if isinstance(page, dict) else None) or row.website,
            seed_phone=phone,
            seed_emails=list((page.get("emails") or []) if isinstance(page, dict) else []),
        )
        email = (found.get("email") or row.email or "").strip()
        contacts = found.get("contacts") or list(row.contacts or [])
        phone = found.get("phone") or phone
        # Ensure email appears in contacts list
        if email and not any(
            (c.get("type") == "email" and (c.get("value") or "").lower() == email.lower())
            for c in contacts
            if isinstance(c, dict)
        ):
            contacts = [{
                "type": "email",
                "value": email,
                "label": "Email",
                "source": "site",
                "role": "general",
            }, *contacts]
        timeline = list(row.agent_timeline or [])
        if email:
            timeline.append({"time": _clock(), "action": f"Refreshed contacts — email {email}"})
        else:
            timeline.append({"time": _clock(), "action": "Refreshed contacts — no public email found"})
        row.email = email
        row.phone = phone or row.phone
        row.contacts = contacts
        row.agent_timeline = timeline
        if row.outreach_draft and isinstance(row.outreach_draft, dict) and email:
            draft = dict(row.outreach_draft)
            if not (draft.get("toEmail") or "").strip():
                draft["toEmail"] = email
                row.outreach_draft = draft
        session.add(row)
        session.commit()
        session.refresh(row)
        return {"prospect": prospect_to_frontend(row), "email": email, "found": bool(email)}


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
            "toEmail": prior.get("toEmail") or _recipient_email(row) or "",
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
        to = (body_in.get("toEmail") or "").strip() or await _ensure_recipient(session, row)
        if subject:
            draft["subject"] = subject
        if body:
            draft["body"] = body
        if to:
            draft["toEmail"] = to
            row.email = to or row.email
            row.outreach_draft = draft
            session.add(row)
            session.commit()
            session.refresh(row)
            draft = dict(row.outreach_draft or {})

        db_user = session.get(User, user.id)
        use_gmail = bool(db_user and gmail_mod.is_connected(db_user))

        if use_gmail:
            try:
                row = await _send_one_gmail(
                    session,
                    row,
                    db_user,
                    to=to,
                    subject=draft.get("subject") or "",
                    body=draft.get("body") or "",
                )
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            _sync_leads_to_sheets(session, business_id, [row])
            return {
                "ok": True,
                "via": "gmail",
                "prospect": prospect_to_frontend(row),
            }

        # Mailto fallback — needs a recipient just like Gmail
        if not to or "@" not in to:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No recipient email for {row.company_name or 'lead'} — "
                    "no public address found on their website/contact page"
                ),
            )
        draft["status"] = "Sent"
        draft["sentAt"] = _now()
        draft["sentVia"] = "mailto"
        draft["toEmail"] = to
        row.email = to or row.email
        row.stage = "Contacted"
        timeline = list(row.agent_timeline or [])
        timeline.append({"time": _clock(), "action": "Opened mailto for human send"})
        row.outreach_draft = draft
        row.agent_timeline = timeline
        session.add(row)
        session.commit()
        session.refresh(row)
        _sync_leads_to_sheets(session, business_id, [row])
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
            email = _recipient_email(row)
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

        if updated:
            _sync_leads_to_sheets(session, business_id, updated)

        return {
            "ok": True,
            "synced": len(updated),
            "prospects": [prospect_to_frontend(r) for r in updated],
        }
