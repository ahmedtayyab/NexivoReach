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
from app.agents.qualify import qualify_account
from app.agents.relevance import qualify_account_with_ai
from app.tools.web_search import WebSearchTool, HEADERS
from app.tools.contact_finder import discover_contacts, contacts_from_text
from app.providers.factory import get_ai_provider


FETCH_CAP = 160
SAVE_CAP = 80
STRONG_SAVE = 40  # amazing / ready to pursue
AVERAGE_SAVE = 40  # workable / worth a look
WAVE1_RESULT_CAP = 400
WAVE2_RESULT_CAP = 160
ENRICH_CAP = 0  # drafts belong in Outreach — keep Discover fast
CONTACT_DURING_HUNT = 0  # contact crawl after AI qualification
SCRAPE_CONCURRENCY = 18
SCRAPE_BATCH = 18
# Skip wave 2 once we already have enough relevant SERP hits
MIN_CANDIDATES_BEFORE_SKIP_WAVE2 = 80
DEFAULT_HUNT_LIMIT = 80
# Stop fetching more sites once we can fill this many persistable leads
EARLY_EXIT_PERSISTABLE = 100
WAVE1_QUERY_CAP = 48
WAVE2_QUERY_CAP = 24
AI_QUALIFY_CONCURRENCY = 8


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
                f"Wave 1: {len(intent['primary_queries'])} exact product×buyer×location Google searches "
                f"(no generic category expansion). "
                f"{len(intent.get('volume_queries') or [])} close variants held for wave 2 if thin. "
                "AI decides business relevance after website fetch."
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

        wave2 = plan_wave2(profile, stats, stats.get("learned_terms"), user_prompt=user_prompt)[:WAVE2_QUERY_CAP]
        # Deepen only when the first wave is thin — saves a full search round when we already have volume
        need_wave2 = bool(wave2) and stats["relevant_count"] < MIN_CANDIDATES_BEFORE_SKIP_WAVE2
        if need_wave2:
            more = await self.web_search.hunt_leads(
                wave2,
                target_location=place,
                exclude_domains=exclude_domains | {_domain(r.get("website")) for r in classified if r.get("website")},
                limit=WAVE2_RESULT_CAP,
                use_maps=maps_for_hunt and profile.strict_geo,
                max_queries=WAVE2_QUERY_CAP,
            )
            extra = [
                classify_serp_row(
                    row,
                    hunting_buyers=profile.hunting_buyers,
                    target_places=profile.places,
                    strict_geo=profile.strict_geo,
                    offer_categories=profile.categories,
                )
                for row in more
            ]
            classified.extend(extra)
            decisions_log.append({
                "step": 3,
                "observation": f"Wave 2 ran {len(wave2)} follow-up searches → {len(more)} new URLs.",
                "decision": "Refine junk/geo + intent-overlay queries for timing signals.",
                "toolCalled": "AdaptiveSearch",
                "toolResultSnippet": "; ".join(q.query for q in wave2[:3]),
            })
        else:
            decisions_log.append({
                "step": 3,
                "observation": "No second wave (enough relevant hits, or nothing useful to refine).",
                "decision": "Proceed to homepage inspection on survivors.",
                "toolCalled": "AdaptiveSearch",
            })

        candidates = []
        seen_names = set()
        for row in classified:
            if row.get("reject"):
                continue
            website = row.get("website") or ""
            name_key = _legal_name_key(row.get("company_name") or "")
            if name_key and name_key in seen_names and not website:
                continue
            if name_key:
                seen_names.add(name_key)
            candidates.append(row)

        if not candidates:
            duration_ms = int((time.time() - start_time) * 1000)
            return {
                "prospects": [],
                "agent_log": {
                    "id": f"run-{int(time.time())}",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "task": user_prompt or "Lead hunt",
                    "durationMs": duration_ms,
                    "toolsUsed": ["SearchPlanner", "WebSearchTool", "SerpClassifier"],
                    "sourcesCount": len(leads),
                    "status": "CompletedWithNoCandidates",
                    "decisions": decisions_log + [{
                        "step": 4,
                        "observation": "Every SERP row was excluded (directories, factories, jobs, or wrong geo).",
                        "decision": "Do not persist junk as leads.",
                        "toolCalled": "LeadPipeline",
                    }],
                    "sellerProfile": profile_to_dict(profile),
                },
            }

    # Also diversify fetch order so homepage scrapes cover every hunt product
        to_fetch_raw = [c for c in candidates if (c.get("website") or "").strip()]
        by_product: Dict[str, List[Dict[str, Any]]] = {}
        product_order: List[str] = []
        for c in to_fetch_raw:
            from app.agents.geo import parse_discovery_query

            prod, _r, _p = parse_discovery_query(c.get("discovery_query") or "")
            key = (prod or "general").lower()
            if key not in by_product:
                by_product[key] = []
                product_order.append(key)
            by_product[key].append(c)
        to_fetch: List[Dict[str, Any]] = []
        idxs = {k: 0 for k in product_order}
        while len(to_fetch) < FETCH_CAP and product_order:
            progressed = False
            for key in product_order:
                i = idxs[key]
                bucket = by_product[key]
                if i < len(bucket):
                    to_fetch.append(bucket[i])
                    idxs[key] = i + 1
                    progressed = True
                    if len(to_fetch) >= FETCH_CAP:
                        break
            if not progressed:
                break
        # Homepage-only for speed; deep about/news pages skipped during hunt.
        # Scrape in batches and stop early once we have enough persistable leads.
        text_by_domain: Dict[str, Dict[str, Any]] = {}
        fetched_count = 0

        async with httpx.AsyncClient(
            timeout=5.0,
            follow_redirects=True,
            headers=HEADERS,
            limits=httpx.Limits(max_connections=SCRAPE_CONCURRENCY, max_keepalive_connections=SCRAPE_CONCURRENCY),
        ) as scrape_client:
            scrape_sem = asyncio.Semaphore(SCRAPE_CONCURRENCY)

            async def _scrape_one(url: str) -> Any:
                async with scrape_sem:
                    return await self.web_search.scrape_relevance_pages(
                        url, limit=8000, client=scrape_client,
                    )

            for batch_start in range(0, len(to_fetch), SCRAPE_BATCH):
                batch = to_fetch[batch_start : batch_start + SCRAPE_BATCH]
                pages = await asyncio.gather(
                    *[_scrape_one(c["website"]) for c in batch],
                    return_exceptions=True,
                )
                fetched_count += len(batch)
                for cand, page in zip(batch, pages):
                    dom = _domain(cand.get("website") or "")
                    if isinstance(page, dict) and page.get("ok"):
                        page = {**page}
                        page.pop("html", None)
                        text_by_domain[dom] = page
                        if page.get("location") and not (cand.get("location") or "").strip():
                            cand["location"] = page["location"]
                        elif page.get("location") and len(str(page["location"])) > len(str(cand.get("location") or "")):
                            cand["location"] = page["location"]
                        if page.get("emails"):
                            cand.setdefault("_seed_emails", page["emails"])
                    else:
                        text_by_domain[dom] = {
                            "text": "", "url": cand.get("website") or "", "ok": False,
                            "location": "", "emails": [],
                        }

                # Early exit: enough scraped sites to build a solid shortlist
                ok_sites = sum(1 for v in text_by_domain.values() if v.get("ok") and (v.get("text") or "").strip())
                if ok_sites >= EARLY_EXIT_PERSISTABLE and fetched_count >= min(24, len(to_fetch)):
                    break

        decisions_log.append({
            "step": 4,
            "observation": (
                f"{len(candidates)} candidates after exclusions; "
                f"fetched {fetched_count} sites (cap {FETCH_CAP}, early-exit at {EARLY_EXIT_PERSISTABLE})."
            ),
            "decision": (
                "AI qualifies business relevance from homepage (+ catalog page when thin). "
                "Missing location on the page is not a reject. Exact product SKU not required."
            ),
            "toolCalled": "SiteFetch",
            "toolResultSnippet": f"{sum(1 for v in text_by_domain.values() if v.get('ok'))} live sites",
        })

        # Qualify with AI (search literally → qualify intelligently).
        seller_brief = " ".join(
            str(x) for x in [
                business.get("name"),
                business.get("description"),
                ", ".join(str(c) for c in (business.get("primaryCategories") or business.get("primary_categories") or [])[:6]),
            ] if x
        ).strip()
        provider = get_ai_provider()
        ai_sem = asyncio.Semaphore(AI_QUALIFY_CONCURRENCY)
        qualified: List[Dict[str, Any]] = []
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ")

        async def _qualify_one(co: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            dom = _domain(co.get("website") or "")
            page = text_by_domain.get(dom) or {}
            site_text = page.get("text") or ""
            async with ai_sem:
                try:
                    q = await qualify_account_with_ai(
                        row=co,
                        site_text=site_text,
                        profile=profile,
                        products=products,
                        page_url=page.get("url") or co.get("website") or "",
                        provider=provider,
                        seller_brief=seller_brief,
                    )
                except Exception:
                    q = qualify_account(
                        row=co,
                        site_text=site_text,
                        profile=profile,
                        products=products,
                        page_url=page.get("url") or co.get("website") or "",
                    )
            if not q.get("shouldPersist"):
                return None
            fit_summary = (q.get("fitSummary") or "").lower()
            priority = (q.get("priority") or "").lower()
            outreach_ready = fit_summary == "high" or priority in ("priority", "nurture")
            return {
                "co": co,
                "q": q,
                "page": page,
                "site_text": site_text,
                "outreach_ready": outreach_ready,
                "source": co.get("source") or "web",
            }

        qualify_jobs = []
        for co in candidates:
            dom = _domain(co.get("website") or "")
            page = text_by_domain.get(dom) or {}
            site_text = page.get("text") or ""
            # Prefer fetched rows; still allow thin SERP-only when we have capacity
            if not site_text and dom and dom not in text_by_domain and len(qualify_jobs) >= SAVE_CAP * 2:
                continue
            qualify_jobs.append(co)

        qualify_results = await asyncio.gather(*[_qualify_one(co) for co in qualify_jobs])
        for item in qualify_results:
            if item:
                qualified.append(item)

        decisions_log.append({
            "step": 4.5,
            "observation": (
                f"AI relevance kept {len(qualified)} of {len(qualify_jobs)} inspected companies."
            ),
            "decision": "Contact discovery runs after relevance — email is optional.",
            "toolCalled": "AIRelevance",
            "toolResultSnippet": f"provider={provider.name()}",
        })

        def _q_rank(item: Dict[str, Any]) -> tuple:
            q = item["q"]
            intent_rank = {"high": 2, "low": 1, "none": 0}.get(q.get("intent") or "none", 0)
            pri = {"priority": 3, "nurture": 2, "review": 1, "low": 0}.get(q.get("priority") or "", 0)
            loc_bonus = 1 if (q.get("location") or "").strip() else 0
            role_bonus = 1 if primary_buyer and primary_buyer in (
                f"{item.get('site_text') or ''} {q.get('whyThisProspect') or ''}"
            ).lower() else 0
            scraped = 1 if (item.get("site_text") or "").strip() else 0
            return (pri, role_bonus, scraped, loc_bonus, intent_rank, int(q.get("fitScore") or 0))

        qualified.sort(key=_q_rank, reverse=True)

        def _is_strong(item: Dict[str, Any]) -> bool:
            q = item["q"]
            fit = (q.get("fitSummary") or "").lower()
            pri = (q.get("priority") or "").lower()
            return fit == "high" or pri in ("priority", "nurture") or int(q.get("fitScore") or 0) >= 70

        def _product_key(item: Dict[str, Any]) -> str:
            from app.agents.geo import parse_discovery_query

            dq = (item.get("co") or {}).get("discovery_query") or ""
            product, _role, _place = parse_discovery_query(dq)
            if product:
                return product.lower()
            fb = (item.get("q") or {}).get("fitBreakdown") or {}
            return (fb.get("huntProduct") or "general").lower()

        def _diversify(pool: List[Dict[str, Any]], cap: int) -> List[Dict[str, Any]]:
            """Round-robin across hunt products so straps don't fill the whole shortlist."""
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

        strong_pool = [item for item in qualified if _is_strong(item)]
        strong = _diversify(strong_pool, STRONG_SAVE)
        strong_ids = {id(item) for item in strong}
        average_pool = [item for item in qualified if id(item) not in strong_ids]
        average = _diversify(average_pool, AVERAGE_SAVE)
        if len(strong) < STRONG_SAVE and average:
            need = STRONG_SAVE - len(strong)
            promoted = average[:need]
            average = average[need:need + AVERAGE_SAVE]
            strong.extend(promoted)

        for i, item in enumerate(strong):
            q = item["q"]
            if (q.get("priority") or "").lower() not in ("priority", "nurture"):
                q["priority"] = "nurture" if int(q.get("fitScore") or 0) >= 55 else "review"
            if (q.get("fitSummary") or "").lower() == "low":
                q["fitSummary"] = "medium"
            item["outreach_ready"] = True
            item["tier"] = "strong"
            item["want_draft"] = False
            item["want_contacts"] = i < CONTACT_DURING_HUNT
        for item in average:
            q = item["q"]
            if (q.get("priority") or "").lower() in ("priority", "nurture", "reject"):
                q["priority"] = "review"
            elif (q.get("priority") or "").lower() not in ("review", "low"):
                q["priority"] = "review"
            item["outreach_ready"] = False
            item["tier"] = "average"
            item["want_draft"] = False
            item["want_contacts"] = False

        qualified = (strong + average)[: min(limit, SAVE_CAP)]

        seller_name = (business.get("name") or "Sales Team").strip() or "Sales Team"
        contact_sem = asyncio.Semaphore(10)
        draft_sem = asyncio.Semaphore(6)

        async def _fill_contacts(item: Dict[str, Any]) -> None:
            """Always run during Discover — user should never need a manual Find email click."""
            co = item["co"]
            page = item["page"]
            site_text = item.get("site_text") or ""
            website = (co.get("website") or "").strip()
            phone = co.get("phone") or ""
            seed_emails = list(page.get("emails") or co.get("_seed_emails") or [])
            if page.get("phones") and not phone:
                phone = (page.get("phones") or [""])[0] or phone

            contacts: List[Dict[str, Any]] = []
            email = ""
            if seed_emails:
                cheap = contacts_from_text(
                    site_text, website=website, seed_phone=phone, seed_emails=seed_emails,
                )
                contacts = cheap.get("contacts") or []
                email = cheap.get("email") or ""
                phone = cheap.get("phone") or phone

            if website:
                async with contact_sem:
                    try:
                        found = await discover_contacts(
                            website=website,
                            homepage_html=(page.get("html") or "")[:400000],
                            homepage_text=site_text,
                            homepage_url=page.get("url") or website,
                            seed_phone=phone,
                            seed_emails=seed_emails,
                        )
                        contacts = found.get("contacts") or contacts
                        if found.get("email"):
                            email = found["email"]
                        phone = found.get("phone") or phone
                    except Exception:
                        pass

            page.pop("html", None)
            if email and not any(
                (c.get("type") == "email" and (c.get("value") or "").lower() == email.lower())
                for c in contacts
            ):
                contacts = [{
                    "type": "email", "value": email, "label": "Email",
                    "source": "site", "role": "general",
                }, *contacts]
            item["email"] = email
            item["phone"] = phone
            item["contacts"] = contacts
            item["_contact_hit"] = bool(email or contacts)

        async def _seed_contacts_only(item: Dict[str, Any]) -> None:
            """Use homepage mailto seeds without crawling contact pages."""
            co = item["co"]
            page = item["page"]
            site_text = item.get("site_text") or ""
            website = (co.get("website") or "").strip()
            phone = co.get("phone") or ""
            seed_emails = list(page.get("emails") or co.get("_seed_emails") or [])
            if page.get("phones") and not phone:
                phone = (page.get("phones") or [""])[0] or phone
            contacts: List[Dict[str, Any]] = []
            email = ""
            if seed_emails or phone:
                cheap = contacts_from_text(
                    site_text, website=website, seed_phone=phone, seed_emails=seed_emails,
                )
                contacts = cheap.get("contacts") or []
                email = cheap.get("email") or ""
                phone = cheap.get("phone") or phone
            page.pop("html", None)
            item["email"] = email
            item["phone"] = phone
            item["contacts"] = contacts
            item["_contact_hit"] = bool(email or contacts)

        # Contact discovery AFTER relevance — keep companies even without email.
        if qualified:
            await asyncio.gather(*[
                _fill_contacts(item) if item.get("want_contacts") else _seed_contacts_only(item)
                for item in qualified
            ])

        # Deep crawl contact pages for shortlisted leads still missing email
        deep_queue = [
            item for item in qualified
            if not (item.get("email") or "").strip() and (item["co"].get("website") or "").strip()
        ][:48]
        if deep_queue:
            await asyncio.gather(*[_fill_contacts(item) for item in deep_queue])

        # Keep all AI-relevant leads (email optional). Diversify by product.
        qualified = _diversify(qualified, min(limit, SAVE_CAP)) if qualified else []

        async def _enrich(item: Dict[str, Any]) -> Dict[str, Any]:
            co = item["co"]
            q = item["q"]
            source = item["source"]
            email = item.get("email") or ""
            phone = item.get("phone") or co.get("phone") or ""
            contacts = list(item.get("contacts") or [])
            outreach_draft = None
            timeline = [
                {"time": time.strftime("%H:%M"), "action": f"Discovered via {source} ({co.get('discovery_pool') or 'search'})"},
                {"time": time.strftime("%H:%M"), "action": f"Fit {q['fitSummary']} · Intent {q['intent']} · {q['priority']}"},
            ]
            contact_hit = bool(item.get("_contact_hit"))
            draft_hit = False
            website = (co.get("website") or "").strip()

            if email:
                timeline.append({"time": time.strftime("%H:%M"), "action": f"Found contact email {email}"})
            elif contact_hit:
                timeline.append({"time": time.strftime("%H:%M"), "action": f"Found {len(contacts)} public contact channel(s)"})
            else:
                timeline.append({"time": time.strftime("%H:%M"), "action": "No public email on homepage yet (deeper crawl runs in background)"})

            if item.get("want_draft") and website:
                async with draft_sem:
                    try:
                        draft = await provider.generate_personalized_outreach(
                            company_name=co.get("company_name") or "there",
                            why_prospect=q.get("whyThisProspect") or "",
                            signals=q.get("buyingSignals") or [],
                            matched_products=q.get("productFit") or [],
                            seller_name=seller_name,
                            why_now=q.get("whyNow") or "",
                            evidence=(q.get("fitBreakdown") or {}).get("evidence") or q.get("evidence") or [],
                            location=(q.get("location") or co.get("location") or ""),
                            industry=(q.get("industry") or ""),
                            recommended_approach=q.get("recommendedApproach") or "",
                            fit_summary=q.get("fitSummary") or "",
                            intent=q.get("intent") or "",
                        )
                        draft_hit = True
                        outreach_draft = {
                            "id": f"draft-{uuid4().hex[:8]}",
                            "subject": draft.get("subject") or f"Introduction — {seller_name}",
                            "body": draft.get("body") or "",
                            "personalizedReason": draft.get("personalizedReason") or "",
                            "outreachRationale": draft.get("outreachRationale") or None,
                            "status": "Draft",
                            "createdAt": now,
                            "toEmail": email or "",
                        }
                        timeline.append({
                            "time": time.strftime("%H:%M"),
                            "action": "Drafted personalized outreach (awaiting human approval)",
                        })
                    except Exception:
                        timeline.append({"time": time.strftime("%H:%M"), "action": "Outreach draft skipped"})

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
                "outreachDraft": outreach_draft,
                "stage": "To contact",
                "discoveredAt": now,
                "agentTimeline": timeline,
                "_contact_hit": contact_hit,
                "_draft_hit": draft_hit,
            }

        enriched = await asyncio.gather(*[_enrich(item) for item in qualified]) if qualified else []
        prospects = []
        contact_runs = 0
        draft_runs = 0
        for row in enriched:
            if row.pop("_contact_hit", False):
                contact_runs += 1
            if row.pop("_draft_hit", False):
                draft_runs += 1
            prospects.append(row)

        def _rank(p: Dict[str, Any]) -> tuple:
            intent_rank = {"high": 2, "low": 1, "none": 0}.get(p.get("intent") or "none", 0)
            pri = {"priority": 3, "nurture": 2, "review": 1, "low": 0}.get(p.get("priority") or "", 0)
            return (pri, intent_rank, int(p.get("fitScore") or 0))

        prospects.sort(key=_rank, reverse=True)

        duration_ms = int((time.time() - start_time) * 1000)
        tools = ["SearchPlanner", "WebSearchTool", "SerpClassifier", "SiteFetch", "AIRelevance"]
        if contact_runs:
            tools.append("ContactFinder")
        if draft_runs:
            tools.append("OutreachDraft")
        agent_log = {
            "id": f"run-{int(time.time())}",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "task": user_prompt or f"Find buyers ({profile.sales_motion})",
            "durationMs": duration_ms,
            "toolsUsed": tools,
            "sourcesCount": len(classified),
            "status": "Completed" if prospects else "CompletedWithNoCandidates",
            "sellerProfile": profile_to_dict(profile),
            "decisions": decisions_log + [{
                "step": 5,
                "observation": (
                    f"Shortlist {len(prospects)} accounts "
                    f"(~{sum(1 for p in prospects if (p.get('priority') or '').lower() in ('priority', 'nurture'))} strong, "
                    f"~{sum(1 for p in prospects if (p.get('priority') or '').lower() in ('review', 'low'))} average). "
                    + (
                        f"Contact crawl on {contact_runs} strong leads."
                        if contact_runs
                        else "Homepage emails seeded; deeper contact crawl continues in the background."
                    )
                ),
                "decision": (
                    f"Target mix is ~{STRONG_SAVE} strong + ~{AVERAGE_SAVE} average. "
                    "Email is optional — relevant companies without a public email are still leads. "
                    "Outreach drafts happen later in Prepare outreach."
                ),
                "toolCalled": "LeadPipeline",
                "toolResultSnippet": (
                    f"{len(prospects)} To contact · "
                    f"{sum(1 for p in prospects if (p.get('email') or '').strip())} with email · "
                    f"{contact_runs} contact crawls"
                ),
            }],
        }
        return {"prospects": prospects, "agent_log": agent_log, "prospect": prospects[0] if prospects else None}
