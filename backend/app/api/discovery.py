from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any
from app.agents.prospecting_agent import ProspectingAgent

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
        icp=req.icp
    )
    return res
