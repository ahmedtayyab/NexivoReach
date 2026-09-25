"""
Persistent paginated Google research for Find Buyers.

Each hunt line is an independent search intent with a page cursor that
persists across runs. A fair scheduler walks pages across intents, saves
leads incrementally, and stops when the per-run lead cap is reached
(split evenly across hunt lines). The next hunt resumes at the next page.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from uuid import uuid4

from sqlmodel import Session, select

from app.agents.geo import interpret_prompt_intent
from app.agents.relevance import qualify_from_fast_decision, serp_triage, website_relevance
from app.agents.search_planner import (
    apply_prompt_focus,
    apply_prompt_geo,
    apply_prompt_roles,
    infer_seller_profile,
)
from app.agents.serp_classifier import classify_serp_row
from app.api.serializers import prospect_to_frontend
from app.config import settings
from app.database.session import engine
from app.models.schemas import (
    AgentRunRecord,
    DiscoveredCompany,
    DiscoveryJob,
    DiscoverySearchIntent,
    DiscoverySerpHit,
    HuntSearchCursor,
    ProspectRecord,
)
from app.services.app_settings import (
    hunt_leads_per_run,
    hunt_max_pages_per_intent,
    leads_per_intent_share,
)
from app.services.enrichment import enrich_website
from app.tools.web_search import WebSearchTool

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _domain(url: str) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _legal_name_key(name: str) -> str:
    raw = (name or "").lower().replace(",", " ")
    for suffix in (
        " incorporated", " inc.", " inc", " llc", " ltd", " limited",
        " co.", " corp", " gmbh",
    ):
        raw = raw.replace(suffix, " ")
    return " ".join(raw.split())


def _fingerprint(domains: List[str]) -> str:
    blob = "|".join(sorted({d for d in domains if d}))
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def _query_key(query: str) -> str:
    return re.sub(r"\s+", " ", (query or "").strip().lower())


def _load_or_create_cursor(
    session: Session,
    *,
    business_id: str,
    search_intent: str,
    location: str,
    query: str,
) -> HuntSearchCursor:
    key = _query_key(query)
    row = session.exec(
        select(HuntSearchCursor).where(
            HuntSearchCursor.business_id == business_id,
            HuntSearchCursor.query_key == key,
        )
    ).first()
    if row:
        return row
    row = HuntSearchCursor(
        id=f"cur-{uuid4().hex[:12]}",
        business_id=business_id,
        query_key=key,
        search_intent=search_intent,
        location=location,
        query=query,
        next_page=1,
        status="active",
        updated_at=_now(),
    )
    session.add(row)
    return row


def _save_cursor_page(
    *,
    business_id: str,
    query: str,
    next_page: int,
    status: str = "active",
    search_intent: str = "",
    location: str = "",
    session: Optional[Session] = None,
) -> None:
    """Persist cross-run page cursor. Uses caller's session when provided (avoids SQLite locks)."""
    key = _query_key(query)
    next_page = max(1, int(next_page or 1))

    def _apply(sess: Session) -> None:
        row = sess.exec(
            select(HuntSearchCursor).where(
                HuntSearchCursor.business_id == business_id,
                HuntSearchCursor.query_key == key,
            )
        ).first()
        if not row:
            row = HuntSearchCursor(
                id=f"cur-{uuid4().hex[:12]}",
                business_id=business_id,
                query_key=key,
                search_intent=search_intent,
                location=location,
                query=query,
                next_page=next_page,
                status="active",
                updated_at=_now(),
            )
        else:
            row.next_page = next_page
            if status == "exhausted":
                row.status = "exhausted"
            elif row.status != "exhausted":
                row.status = status
            if search_intent and not row.search_intent:
                row.search_intent = search_intent
            if location and not row.location:
                row.location = location
            row.updated_at = _now()
        sess.add(row)

    if session is not None:
        _apply(session)
        return

    for attempt in range(4):
        try:
            with Session(engine) as sess:
                _apply(sess)
                sess.commit()
            return
        except Exception as exc:
            if attempt >= 3:
                log.warning("Cursor save failed for %s: %s", key[:80], exc)
                return
            time.sleep(0.15 * (attempt + 1))


def _update_job(job_id: str, **fields: Any) -> None:
    for attempt in range(4):
        try:
            with Session(engine) as session:
                job = session.get(DiscoveryJob, job_id)
                if not job:
                    return
                for k, v in fields.items():
                    setattr(job, k, v)
                job.updated_at = _now()
                session.add(job)
                session.commit()
            return
        except Exception as exc:
            if attempt >= 3:
                log.warning("Job update failed for %s: %s", job_id, exc)
                return
            time.sleep(0.15 * (attempt + 1))


