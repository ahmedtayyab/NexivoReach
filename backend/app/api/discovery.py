from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from typing import List, Dict, Any
from uuid import uuid4
from sqlmodel import Session, select
from app.agents.prospecting_agent import ProspectingAgent
from app.models.schemas import ProspectRecord, AgentRunRecord
from app.database.session import engine
from app.api.deps import AuthUser, get_current_user, resolve_business_id
from app.api.serializers import prospect_to_frontend, run_to_frontend

router = APIRouter(prefix="/api/discovery", tags=["discovery"])


class DiscoveryRunRequest(BaseModel):
    user_prompt: str
    products: List[Dict[str, Any]] = []
    icp: Dict[str, Any] = {}


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
    user: AuthUser = Depends(get_current_user),
):
    agent = ProspectingAgent()
    res = await agent.execute_discovery_goal(
        user_prompt=req.user_prompt,
        products=req.products,
        icp=req.icp,
    )

    prospect = res.get("prospect") or {}
    agent_log = res.get("agent_log") or {}

    try:
        with Session(engine) as session:
            business_id = resolve_business_id(request, user, session)
            prospect_id = prospect.get("id") or f"prospect-{uuid4().hex[:8]}"
            pr = ProspectRecord(
                id=prospect_id,
                company_name=prospect.get("companyName") or "",
                website=prospect.get("website") or "",
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
                stage=prospect.get("stage") or "Qualified",
                discovered_at=prospect.get("discoveredAt") or "",
                agent_timeline=prospect.get("agentTimeline") or [],
                user_id=user.id,
                business_id=business_id,
            )
            session.add(pr)

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
            prospect = prospect_to_frontend(pr)
            agent_log = run_to_frontend(ar)
    except Exception as e:
        print("Failed to persist discovery run:", e)

    return {"prospect": prospect, "agent_log": agent_log}
