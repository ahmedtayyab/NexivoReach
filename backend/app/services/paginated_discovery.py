"""
Persistent paginated Google research for Find Buyers.

Each hunt row is an independent Google search with a page cursor that
persists across runs. A fair scheduler walks pages across those searches
and saves leads until the hunt-wide lead cap, the page budget, or Google
runs out. The next hunt resumes at the next page.
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
)
from app.services.enrichment import enrich_website
from app.tools.web_search import WebSearchTool

log = logging.getLogger(__name__)


def _db() -> Session:
    """Hunt opens many short sessions; keep attrs usable after commit (no DetachedInstanceError)."""
    return Session(engine, expire_on_commit=False)


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


def _norm_email(value: str) -> str:
    return (value or "").strip().lower()


def _prospect_emails(pr: Any) -> set[str]:
    out: set[str] = set()
    e = _norm_email(getattr(pr, "email", "") or "")
    if e and "@" in e:
        out.add(e)
    for c in getattr(pr, "contacts", None) or []:
        if not isinstance(c, dict):
            continue
        ctype = str(c.get("type") or "").lower()
        val = _norm_email(str(c.get("value") or ""))
        if val.startswith("mailto:"):
            val = val.split(":", 1)[-1].split("?", 1)[0].strip().lower()
        if "@" not in val:
            continue
        if ctype and ctype not in ("email", "mail", "e-mail"):
            continue
        out.add(val)
    return out


def _fingerprint(domains: List[str]) -> str:
    blob = "|".join(sorted({d for d in domains if d}))
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def _query_key(query: str) -> str:
    return re.sub(r"\s+", " ", (query or "").strip().lower())


def should_fetch_intent_page(*, pages_processed_this_run: int, pages_per_run: int) -> bool:
    """True while this run still has new pages left.

    pages_per_run is a budget of new Google pages, not an absolute page number.
    A cursor sitting on page 11 is still fetched when this run has processed 0 pages.
    """
    return int(pages_processed_this_run or 0) < max(1, int(pages_per_run or 1))


def should_exhaust_after_gaps(consecutive: int, page: int = 1) -> bool:
    """Blank or repeated pages only end a line after page 8, three times in a row.

    Google page 10 still has businesses. One empty page 2 must not finish the search.
    """
    return int(consecutive or 0) >= 3 and int(page or 1) >= 8


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
            with _db() as sess:
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
            with _db() as session:
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


FUNNEL_KEYS = (
    "serp_results",
    "unique_domains",
    "junk_filtered",
    "triage_rejected",
    "already_seen",
    "queued",
    "fetch_ok",
    "fetch_failed",
    "irrelevant",
    "location_match",
    "location_uncertain",
    "location_wrong",
    "location_rejected",
    "duplicates",
    "leads_created",
)


def _empty_funnel() -> Dict[str, int]:
    return {key: 0 for key in FUNNEL_KEYS}


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
    funnel: Dict[str, int] = field(default_factory=_empty_funnel)
    funnel_by_intent: Dict[str, Dict[str, int]] = field(default_factory=dict)
    logs: List[str] = field(default_factory=list)


def _note(stats: HuntStats, message: str) -> None:
    """One line in the hunt log shown in the app."""
    line = f"{time.strftime('%H:%M:%S')}  {message}"
    stats.logs.append(line)
    if len(stats.logs) > 500:
        del stats.logs[: len(stats.logs) - 500]
    log.info("HUNT %s", message)


_STOP_TEXT = {
    "leads_per_run": "Reached the new-lead limit for this run.",
    "pages_per_run": "Used this run's Google page budget. The next hunt continues on the following page.",
    "no_more_results": "Google returned empty pages, so this search is finished.",
    "repeated_results": "Google kept returning the same page, so this search is finished.",
    "search_error": "The search request failed.",
    "previously_exhausted": "Already finished on an earlier hunt. Start over to search it from page 1.",
    "blank_page": "This page was empty. The hunt continued.",
    "max_runtime": "Stopped because the hunt hit the time limit.",
    "max_google_requests": "Stopped because the hunt hit the Google request limit.",
    "max_total_pages": "Stopped because the hunt hit the page limit.",
    "max_domains": "Stopped because the hunt hit the website limit.",
    "max_enrichments": "Stopped because the hunt hit the website-open limit.",
    "hunt_finished": "Every search in this run was processed.",
}


def _stop_summary(stats: HuntStats) -> str:
    reasons = dict(stats.stop_reasons or {})
    if not reasons and stats.google_requests == 0:
        return "The hunt stopped before any search ran."
    parts = []
    for name, reason in reasons.items():
        parts.append(f"{name}: {_STOP_TEXT.get(reason, reason)}")
    if stats.leads_saved:
        parts.append(f"Saved {stats.leads_saved} new leads.")
    else:
        parts.append("No new leads were saved.")
    if stats.google_requests == 0:
        parts.append("No search request was sent.")
    return " ".join(parts)


def _bump_funnel(stats: HuntStats, search_intent: str, key: str, n: int = 1) -> None:
    stats.funnel[key] = int(stats.funnel.get(key) or 0) + n
    bucket = stats.funnel_by_intent.setdefault(search_intent or "", _empty_funnel())
    bucket[key] = int(bucket.get(key) or 0) + n


def funnel_report(stats: HuntStats) -> str:
    """One block of counts from Google results down to new leads."""
    f = stats.funnel or {}
    return "\n".join([
        f"Google results: {f.get('serp_results', 0)}",
        f"Unique domains: {f.get('unique_domains', 0)}",
        f"Filtered directories/marketplaces/news: {f.get('junk_filtered', 0)}",
        f"Rejected before opening (unrelated): {f.get('triage_rejected', 0)}",
        f"Already seen: {f.get('already_seen', 0)}",
        f"Queued for inspection: {f.get('queued', 0)}",
        f"Websites opened: {f.get('fetch_ok', 0)}",
        f"Website fetch failures: {f.get('fetch_failed', 0)}",
        f"Rejected as irrelevant: {f.get('irrelevant', 0)}",
        f"Location match: {f.get('location_match', 0)}",
        f"Uncertain location: {f.get('location_uncertain', 0)}",
        f"Wrong location: {f.get('location_wrong', 0)}",
        f"Rejected for location: {f.get('location_rejected', 0)}",
        f"Existing leads: {f.get('duplicates', 0)}",
        f"New leads created: {f.get('leads_created', 0)}",
    ])


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
    with _db() as session:
        for spec in intent_specs:
            cursor = _load_or_create_cursor(
                session,
                business_id=business_id,
                search_intent=spec["search_intent"],
                location=spec["location"],
                query=spec["query"],
            )
            start_page = max(1, int(cursor.next_page or 1))
            # A line marked finished after page 2 never reaches the leads that
            # are still on Google pages 3–10. Reopen those and keep going.
            if cursor.status == "exhausted" and start_page <= 3:
                cursor.status = "active"
                cursor.updated_at = _now()
                session.add(cursor)
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
                _note(
                    stats,
                    f"Not searching “{row.query}”. It was already finished on an earlier hunt. Start over to run it from page 1.",
                )

    if settings.SERPER_API_KEY:
        _note(stats, "Google search is on (Serper).")
    else:
        _note(stats, "SERPER_API_KEY is missing. This hunt cannot search Google.")
    _note(
        stats,
        f"Starting {len(intent_rows)} search(es). Limit {budget.leads_per_run} new leads, {budget.max_pages_per_intent} new Google pages per search.",
    )
    for row in intent_rows:
        if row.status != "exhausted":
            _note(stats, f"Will search: {row.query} (starting at Google page {row.current_page})")

    _update_job(
        job_id,
        phase=(
            f"Cap {budget.leads_per_run} new leads this run across all searches · "
            f"resuming saved Google pages"
        ),
        progress=6,
        telemetry={
            "leadsPerRun": budget.leads_per_run,
            "searchIntents": len(intent_specs),
            "huntLog": list(stats.logs),
        },
    )

    saved_ids: List[str] = []
    saved_front: List[Dict[str, Any]] = []
    seen_domains_this_hunt: set[str] = set()
    empty_streaks: Dict[str, int] = {}
    repeat_streaks: Dict[str, int] = {}
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
                        use_hunter=False,
                    ),
                    timeout=14.0,
                )
            except Exception:
                found = {"email": "", "phone": "", "contacts": [], "site_text": "", "sources": []}
                _bump_funnel(stats, search_intent, "fetch_failed")
            else:
                if (found.get("site_text") or "").strip():
                    _bump_funnel(stats, search_intent, "fetch_ok")
                else:
                    _bump_funnel(stats, search_intent, "fetch_failed")
            stats.websites_inspected += 1
            site_text = (found.get("site_text") or "")[:8000]
            phone = found.get("phone") or ""
            contacts = list(found.get("contacts") or [])

            # Note the site's own location. The hunt place stays in the Google query only.
            from app.agents.location_verify import verify_business_location

            loc_check = verify_business_location(
                requested_places=list(profile.places or []),
                site_text=site_text,
                title=title,
                snippet=snippet,
                row_location=str(found.get("location") or ""),
                phones=[phone] if phone else [],
                website=website,
            )
            verdict = str(loc_check.get("location_verdict") or "UNCERTAIN")
            if verdict == "MATCH":
                _bump_funnel(stats, search_intent, "location_match")
            elif verdict == "WRONG_LOCATION":
                _bump_funnel(stats, search_intent, "location_wrong")
            else:
                _bump_funnel(stats, search_intent, "location_uncertain")
            if loc_check.get("should_reject"):
                _bump_funnel(stats, search_intent, "location_rejected")

            # Hunter after the page is read — location is recorded, not a save gate.
            email = ""
            email_status = "email_not_found"
            email_source = ""
            if found.get("email"):
                email = found["email"]
                email_status = "email_found"
                email_source = (found.get("sources") or ["website"])[0]
                stats.emails_found += 1
            elif website:
                try:
                    from app.services.enrichment import hunter_domain_search
                    from urllib.parse import urlparse

                    host = (urlparse(website).hostname or "").lower()
                    if host.startswith("www."):
                        host = host[4:]
                    hunter = await hunter_domain_search(host)
                    if hunter.get("email"):
                        email = hunter["email"]
                        email_status = "email_found"
                        email_source = "hunter"
                        contacts = list(hunter.get("contacts") or []) + contacts
                        stats.emails_found += 1
                except Exception:
                    pass

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
                # Never use location_hint (hunt place) as business location
                "location": (loc_check.get("business_location") or found.get("location") or ""),
                "phone": phone,
                "source": "web",
            }
            triage = serp_triage(row, categories=profile.categories, buyers=profile.buyers)
            level = graded.get("level") or "irrelevant"
            relevant = bool(graded.get("relevant")) and level != "irrelevant"

            with _db() as session:
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
                # The Google query already selected this company website.
                # Product-word checks are stored on the lead. They do not drop it.

                q = qualify_from_fast_decision(
                    row=row,
                    profile=profile,
                    products=products,
                    triage=triage,
                    site_text=site_text or f"{title}\n{snippet}",
                )
                if not relevant or not q.get("shouldPersist"):
                    _bump_funnel(stats, search_intent, "irrelevant")
                    q["shouldPersist"] = True

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
                email_key = _norm_email(email)
                prospects_here = list(
                    session.exec(
                        select(ProspectRecord).where(ProspectRecord.business_id == business_id)
                    ).all()
                )
                if domain:
                    for pr in prospects_here:
                        if _domain(pr.website) == domain:
                            existing = pr
                            break
                if not existing and email_key and "@" in email_key:
                    for pr in prospects_here:
                        if email_key in _prospect_emails(pr):
                            existing = pr
                            break
                if not existing and company_name:
                    name_key = _legal_name_key(company_name)
                    for pr in prospects_here:
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
                    # Already in Leads — never re-surface in Latest hunt / found count.
                    # Same domain, same email, or same legal name after Start over.
                    existing_emails = _prospect_emails(existing)
                    email_dupe = bool(email_key and "@" in email_key and email_key in existing_emails)
                    if email and not (existing.email or "").strip():
                        existing.email = email
                    if phone and not (existing.phone or "").strip():
                        existing.phone = phone
                    efb = dict(existing.fit_breakdown or {})
                    old_i = list(efb.get("matchedSearchIntents") or [])
                    for intent in fb.get("matchedSearchIntents") or []:
                        if intent and intent not in old_i:
                            old_i.append(intent)
                    efb["matchedSearchIntents"] = old_i[:16]
                    efb["relevance"] = efb.get("relevance") or level
                    if email_status:
                        efb["emailStatus"] = email_status
                    existing.fit_breakdown = efb
                    if contacts and not (existing.contacts or []):
                        existing.contacts = contacts
                    session.add(existing)
                    mem.status = "saved"
                    mem.prospect_id = existing.id
                    session.add(mem)
                    session.commit()
                    stats.already_known_skips += 1
                    _bump_funnel(stats, search_intent, "duplicates")
                    _note(stats, f"Duplicate {company_name} — already a lead")
                    return {
                        "prospect": None,
                        "id": existing.id,
                        "merged": True,
                        "changed": False,
                        "duplicate": True,
                        "duplicateReason": "email" if email_dupe else "existing_lead",
                    }

                # Email already on another lead → do not create a second row
                if email_key and "@" in email_key:
                    for pr in prospects_here:
                        if email_key in _prospect_emails(pr):
                            mem.status = "saved"
                            mem.prospect_id = pr.id
                            session.add(mem)
                            session.commit()
                            stats.already_known_skips += 1
                            _bump_funnel(stats, search_intent, "duplicates")
                            _note(stats, f"Duplicate {company_name} — already a lead")
                            return {
                                "prospect": None,
                                "id": pr.id,
                                "merged": True,
                                "changed": False,
                                "duplicate": True,
                                "duplicateReason": "email",
                            }

                prospect_id = f"prospect-{uuid4().hex[:10]}"
                pr = ProspectRecord(
                    id=prospect_id,
                    company_name=company_name or "Unknown",
                    website=website,
                    location=(q.get("location") or "")[:200],
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
                _bump_funnel(stats, search_intent, "leads_created")
                _note(stats, f"Saved lead: {company_name} ({domain})")
                if intent_id:
                    intent_leads_this_run[intent_id] = intent_leads_this_run.get(intent_id, 0) + 1
                front = prospect_to_frontend(pr)
                return {"prospect": front, "id": prospect_id, "merged": False, "changed": True, "intent_id": intent_id}

    # ---- Main fair pagination loop ----
    while True:
        hit_reasons: List[str] = []
        if _budget_hit(hit_reasons):
            reason = hit_reasons[0] if hit_reasons else "budget"
            _note(stats, _STOP_TEXT.get(reason, reason))
            for row in intent_rows:
                if row.status == "active":
                    row.status = "budget"
                    row.stop_reason = hit_reasons[0]
                    stats.stop_reasons[row.search_intent] = hit_reasons[0]
            break

        active = [r for r in intent_rows if r.status == "active"]
        if not active:
            _note(stats, "Every search has stopped.")
            break

        # Round-robin across searches. The 100-lead cap is hunt-wide, not per search.
        intent = active[rr_index % len(active)]
        rr_index += 1
        intent_id = intent.id or ""

        page = intent.current_page
        # Budget is new pages this run. next_page=11 is not exhausted just because
        # the setting is 10.
        if not should_fetch_intent_page(
            pages_processed_this_run=int(intent.pages_processed or 0),
            pages_per_run=budget.max_pages_per_intent,
        ):
            intent.status = "quota"
            intent.stop_reason = "pages_per_run"
            stats.stop_reasons[intent.search_intent] = "pages_per_run"
            _note(
                stats,
                f"“{intent.query}” used its {budget.max_pages_per_intent} new pages for this run. Next hunt starts at page {intent.current_page}.",
            )
            _persist_intent(intent)
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
            telemetry=_telemetry_payload(stats, intent_rows, current_q, budget),
        )

        try:
            report = await web.search_organic_page(
                intent.query,
                page=page,
                num=budget.results_per_page,
            )
        except Exception as exc:
            log.warning("Search failed for %s page %s: %s", intent.query, page, exc)
            _note(stats, f"Search crashed for “{intent.query}” page {page}: {exc}")
            intent.status = "error"
            intent.stop_reason = "search_error"
            stats.stop_reasons[intent.search_intent] = "search_error"
            _persist_intent(intent)
            continue

        organic = list(report.get("hits") or [])
        provider = str(report.get("provider") or "none")
        search_error = str(report.get("error") or "")
        provider_label = {
            "serper": "Google via Serper",
            "brave": "Brave, not Google",
            "tavily": "Tavily, not Google",
            "duckduckgo": "DuckDuckGo, not Google",
        }.get(provider, "No search provider")
        _note(stats, f"{provider_label} — page {page}: {intent.query}")
        if search_error:
            _note(stats, search_error)
        _note(stats, f"Page {page} returned {len(organic)} results.")

        stats.google_requests += 1
        stats.google_pages += 1
        stats.raw_results += len(organic)
        _bump_funnel(stats, intent.search_intent, "serp_results", len(organic))

        if not organic:
            streak = empty_streaks.get(intent_id, 0) + 1
            empty_streaks[intent_id] = streak
            if page <= 1 or not should_exhaust_after_gaps(streak, page):
                # Skip this blank page and ask for the next one. Do not finish the line.
                intent.current_page = page + 1
                intent.stop_reason = "blank_page"
                stats.stop_reasons.pop(intent.search_intent, None)
                _persist_intent(intent)
                _save_cursor_page(
                    business_id=business_id,
                    query=intent.query,
                    next_page=intent.current_page,
                    status="active",
                )
                log.warning(
                    "Blank Google page %s for %s (%s in a row) — continuing",
                    page,
                    intent.query,
                    streak,
                )
                _note(stats, f"Google page {page} for “{intent.query}” was empty. Continuing to the next page.")
                continue
            intent.status = "exhausted"
            intent.stop_reason = "no_more_results"
            stats.stop_reasons[intent.search_intent] = "no_more_results"
            _note(stats, f"“{intent.query}” has no more Google results after page {page}.")
            _persist_intent(intent)
            _save_cursor_page(
                business_id=business_id,
                query=intent.query,
                next_page=page,
                status="exhausted",
            )
            continue

        empty_streaks[intent_id] = 0

        page_domains: List[str] = []
        enrich_jobs: List[Dict[str, Any]] = []
        # Advance the cross-run cursor only after this page is fully handled.
        pending_cursor: Optional[int] = None

        with _db() as session:
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
                    _bump_funnel(stats, intent.search_intent, "junk_filtered")
                    _note(
                        stats,
                        f"Skipped “{(title or domain or 'result')[:80]}” — {classified.get('reject_reason') or 'not a business'}",
                    )
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
                        if domain not in seen_domains_this_hunt:
                            _bump_funnel(stats, intent.search_intent, "unique_domains")
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
                    _bump_funnel(stats, intent.search_intent, "triage_rejected")

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
                    _bump_funnel(stats, intent.search_intent, "already_seen")
                    _note(stats, f"Already opened {domain} on an earlier hunt — skipped")
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
                    if domain not in seen_domains_this_hunt:
                        _bump_funnel(stats, intent.search_intent, "unique_domains")
                    seen_domains_this_hunt.add(domain)
                    stats.unique_domains = len(seen_domains_this_hunt)

                if already or not domain or not url:
                    continue
                if stats.enrichments + len(enrich_jobs) >= budget.max_enrichments:
                    continue
                if stats.leads_saved >= budget.leads_per_run:
                    continue
                _bump_funnel(stats, intent.search_intent, "queued")
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
                repeats = repeat_streaks.get(intent_id, 0) + 1
                repeat_streaks[intent_id] = repeats
                if should_exhaust_after_gaps(repeats, page):
                    intent.status = "exhausted"
                    intent.stop_reason = "repeated_results"
                    stats.stop_reasons[intent.search_intent] = "repeated_results"
                    _note(stats, f"“{intent.query}” page {page} repeated earlier results. This search is finished.")
                    _save_cursor_page(
                        business_id=business_id,
                        query=intent.query,
                        next_page=page,
                        status="exhausted",
                        session=session,
                    )
                else:
                    # Same results once is not the end of Google. Request the next page.
                    intent.current_page = page + 1
                    pending_cursor = intent.current_page
            else:
                repeat_streaks[intent_id] = 0
                intent.last_page_fingerprint = fp
                intent.current_page = page + 1
                intent.new_domains += len(enrich_jobs)
                pending_cursor = intent.current_page
            intent.updated_at = _now()
            session.add(intent)
            session.commit()
            # Keep a live copy on the round-robin list (same object; expire_on_commit=False).
            for i, r in enumerate(intent_rows):
                if r.id == intent_id:
                    intent_rows[i] = intent
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
                with _db() as session:
                    it = session.get(DiscoverySearchIntent, intent_id)
                    if it and not res.get("merged"):
                        it.relevant_leads = int(it.relevant_leads or 0) + 1
                        intent.relevant_leads = it.relevant_leads
                        session.add(it)
                        session.commit()

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
                telemetry=_telemetry_payload(stats, intent_rows, current_q, budget),
            )

        if pending_cursor is not None:
            _save_cursor_page(
                business_id=business_id,
                query=intent.query,
                next_page=pending_cursor,
                status="active",
            )

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
            f"intents={stats.search_intents} pages={stats.google_pages} "
            f"raw={stats.raw_results} unique={stats.unique_domains} known={stats.previously_known} "
            f"new={stats.new_domains} inspected={stats.websites_inspected} "
            f"emails={stats.emails_found}\n{funnel_report(stats)}"
        ),
        "decision": (
            "Hunt-wide lead cap; Google page cursors saved for the next hunt."
        ),
        "toolCalled": "PaginatedDiscovery",
        "toolResultSnippet": str(stats.stop_reasons)[:500],
    }]
    run_id = f"run-{uuid4().hex[:8]}"
    with _db() as session:
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

    summary = _stop_summary(stats)
    _note(stats, summary)
    telemetry = _telemetry_payload(stats, intent_rows, "", budget)
    telemetry["durationMs"] = duration_ms
    telemetry["complete"] = True
    telemetry["stopSummary"] = summary
    telemetry["huntLog"] = list(stats.logs)
    log.info("Hunt funnel\n%s", funnel_report(stats))
    done_phase = summary

    _update_job(
        job_id,
        status="completed",
        phase=done_phase,
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
            with _db() as session:
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
) -> Dict[str, Any]:
    leads_cap = budget.leads_per_run if budget else hunt_leads_per_run()
    funnel = dict(stats.funnel or {})
    return {
        "leadsPerRun": leads_cap,
        "searchIntents": stats.search_intents,
        "funnel": funnel,
        "funnelByIntent": {
            name: dict(bucket) for name, bucket in (stats.funnel_by_intent or {}).items()
        },
        "serpResults": funnel.get("serp_results", 0),
        "junkFiltered": funnel.get("junk_filtered", 0),
        "triageRejected": funnel.get("triage_rejected", 0),
        "alreadySeen": funnel.get("already_seen", 0),
        "queued": funnel.get("queued", 0),
        "fetchOk": funnel.get("fetch_ok", 0),
        "fetchFailed": funnel.get("fetch_failed", 0),
        "irrelevantRejected": funnel.get("irrelevant", 0),
        "locationUncertain": funnel.get("location_uncertain", 0),
        "locationWrong": funnel.get("location_wrong", 0),
        "locationRejected": funnel.get("location_rejected", 0),
        "duplicates": funnel.get("duplicates", 0),
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
        "huntLog": list(stats.logs),
        "stopSummary": _stop_summary(stats),
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
