"""Lead-hunting agent: many companies from web + maps, catalog-aware, no mock data."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4
from urllib.parse import urlparse

from app.tools.web_search import WebSearchTool
from app.tools.score_calculator import ScoreCalculatorTool


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


def _domain(url: str) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def build_hunt_queries(
    user_prompt: str,
    products: List[Dict[str, Any]],
    icp: Dict[str, Any],
    business: Dict[str, Any],
) -> tuple[list[str], str]:
    categories = [
        *(business.get("primaryCategories") or business.get("primary_categories") or []),
        *[p.get("category") for p in products if p.get("category") and p.get("category") != "Uncategorized"],
    ]
    # unique, keep order
    seen = set()
    cats: List[str] = []
    for c in categories:
        key = (c or "").strip()
        if not key or key.lower() in seen:
            continue
        seen.add(key.lower())
        cats.append(key)
    cats = cats[:4] or ["wholesale"]

    buyers = list(icp.get("targetBuyerTypes") or icp.get("target_buyer_types") or [])[:4]
    if not buyers:
        buyers = ["distributors", "retailers", "wholesalers", "importers"]

    countries = list(icp.get("targetCountries") or icp.get("target_countries") or [])[:4]
    markets = list(business.get("targetMarkets") or business.get("target_markets") or [])[:4]
    places = []
    for p in countries + markets:
        if p and p not in places:
            places.append(p)
    if not places:
        places = [""]

    queries: List[str] = []
    if user_prompt.strip():
        queries.append(user_prompt.strip())

    for place in places[:3]:
        loc = place.strip()
        for buyer in buyers[:2]:
            for cat in cats[:2]:
                q = f"{buyer} {cat} {loc}".strip()
                if q and q not in queries:
                    queries.append(q)
        queries.append(f"{cats[0]} distributors {loc}".strip())
        queries.append(f"{cats[0]} retailers {loc}".strip())

    # de-dupe / trim
    out: List[str] = []
    seen_q = set()
    for q in queries:
        key = re.sub(r"\s+", " ", q.lower()).strip()
        if not key or key in seen_q:
            continue
        seen_q.add(key)
        out.append(q)
        if len(out) >= 8:
            break
    primary_place = next((p for p in places if p), "")
    return out, primary_place


class ProspectingAgent:
    def __init__(self):
        self.web_search = WebSearchTool()
        self.score_calc = ScoreCalculatorTool()

    async def execute_discovery_goal(
        self,
        user_prompt: str,
        products: List[Dict[str, Any]],
        icp: Dict[str, Any],
        business: Optional[Dict[str, Any]] = None,
        exclude_websites: Optional[List[str]] = None,
        limit: int = 35,
    ) -> Dict[str, Any]:
        start_time = time.time()
        decisions_log: List[Dict[str, Any]] = []
        business = business or {}
        queries, location = build_hunt_queries(user_prompt, products, icp, business)

        exclude_domains = {_domain(u) for u in (exclude_websites or []) if _domain(u)}

        decisions_log.append({
            "step": 1,
            "observation": f"Hunt for buyers of {len(products)} catalog items in {location or 'target markets'}.",
            "decision": f"Run {len(queries)} web + Maps searches (skip {len(exclude_domains)} already-known domains).",
            "toolCalled": "QueryBuilder",
            "toolResultSnippet": "; ".join(queries[:4]),
        })

        leads = await self.web_search.hunt_leads(
            queries,
            target_location=location,
            exclude_domains=exclude_domains,
            limit=limit,
        )

        decisions_log.append({
            "step": 2,
            "observation": f"Found {len(leads)} unique companies (web + Google Maps).",
            "decision": "Score each lead against catalog, buyers, and target countries. Skip mock/gym templates.",
            "toolCalled": "WebSearchTool",
            "toolResultSnippet": ", ".join(c.get("company_name", "") for c in leads[:8]),
        })

        if not leads:
            duration_ms = int((time.time() - start_time) * 1000)
            return {
                "prospects": [],
                "agent_log": {
                    "id": f"run-{int(time.time())}",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "task": user_prompt or "Lead hunt",
                    "durationMs": duration_ms,
                    "toolsUsed": ["WebSearchTool"],
                    "sourcesCount": 0,
                    "status": "CompletedWithNoCandidates",
                    "decisions": decisions_log,
                },
            }

        product_names = [p.get("name") for p in products if p.get("name")][:6]
        cats = list({p.get("category") for p in products if p.get("category")})[:4]
        seller = (business.get("name") or "your catalog").strip()
        countries = icp.get("targetCountries") or icp.get("target_countries") or []
        buyers = icp.get("targetBuyerTypes") or icp.get("target_buyer_types") or []

        prospects: List[Dict[str, Any]] = []
        for co in leads:
            snippet = co.get("snippet") or ""
            industry = co.get("industry") or snippet or (cats[0] if cats else "Buyer")
            matches = [
                {
                    "productName": name,
                    "fitLevel": "Medium",
                    "reasoning": f"Possible buyer for {name} based on {co.get('company_name')} appearing in {co.get('source') or 'search'} for {cats[0] if cats else 'your category'}.",
                }
                for name in product_names[:3]
            ]
            score_res = self.score_calc.calculate_fit_score(
                company_industry=industry,
                company_location=co.get("location") or "",
                target_countries=list(countries),
                buying_signals=[],
                product_matches=matches,
                target_buyer_types=list(buyers),
                research_text=f"{co.get('company_name')} {snippet}",
            )
            source = co.get("source") or "web"
            why = (
                f"{co.get('company_name')} showed up as a {source} result for "
                f"{(cats[0] if cats else 'your products')} in {co.get('location') or location or 'your target market'}."
            )
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ")
            prospects.append({
                "id": f"prospect-{uuid4().hex[:10]}",
                "companyName": co.get("company_name") or "Unknown",
                "website": co.get("website") or "",
                "location": co.get("location") or location or "",
                "industry": industry[:80],
                "companySize": "",
                "phone": co.get("phone") or "",
                "source": source,
                "fitScore": score_res["total_score"],
                "fitBreakdown": score_res["breakdown"],
                "whyThisProspect": why,
                "buyingSignals": [],
                "productFit": matches,
                "recommendedApproach": (
                    f"Reach out as {seller}. Lead with {product_names[0] if product_names else 'your catalog'} "
                    f"and confirm they buy {cats[0] if cats else 'this category'}."
                ),
                "outreachDraft": None,
                "stage": "To contact",
                "discoveredAt": now,
                "agentTimeline": [
                    {"time": time.strftime("%H:%M"), "action": f"Discovered via {source} search"},
                    {"time": time.strftime("%H:%M"), "action": f"Scored {score_res['total_score']}/100 against catalog/ICP"},
                ],
            })

        prospects.sort(key=lambda p: int(p.get("fitScore") or 0), reverse=True)

        duration_ms = int((time.time() - start_time) * 1000)
        agent_log = {
            "id": f"run-{int(time.time())}",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "task": user_prompt or f"Find buyers in {location}",
            "durationMs": duration_ms,
            "toolsUsed": ["QueryBuilder", "WebSearchTool", "MapsSearch", "ScoreCalculatorTool"],
            "sourcesCount": len(leads),
            "status": "Completed",
            "decisions": decisions_log + [{
                "step": 3,
                "observation": f"Qualified {len(prospects)} leads to contact.",
                "decision": "Persist all leads (not just the first) and sync to Google Sheets.",
                "toolCalled": "LeadPipeline",
                "toolResultSnippet": f"{len(prospects)} To contact",
            }],
        }
        return {"prospects": prospects, "agent_log": agent_log}