@dataclass
class HuntBudget:
    leads_per_run: int = field(default_factory=lambda: hunt_leads_per_run())
    max_pages_per_intent: int = field(default_factory=lambda: hunt_max_pages_per_intent())
    max_total_pages: int = field(
        default_factory=lambda: int(settings.HUNT_MAX_TOTAL_PAGES or 150)
    )
    max_google_requests: int = field(
        default_factory=lambda: int(settings.HUNT_MAX_GOOGLE_REQUESTS or 200)
    )
    max_domains: int = field(
        default_factory=lambda: int(settings.HUNT_MAX_DOMAINS or 2000)
    )
    max_enrichments: int = field(
        default_factory=lambda: int(settings.HUNT_MAX_ENRICHMENTS or 800)
    )
    max_runtime_sec: float = field(
        default_factory=lambda: float(settings.HUNT_MAX_RUNTIME_SEC or 2700)
    )
    enrich_concurrency: int = field(
        default_factory=lambda: int(settings.HUNT_ENRICH_CONCURRENCY or 12)
    )
    results_per_page: int = field(
        default_factory=lambda: int(settings.HUNT_RESULTS_PER_PAGE or 10)
    )


@dataclass
class HuntStats:
    search_intents: int = 0
    google_pages: int = 0
    google_requests: int = 0
    raw_results: int = 0
    unique_domains: int = 0
    previously_known: int = 0
    new_domains: int = 0
    websites_inspected: int = 0
    relevant: int = 0
    irrelevant: int = 0
    emails_found: int = 0
    leads_saved: int = 0
    already_known_skips: int = 0
    enrichments: int = 0
    stop_reasons: Dict[str, str] = field(default_factory=dict)


def _phase_from_stats(
    stats: HuntStats,
    current_query: str,
    intents_done: int,
    intents_total: int,
    *,
    leads_cap: int = 40,
) -> str:
    parts = [
        f"Leads {stats.leads_saved}/{leads_cap}",
        f"Search intents: {intents_done}/{intents_total}",
    ]
    if current_query:
        short = current_query if len(current_query) <= 72 else current_query[:69] + "…"
        parts.append(f"Currently: {short}")
    parts.append(f"Google pages: {stats.google_pages}")
    parts.append(f"Businesses: {stats.unique_domains}")
    parts.append(f"Inspected: {stats.websites_inspected}")
    parts.append(f"Emails: {stats.emails_found}")
    if stats.already_known_skips:
        parts.append(f"Already known: {stats.already_known_skips}")
    return " · ".join(parts)


def _progress_pct(stats: HuntStats, budget: HuntBudget, intents_done: int, intents_total: int) -> int:
    if intents_total <= 0:
        return 5
    lead_frac = min(1.0, stats.leads_saved / max(budget.leads_per_run, 1))
    intent_frac = intents_done / max(intents_total, 1)
    raw = 8 + int(80 * (0.7 * lead_frac + 0.3 * intent_frac))
    return max(5, min(95, raw))


def _build_intents_from_prompt(user_prompt: str, location: str) -> List[Dict[str, str]]:
    """Each hunt line → independent search intent with full Google query."""
    place = re.sub(r"\s+", " ", (location or "").strip())
    intent = interpret_prompt_intent(user_prompt or "", place)
    out: List[Dict[str, str]] = []
    pairs = intent.get("pairs") or []
    primary = intent.get("primary_queries") or []
    if pairs and primary and len(pairs) == len(primary):
        for pair, q in zip(pairs, primary):
            product = (pair.get("product") or "").strip()
            buyer = (pair.get("buyer") or "").strip()
            search_intent = f"{product} {buyer}".strip()
            out.append({
                "search_intent": search_intent,
                "location": place or (intent.get("location") or ""),
                "query": q,
            })
        return out
    if primary:
        for q in primary:
            out.append({
                "search_intent": q,
                "location": place or (intent.get("location") or ""),
                "query": q,
            })
        return out
    # Fallback: freeform prompt as a single intent
    q = (user_prompt or "").strip()
    if place and place.lower() not in q.lower():
        q = f"{q} {place}".strip()
    if q:
        out.append({"search_intent": q, "location": place, "query": q})
    return out


