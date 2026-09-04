"""Lead-hunting agent: planned discovery → classify → cheap fetch → Fit vs Intent."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4
from urllib.parse import urlparse

from app.agents.search_planner import (
    apply_prompt_geo,
    apply_prompt_roles,
    infer_seller_profile,
    plan_wave1,
    plan_wave2,
    profile_to_dict,
)
from app.agents.serp_classifier import classify_serp_row, summarize_classifications
from app.agents.qualify import qualify_account
from app.tools.web_search import WebSearchTool
from app.tools.contact_finder import discover_contacts, contacts_from_text
from app.providers.factory import get_ai_provider


FETCH_CAP = 40
SAVE_CAP = 40
WAVE1_RESULT_CAP = 70
WAVE2_RESULT_CAP = 35
ENRICH_CAP = 12  # AI drafts for top fits
CONTACT_CAP = 40  # emails scraped automatically for (almost) every saved lead


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
        limit: int = 40,
    ) -> Dict[str, Any]:
        start_time = time.time()
        decisions_log: List[Dict[str, Any]] = []
        business = business or {}
        profile = apply_prompt_roles(
            apply_prompt_geo(infer_seller_profile(products, icp, business), user_prompt),
            user_prompt,
        )
        wave1 = plan_wave1(profile, user_prompt)
        place = profile.places[0] if profile.places else ""
        exclude_domains = {_domain(u) for u in (exclude_websites or []) if _domain(u)}

        decisions_log.append({
            "step": 1,
            "observation": (
                f"Seller motion={profile.sales_motion}, offer={profile.offer_class}, "
                f"buyers={profile.buyers}, geo={profile.geo_mode}, places={profile.places or ['(none)']}, "
                f"strict_geo={profile.strict_geo}, maps={'on' if profile.use_maps else 'off'}."
            ),
            "decision": (
                f"Wave 1: {len(wave1)} query families "
                f"({', '.join(sorted({q.family for q in wave1}))}). "
                + (
                    f"Prioritizing {profile.buyers[0]} in {', '.join(profile.places[:2])}."
                    if profile.buyers and profile.places
                    else (
                        f"Strict location filter for {', '.join(profile.places[:2])}."
                        if profile.strict_geo
                        else "Not running synonym clones."
                    )
                )
            ),
            "toolCalled": "SearchPlanner",
            "toolResultSnippet": "; ".join(q.query for q in wave1[:4]),
        })

        leads = await self.web_search.hunt_leads(
            wave1,
            target_location=place,
            exclude_domains=exclude_domains,
            limit=WAVE1_RESULT_CAP,
            use_maps=profile.use_maps,
        )
        classified = [
            classify_serp_row(
                row,
                hunting_buyers=profile.hunting_buyers,
                target_places=profile.places,
                strict_geo=profile.strict_geo,
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
        decisions_log.append({
            "step": 2,
            "observation": (
                f"Wave 1 returned {len(leads)} unique URLs. "
                f"Junk {stats['junk_ratio']:.0%}, manufacturers {stats['manufacturer_ratio']:.0%}, "
                f"wrong geo {stats['wrong_geo_ratio']:.0%}, relevant {stats['relevant_count']}."
            ),
            "decision": "Inspect SERP patterns before more searches.",
            "toolCalled": "SerpClassifier",
            "toolResultSnippet": f"rejected={stats['rejected']} seeds={len(stats['competitor_names'])}",
        })

        wave2 = plan_wave2(profile, stats, stats.get("learned_terms"))
        # Skip wave 2 when we already have enough in-geo hits (speed)
        need_wave2 = bool(wave2) and stats["relevant_count"] < (12 if profile.strict_geo else 18)
        if need_wave2:
            more = await self.web_search.hunt_leads(
                wave2,
                target_location=place,
                exclude_domains=exclude_domains | {_domain(r.get("website")) for r in classified if r.get("website")},
                limit=WAVE2_RESULT_CAP,
                use_maps=profile.use_maps and profile.strict_geo,
            )
            extra = [
                classify_serp_row(
                    row,
                    hunting_buyers=profile.hunting_buyers,
                    target_places=profile.places,
                    strict_geo=profile.strict_geo,
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

        to_fetch = [c for c in candidates if (c.get("website") or "").strip()][:FETCH_CAP]
        # Homepage-only for speed; deep about/news pages skipped during hunt
        pages = await asyncio.gather(
            *[self.web_search.scrape_homepage(c["website"], limit=6000) for c in to_fetch],
            return_exceptions=True,
        )
        text_by_domain: Dict[str, Dict[str, Any]] = {}
        for cand, page in zip(to_fetch, pages):
            dom = _domain(cand.get("website") or "")
            if isinstance(page, dict) and page.get("ok"):
                page = {**page}
                # Keep raw HTML for contact mailto parsing during enrich
                # (visible text often says "Email us" without the address)
                text_by_domain[dom] = page
                if page.get("location") and not (cand.get("location") or "").strip():
                    cand["location"] = page["location"]
                elif page.get("location") and len(str(page["location"])) > len(str(cand.get("location") or "")):
                    cand["location"] = page["location"]
                if page.get("emails"):
                    cand.setdefault("_seed_emails", page["emails"])
            else:
                text_by_domain[dom] = {"text": "", "url": cand.get("website") or "", "ok": False, "location": "", "emails": []}

        decisions_log.append({
            "step": 4,
            "observation": (
                f"{len(candidates)} candidates after exclusions; "
                f"fetched {len(to_fetch)} homepages (cap {FETCH_CAP}, fast mode)."
            ),
            "decision": (
                "Qualify Fit vs Intent from homepage text. "
                + (f"Strict geo: must evidence {', '.join(profile.places[:2])}." if profile.strict_geo else "Do not invent buying signals.")
            ),
            "toolCalled": "SiteFetch",
            "toolResultSnippet": f"{sum(1 for v in text_by_domain.values() if v.get('ok'))} live sites",
        })

        # Qualify cheaply first; enrich high-fit leads in parallel afterward.
        qualified: List[Dict[str, Any]] = []
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        save_limit = min(limit, SAVE_CAP)
        for co in candidates[:SAVE_CAP + 16]:
            if len(qualified) >= save_limit:
                break
            dom = _domain(co.get("website") or "")
            page = text_by_domain.get(dom) or {}
            site_text = page.get("text") or ""
            q = qualify_account(
                row=co,
                site_text=site_text,
                profile=profile,
                products=products,
                page_url=page.get("url") or co.get("website") or "",
            )
            if not q.get("shouldPersist"):
                continue
            fit_summary = (q.get("fitSummary") or "").lower()
            priority = (q.get("priority") or "").lower()
            outreach_ready = fit_summary == "high" or priority in ("priority", "nurture")
            source = co.get("source") or "web"
            qualified.append({
                "co": co,
                "q": q,
                "page": page,
                "site_text": site_text,
                "outreach_ready": outreach_ready,
                "source": source,
            })

        # Rank before enrich so we spend contact/AI budget on best fits
        def _q_rank(item: Dict[str, Any]) -> tuple:
            q = item["q"]
            intent_rank = {"high": 2, "low": 1, "none": 0}.get(q.get("intent") or "none", 0)
            pri = {"priority": 3, "nurture": 2, "review": 1, "low": 0}.get(q.get("priority") or "", 0)
            loc_bonus = 1 if (q.get("location") or "").strip() else 0
            role_bonus = 1 if primary_buyer and primary_buyer in (
                f"{item.get('site_text') or ''} {q.get('whyThisProspect') or ''}"
            ).lower() else 0
            return (pri, role_bonus, loc_bonus, intent_rank, int(q.get("fitScore") or 0))

        qualified.sort(key=_q_rank, reverse=True)
        for i, item in enumerate(qualified):
            item["want_draft"] = item["outreach_ready"] and i < ENRICH_CAP

        seller_name = (business.get("name") or "Sales Team").strip() or "Sales Team"
        provider = get_ai_provider()
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
                            homepage_html=(page.get("html") or "")[:200000],
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

        # Phase 1 — emails for every lead (before drafts, so nothing is skipped)
        if qualified:
            await asyncio.gather(*[_fill_contacts(item) for item in qualified])

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
                timeline.append({"time": time.strftime("%H:%M"), "action": "No public email on site (contact page checked)"})

            if item.get("want_draft") and website:
                async with draft_sem:
                    try:
                        draft = await provider.generate_personalized_outreach(
                            company_name=co.get("company_name") or "there",
                            why_prospect=q.get("whyThisProspect") or "",
                            signals=q.get("buyingSignals") or [],
                            matched_products=q.get("productFit") or [],
                            seller_name=seller_name,
                        )
                        draft_hit = True
                        outreach_draft = {
                            "id": f"draft-{uuid4().hex[:8]}",
                            "subject": draft.get("subject") or f"Introduction — {seller_name}",
                            "body": draft.get("body") or "",
                            "personalizedReason": draft.get("personalizedReason") or "",
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
        tools = ["SearchPlanner", "WebSearchTool", "SerpClassifier", "SiteFetch", "QualifyAccount"]
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
                    f"Persisting {len(prospects)} qualified accounts. "
                    f"Contact crawl on {contact_runs} leads; {draft_runs} outreach drafts."
                ),
                "decision": (
                    "Emails scraped automatically for every saved lead (homepage + contact pages). "
                    f"AI drafts for top {ENRICH_CAP}. Human reviews before send."
                ),
                "toolCalled": "LeadPipeline",
                "toolResultSnippet": f"{len(prospects)} To contact · {draft_runs} drafts",
            }],
        }
        return {"prospects": prospects, "agent_log": agent_log, "prospect": prospects[0] if prospects else None}
