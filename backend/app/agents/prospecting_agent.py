"""Lead-hunting agent: planned discovery → classify → cheap fetch → Fit vs Intent."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4
from urllib.parse import urlparse

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
from app.agents.relevance import qualify_from_fast_decision, serp_triage, website_relevance
from app.tools.web_search import WebSearchTool
from app.services.enrichment import enrich_website


# Multi-query Google hunt → Stage-1 junk filter → Stage-2 website inspect → contacts.
# Targets are goals, not guarantees — never invent leads to hit them.
MIN_LEADS = 20
PREFERRED_LEADS = 30
TARGET_LEADS = PREFERRED_LEADS
MAX_LEADS = 50
SAVE_CAP = 50
STRONG_SAVE = 30
AVERAGE_SAVE = 20
WAVE1_RESULT_CAP = 320
WAVE2_RESULT_CAP = 120
MIN_CANDIDATES_BEFORE_SKIP_WAVE2 = MIN_LEADS
DEFAULT_HUNT_LIMIT = PREFERRED_LEADS
WAVE1_QUERY_CAP = 48
WAVE2_QUERY_CAP = 12
# Site inspect + contact pages + optional Hunter — bounded per domain
CONTACT_CONCURRENCY = 10
CONTACT_BUDGET_SEC = 70.0
SITE_ENRICH_TIMEOUT_SEC = 14.0
CONTACT_ENRICH_CAP = 80


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
        limit = min(max(limit or DEFAULT_HUNT_LIMIT, MIN_LEADS), MAX_LEADS)
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
                f"Stage-1 junk filter → Stage-2 website inspect → contacts; "
                f"target {PREFERRED_LEADS} leads (max {MAX_LEADS})."
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

        # --- Stage 1: cheap SERP junk filter (title/snippet/URL only) ---
        promising_rows: List[Dict[str, Any]] = []
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
            if triage.get("verdict") == "reject":
                triage_reject += 1
                continue
            promising_rows.append(row)

        decisions_log.append({
            "step": 3,
            "observation": (
                f"Stage-1 SERP filter: {len(promising_rows)} promising candidates, "
                f"{triage_reject} rejected (+ {stats['rejected']} junk hosts)."
            ),
            "decision": (
                f"Target {PREFERRED_LEADS} leads (min {MIN_LEADS}, max {MAX_LEADS}). "
                f"Website inspect + contact enrich for promising domains only."
            ),
            "toolCalled": "SerpTriage",
            "toolResultSnippet": f"promising={len(promising_rows)} rejected={triage_reject}",
        })

        # Wave 2 variants only when primary pool is thin
        wave2 = plan_wave2(profile, stats, stats.get("learned_terms"), user_prompt=user_prompt)[:WAVE2_QUERY_CAP]
        need_wave2 = bool(wave2) and len(promising_rows) < MIN_LEADS
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
                if triage.get("verdict") != "reject":
                    promising_rows.append(classified_row)
            decisions_log.append({
                "step": 3.5,
                "observation": (
                    f"Wave 2: {len(wave2)} variant searches → {len(more)} URLs; "
                    f"promising now {len(promising_rows)}."
                ),
                "decision": "Continue website inspection on the combined pool.",
                "toolCalled": "AdaptiveSearch",
                "toolResultSnippet": "; ".join(q.query for q in wave2[:3]),
            })
        else:
            decisions_log.append({
                "step": 3.5,
                "observation": (
                    f"Skipped wave 2 — already have {len(promising_rows)} promising candidates "
                    f"(min {MIN_LEADS})."
                    if len(promising_rows) >= MIN_LEADS
                    else "No useful wave-2 queries."
                ),
                "decision": "Proceed to website inspection.",
                "toolCalled": "AdaptiveSearch",
            })

        if not promising_rows:
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
                        "observation": "No promising candidates after Stage-1 filter.",
                        "decision": "Do not persist junk as leads.",
                        "toolCalled": "LeadPipeline",
                    }],
                    "sellerProfile": profile_to_dict(profile),
                },
            }

        # Domain-level merge: one enrichment per domain, keep all matched intents
        by_domain: Dict[str, Dict[str, Any]] = {}
        for row in promising_rows:
            website = (row.get("website") or "").strip()
            key = _domain(website) or _legal_name_key(row.get("company_name") or "") or uuid4().hex
            if key in by_domain:
                kept = by_domain[key]
                dq = (row.get("discovery_query") or "").strip()
                matches = kept.setdefault("discovery_queries", [])
                if dq and dq not in matches:
                    matches.append(dq)
                for extra_q in row.get("discovery_queries") or []:
                    if extra_q and extra_q not in matches:
                        matches.append(extra_q)
                continue
            row = dict(row)
            intents = list(row.get("discovery_queries") or [])
            dq0 = (row.get("discovery_query") or "").strip()
            if dq0 and dq0 not in intents:
                intents.insert(0, dq0)
            row["discovery_queries"] = intents
            by_domain[key] = row

        domain_pool = list(by_domain.values())

        def _product_key_row(row: Dict[str, Any]) -> str:
            from app.agents.geo import parse_discovery_query

            dq = row.get("discovery_query") or ""
            product, _role, _place = parse_discovery_query(dq)
            return (product or "general").lower()

        def _diversify_rows(pool: List[Dict[str, Any]], cap: int) -> List[Dict[str, Any]]:
            if cap <= 0 or not pool:
                return []
            buckets: Dict[str, List[Dict[str, Any]]] = {}
            order: List[str] = []
            for row in pool:
                key = _product_key_row(row)
                if key not in buckets:
                    buckets[key] = []
                    order.append(key)
                buckets[key].append(row)
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

        inspect_pool = _diversify_rows(domain_pool, min(len(domain_pool), CONTACT_ENRICH_CAP))
        contact_sem = asyncio.Semaphore(CONTACT_CONCURRENCY)
        kept_items: List[Dict[str, Any]] = []
        irrelevant_count = 0
        email_hits = 0
        inspected = 0

        async def _inspect_one(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            nonlocal irrelevant_count, email_hits, inspected
            website = (row.get("website") or "").strip()
            triage = row.get("_triage") or {"verdict": "keep", "confidence": 0.5, "reason": ""}
            site_text = ""
            page: Dict[str, Any] = {}
            email = ""
            phone = row.get("phone") or ""
            contacts: List[Dict[str, Any]] = []
            email_status = "email_not_found"
            email_source = ""

            if website:
                async with contact_sem:
                    try:
                        found = await asyncio.wait_for(
                            enrich_website(
                                website,
                                seed_email="",
                                seed_phone=phone,
                                seed_contacts=[],
                                use_hunter=True,
                            ),
                            timeout=SITE_ENRICH_TIMEOUT_SEC,
                        )
                    except asyncio.TimeoutError:
                        found = {"email": "", "phone": phone, "contacts": [], "site_text": "", "sources": []}
                    except Exception:
                        found = {"email": "", "phone": phone, "contacts": [], "site_text": "", "sources": []}
                inspected += 1
                site_text = (found.get("site_text") or "")[:8000]
                page = {"ok": bool(site_text), "text": site_text, "emails": []}
                if found.get("email"):
                    email = found["email"]
                    email_hits += 1
                    email_status = "email_found"
                    sources = found.get("sources") or []
                    email_source = sources[0] if sources else "website"
                phone = found.get("phone") or phone
                contacts = list(found.get("contacts") or [])
                if found.get("location") and not (row.get("location") or "").strip():
                    row["location"] = found["location"]

            from app.agents.geo import parse_discovery_query

            dq = (row.get("discovery_query") or "")
            product, role, _place = parse_discovery_query(dq)
            if not product:
                product = (profile.categories[0] if profile.categories else "") or ""
            if not role:
                role = (profile.buyers[0] if profile.buyers else "distributors") or "distributors"

            graded = website_relevance(
                product=product,
                buyer_type=role,
                company_name=row.get("company_name") or "",
                title=row.get("title") or "",
                snippet=row.get("snippet") or "",
                site_text=site_text or f"{row.get('title') or ''}\n{row.get('snippet') or ''}",
                categories=list(profile.categories or []),
            )
            if graded.get("level") == "irrelevant" or not graded.get("relevant"):
                irrelevant_count += 1
                return None

            q = qualify_from_fast_decision(
                row=row,
                profile=profile,
                products=products,
                triage=triage,
                site_text=site_text or f"{row.get('title') or ''}\n{row.get('snippet') or ''}",
            )
            if not q.get("shouldPersist"):
                irrelevant_count += 1
                return None

            fb = q.setdefault("fitBreakdown", {})
            fb["relevance"] = graded.get("level") or fb.get("relevance")
            fb["matchedSearchIntents"] = list(row.get("discovery_queries") or [])
            fb["emailStatus"] = email_status
            fb["emailSource"] = email_source
            if graded.get("evidence"):
                fb["relevanceEvidence"] = graded["evidence"]

            return {
                "co": row,
                "q": q,
                "page": page,
                "site_text": site_text,
                "email": email,
                "phone": phone,
                "contacts": contacts,
                "email_status": email_status,
                "email_source": email_source,
                "relevance": graded.get("level") or "medium",
                "outreach_ready": True,
                "source": row.get("source") or "web",
            }

        if inspect_pool:
            tasks = [asyncio.create_task(_inspect_one(row)) for row in inspect_pool]
            done, pending = await asyncio.wait(tasks, timeout=CONTACT_BUDGET_SEC)
            for t in pending:
                t.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            for t in done:
                try:
                    item = t.result()
                except Exception:
                    continue
                if item:
                    kept_items.append(item)
                    if len(kept_items) >= MAX_LEADS:
                        break

        decisions_log.append({
            "step": 4,
            "observation": (
                f"Stage-2 inspect: {inspected}/{len(inspect_pool)} domains checked; "
                f"{len(kept_items)} relevant (high/medium/low), {irrelevant_count} irrelevant; "
                f"{email_hits} emails found."
            ),
            "decision": (
                "Relevance from website content; email is enrichment only. "
                "Keep relevant companies even without email."
            ),
            "toolCalled": "WebsiteInspect",
            "toolResultSnippet": (
                f"relevant={len(kept_items)} emails={email_hits} irrelevant={irrelevant_count}"
            ),
        })

        primary_buyer = (profile.buyers[0] or "").lower().rstrip("s") if profile.buyers else ""

        def _q_rank(item: Dict[str, Any]) -> tuple:
            q = item["q"]
            rel = {"high": 3, "medium": 2, "low": 1}.get(item.get("relevance") or "", 0)
            has_email = 1 if (item.get("email") or "").strip() else 0
            pri = {"priority": 3, "nurture": 2, "review": 1, "low": 0}.get(q.get("priority") or "", 0)
            loc_bonus = 1 if (q.get("location") or "").strip() else 0
            role_bonus = 1 if primary_buyer and primary_buyer in (
                f"{item.get('site_text') or ''} {q.get('whyThisProspect') or ''} "
                f"{(item.get('co') or {}).get('snippet') or ''}"
            ).lower() else 0
            return (has_email, rel, pri, role_bonus, loc_bonus, int(q.get("fitScore") or 0))

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

        # Prefer contactable, but never drop relevant no-email leads to invent volume
        with_email = [i for i in kept_items if (i.get("email") or "").strip()]
        without_email = [i for i in kept_items if not (i.get("email") or "").strip()]
        target = min(limit, SAVE_CAP, MAX_LEADS)
        preferred = min(PREFERRED_LEADS, target)
        qualified = _diversify(with_email, preferred)
        if len(qualified) < preferred:
            need = preferred - len(qualified)
            qualified.extend(_diversify(without_email, need))
        if len(qualified) < target and len(kept_items) > len(qualified):
            # Fill toward max from remaining relevant (email first via sort)
            seen_ids = {id(x) for x in qualified}
            for item in kept_items:
                if len(qualified) >= target:
                    break
                if id(item) not in seen_ids:
                    qualified.append(item)
                    seen_ids.add(id(item))

        decisions_log.append({
            "step": 4.5,
            "observation": (
                f"Shortlist {len(qualified)} relevant leads "
                f"({sum(1 for i in qualified if (i.get('email') or '').strip())} with email) "
                f"from {len(kept_items)} relevant / {len(inspect_pool)} inspected."
            ),
            "decision": (
                f"Prefer emailed companies, keep relevant without email. "
                f"Target {PREFERRED_LEADS} (cap {MAX_LEADS})."
            ),
            "toolCalled": "ContactFinder",
            "toolResultSnippet": f"saved={len(qualified)} emails={email_hits}",
        })

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ")

        async def _enrich(item: Dict[str, Any]) -> Dict[str, Any]:
            co = item["co"]
            q = item["q"]
            source = item["source"]
            email = item.get("email") or ""
            phone = item.get("phone") or co.get("phone") or ""
            contacts = list(item.get("contacts") or [])
            email_status = item.get("email_status") or ("email_found" if email else "email_not_found")
            timeline = [
                {
                    "time": time.strftime("%H:%M"),
                    "action": f"Discovered via {source} ({co.get('discovery_pool') or 'search'})",
                },
                {
                    "time": time.strftime("%H:%M"),
                    "action": (
                        f"Fit {q['fitSummary']} · {item.get('relevance') or q['priority']} "
                        f"(website inspect)"
                    ),
                },
            ]
            if email:
                timeline.append({
                    "time": time.strftime("%H:%M"),
                    "action": f"Found contact email {email} ({item.get('email_source') or 'website'})",
                })
            else:
                timeline.append({
                    "time": time.strftime("%H:%M"),
                    "action": "Email not found on inspected pages — lead kept as relevant",
                })
            fb = dict(q.get("fitBreakdown") or {})
            fb["emailStatus"] = email_status
            fb["emailSource"] = item.get("email_source") or ""
            fb["matchedSearchIntents"] = list(co.get("discovery_queries") or fb.get("matchedSearchIntents") or [])
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
                "fitBreakdown": fb,
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
            has_email = 1 if (p.get("email") or "").strip() else 0
            fb = p.get("fitBreakdown") or {}
            rel = {"high": 3, "medium": 2, "low": 1}.get(fb.get("relevance") or "", 0)
            pri = {"priority": 3, "nurture": 2, "review": 1, "low": 0}.get(p.get("priority") or "", 0)
            return (has_email, rel, pri, int(p.get("fitScore") or 0))

        prospects.sort(key=_rank, reverse=True)

        duration_ms = int((time.time() - start_time) * 1000)
        with_email_n = sum(1 for p in prospects if (p.get("email") or "").strip())
        agent_log = {
            "id": f"run-{int(time.time())}",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "task": user_prompt or f"Find buyers ({profile.sales_motion})",
            "durationMs": duration_ms,
            "toolsUsed": [
                "SearchPlanner", "WebSearchTool", "SerpClassifier", "SerpTriage",
                "WebsiteInspect", "ContactFinder",
            ],
            "sourcesCount": len(classified),
            "status": "Completed" if prospects else "CompletedWithNoCandidates",
            "sellerProfile": profile_to_dict(profile),
            "decisions": decisions_log + [{
                "step": 5,
                "observation": (
                    f"Returned {len(prospects)} relevant leads ({with_email_n} with email) "
                    f"in {duration_ms}ms after inspecting {inspected} domains."
                ),
                "decision": (
                    "Independent product×buyer Google searches → Stage-1 junk filter → "
                    "website relevance → contact enrichment. Email is not a relevance gate."
                ),
                "toolCalled": "LeadPipeline",
                "toolResultSnippet": (
                    f"{len(prospects)} leads · {with_email_n} emails · inspected={inspected}"
                ),
            }],
        }
        return {"prospects": prospects, "agent_log": agent_log, "prospect": prospects[0] if prospects else None}
