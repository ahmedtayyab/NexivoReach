from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any
from uuid import uuid4
from sqlmodel import Session
from app.agents.prospecting_agent import ProspectingAgent
from app.models.schemas import ProspectRecord, AgentRunRecord
from app.database.session import engine

router = APIRouter(prefix="/api/discovery", tags=["discovery"])


class DiscoveryRunRequest(BaseModel):
    user_prompt: str
    products: List[Dict[str, Any]] = []
    icp: Dict[str, Any] = {}


@router.post("/run")
async def run_discovery_agent(req: DiscoveryRunRequest):
    agent = ProspectingAgent()
    res = await agent.execute_discovery_goal(
        user_prompt=req.user_prompt,
        products=req.products,
        icp=req.icp,
    )

    prospect = res.get("prospect")
    agent_log = res.get("agent_log")

    # Persist results to DB
    try:
        with Session(engine) as session:
            prospect_id = prospect.get("id") if prospect.get("id") else f"prospect-{uuid4().hex[:8]}"
            pr = ProspectRecord(
                id=prospect_id,
                company_name=prospect.get("companyName"),
                website=prospect.get("website"),
                location=prospect.get("location"),
                industry=prospect.get("industry"),
                company_size=prospect.get("companySize"),
                fit_score=int(prospect.get("fitScore", 0)),
                fit_breakdown=prospect.get("fitBreakdown", {}),
                why_this_prospect=prospect.get("whyThisProspect", ""),
                buying_signals=prospect.get("buyingSignals", []),
                product_fit=prospect.get("productFit", []),
                recommended_approach=prospect.get("recommendedApproach", ""),
                outreach_draft=prospect.get("outreachDraft"),
                stage=prospect.get("stage", "Qualified"),
                discovered_at=prospect.get("discoveredAt", ""),
                agent_timeline=prospect.get("agentTimeline", []),
            )
            session.add(pr)

            run_id = agent_log.get("id") if agent_log.get("id") else f"run-{uuid4().hex[:8]}"
            ar = AgentRunRecord(
                id=run_id,
                timestamp=agent_log.get("timestamp"),
                task=agent_log.get("task"),
                duration_ms=int(agent_log.get("durationMs", 0)),
                tools_used=agent_log.get("toolsUsed", []),
                sources_count=int(agent_log.get("sourcesCount", 0)),
                status=agent_log.get("status", ""),
                decisions=agent_log.get("decisions", []),
            )
            session.add(ar)

            session.commit()
    except Exception as e:
        # If persistence fails, log and continue returning agent output
        print("Failed to persist discovery run:", e)

    return {"prospect": prospect, "agent_log": agent_log}
