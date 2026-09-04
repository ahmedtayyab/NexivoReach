from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel
from typing import List, Dict, Any
from uuid import uuid4
from sqlmodel import Session, select
from app.agents.prospecting_agent import ProspectingAgent
from app.models.schemas import ProspectRecord, AgentRunRecord, Business
from app.database.session import engine
from app.api.deps import AuthUser, get_current_user, resolve_business_id
from app.api.serializers import prospect_to_frontend, run_to_frontend
from app.integrations import sheets as sheets_mod
from urllib.parse import urlparse
import logging

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/discovery", tags=["discovery"])


class DiscoveryRunRequest(BaseModel):
    user_prompt: str = ""
    products: List[Dict[str, Any]] = []
    icp: Dict[str, Any] = {}
    business: Dict[str, Any] = {}


def _domain(url: str) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _sync_leads_job(business_id: str, prospects: list[dict]) -> None:
    try:
        with Session(engine) as session:
            biz = session.get(Business, business_id)
            from app.models.schemas import ProductItem
            product_rows = session.exec(
                select(ProductItem).where(ProductItem.business_id == business_id)
            ).all()
            products = [
                {"sourceUrl": r.source_url, "productUrl": r.product_url}
                for r in product_rows
                if r.source_url or r.product_url
            ]
            seller = sheets_mod.resolve_company_tab_name(biz, products, fallback="Company")
        sheets_mod.sync_leads(seller, prospects)
    except Exception as exc:
        log.warning("Sheets lead sync failed: %s", exc)


@router.get("/runs")
def list_runs(request: Request, user: AuthUser = Depends(get_current_user)):
    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        rows = session.exec(
            select(AgentRunRecord)
            .where(AgentRunRecord.business_id == business_id)
            .order_by(AgentRunRecord.timestamp.desc())
        ).all()
        return [run_to_frontend(r) for r in rows]


@router.post("/run")
async def run_discovery_agent(
    req: DiscoveryRunRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user: AuthUser = Depends(get_current_user),
):
    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        existing = session.exec(
            select(ProspectRecord).where(ProspectRecord.business_id == business_id)
        ).all()
        exclude = [r.website for r in existing if r.website]
        biz = session.get(Business, business_id)
        business_payload = req.business or {}
        if biz:
            business_payload = {
                "name": biz.name,
                "website": biz.website,
                "description": biz.description,
                "primaryCategories": biz.primary_categories or [],
                "targetMarkets": biz.target_markets or [],
                **business_payload,
            }

    agent = ProspectingAgent()
    res = await agent.execute_discovery_goal(
        user_prompt=req.user_prompt,
        products=req.products,
        icp=req.icp,
        business=business_payload,
        exclude_websites=exclude,
        limit=40,
    )

    prospects = res.get("prospects") or []
    agent_log = res.get("agent_log") or {}
    saved_front: List[Dict[str, Any]] = []

    try:
        with Session(engine) as session:
            known = {
                _domain(r.website)
                for r in session.exec(
                    select(ProspectRecord).where(ProspectRecord.business_id == business_id)
                ).all()
                if r.website
            }
            known_names = {
                (r.company_name or "").strip().lower()
                for r in session.exec(
                    select(ProspectRecord).where(ProspectRecord.business_id == business_id)
                ).all()
            }
            for prospect in prospects:
                website = prospect.get("website") or ""
                name = (prospect.get("companyName") or "").strip().lower()
                dom = _domain(website)
                if (dom and dom in known) or (name and name in known_names):
                    continue
                prospect_id = prospect.get("id") or f"prospect-{uuid4().hex[:8]}"
                pr = ProspectRecord(
                    id=prospect_id,
                    company_name=prospect.get("companyName") or "",
                    website=website,
                    location=prospect.get("location") or "",
                    industry=prospect.get("industry") or "",
                    company_size=prospect.get("companySize") or "",
                    fit_score=int(prospect.get("fitScore", 0) or 0),
                    fit_breakdown=prospect.get("fitBreakdown") or {},
                    why_this_prospect=prospect.get("whyThisProspect") or "",
                    buying_signals=prospect.get("buyingSignals") or [],
                    product_fit=prospect.get("productFit") or [],
                    recommended_approach=prospect.get("recommendedApproach") or "",
                    outreach_draft=prospect.get("outreachDraft"),
                    stage=prospect.get("stage") or "To contact",
                    discovered_at=prospect.get("discoveredAt") or "",
                    agent_timeline=prospect.get("agentTimeline") or [],
                    user_id=user.id,
                    business_id=business_id,
                    source=prospect.get("source") or "web",
                    phone=prospect.get("phone") or "",
                    why_now=prospect.get("whyNow") or "",
                    email=prospect.get("email") or "",
                    contacts=prospect.get("contacts") or [],
                    contact_again=bool(prospect.get("contactAgain", True)),
                    last_reply_at=prospect.get("lastReplyAt") or "",
                    reply_summary=prospect.get("replySummary") or "",
                )
                session.add(pr)
                saved_front.append(prospect_to_frontend(pr))
                if dom:
                    known.add(dom)
                if name:
                    known_names.add(name)

            run_id = agent_log.get("id") or f"run-{uuid4().hex[:8]}"
            ar = AgentRunRecord(
                id=run_id,
                timestamp=agent_log.get("timestamp") or "",
                task=agent_log.get("task") or "",
                duration_ms=int(agent_log.get("durationMs", 0) or 0),
                tools_used=agent_log.get("toolsUsed") or [],
                sources_count=int(agent_log.get("sourcesCount", 0) or 0),
                status=agent_log.get("status") or "",
                decisions=agent_log.get("decisions") or [],
                user_id=user.id,
                business_id=business_id,
            )
            session.add(ar)
            session.commit()
            agent_log = run_to_frontend(ar)
    except Exception as e:
        log.warning("Failed to persist discovery run: %s", e)
        saved_front = prospects

    if sheets_mod.is_configured() and saved_front:
        background_tasks.add_task(_sync_leads_job, business_id, saved_front)

    return {
        "prospects": saved_front,
        "foundCount": len(saved_front),
        "agent_log": agent_log,
        # keep old key so older clients don't crash
        "prospect": saved_front[0] if saved_front else None,
    }
