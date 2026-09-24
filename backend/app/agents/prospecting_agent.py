"""Lead-hunting agent: planned discovery → classify → cheap fetch → Fit vs Intent."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4
from urllib.parse import urlparse

import httpx

from app.agents.search_planner import (
    apply_prompt_focus,
    apply_prompt_geo,
    apply_prompt_roles,
    infer_seller_profile,
    plan_wave1,
    plan_wave2,
    profile_to_dict,
)
from app.agents.serp_classifier import classify_serp_row, summarize_classifications
from app.agents.relevance import qualify_from_fast_decision, serp_triage
from app.tools.web_search import WebSearchTool, HEADERS
from app.tools.contact_finder import discover_contacts


# Fast discovery targets — return leads quickly; enrich contacts in the background.
TARGET_LEADS = 30
MIN_LEADS = 20
SAVE_CAP = 40
STRONG_SAVE = 24
AVERAGE_SAVE = 16
WAVE1_RESULT_CAP = 280
WAVE2_RESULT_CAP = 80
# Homepage fetch only for ambiguous SERP rows, and only when below target
AMBIGUOUS_FETCH_CAP = 16
SCRAPE_CONCURRENCY = 12
MIN_CANDIDATES_BEFORE_SKIP_WAVE2 = MIN_LEADS
DEFAULT_HUNT_LIMIT = 30
WAVE1_QUERY_CAP = 48
WAVE2_QUERY_CAP = 12
# Parallel contact crawl on the shortlist — hard time budget so the hunt stays fast
CONTACT_CONCURRENCY = 12
CONTACT_BUDGET_SEC = 22.0


def _domain(url: str) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _legal_name_key(name: str) -> str:
    raw = (name or "").lower()
    raw = raw.replace(",", " ")
    for suffix in (" incorporated", " inc.", " inc", " llc", " ltd", " limited", " co.", " corp", " gmbh"):
        raw = raw.replace(suffix, " ")
    return " ".join(raw.split())


class ProspectingAgent:
    def __init__(self):
        self.web_search = WebSearchTool()

    async def execute_discovery_goal(
        self,
        user_prompt: str,
        products: List[Dict[str, Any]],
        icp: Dict[str, Any],
        business: Optional[Dict[str, Any]] = None,
        exclude_websites: Optional[List[str]] = None,
        limit: int = 60,
    ) -> Dict[str, Any]:
        start_time = time.time()
        decisions_log: List[Dict[str, Any]] = []
        business = business or {}
        limit = max(limit, DEFAULT_HUNT_LIMIT)
        profile = apply_prompt_focus(
            apply_prompt_roles(
                apply_prompt_geo(infer_seller_profile(products, icp, business), user_prompt),
                user_prompt,
            ),
            user_prompt,
        )
        wave1 = plan_wave1(profile, user_prompt)
        place = profile.places[0] if profile.places else ""
        exclude_domains = {_domain(u) for u in (exclude_websites or []) if _domain(u)}

        from app.agents.geo import interpret_prompt_intent

        intent = interpret_prompt_intent(user_prompt or "", place) if (user_prompt or "").strip() else None
        # Product hunts behave like a plain Google search. Maps fuzzy-matches
        # "wrist wraps wholesalers in Houston" to record shops and clinics, so it is off here.
        product_hunt = bool(intent and intent.get("primary_queries"))
        maps_for_hunt = profile.use_maps and not product_hunt
        if product_hunt:
            observation = (
                f"Interpreted exact products={intent['products']}, "
                f"buyer types={intent['buyers']}, location={intent['location'] or '(none)'}."
            )
            decision = (
                f"Wave 1: {len(intent['primary_queries'])} exact Google searches in parallel. "
                "SERP title/snippet triage first; homepage only for ambiguous rows; "
                f"stop around {TARGET_LEADS} leads. Contacts enrich in the background."
            )
            snippet = "; ".join(intent["primary_queries"][:6])
        else:
            observation = (
                f"Seller motion={profile.sales_motion}, offer={profile.offer_class}, "
                f"buyers={profile.buyers}, geo={profile.geo_mode}, places={profile.places or ['(none)']}, "
                f"strict_geo={profile.strict_geo}, maps={'on' if profile.use_maps else 'off'}."
            )
            decision = (
                f"Wave 1: {len(wave1)} query families "
                f"({', '.join(sorted({q.family for q in wave1}))}). "
            )
            snippet = "; ".join(q.query for q in wave1[:4])

        decisions_log.append({
            "step": 1,
            "observation": observation,
            "decision": decision,
            "toolCalled": "HuntIntent",
            "toolResultSnippet": snippet,
        })

        leads = await self.web_search.hunt_leads(
            wave1[:WAVE1_QUERY_CAP],
            target_location=place,
            exclude_domains=exclude_domains,
            limit=WAVE1_RESULT_CAP,
            use_maps=maps_for_hunt,
            max_queries=WAVE1_QUERY_CAP,
        )
        classified = [
            classify_serp_row(
                row,
                hunting_buyers=profile.hunting_buyers,
                target_places=profile.places,
                strict_geo=profile.strict_geo,
                offer_categories=profile.categories,
            )
            for row in leads
        ]
        # Prefer in-geo rows and ones that name the requested buyer role (importer…)
        primary_buyer = (profile.buyers[0] or "").lower().rstrip("s") if profile.buyers else ""

        def _serp_rank(r: Dict[str, Any]) -> tuple:
            blob = f"{r.get('title') or ''} {r.get('snippet') or ''} {r.get('location') or ''}".lower()
            role_hit = 1 if primary_buyer and primary_buyer in blob else 0
            return (
                0 if r.get("reject") else 1,
                1 if r.get("geo_mentioned") else 0,
                role_hit,
                1 if (r.get("source") or "") == "maps" else 0,
            )

        classified.sort(key=_serp_rank, reverse=True)
        stats = summarize_classifications(classified)
        reject_samples: List[Dict[str, Any]] = []
        seen_reject_domains: set[str] = set()
        for row in classified:
            if not row.get("reject"):
                continue
            domain = (_domain(row.get("website")) or "").lower()
            if domain and domain in seen_reject_domains:
                continue
            if domain:
                seen_reject_domains.add(domain)
            reject_samples.append({
                "domain": domain or (row.get("company_name") or "unknown"),
                "entityType": row.get("entity_type") or "junk",
                "reason": row.get("reject_reason") or "filtered",
            })
            if len(reject_samples) >= 18:
                break
        reject_lines = [
            f"{s['domain']} — {s['entityType']}: {s['reason']}" for s in reject_samples
        ]
        decisions_log.append({
            "step": 2,
            "observation": (
                f"Wave 1 returned {len(leads)} unique URLs. "
                f"Junk {stats['junk_ratio']:.0%}, manufacturers {stats['manufacturer_ratio']:.0%}, "
                f"wrong geo {stats['wrong_geo_ratio']:.0%}, relevant {stats['relevant_count']}."
            ),
            "decision": "Inspect SERP patterns before more searches.",
            "toolCalled": "SerpClassifier",
            "toolResultSnippet": (
                f"rejected={stats['rejected']} seeds={len(stats['competitor_names'])}"
                + (f"\nFiltered out:\n" + "\n".join(reject_lines) if reject_lines else "")
            ),
            "filteredOut": reject_samples,
        })

        # --- Fast SERP triage (title + snippet) before any website fetch ---
        kept_items: List[Dict[str, Any]] = []
        ambiguous_rows: List[Dict[str, Any]] = []
        triage_reject = 0
        seen_names: set = set()
        for row in classified:
            if row.get("reject"):
                continue
            website = (row.get("website") or "").strip()
            name_key = _legal_name_key(row.get("company_name") or "")
            if name_key and name_key in seen_names and not website:
                continue
            if name_key:
                seen_names.add(name_key)
            triage = serp_triage(
                row,
                categories=profile.categories,
                buyers=profile.buyers,
            )
            row["_triage"] = triage
            verdict = triage.get("verdict")
            if verdict == "reject":
                triage_reject += 1
                continue
            if verdict == "keep":
                q = qualify_from_fast_decision(
                    row=row, profile=profile, products=products, triage=triage, site_text="",
                )
                if q.get("shouldPersist"):
                    kept_items.append({
                        "co": row, "q": q, "page": {}, "site_text": "",
                        "outreach_ready": True, "source": row.get("source") or "web",
                    })
            else:
                ambiguous_rows.append(row)

        decisions_log.append({
            "step": 3,
            "observation": (
                f"SERP triage: {len(kept_items)} keep, {len(ambiguous_rows)} ambiguous, "
                f"{triage_reject} rejected (+ {stats['rejected']} junk hosts)."
            ),
            "decision": (
                f"Target {TARGET_LEADS} leads. Homepage fetch only for ambiguous rows "
                f"when below target. No contact crawl during discovery."
            ),
            "toolCalled": "SerpTriage",
            "toolResultSnippet": f"kept={len(kept_items)} ambiguous={len(ambiguous_rows)}",
        })

        # Wave 2 only if we are short of MIN_LEADS after primary searches
        wave2 = plan_wave2(profile, stats, stats.get("learned_terms"), user_prompt=user_prompt)[:WAVE2_QUERY_CAP]
        need_wave2 = bool(wave2) and len(kept_items) < MIN_LEADS
        if need_wave2:
            more = await self.web_search.hunt_leads(
                wave2,
                target_location=place,
                exclude_domains=exclude_domains | {_domain(r.get("website")) for r in classified if r.get("website")},
                limit=WAVE2_RESULT_CAP,
                use_maps=maps_for_hunt and profile.strict_geo,
                max_queries=WAVE2_QUERY_CAP,
            )
            for row in more:
                classified_row = classify_serp_row(
                    row,
                    hunting_buyers=profile.hunting_buyers,
                    target_places=profile.places,
                    strict_geo=profile.strict_geo,
                    offer_categories=profile.categories,
                )
                classified.append(classified_row)
                if classified_row.get("reject"):
                    continue
                name_key = _legal_name_key(classified_row.get("company_name") or "")
                if name_key and name_key in seen_names and not (classified_row.get("website") or "").strip():
                    continue
                if name_key:
                    seen_names.add(name_key)
                triage = serp_triage(
                    classified_row,
                    categories=profile.categories,
                    buyers=profile.buyers,
                )
                classified_row["_triage"] = triage
                if triage.get("verdict") == "keep":
                    q = qualify_from_fast_decision(
                        row=classified_row, profile=profile, products=products,
                        triage=triage, site_text="",
                    )
                    if q.get("shouldPersist"):
                        kept_items.append({
                            "co": classified_row, "q": q, "page": {}, "site_text": "",
                            "outreach_ready": True, "source": classified_row.get("source") or "web",
                        })
                elif triage.get("verdict") == "ambiguous":
                    ambiguous_rows.append(classified_row)
            decisions_log.append({
                "step": 3.5,
                "observation": f"Wave 2: {len(wave2)} variant searches → {len(more)} URLs; kept now {len(kept_items)}.",
                "decision": "Continue only if still below target.",
                "toolCalled": "AdaptiveSearch",
                "toolResultSnippet": "; ".join(q.query for q in wave2[:3]),
            })
        else:
            decisions_log.append({
                "step": 3.5,
                "observation": (
                    f"Skipped wave 2 — already have {len(kept_items)} SERP keeps "
                    f"(min {MIN_LEADS})."
                    if len(kept_items) >= MIN_LEADS
                    else "No useful wave-2 queries."
                ),
                "decision": "Proceed to ambiguous homepage checks only if needed.",
                "toolCalled": "AdaptiveSearch",
            })

        if not kept_items and not ambiguous_rows:
            duration_ms = int((time.time() - start_time) * 1000)
            return {
                "prospects": [],
                "agent_log": {
                    "id": f"run-{int(time.time())}",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "task": user_prompt or "Lead hunt",
                    "durationMs": duration_ms,
                    "toolsUsed": ["SearchPlanner", "WebSearchTool", "SerpClassifier", "SerpTriage"],
                    "sourcesCount": len(leads),
                    "status": "CompletedWithNoCandidates",
                    "decisions": decisions_log + [{
                        "step": 4,
                        "observation": "No keep or ambiguous candidates after triage.",
                        "decision": "Do not persist junk as leads.",
                        "toolCalled": "LeadPipeline",
                    }],
                    "sellerProfile": profile_to_dict(profile),
                },
            }

        # Homepage only for ambiguous rows, and only until we hit TARGET_LEADS
        fetched_count = 0
        need_more = max(0, TARGET_LEADS - len(kept_items))
        if need_more > 0 and ambiguous_rows:
            # Round-robin ambiguous by product so one product doesn't eat the budget
            from app.agents.geo import parse_discovery_query

            by_product: Dict[str, List[Dict[str, Any]]] = {}
            product_order: List[str] = []
            for c in ambiguous_rows:
                if not (c.get("website") or "").strip():
                    continue
                prod, _r, _p = parse_discovery_query(c.get("discovery_query") or "")
                key = (prod or "general").lower()
                if key not in by_product:
                    by_product[key] = []
                    product_order.append(key)
                by_product[key].append(c)
            to_fetch: List[Dict[str, Any]] = []
            idxs = {k: 0 for k in product_order}
            fetch_cap = min(AMBIGUOUS_FETCH_CAP, max(need_more * 2, need_more + 4))
            while len(to_fetch) < fetch_cap and product_order:
                progressed = False
                for key in product_order:
                    i = idxs[key]
                    if i < len(by_product[key]):
                        to_fetch.append(by_product[key][i])
                        idxs[key] = i + 1
                        progressed = True
                        if len(to_fetch) >= fetch_cap:
                            break
                if not progressed:
                    break

            async with httpx.AsyncClient(
                timeout=4.0,
                follow_redirects=True,
                headers=HEADERS,
                limits=httpx.Limits(
                    max_connections=SCRAPE_CONCURRENCY,
                    max_keepalive_connections=SCRAPE_CONCURRENCY,
                ),
            ) as scrape_client:
                scrape_sem = asyncio.Semaphore(SCRAPE_CONCURRENCY)

                async def _scrape_one(url: str) -> Any:
                    async with scrape_sem:
                        # Homepage only — no catalog crawl during discovery
                        return await self.web_search.scrape_homepage(
                            url, limit=4000, client=scrape_client, keep_html=False,
                        )

                pages = await asyncio.gather(
                    *[_scrape_one(c["website"]) for c in to_fetch],
                    return_exceptions=True,
                )
                fetched_count = len(to_fetch)
                for cand, page in zip(to_fetch, pages):
                    if len(kept_items) >= TARGET_LEADS:
                        break
                    site_text = ""
                    if isinstance(page, dict) and page.get("ok"):
                        site_text = page.get("text") or ""
                        if page.get("location") and not (cand.get("location") or "").strip():
                            cand["location"] = page["location"]
                        if page.get("emails"):
                            cand.setdefault("_seed_emails", page["emails"])
                    triage = cand.get("_triage") or {"verdict": "ambiguous", "confidence": 0.4, "reason": ""}
                    q = qualify_from_fast_decision(
                        row=cand, profile=profile, products=products,
                        triage=triage, site_text=site_text,
                    )
                    if q.get("shouldPersist"):
                        kept_items.append({
                            "co": cand, "q": q,
                            "page": page if isinstance(page, dict) else {},
                            "site_text": site_text,
                            "outreach_ready": True,
                            "source": cand.get("source") or "web",
                        })

        decisions_log.append({
            "step": 4,
            "observation": (
                f"{len(kept_items)} candidates after triage"
                + (f"; fetched {fetched_count} ambiguous homepages." if fetched_count else " (no homepage fetches needed).")
            ),
            "decision": "Show leads now. Contact enrichment runs in the background after save.",
            "toolCalled": "FastQualify",
            "toolResultSnippet": f"kept={len(kept_items)} fetched={fetched_count}",
        })

        primary_buyer = (profile.buyers[0] or "").lower().rstrip("s") if profile.buyers else ""

        def _q_rank(item: Dict[str, Any]) -> tuple:
            q = item["q"]
            pri = {"priority": 3, "nurture": 2, "review": 1, "low": 0}.get(q.get("priority") or "", 0)
            loc_bonus = 1 if (q.get("location") or "").strip() else 0
            role_bonus = 1 if primary_buyer and primary_buyer in (
                f"{item.get('site_text') or ''} {q.get('whyThisProspect') or ''} "
                f"{(item.get('co') or {}).get('snippet') or ''}"
            ).lower() else 0
            return (pri, role_bonus, loc_bonus, int(q.get("fitScore") or 0))

        kept_items.sort(key=_q_rank, reverse=True)

        def _product_key(item: Dict[str, Any]) -> str:
            from app.agents.geo import parse_discovery_query

            dq = (item.get("co") or {}).get("discovery_query") or ""
            product, _role, _place = parse_discovery_query(dq)
            if product:
                return product.lower()
            fb = (item.get("q") or {}).get("fitBreakdown") or {}
            return (fb.get("huntProduct") or "general").lower()

        def _diversify(pool: List[Dict[str, Any]], cap: int) -> List[Dict[str, Any]]:
            if cap <= 0 or not pool:
                return []
            buckets: Dict[str, List[Dict[str, Any]]] = {}
            order: List[str] = []
            for item in pool:
                key = _product_key(item)
                if key not in buckets:
                    buckets[key] = []
                    order.append(key)
                buckets[key].append(item)
            picked: List[Dict[str, Any]] = []
            idxs = {k: 0 for k in order}
            while len(picked) < cap:
                progressed = False
                for key in order:
                    i = idxs[key]
                    if i < len(buckets[key]):
                        picked.append(buckets[key][i])
                        idxs[key] = i + 1
                        progressed = True
                        if len(picked) >= cap:
                            break
                if not progressed:
                    break
            return picked

        target = min(limit, SAVE_CAP, max(TARGET_LEADS, MIN_LEADS))
        qualified = _diversify(kept_items, target)
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Parallel contact crawl for the shortlist (homepage + /contact). Hard time budget.
        contact_sem = asyncio.Semaphore(CONTACT_CONCURRENCY)
        contact_hits = 0

        async def _fill_contacts(item: Dict[str, Any]) -> None:
            nonlocal contact_hits
            co = item["co"]
            page = item.get("page") or {}
            website = (co.get("website") or "").strip()
            phone = co.get("phone") or ""
            seed_emails = list(page.get("emails") or co.get("_seed_emails") or [])
            if page.get("phones") and not phone:
                phone = (page.get("phones") or [""])[0] or phone
            email = (seed_emails[0] if seed_emails else "") or ""
            contacts: List[Dict[str, Any]] = []
            if seed_emails:
                contacts = [{
                    "type": "email", "value": seed_emails[0], "label": "Email",
                    "source": "site", "role": "general",
                }]
            if website:
                async with contact_sem:
                    try:
                        found = await discover_contacts(
                            website=website,
                            homepage_html="",
                            homepage_text=item.get("site_text") or "",
                            homepage_url=page.get("url") or website,
                            seed_phone=phone,
                            seed_emails=seed_emails,
                        )
                        if found.get("email"):
                            email = found["email"]
                        phone = found.get("phone") or phone
                        contacts = found.get("contacts") or contacts
                    except Exception:
                        pass
            item["email"] = email
            item["phone"] = phone
            item["contacts"] = contacts
            if email:
                contact_hits += 1

        if qualified:
            tasks = [asyncio.create_task(_fill_contacts(item)) for item in qualified]
            done, pending = await asyncio.wait(tasks, timeout=CONTACT_BUDGET_SEC)
            for t in pending:
                t.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        decisions_log.append({
            "step": 4.5,
            "observation": (
                f"Contact crawl: {contact_hits}/{len(qualified)} emails in "
                f"≤{int(CONTACT_BUDGET_SEC)}s ({CONTACT_CONCURRENCY} concurrent)."
            ),
            "decision": "Leads without email are still saved; background enrich continues.",
            "toolCalled": "ContactFinder",
            "toolResultSnippet": f"emails={contact_hits}",
        })

        async def _enrich(item: Dict[str, Any]) -> Dict[str, Any]:
            co = item["co"]
            q = item["q"]
            source = item["source"]
            email = item.get("email") or ""
            phone = item.get("phone") or co.get("phone") or ""
            contacts = list(item.get("contacts") or [])
            timeline = [
                {"time": time.strftime("%H:%M"), "action": f"Discovered via {source} ({co.get('discovery_pool') or 'search'})"},
                {"time": time.strftime("%H:%M"), "action": f"Fit {q['fitSummary']} · {q['priority']} (fast SERP triage)"},
            ]
            if email:
                timeline.append({"time": time.strftime("%H:%M"), "action": f"Found contact email {email}"})
            else:
                timeline.append({"time": time.strftime("%H:%M"), "action": "No public email yet — background enrich continues"})
            return {
                "id": f"prospect-{uuid4().hex[:10]}",
                "companyName": co.get("company_name") or "Unknown",
                "website": co.get("website") or "",
                "location": (q.get("location") or co.get("location") or "").strip(),
                "industry": (q.get("industry") or "")[:80],
                "companySize": "",
                "phone": phone,
                "email": email,
                "contacts": contacts,
                "contactAgain": True,
                "lastReplyAt": "",
                "replySummary": "",
                "source": source,
                "fitScore": q["fitScore"],
                "fitBreakdown": q["fitBreakdown"],
                "whyThisProspect": q["whyThisProspect"],
                "whyNow": q["whyNow"],
                "icpFit": q["icpFit"],
                "offerFit": q["offerFit"],
                "motionFit": q["motionFit"],
                "intent": q["intent"],
                "confidence": q["confidence"],
                "priority": q["priority"],
                "evidence": q["evidence"],
                "entityType": co.get("entity_type") or "company",
                "discoveryPool": co.get("discovery_pool") or "",
                "buyingSignals": q["buyingSignals"],
                "productFit": q["productFit"],
                "recommendedApproach": q["recommendedApproach"],
                "outreachDraft": None,
                "stage": "To contact",
                "discoveredAt": now,
                "agentTimeline": timeline,
            }

        prospects = [await _enrich(item) for item in qualified]

        def _rank(p: Dict[str, Any]) -> tuple:
            # Prefer leads with email so "With email" is useful out of the box
            has_email = 1 if (p.get("email") or "").strip() else 0
            pri = {"priority": 3, "nurture": 2, "review": 1, "low": 0}.get(p.get("priority") or "", 0)
            return (has_email, pri, int(p.get("fitScore") or 0))

        prospects.sort(key=_rank, reverse=True)

        duration_ms = int((time.time() - start_time) * 1000)
        with_email = sum(1 for p in prospects if (p.get("email") or "").strip())
        agent_log = {
            "id": f"run-{int(time.time())}",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "task": user_prompt or f"Find buyers ({profile.sales_motion})",
            "durationMs": duration_ms,
            "toolsUsed": ["SearchPlanner", "WebSearchTool", "SerpClassifier", "SerpTriage"]
            + (["SiteFetch"] if fetched_count else [])
            + (["ContactFinder"] if qualified else []),
            "sourcesCount": len(classified),
            "status": "Completed" if prospects else "CompletedWithNoCandidates",
            "sellerProfile": profile_to_dict(profile),
            "decisions": decisions_log + [{
                "step": 5,
                "observation": (
                    f"Returned {len(prospects)} leads ({with_email} with email) in {duration_ms}ms "
                    f"(target {TARGET_LEADS})."
                ),
                "decision": (
                    "Discovery stays SERP-first; contact pages are crawled in parallel "
                    f"with a {int(CONTACT_BUDGET_SEC)}s budget before save."
                ),
                "toolCalled": "LeadPipeline",
                "toolResultSnippet": f"{len(prospects)} leads · {with_email} emails · {fetched_count} homepage checks",
            }],
        }
        return {"prospects": prospects, "agent_log": agent_log, "prospect": prospects[0] if prospects else None}
