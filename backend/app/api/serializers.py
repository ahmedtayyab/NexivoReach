import time
from typing import Any, Dict, Optional
from app.models.schemas import ProspectRecord, AgentRunRecord, Business, ProductItem, ICPConfig


def prospect_to_frontend(pr: ProspectRecord) -> Dict[str, Any]:
    return {
        "id": pr.id,
        "companyName": pr.company_name,
        "website": pr.website,
        "location": pr.location,
        "industry": pr.industry,
        "companySize": pr.company_size,
        "fitScore": pr.fit_score,
        "fitBreakdown": pr.fit_breakdown or {},
        "whyThisProspect": pr.why_this_prospect,
        "buyingSignals": pr.buying_signals or [],
        "productFit": pr.product_fit or [],
        "recommendedApproach": pr.recommended_approach,
        "outreachDraft": pr.outreach_draft,
        "stage": pr.stage,
        "discoveredAt": pr.discovered_at,
        "agentTimeline": pr.agent_timeline or [],
    }


def prospect_from_frontend(payload: Dict[str, Any]) -> Dict[str, Any]:
    draft = payload.get("outreachDraft") or payload.get("outreach_draft")
    return {
        "id": payload.get("id"),
        "company_name": payload.get("companyName") or payload.get("company_name") or "",
        "website": payload.get("website") or "",
        "location": payload.get("location") or "",
        "industry": payload.get("industry") or "",
        "company_size": payload.get("companySize") or payload.get("company_size") or "",
        "fit_score": int(payload.get("fitScore") or payload.get("fit_score") or 0),
        "fit_breakdown": payload.get("fitBreakdown") or payload.get("fit_breakdown") or {},
        "why_this_prospect": payload.get("whyThisProspect") or payload.get("why_this_prospect") or "",
        "buying_signals": payload.get("buyingSignals") or payload.get("buying_signals") or [],
        "product_fit": payload.get("productFit") or payload.get("product_fit") or [],
        "recommended_approach": payload.get("recommendedApproach") or payload.get("recommended_approach") or "",
        "outreach_draft": draft,
        "stage": payload.get("stage") or "Qualified",
        "discovered_at": payload.get("discoveredAt") or payload.get("discovered_at") or "",
        "agent_timeline": payload.get("agentTimeline") or payload.get("agent_timeline") or [],
    }


def run_to_frontend(run: AgentRunRecord) -> Dict[str, Any]:
    return {
        "id": run.id,
        "timestamp": run.timestamp,
        "task": run.task,
        "durationMs": run.duration_ms,
        "toolsUsed": run.tools_used or [],
        "sourcesCount": run.sources_count,
        "status": run.status,
        "decisions": run.decisions or [],
    }


def business_to_frontend(biz: Optional[Business]) -> Optional[Dict[str, Any]]:
    if not biz:
        return None
    return {
        "id": biz.id,
        "name": biz.name,
        "website": biz.website,
        "description": biz.description,
        "targetMarkets": biz.target_markets or [],
        "primaryCategories": biz.primary_categories or [],
        "extractedByAi": biz.extracted_by_ai,
    }


def product_to_frontend(item: ProductItem) -> Dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "category": item.category,
        "description": item.description,
        "price": item.price,
        "moq": item.moq,
        "specs": item.specs or [],
        "targetBuyer": item.target_buyer,
        "features": item.features or [],
        "productUrl": item.product_url,
        "imageUrl": item.image_url,
        "aiExtracted": item.ai_extracted,
        "verifiedByUser": item.verified_by_user,
    }


def normalize_extracted_product(raw: Dict[str, Any], index: int) -> Dict[str, Any]:
    return {
        "id": raw.get("id") or f"prod-{index}-{int(time.time())}",
        "name": raw.get("name") or raw.get("productName") or f"Product {index + 1}",
        "category": raw.get("category") or "Uncategorized",
        "description": raw.get("description") or "",
        "price": raw.get("price"),
        "moq": raw.get("moq"),
        "specs": raw.get("specs") or [],
        "targetBuyer": raw.get("targetBuyer") or raw.get("target_buyer"),
        "features": raw.get("features") or [],
        "productUrl": raw.get("productUrl") or raw.get("product_url"),
        "imageUrl": raw.get("imageUrl") or raw.get("image_url"),
        "aiExtracted": bool(raw.get("aiExtracted", raw.get("ai_extracted", True))),
        "verifiedByUser": bool(raw.get("verifiedByUser", raw.get("verified_by_user", False))),
    }


def icp_to_frontend(icp: Optional[ICPConfig]) -> Optional[Dict[str, Any]]:
    if not icp:
        return None
    return {
        "id": icp.id,
        "targetBuyerTypes": icp.target_buyer_types or [],
        "targetCountries": icp.target_countries or [],
        "companySize": icp.company_size,
        "minDealSize": icp.min_deal_size,
        "shippingMarkets": icp.shipping_markets or [],
        "salesConstraints": icp.sales_constraints or [],
        "buyingSignals": icp.buying_signals or [],
    }
