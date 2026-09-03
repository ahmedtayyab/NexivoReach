"""Lead-hunting agent: planned discovery → classify → cheap fetch → Fit vs Intent."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4
from urllib.parse import urlparse

from app.agents.search_planner import (
    infer_seller_profile,
    plan_wave1,
    plan_wave2,
    profile_to_dict,
)
from app.agents.serp_classifier import classify_serp_row, summarize_classifications
from app.agents.qualify import qualify_account
from app.tools.web_search import WebSearchTool


LEAD_STAGES = (
    "To contact",
    "Contacted",
    "Replied",
    "Re-contact",
    "Denied",
    "Avoid",
    "Meeting",
    "Won",
)

FETCH_CAP = 12
SAVE_CAP = 15
WAVE1_RESULT_CAP = 40


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
        limit: int = 15,
    ) -> Dict[str, Any]:
        start_time = time.time()
        decisions_log: List[Dict[str, Any]] = []
        business = business or {}
        profile = infer_seller_profile(products, icp, business)
        wave1 = plan_wave1(profile, user_prompt)
        place = profile.places[0] if profile.places else ""
        exclude_domains = {_domain(u) for u in (exclude_websites or []) if _domain(u)}

        decisions_log.append({
            "step": 1,
            "observation": (
                f"Seller motion={profile.sales_motion}, offer={profile.offer_class}, "
                f"geo={profile.geo_mode}, maps={'on' if profile.use_maps else 'off'}."
            ),
            "decision": (
                f"Wave 1: {len(wave1)} query families "
                f"({', '.join(sorted({q.family for q in wave1}))}). "
                "Not running synonym clones."
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
            classify_serp_row(row, hunting_buyers=profile.hunting_buyers, target_places=profile.places)
            for row in leads
        ]
        stats = summarize_classifications(classified)
        decisions_log.append({
            "step": 2,
            "observation": (
                f"Wave 1 returned {len(leads)} unique URLs. "
                f"Junk {stats['junk_ratio']:.0%}, manufacturers {stats['manufacturer_ratio']:.0%}, "
                f"relevant {stats['relevant_count']}."
            ),
            "decision": "Inspect SERP patterns before more searches.",
            "toolCalled": "SerpClassifier",
            "toolResultSnippet": f"rejected={stats['rejected']} seeds={len(stats['competitor_names'])}",
        })

        wave2 = plan_wave2(profile, stats, stats.get("learned_terms"))
        if wave2 and stats["relevant_count"] < 8:
            more = await self.web_search.hunt_leads(
                wave2,
                target_location=place,
                exclude_domains=exclude_domains | {_domain(r.get("website")) for r in classified if r.get("website")},
                limit=25,
                use_maps=False,
            )
            extra = [
                classify_serp_row(row, hunting_buyers=profile.hunting_buyers, target_places=profile.places)
                for row in more
            ]
            classified.extend(extra)
            decisions_log.append({
                "step": 3,
                "observation": f"Wave 2 ran {len(wave2)} follow-up searches → {len(more)} new URLs.",
                "decision": "Use learned terms / manufacturer exclusions / competitor-customer queries.",
                "toolCalled": "AdaptiveSearch",
                "toolResultSnippet": "; ".join(q.query for q in wave2[:3]),
            })
        else:
            decisions_log.append({
                "step": 3,
                "observation": "No second wave (enough relevant hits, or nothing useful to refine).",
                "decision": "Proceed to cheap homepage inspection on survivors only.",
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
        pages = await asyncio.gather(
            *[self.web_search.scrape_homepage(c["website"]) for c in to_fetch],
            return_exceptions=True,
        )
        text_by_domain: Dict[str, Dict[str, Any]] = {}
        for cand, page in zip(to_fetch, pages):
            dom = _domain(cand.get("website") or "")
            if isinstance(page, dict) and page.get("ok"):
                text_by_domain[dom] = page
            else:
                text_by_domain[dom] = {"text": "", "url": cand.get("website") or "", "ok": False}

        decisions_log.append({
            "step": 4,
            "observation": f"{len(candidates)} candidates after exclusions; fetched {len(to_fetch)} homepages (cap {FETCH_CAP}).",
            "decision": "Qualify Fit vs Intent from site text. Do not invent buying signals.",
            "toolCalled": "HomepageFetch",
            "toolResultSnippet": f"{sum(1 for v in text_by_domain.values() if v.get('ok'))} live pages",
        })

        prospects: List[Dict[str, Any]] = []
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        for co in candidates[:SAVE_CAP + 8]:
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
            source = co.get("source") or "web"
            location = (co.get("location") or "").strip()
            prospects.append({
                "id": f"prospect-{uuid4().hex[:10]}",
                "companyName": co.get("company_name") or "Unknown",
                "website": co.get("website") or "",
                "location": location,
                "industry": (q.get("industry") or "")[:80],
                "companySize": "",
                "phone": co.get("phone") or "",
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
                "agentTimeline": [
                    {"time": time.strftime("%H:%M"), "action": f"Discovered via {source} ({co.get('discovery_pool') or 'search'})"},
                    {"time": time.strftime("%H:%M"), "action": f"Fit {q['fitSummary']} · Intent {q['intent']} · {q['priority']}"},
                ],
            })
            if len(prospects) >= min(limit, SAVE_CAP):
                break

        def _rank(p: Dict[str, Any]) -> tuple:
            intent_rank = {"high": 2, "low": 1, "none": 0}.get(p.get("intent") or "none", 0)
            pri = {"priority": 3, "nurture": 2, "review": 1, "low": 0}.get(p.get("priority") or "", 0)
            return (pri, intent_rank, int(p.get("fitScore") or 0))

        prospects.sort(key=_rank, reverse=True)

        duration_ms = int((time.time() - start_time) * 1000)
        agent_log = {
            "id": f"run-{int(time.time())}",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "task": user_prompt or f"Find buyers ({profile.sales_motion})",
            "durationMs": duration_ms,
            "toolsUsed": ["SearchPlanner", "WebSearchTool", "SerpClassifier", "HomepageFetch", "QualifyAccount"],
            "sourcesCount": len(leads),
            "status": "Completed" if prospects else "CompletedWithNoCandidates",
            "sellerProfile": profile_to_dict(profile),
            "decisions": decisions_log + [{
                "step": 5,
                "observation": f"Persisting {len(prospects)} qualified accounts (Fit not Low). Intent is scored separately.",
                "decision": "Skip contact discovery until a lead is outreach-ready. Do not fabricate why-now.",
                "toolCalled": "LeadPipeline",
                "toolResultSnippet": f"{len(prospects)} To contact",
            }],
        }
        return {"prospects": prospects, "agent_log": agent_log, "prospect": prospects[0] if prospects else None}
