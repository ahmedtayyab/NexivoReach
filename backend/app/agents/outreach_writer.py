"""Compose personalized outreach: brief → generate → quality check → final draft."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.agents.outreach_strategy import (
    brief_to_personalized_reason,
    build_follow_up_prompt,
    build_generation_prompt,
    build_outreach_brief,
    format_outreach_body,
    heuristic_quality_check,
    render_fallback_email,
)
from app.providers.json_util import parse_json_payload
import logging

log = logging.getLogger(__name__)


def _normalize_draft(parsed: Dict[str, Any], brief: Dict[str, Any]) -> Dict[str, Any]:
    subject = (parsed.get("subject") or "").strip()
    body = (parsed.get("body") or "").strip()
    body = format_outreach_body(
        body,
        company_name=str(brief.get("company_name") or ""),
        seller_name=str(brief.get("seller_name") or ""),
    )
    reason = (parsed.get("personalizedReason") or "").strip() or brief_to_personalized_reason(brief)
    candidates = parsed.get("subjectCandidates") or []
    if isinstance(candidates, list):
        candidates = [str(c).strip() for c in candidates if str(c).strip()][:3]
    else:
        candidates = []
    if not subject and candidates:
        subject = candidates[0]
    return {
        "subject": subject[:140],
        "body": body,
        "personalizedReason": reason[:400],
        "subjectCandidates": candidates,
        "outreachRationale": {
            "primary_signal": brief.get("primary_signal") or "",
            "signal_source": brief.get("signal_source") or "",
            "signal_confidence": brief.get("signal_confidence") or "low",
            "pain_hypothesis": brief.get("pain_hypothesis") or "",
            "matched_product": brief.get("matched_product") or "",
            "value_proposition": brief.get("value_proposition") or "",
            "cta_strategy": brief.get("cta_strategy") or "low_friction_interest",
            "angle": brief.get("angle") or "",
        },
    }


def _llm_generate(provider: Any, prompt: str) -> Optional[Dict[str, Any]]:
    """Call provider-specific text generation if available."""
    try:
        if hasattr(provider, "_generate") and getattr(provider, "available", False):
            raw = provider._generate(prompt)
            parsed = parse_json_payload(raw)
            if isinstance(parsed, dict):
                return parsed
        if hasattr(provider, "_complete") and getattr(provider, "available", False):
            raw = provider._complete(prompt)
            parsed = parse_json_payload(raw)
            if isinstance(parsed, dict):
                return parsed
    except Exception as exc:
        log.warning("Outreach LLM generate failed: %s", exc)
    return None


async def compose_personalized_outreach(
    provider: Any,
    *,
    company_name: str,
    why_prospect: str = "",
    signals: Optional[List[Dict[str, Any]]] = None,
    matched_products: Optional[List[Dict[str, Any]]] = None,
    seller_name: str = "Sales Team",
    why_now: str = "",
    evidence: Optional[List[Dict[str, Any]]] = None,
    location: str = "",
    industry: str = "",
    recommended_approach: str = "",
    fit_summary: str = "",
    intent: str = "",
) -> Dict[str, Any]:
    """
    Full pipeline: brief → LLM (or fallback) → heuristic QC → one regenerate → final.
    """
    brief = build_outreach_brief(
        company_name=company_name,
        why_prospect=why_prospect,
        why_now=why_now,
        signals=signals or [],
        matched_products=matched_products or [],
        evidence=evidence or [],
        location=location,
        industry=industry,
        recommended_approach=recommended_approach,
        fit_summary=fit_summary,
        intent=intent,
        seller_name=seller_name,
    )

    prompt = build_generation_prompt(brief)
    parsed = _llm_generate(provider, prompt)
    draft = _normalize_draft(parsed, brief) if parsed and parsed.get("body") else None

    if draft:
        ok, issues = heuristic_quality_check(draft, brief)
        if not ok:
            log.info("Outreach QC failed (%s) — regenerating once", issues)
            retry_prompt = (
                prompt
                + "\n\nREVISION REQUIRED. Prior draft failed: "
                + ", ".join(issues)
                + ". Fix those issues. Stay within allowed facts."
            )
            parsed2 = _llm_generate(provider, retry_prompt)
            if parsed2 and parsed2.get("body"):
                draft2 = _normalize_draft(parsed2, brief)
                ok2, _ = heuristic_quality_check(draft2, brief)
                if ok2 or len((draft2.get("body") or "")) > len(draft.get("body") or ""):
                    draft = draft2

    if not draft or not (draft.get("body") or "").strip():
        draft = render_fallback_email(brief)

    # Ensure rationale always present
    if not draft.get("outreachRationale"):
        draft = _normalize_draft(draft, brief)
    if not draft.get("personalizedReason"):
        draft["personalizedReason"] = brief_to_personalized_reason(brief)
    return draft


async def compose_follow_up_outreach(
    provider: Any,
    *,
    company_name: str,
    why_prospect: str = "",
    prior_subject: str = "",
    prior_body: str = "",
    reply_summary: str = "",
    seller_name: str = "Sales Team",
) -> Dict[str, Any]:
    prompt = build_follow_up_prompt(
        company_name=company_name,
        why_prospect=why_prospect,
        prior_subject=prior_subject,
        prior_body=prior_body,
        reply_summary=reply_summary,
        seller_name=seller_name,
    )
    parsed = _llm_generate(provider, prompt)
    if isinstance(parsed, dict) and parsed.get("subject") and parsed.get("body"):
        return {
            "subject": str(parsed["subject"])[:140],
            "body": format_outreach_body(
                str(parsed["body"]).strip(),
                company_name=company_name,
                seller_name=seller_name,
            ),
            "personalizedReason": (
                str(parsed.get("personalizedReason") or "").strip()
                or (
                    "Follow-up drafted from their reply."
                    if (reply_summary or "").strip()
                    else "Follow-up after silence (no reply logged yet)."
                )
            ),
        }

    # Provider-native fallback
    if hasattr(provider, "generate_follow_up_outreach"):
        # Avoid recursion if provider delegates here — call Fallback directly
        from app.providers.fallback import FallbackProvider
        return await FallbackProvider().generate_follow_up_outreach(
            company_name, why_prospect, prior_subject, prior_body, reply_summary, seller_name
        )
    from app.providers.fallback import FallbackProvider
    return await FallbackProvider().generate_follow_up_outreach(
        company_name, why_prospect, prior_subject, prior_body, reply_summary, seller_name
    )