async def run_paginated_discovery(
    *,
    job_id: str,
    user_id: str,
    business_id: str,
    user_prompt: str,
    products: List[Dict[str, Any]],
    icp: Dict[str, Any],
    business: Optional[Dict[str, Any]] = None,
    budget: Optional[HuntBudget] = None,
) -> Dict[str, Any]:
    budget = budget or HuntBudget()
    # SQLite cannot handle many concurrent writers; keep enrich workers small locally.
    try:
        from app.config import database_backend

        if database_backend() == "sqlite" and budget.enrich_concurrency > 3:
            budget.enrich_concurrency = 3
    except Exception:
        pass
    start = time.time()
    stats = HuntStats()
    web = WebSearchTool()
    business = business or {}

    profile = apply_prompt_focus(
        apply_prompt_roles(
            apply_prompt_geo(infer_seller_profile(products, icp, business), user_prompt),
            user_prompt,
        ),
        user_prompt,
    )
    place = profile.places[0] if profile.places else ""
    # Prefer location embedded in the prompt / ICP
    from app.agents.geo import interpret_prompt_intent as _ipi

    parsed = _ipi(user_prompt or "", place)
    if parsed.get("location"):
        place = parsed["location"]

    intent_specs = _build_intents_from_prompt(user_prompt, place)
    stats.search_intents = len(intent_specs)
    per_intent_cap = leads_per_intent_share(budget.leads_per_run, len(intent_specs) or 1)
    intent_leads_this_run: Dict[str, int] = {}

    if not intent_specs:
        _update_job(
            job_id,
            status="completed",
            phase="No search intents parsed from hunt description.",
            progress=100,
            found_count=0,
            completed_at=_now(),
            telemetry={"stats": stats.__dict__, "stop": "no_intents"},
        )
        return {"prospects": [], "stats": stats.__dict__}

    # Persist intent cursors — resume next_page from workspace HuntSearchCursor
    intent_rows: List[DiscoverySearchIntent] = []
    with Session(engine) as session:
        for spec in intent_specs:
            cursor = _load_or_create_cursor(
                session,
                business_id=business_id,
                search_intent=spec["search_intent"],
                location=spec["location"],
                query=spec["query"],
            )
            start_page = max(1, int(cursor.next_page or 1))
            initial_status = "exhausted" if cursor.status == "exhausted" else "active"
            row = DiscoverySearchIntent(
                id=f"intent-{uuid4().hex[:12]}",
                job_id=job_id,
                business_id=business_id,
                search_intent=spec["search_intent"],
                location=spec["location"],
                query=spec["query"],
                current_page=start_page,
                pages_processed=0,
                results_processed=0,
                new_domains=0,
                relevant_leads=0,
                status=initial_status,
                stop_reason="previously_exhausted" if initial_status == "exhausted" else "",
                created_at=_now(),
                updated_at=_now(),
            )
            session.add(row)
            intent_rows.append(row)
            intent_leads_this_run[row.id or ""] = 0
        session.commit()
        for row in intent_rows:
            session.refresh(row)
            intent_leads_this_run[row.id or ""] = 0
            if row.stop_reason == "previously_exhausted":
                stats.stop_reasons[row.search_intent] = "previously_exhausted"

    _update_job(
        job_id,
        phase=(
            f"Cap {budget.leads_per_run} leads this run "
            f"(~{per_intent_cap}/line across {len(intent_specs)} searches) · "
            f"resuming saved Google pages"
        ),
        progress=6,
        telemetry={
            "leadsPerRun": budget.leads_per_run,
            "perIntentCap": per_intent_cap,
            "searchIntents": len(intent_specs),
        },
    )

    saved_ids: List[str] = []
    saved_front: List[Dict[str, Any]] = []
    seen_domains_this_hunt: set[str] = set()
    rr_index = 0

    def _budget_hit(reason_holder: List[str]) -> bool:
        elapsed = time.time() - start
        if stats.leads_saved >= budget.leads_per_run:
            reason_holder.append("leads_per_run")
            return True
        if elapsed >= budget.max_runtime_sec:
            reason_holder.append("max_runtime")
            return True
        if stats.google_requests >= budget.max_google_requests:
            reason_holder.append("max_google_requests")
            return True
        if stats.google_pages >= budget.max_total_pages:
            reason_holder.append("max_total_pages")
            return True
        if stats.unique_domains >= budget.max_domains:
            reason_holder.append("max_domains")
            return True
        if stats.enrichments >= budget.max_enrichments:
            reason_holder.append("max_enrichments")
            return True
        return False

    enrich_sem = asyncio.Semaphore(budget.enrich_concurrency)

    async def _enrich_and_maybe_save(
        *,
        domain: str,
        website: str,
        company_name: str,
        title: str,
        snippet: str,
        discovery_query: str,
        search_intent: str,
        discovery_queries: List[str],
        location_hint: str,
        intent_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        nonlocal stats
        async with enrich_sem:
            if stats.leads_saved >= budget.leads_per_run:
                return None
            if intent_id and intent_leads_this_run.get(intent_id, 0) >= per_intent_cap:
                return None
            if stats.enrichments >= budget.max_enrichments:
                return None
            stats.enrichments += 1
            site_text = ""
            email = ""
            phone = ""
            contacts: List[Dict[str, Any]] = []
            email_status = "email_not_found"
            email_source = ""
            try:
                found = await asyncio.wait_for(
                    enrich_website(
                        website,
                        seed_email="",
                        seed_phone="",
                        seed_contacts=[],
                        use_hunter=True,
                    ),
                    timeout=14.0,
                )
            except Exception:
                found = {"email": "", "phone": "", "contacts": [], "site_text": "", "sources": []}
            stats.websites_inspected += 1
            site_text = (found.get("site_text") or "")[:8000]
            if found.get("email"):
                email = found["email"]
                email_status = "email_found"
                email_source = (found.get("sources") or ["website"])[0]
                stats.emails_found += 1
            phone = found.get("phone") or ""
            contacts = list(found.get("contacts") or [])

            product, role, _p = __import__(
                "app.agents.geo", fromlist=["parse_discovery_query"]
            ).parse_discovery_query(discovery_query)
            if not product:
                product = (profile.categories[0] if profile.categories else "") or ""
            if not role:
                role = (profile.buyers[0] if profile.buyers else "distributors") or "distributors"

            graded = website_relevance(
                product=product,
                buyer_type=role,
                company_name=company_name,
                title=title,
                snippet=snippet,
                site_text=site_text or f"{title}\n{snippet}",
                categories=list(profile.categories or []),
            )

            row = {
                "company_name": company_name,
                "website": website,
                "title": title,
                "snippet": snippet,
                "discovery_query": discovery_query,
                "discovery_queries": discovery_queries,
                "location": location_hint or found.get("location") or "",
                "source": "web",
            }
            triage = serp_triage(row, categories=profile.categories, buyers=profile.buyers)
            level = graded.get("level") or "irrelevant"
            relevant = bool(graded.get("relevant")) and level != "irrelevant"

            with Session(engine) as session:
                mem = session.exec(
                    select(DiscoveredCompany).where(
                        DiscoveredCompany.business_id == business_id,
                        DiscoveredCompany.domain == domain,
                    )
                ).first()
                now = _now()
                if not mem:
                    mem = DiscoveredCompany(
                        id=f"disc-{uuid4().hex[:12]}",
                        business_id=business_id,
                        domain=domain,
                        company_name=company_name,
                        company_name_normalized=_legal_name_key(company_name),
                        website=website,
                        first_seen_at=now,
                        last_seen_at=now,
                        matched_search_intents=[search_intent] if search_intent else [],
                    )
                else:
                    mem.last_seen_at = now
                    intents = list(mem.matched_search_intents or [])
                    if search_intent and search_intent not in intents:
                        intents.append(search_intent)
                    mem.matched_search_intents = intents[:24]
                    if company_name and not mem.company_name:
                        mem.company_name = company_name
                    if website and not mem.website:
                        mem.website = website

                mem.processed = True
                mem.email = email or mem.email or ""
                mem.email_status = email_status
                if not relevant:
                    mem.status = "irrelevant"
                    stats.irrelevant += 1
                    session.add(mem)
                    session.commit()
                    return None

                q = qualify_from_fast_decision(
                    row=row,
                    profile=profile,
                    products=products,
                    triage=triage,
                    site_text=site_text or f"{title}\n{snippet}",
                )
                if not q.get("shouldPersist"):
                    mem.status = "irrelevant"
                    stats.irrelevant += 1
                    session.add(mem)
                    session.commit()
                    return None

                stats.relevant += 1

                fb = dict(q.get("fitBreakdown") or {})
                fb["relevance"] = level
                fb["matchedSearchIntents"] = list(
                    dict.fromkeys(
                        list(discovery_queries or [])
                        + list(mem.matched_search_intents or [])
                        + ([search_intent] if search_intent else [])
                    )
                )[:16]
                fb["emailStatus"] = email_status
                fb["emailSource"] = email_source

                # Merge into existing prospect or create
                existing = None
                if domain:
                    for pr in session.exec(
                        select(ProspectRecord).where(ProspectRecord.business_id == business_id)
                    ).all():
                        if _domain(pr.website) == domain:
                            existing = pr
                            break
                if not existing and company_name:
                    name_key = _legal_name_key(company_name)
                    for pr in session.exec(
                        select(ProspectRecord).where(ProspectRecord.business_id == business_id)
                    ).all():
                        if _legal_name_key(pr.company_name) == name_key:
                            existing = pr
                            break

                timeline = [
                    {"time": time.strftime("%H:%M"), "action": f"Discovered via Google ({search_intent})"},
                    {
                        "time": time.strftime("%H:%M"),
                        "action": f"Fit {q.get('fitSummary')} · {level} (website inspect)",
                    },
                ]
                if email:
                    timeline.append({
                        "time": time.strftime("%H:%M"),
                        "action": f"Found contact email {email} ({email_source or 'website'})",
                    })
                else:
                    timeline.append({
                        "time": time.strftime("%H:%M"),
                        "action": "Email not found — lead kept as relevant",
                    })

                if existing:
                    changed = False
                    if email and not (existing.email or "").strip():
                        existing.email = email
                        changed = True
                    if phone and not (existing.phone or "").strip():
                        existing.phone = phone
                        changed = True
                    efb = dict(existing.fit_breakdown or {})
                    old_i = list(efb.get("matchedSearchIntents") or [])
                    for intent in fb.get("matchedSearchIntents") or []:
                        if intent and intent not in old_i:
                            old_i.append(intent)
                            changed = True
                    efb["matchedSearchIntents"] = old_i[:16]
                    efb["relevance"] = efb.get("relevance") or level
                    efb["emailStatus"] = email_status
                    existing.fit_breakdown = efb
                    if contacts:
                        existing.contacts = contacts
                    session.add(existing)
                    mem.status = "saved"
                    mem.prospect_id = existing.id
                    session.add(mem)
                    session.commit()
                    front = prospect_to_frontend(existing)
                    return {"prospect": front, "id": existing.id, "merged": True, "changed": changed}

                prospect_id = f"prospect-{uuid4().hex[:10]}"
                pr = ProspectRecord(
                    id=prospect_id,
                    company_name=company_name or "Unknown",
                    website=website,
                    location=(q.get("location") or location_hint or "")[:200],
                    industry=(q.get("industry") or "")[:80],
                    company_size="",
                    fit_score=int(q.get("fitScore") or 0),
                    fit_breakdown=fb,
                    why_this_prospect=q.get("whyThisProspect") or "",
                    buying_signals=q.get("buyingSignals") or [],
                    product_fit=q.get("productFit") or [],
                    recommended_approach=q.get("recommendedApproach") or "",
                    outreach_draft=None,
                    stage="To contact",
                    discovered_at=_now(),
                    agent_timeline=timeline,
                    user_id=user_id,
                    business_id=business_id,
                    source="web",
                    phone=phone,
                    why_now=q.get("whyNow") or "",
                    email=email,
                    contacts=contacts,
                    contact_again=True,
                    last_reply_at="",
                    reply_summary="",
                    discovery_job_id=job_id,
                )
                session.add(pr)
                mem.status = "saved"
                mem.prospect_id = prospect_id
                session.add(mem)
                session.commit()
                stats.leads_saved += 1
                if intent_id:
                    intent_leads_this_run[intent_id] = intent_leads_this_run.get(intent_id, 0) + 1
                front = prospect_to_frontend(pr)
                return {"prospect": front, "id": prospect_id, "merged": False, "changed": True, "intent_id": intent_id}

    # ---- Main fair pagination loop ----
    while True:
        hit_reasons: List[str] = []
        if _budget_hit(hit_reasons):
            for row in intent_rows:
                if row.status == "active":
                    row.status = "budget"
                    row.stop_reason = hit_reasons[0]
                    stats.stop_reasons[row.search_intent] = hit_reasons[0]
            break

        active = [r for r in intent_rows if r.status == "active"]
        if not active:
            break

        # Prefer intents still under their per-line share
        under_quota = [
            r for r in active
            if intent_leads_this_run.get(r.id or "", 0) < per_intent_cap
        ]
        if not under_quota:
            # All active intents hit their share — stop run (pages resume next time)
            for row in active:
                row.status = "quota"
                row.stop_reason = "per_intent_lead_cap"
                stats.stop_reasons[row.search_intent] = "per_intent_lead_cap"
                _persist_intent(row)
                _save_cursor_page(
                    business_id=business_id,
                    query=row.query,
                    next_page=row.current_page,
                    status="active",
                )
            break

        # Fair round-robin among intents still needing leads
        intent = under_quota[rr_index % len(under_quota)]
        rr_index += 1

        page = intent.current_page
        if page > budget.max_pages_per_intent:
            intent.status = "completed"
            intent.stop_reason = "max_pages_per_intent"
            stats.stop_reasons[intent.search_intent] = "max_pages_per_intent"
            _persist_intent(intent)
            _save_cursor_page(
                business_id=business_id,
                query=intent.query,
                next_page=page,
                status="active",
            )
            continue

        current_q = intent.query
        intents_done = sum(1 for r in intent_rows if r.status != "active")
        _update_job(
            job_id,
            status="running",
            phase=_phase_from_stats(
                stats, current_q, intents_done, len(intent_rows),
                leads_cap=budget.leads_per_run,
            ),
            progress=_progress_pct(stats, budget, intents_done, len(intent_rows)),
            found_count=stats.leads_saved,
            skipped_existing=stats.already_known_skips,
            result_prospect_ids=saved_ids[-200:],
            telemetry=_telemetry_payload(stats, intent_rows, current_q, budget, per_intent_cap),
        )

        try:
            organic = await web.search_organic_page(
                intent.query,
                page=page,
                num=budget.results_per_page,
            )
        except Exception as exc:
            log.warning("Search failed for %s page %s: %s", intent.query, page, exc)
            intent.status = "error"
            intent.stop_reason = f"search_error:{exc}"
            stats.stop_reasons[intent.search_intent] = intent.stop_reason
            _persist_intent(intent)
            continue

        stats.google_requests += 1
        stats.google_pages += 1
        stats.raw_results += len(organic)

        if not organic:
            intent.status = "exhausted"
            intent.stop_reason = "no_more_results"
            stats.stop_reasons[intent.search_intent] = "no_more_results"
            _persist_intent(intent)
            _save_cursor_page(
                business_id=business_id,
                query=intent.query,
                next_page=page,
                status="exhausted",
            )
            continue

        page_domains: List[str] = []
        enrich_jobs: List[Dict[str, Any]] = []

        with Session(engine) as session:
            for pos, hit in enumerate(organic, start=1):
                url = (hit.get("href") or "").strip()
                title = (hit.get("title") or "").strip()
                snippet = (hit.get("body") or "").strip()
                domain = _domain(url)
                if not domain and not title:
                    continue
                page_domains.append(domain or title.lower())

                serp = DiscoverySerpHit(
                    id=f"serp-{uuid4().hex[:12]}",
                    job_id=job_id,
                    intent_id=intent.id or "",
                    business_id=business_id,
                    search_intent=intent.search_intent,
                    query=intent.query,
                    page=page,
                    position=pos,
                    title=title[:300],
                    url=url[:500],
                    domain=domain,
                    snippet=snippet[:800],
                    already_known=False,
                    created_at=_now(),
                )

                # Junk host filter (cheap)
                classified = classify_serp_row(
                    {
                        "company_name": title,
                        "website": url,
                        "title": title,
                        "snippet": snippet,
                        "discovery_query": intent.query,
                    },
                    hunting_buyers=profile.hunting_buyers,
                    target_places=profile.places,
                    strict_geo=False,
                    offer_categories=profile.categories,
                )
                if classified.get("reject"):
                    session.add(serp)
                    # Record as seen/irrelevant junk without enrich
                    if domain:
                        _touch_discovered(
                            session,
                            business_id=business_id,
                            domain=domain,
                            company_name=classified.get("company_name") or title,
                            website=url,
                            search_intent=intent.search_intent,
                            status="irrelevant",
                            processed=True,
                        )
                        seen_domains_this_hunt.add(domain)
                        stats.unique_domains = len(seen_domains_this_hunt)
                    continue

                triage = serp_triage(
                    {
                        "company_name": classified.get("company_name") or title,
                        "title": title,
                        "snippet": snippet,
                        "discovery_query": intent.query,
                        "website": url,
                    },
                    categories=profile.categories,
                    buyers=profile.buyers,
                )
                if triage.get("verdict") == "reject":
                    session.add(serp)
                    if domain:
                        _touch_discovered(
                            session,
                            business_id=business_id,
                            domain=domain,
                            company_name=classified.get("company_name") or title,
                            website=url,
                            search_intent=intent.search_intent,
                            status="irrelevant",
                            processed=True,
                        )
                        seen_domains_this_hunt.add(domain)
                        stats.unique_domains = len(seen_domains_this_hunt)
                    continue

                already = False
                mem = None
                if domain:
                    mem = session.exec(
                        select(DiscoveredCompany).where(
                            DiscoveredCompany.business_id == business_id,
                            DiscoveredCompany.domain == domain,
                        )
                    ).first()
                if mem and mem.processed:
                    already = True
                    serp.already_known = True
                    stats.previously_known += 1
                    stats.already_known_skips += 1
                    # Still merge search intent memory; do NOT stop pagination
                    intents = list(mem.matched_search_intents or [])
                    if intent.search_intent and intent.search_intent not in intents:
                        intents.append(intent.search_intent)
                        mem.matched_search_intents = intents[:24]
                    mem.last_seen_at = _now()
                    session.add(mem)
                    # If saved prospect exists, merge intent onto fit_breakdown
                    if mem.prospect_id:
                        pr = session.get(ProspectRecord, mem.prospect_id)
                        if pr:
                            fb = dict(pr.fit_breakdown or {})
                            mi = list(fb.get("matchedSearchIntents") or [])
                            if intent.search_intent and intent.search_intent not in mi:
                                mi.append(intent.search_intent)
                                fb["matchedSearchIntents"] = mi[:16]
                                pr.fit_breakdown = fb
                                session.add(pr)
                elif domain:
                    stats.new_domains += 1
                    _touch_discovered(
                        session,
                        business_id=business_id,
                        domain=domain,
                        company_name=classified.get("company_name") or title,
                        website=url,
                        search_intent=intent.search_intent,
                        status="seen",
                        processed=False,
                    )

                session.add(serp)
                if domain:
                    seen_domains_this_hunt.add(domain)
                    stats.unique_domains = len(seen_domains_this_hunt)

                if already or not domain or not url:
                    continue
                if stats.enrichments + len(enrich_jobs) >= budget.max_enrichments:
                    continue
                if stats.leads_saved >= budget.leads_per_run:
                    continue
                if intent_leads_this_run.get(intent.id or "", 0) >= per_intent_cap:
                    continue
                enrich_jobs.append({
                    "domain": domain,
                    "website": url,
                    "company_name": classified.get("company_name") or title,
                    "title": title,
                    "snippet": snippet,
                    "discovery_query": intent.query,
                    "search_intent": intent.search_intent,
                    "discovery_queries": [intent.query],
                    "location_hint": intent.location,
                    "intent_id": intent.id or "",
                })

            intent.results_processed += len(organic)
            intent.pages_processed += 1
            fp = _fingerprint(page_domains)
            if fp and fp == intent.last_page_fingerprint:
                intent.status = "exhausted"
                intent.stop_reason = "repeated_results"
                stats.stop_reasons[intent.search_intent] = "repeated_results"
                _save_cursor_page(
                    business_id=business_id,
                    query=intent.query,
                    next_page=page,
                    status="exhausted",
                    session=session,
                )
            else:
                intent.last_page_fingerprint = fp
                intent.current_page = page + 1
                intent.new_domains += len(enrich_jobs)
                _save_cursor_page(
                    business_id=business_id,
                    query=intent.query,
                    next_page=intent.current_page,
                    status="active",
                    session=session,
                )
            intent.updated_at = _now()
            session.add(intent)
            session.commit()

        # Refresh in-memory intent row
        with Session(engine) as session:
            fresh = session.get(DiscoverySearchIntent, intent.id)
            if fresh:
                for i, r in enumerate(intent_rows):
                    if r.id == fresh.id:
                        intent_rows[i] = fresh
                        break

        # Enrich new domains from this page (bounded concurrency) — incremental save
        if enrich_jobs:
            tasks = [
                asyncio.create_task(_enrich_and_maybe_save(**job))
                for job in enrich_jobs
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, Exception) or not res:
                    continue
                pid = res.get("id")
                prospect = res.get("prospect")
                if pid and prospect and not res.get("merged"):
                    if pid not in saved_ids:
                        saved_ids.append(pid)
                        saved_front.append(prospect)
                elif pid and prospect and res.get("merged") and res.get("changed"):
                    if pid not in saved_ids:
                        saved_ids.append(pid)
                    # refresh front copy
                    saved_front = [p for p in saved_front if p.get("id") != pid] + [prospect]

                # bump intent relevant count
                with Session(engine) as session:
                    it = session.get(DiscoverySearchIntent, intent.id)
                    if it and not res.get("merged"):
                        it.relevant_leads = int(it.relevant_leads or 0) + 1
                        session.add(it)
                        session.commit()

            # Stop this intent for the run once its share is filled (resume later pages next hunt)
            if intent_leads_this_run.get(intent.id or "", 0) >= per_intent_cap and intent.status == "active":
                intent.status = "quota"
                intent.stop_reason = "per_intent_lead_cap"
                stats.stop_reasons[intent.search_intent] = "per_intent_lead_cap"
                _persist_intent(intent)

            if stats.leads_saved >= budget.leads_per_run:
                for row in intent_rows:
                    if row.status == "active":
                        row.status = "quota"
                        row.stop_reason = "leads_per_run"
                        stats.stop_reasons[row.search_intent] = "leads_per_run"
                        _persist_intent(row)
                        _save_cursor_page(
                            business_id=business_id,
                            query=row.query,
                            next_page=row.current_page,
                            status="active",
                        )

            _update_job(
                job_id,
                phase=_phase_from_stats(
                    stats,
                    current_q,
                    sum(1 for r in intent_rows if r.status != "active"),
                    len(intent_rows),
                    leads_cap=budget.leads_per_run,
                ),
                progress=_progress_pct(
                    stats,
                    budget,
                    sum(1 for r in intent_rows if r.status != "active"),
                    len(intent_rows),
                ),
                found_count=stats.leads_saved,
                skipped_existing=stats.already_known_skips,
                result_prospect_ids=saved_ids[-200:],
                telemetry=_telemetry_payload(stats, intent_rows, current_q, budget, per_intent_cap),
            )

        # Mark intent completed if page cap reached after this page
        if intent.status == "active" and intent.current_page > budget.max_pages_per_intent:
            intent.status = "completed"
            intent.stop_reason = "max_pages_per_intent"
            stats.stop_reasons[intent.search_intent] = "max_pages_per_intent"
            _persist_intent(intent)

    # Finalize remaining active intents — keep cursors for next run
    for row in intent_rows:
        if row.status == "active":
            row.status = "quota" if stats.leads_saved >= budget.leads_per_run else "completed"
            row.stop_reason = row.stop_reason or (
                "leads_per_run" if row.status == "quota" else "hunt_finished"
            )
            stats.stop_reasons[row.search_intent] = row.stop_reason
            _persist_intent(row)
            _save_cursor_page(
                business_id=business_id,
                query=row.query,
                next_page=row.current_page,
                status="active",
            )

    duration_ms = int((time.time() - start) * 1000)
    decisions = [{
        "step": 1,
        "observation": (
            f"HUNT COMPLETE — leads={stats.leads_saved}/{budget.leads_per_run} "
            f"(~{per_intent_cap}/line) intents={stats.search_intents} pages={stats.google_pages} "
            f"raw={stats.raw_results} unique={stats.unique_domains} known={stats.previously_known} "
            f"new={stats.new_domains} inspected={stats.websites_inspected} "
            f"emails={stats.emails_found}"
        ),
        "decision": (
            "Per-run lead cap split across hunt lines; Google page cursors saved for the next hunt."
        ),
        "toolCalled": "PaginatedDiscovery",
        "toolResultSnippet": str(stats.stop_reasons)[:500],
    }]
    run_id = f"run-{uuid4().hex[:8]}"
    with Session(engine) as session:
        ar = AgentRunRecord(
            id=run_id,
            timestamp=_now(),
            task=user_prompt or "Paginated lead hunt",
            duration_ms=duration_ms,
            tools_used=[
                "PaginatedDiscovery", "WebSearchTool", "SerpClassifier",
                "WebsiteInspect", "ContactFinder",
            ],
            sources_count=stats.raw_results,
            status="Completed" if stats.leads_saved else "CompletedWithNoCandidates",
            decisions=decisions,
            user_id=user_id,
            business_id=business_id,
        )
        session.add(ar)
        session.commit()

    telemetry = _telemetry_payload(stats, intent_rows, "", budget, per_intent_cap)
    telemetry["durationMs"] = duration_ms
    telemetry["complete"] = True

    _update_job(
        job_id,
        status="completed",
        phase=(
            f"Done · {stats.leads_saved}/{budget.leads_per_run} leads · "
            f"{stats.google_pages} Google pages · {stats.emails_found} emails "
            f"(next run resumes deeper pages)"
        ),
        progress=100,
        found_count=stats.leads_saved,
        skipped_existing=stats.already_known_skips,
        result_prospect_ids=saved_ids,
        agent_log_id=run_id,
        completed_at=_now(),
        telemetry=telemetry,
    )

    return {
        "prospects": saved_front,
        "stats": stats.__dict__,
        "agent_log_id": run_id,
        "telemetry": telemetry,
    }


def _persist_intent(intent: DiscoverySearchIntent) -> None:
    for attempt in range(4):
        try:
            with Session(engine) as session:
                row = session.get(DiscoverySearchIntent, intent.id)
                if not row:
                    return
                row.status = intent.status
                row.stop_reason = intent.stop_reason
                row.current_page = intent.current_page
                row.pages_processed = intent.pages_processed
                row.results_processed = intent.results_processed
                row.new_domains = intent.new_domains
                row.relevant_leads = intent.relevant_leads
                row.last_page_fingerprint = intent.last_page_fingerprint
                row.updated_at = _now()
                session.add(row)
                session.commit()
            return
        except Exception as exc:
            if attempt >= 3:
                log.warning("Intent persist failed for %s: %s", intent.id, exc)
                return
            time.sleep(0.15 * (attempt + 1))


def _touch_discovered(
    session: Session,
    *,
    business_id: str,
    domain: str,
    company_name: str,
    website: str,
    search_intent: str,
    status: str,
    processed: bool,
) -> DiscoveredCompany:
    mem = session.exec(
        select(DiscoveredCompany).where(
            DiscoveredCompany.business_id == business_id,
            DiscoveredCompany.domain == domain,
        )
    ).first()
    now = _now()
    if not mem:
        mem = DiscoveredCompany(
            id=f"disc-{uuid4().hex[:12]}",
            business_id=business_id,
            domain=domain,
            company_name=company_name or "",
            company_name_normalized=_legal_name_key(company_name),
            website=website or "",
            status=status,
            processed=processed,
            matched_search_intents=[search_intent] if search_intent else [],
            first_seen_at=now,
            last_seen_at=now,
        )
    else:
        mem.last_seen_at = now
        intents = list(mem.matched_search_intents or [])
        if search_intent and search_intent not in intents:
            intents.append(search_intent)
        mem.matched_search_intents = intents[:24]
        if not mem.processed:
            mem.status = status
            mem.processed = processed
        if company_name and not mem.company_name:
            mem.company_name = company_name
        if website and not mem.website:
            mem.website = website
    session.add(mem)
    return mem


def _telemetry_payload(
    stats: HuntStats,
    intent_rows: List[DiscoverySearchIntent],
    current_query: str,
    budget: Optional[HuntBudget] = None,
    per_intent_cap: int = 0,
) -> Dict[str, Any]:
    leads_cap = budget.leads_per_run if budget else hunt_leads_per_run()
    return {
        "leadsPerRun": leads_cap,
        "perIntentCap": per_intent_cap,
        "searchIntents": stats.search_intents,
        "completedIntents": sum(1 for r in intent_rows if r.status != "active"),
        "currentQuery": current_query,
        "googlePages": stats.google_pages,
        "googleRequests": stats.google_requests,
        "rawResults": stats.raw_results,
        "uniqueDomains": stats.unique_domains,
        "previouslyKnown": stats.previously_known,
        "newDomains": stats.new_domains,
        "websitesInspected": stats.websites_inspected,
        "relevant": stats.relevant,
        "irrelevant": stats.irrelevant,
        "emailsFound": stats.emails_found,
        "leadsSaved": stats.leads_saved,
        "alreadyKnown": stats.already_known_skips,
        "intentStatus": [
            {
                "searchIntent": r.search_intent,
                "query": r.query,
                "page": r.current_page,
                "pagesProcessed": r.pages_processed,
                "status": r.status,
                "stopReason": r.stop_reason,
                "relevantLeads": r.relevant_leads,
            }
            for r in intent_rows
        ],
        "stopReasons": dict(stats.stop_reasons),
    }
