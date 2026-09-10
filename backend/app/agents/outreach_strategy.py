"""
Outreach strategy: Research → Relevance → Problem → Value → Credibility → CTA.

Builds an internal brief from prospect evidence. Never invents facts.
Does not expose chain-of-thought — only structured rationale for the UI.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# Tier-1 / trigger language in signals & why-now copy
TIER1_PATTERNS = (
    r"\bnew (facility|facilities|location|locations|store|stores|branch|branches|plant|plants|clinic|clinics)\b",
    r"\b(open(?:ing|ed)|launch(?:ing|ed)|expand(?:ing|ed)|expansion)\b",
    r"\b(renovat(?:ion|ing)|construction|build(?:ing)? out)\b",
    r"\b(hiring|recruiting|job posting)\b",
    r"\b(procurement|rfp|rfq|tender|supplier search)\b",
    r"\b(capacity|production) (increase|expansion|ramp)\b",
    r"\bnew (product|line|division|market|contract|project)\b",
)

TIER2_PATTERNS = (
    r"\b(growth|growing|scale|scaling)\b",
    r"\b(partnership|partnered|acquisition)\b",
    r"\b(multi[- ]?location|franchise|chain)\b",
    r"\b(international|export|import)\b",
)

WEAK_PATTERNS = (
    r"\bfounded in\b",
    r"\bleading (manufacturer|provider|company)\b",
    r"\bheadquartered\b",
    r"\bestablished\b",
    r"\bproud to\b",
)

BANNED_OPENERS = (
    "i hope you're doing well",
    "i hope this email finds you",
    "my name is",
    "i came across your",
    "i was impressed by",
    "congratulations on",
    "i noticed your company",
)

AI_CLICHES = (
    "synergy", "revolutionize", "game-changing", "cutting-edge",
    "leverage", "seamless", "delve", "landscape", "elevate your",
    "unlock", "transform your", "robust solution",
)

_SIGN_OFF_RE = re.compile(
    r"(?is)^(.*?)(?:\n+)((?:best regards|kind regards|regards|best|thanks|thank you|sincerely|"
    r"warm regards|cheers)[,!]?\s*\n+.+)\s*$"
)
_GREETING_RE = re.compile(
    r"(?is)^(hi|hello|dear)\b[^\n]{0,100},?\s*(?:\n+|$)"
)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'])")


def format_outreach_body(
    body: str,
    *,
    company_name: str = "",
    seller_name: str = "",
) -> str:
    """
    Ensure plain-text cold emails have scannable paragraph spacing.
    Models often return greeting + one dense wall + sign-off; split the wall.
    """
    text = (body or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return text

    # Normalize literal escaped newlines from some JSON payloads
    if "\\n" in text and text.count("\n") < 2:
        text = text.replace("\\n", "\n")

    greeting = ""
    sign_off = ""
    mid = text

    g = _GREETING_RE.match(text)
    if g:
        greeting = re.sub(r",?\s*$", ",", g.group(0).split("\n")[0].strip())
        # Prefer "Hi Company team," over bare "Hello," when we know the company
        if re.match(r"(?i)^hello,?$", greeting.rstrip(",")) and company_name:
            greeting = f"Hi {company_name.strip()} team,"
        mid = text[g.end():].strip()
    elif company_name:
        greeting = f"Hi {company_name.strip()} team,"

    sm = _SIGN_OFF_RE.match(mid)
    if sm:
        mid = (sm.group(1) or "").strip()
        sign_block = (sm.group(2) or "").strip()
        lines = [ln.strip() for ln in sign_block.split("\n") if ln.strip()]
        if lines:
            closer_raw = lines[0].rstrip(",!").strip().lower()
            if closer_raw in ("best", "thanks", "thank you", "cheers") or "regard" in closer_raw:
                closer = "Best regards"
            else:
                closer = lines[0].rstrip(",!")
            name = lines[1] if len(lines) > 1 else (seller_name or "")
            sign_off = f"{closer},\n{name}".strip() if name else f"{closer},"
    elif seller_name:
        sign_off = f"Best regards,\n{seller_name}"

    mid = re.sub(r"[ \t]+", " ", mid)
    mid = re.sub(r"\n{3,}", "\n\n", mid).strip()
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", mid) if p.strip()]
    # Single newlines inside a "paragraph" → treat as soft wraps, join
    paragraphs = [re.sub(r"\s*\n\s*", " ", p).strip() for p in paragraphs]

    needs_reflow = (
        len(paragraphs) <= 1
        or (len(paragraphs) == 2 and sum(len(p) for p in paragraphs) > 420)
        or any(len(p) > 380 for p in paragraphs)
    )
    if needs_reflow:
        flat = " ".join(paragraphs)
        sentences = [s.strip() for s in _SENTENCE_RE.split(flat) if s.strip()]
        if len(sentences) <= 1 and flat:
            sentences = [flat]
        paragraphs = _group_sentences_into_paragraphs(sentences)

    parts: List[str] = []
    if greeting:
        parts.append(greeting)
    parts.extend(paragraphs)
    if sign_off:
        parts.append(sign_off)
    return "\n\n".join(p for p in parts if p).strip() + "\n"


def _group_sentences_into_paragraphs(sentences: List[str]) -> List[str]:
    """1–2 sentences per paragraph; keep CTA question as its own block when possible."""
    if not sentences:
        return []
    out: List[str] = []
    buf: List[str] = []

    def flush() -> None:
        nonlocal buf
        if buf:
            out.append(" ".join(buf))
            buf = []

    for i, s in enumerate(sentences):
        is_cta = "?" in s and i >= max(0, len(sentences) - 2)
        starts_value = bool(re.match(r"^(For |Our |We('|’)ve |As |A brief )", s))
        if is_cta and buf:
            flush()
            out.append(s)
            continue
        if starts_value and buf:
            flush()
        buf.append(s)
        if len(buf) >= 2 or (len(buf) == 1 and len(s) > 180):
            flush()
    flush()
    return out


def _blob(*parts: Any) -> str:
    bits: List[str] = []
    for p in parts:
        if isinstance(p, str) and p.strip():
            bits.append(p.strip())
        elif isinstance(p, dict):
            for k in ("signal", "statement", "claim", "whyItMatters", "why_it_matters", "quote", "sourceExcerpt"):
                v = p.get(k)
                if isinstance(v, str) and v.strip():
                    bits.append(v.strip())
        elif isinstance(p, list):
            bits.append(_blob(*p))
    return " ".join(bits)


def _matches_any(text: str, patterns: Tuple[str, ...]) -> bool:
    low = (text or "").lower()
    return any(re.search(p, low) for p in patterns)


def _signal_tier(text: str) -> int:
    if not (text or "").strip():
        return 4
    if _matches_any(text, WEAK_PATTERNS) and not _matches_any(text, TIER1_PATTERNS + TIER2_PATTERNS):
        return 4
    if _matches_any(text, TIER1_PATTERNS):
        return 1
    if _matches_any(text, TIER2_PATTERNS):
        return 2
    return 3


def _first_product(matched_products: List[Dict[str, Any]]) -> Dict[str, str]:
    if not matched_products:
        return {"name": "", "fit": "", "reasoning": ""}
    p = matched_products[0]
    return {
        "name": (p.get("productName") or p.get("name") or "").strip(),
        "fit": (p.get("fitLevel") or p.get("fit") or "").strip(),
        "reasoning": (p.get("reasoning") or "").strip(),
    }


def _pick_primary_signal(
    signals: List[Dict[str, Any]],
    why_now: str,
    why_prospect: str,
    evidence: List[Dict[str, Any]],
) -> Tuple[str, str, int]:
    """Return (signal_text, source_label, tier). Prefer tier-1 buying signals."""
    candidates: List[Tuple[int, str, str]] = []

    if why_now and why_now.strip():
        candidates.append((_signal_tier(why_now), why_now.strip()[:280], "why_now"))

    for s in signals or []:
        label = (s.get("signal") or s.get("statement") or "").strip()
        matter = (s.get("whyItMatters") or s.get("why_it_matters") or "").strip()
        text = f"{label}. {matter}".strip(". ")
        if text:
            candidates.append((_signal_tier(text), text[:280], "buying_signal"))

    for e in evidence or []:
        claim = (e.get("claim") or "").lower()
        if claim not in ("intent", "offer", "icp", "motion"):
            continue
        stmt = (e.get("statement") or e.get("quote") or "").strip()
        if stmt:
            candidates.append((_signal_tier(stmt), stmt[:280], f"evidence:{claim}"))

    if why_prospect and why_prospect.strip():
        candidates.append((_signal_tier(why_prospect), why_prospect.strip()[:280], "why_prospect"))

    if not candidates:
        return ("", "none", 4)

    candidates.sort(key=lambda c: (c[0], -len(c[1])))
    best = candidates[0]
    return best[1], best[2], best[0]


def _select_angle(tier: int, signal: str, product_name: str, intent: str) -> str:
    low = (signal or "").lower()
    intent_l = (intent or "").lower()
    if tier <= 1 and _matches_any(low, (r"\b(expand|opening|new location|new facility|launch)\b",)):
        return "expansion"
    if tier <= 1 and _matches_any(low, (r"\b(hiring|procurement|rfp|rfq)\b",)):
        return "procurement"
    if tier <= 2 and _matches_any(low, (r"\b(renovat|construction|capacity|operational)\b",)):
        return "pain"
    if product_name and (intent_l in ("high", "low") or tier <= 2):
        return "product_fit"
    if tier <= 2:
        return "trigger"
    return "product_fit" if product_name else "conservative"


def _pain_hypothesis(signal: str, angle: str, product_name: str, confidence: str) -> str:
    """Inferred business implication — always hedged; never stated as confirmed fact."""
    if confidence == "low" or not signal:
        if product_name:
            return (
                f"Teams sourcing {product_name} often look for a supplier that can "
                "keep quality and availability steady as demand fluctuates."
            )
        return "They may periodically evaluate suppliers in categories that match our catalog."

    low = signal.lower()
    if angle == "expansion" or _matches_any(low, (r"\b(location|facility|store|branch|expand)\b",)):
        return (
            "As new sites come online, keeping product and equipment sourcing consistent "
            "across locations can become harder than expected."
        )
    if angle == "procurement" or _matches_any(low, (r"\b(hir|procur|rfp|rfq|supplier)\b",)):
        return (
            "When buying or staffing ramps up, having a clear shortlist of capable suppliers "
            "can reduce back-and-forth and delays."
        )
    if angle == "pain":
        return (
            "Operational changes like this often create pressure on supply consistency, "
            "lead times, or category coverage."
        )
    if product_name:
        return (
            f"Given their focus, they may periodically need reliable supply of {product_name} "
            "without juggling multiple one-off vendors."
        )
    return (
        "Their current activity suggests they may value a supplier who understands the "
        "category and can respond with relevant options quickly."
    )


def _value_proposition(product: Dict[str, str], angle: str, seller: str) -> str:
    name = product.get("name") or "our catalog"
    reason = product.get("reasoning") or ""
    base = (
        f"{seller} supplies {name}"
        if name != "our catalog"
        else f"{seller} can support categories that appear relevant to their operations"
    )
    if angle == "expansion":
        outcome = (
            "which can help standardize what new locations receive and simplify multi-site procurement"
        )
    elif angle == "procurement":
        outcome = "so their team can review fit and availability without starting from a blank search"
    elif angle == "pain":
        outcome = "with an eye toward reliability and fewer supplier handoffs"
    else:
        outcome = "when a practical, category-fit option is useful"
    if reason and len(reason) < 160 and not _matches_any(reason, WEAK_PATTERNS):
        return f"{base} — {reason.rstrip('.')} — {outcome}."
    return f"{base}, {outcome}."


def _cta_for_angle(angle: str, confidence: str) -> str:
    if confidence == "low":
        return "Is this category something you evaluate from time to time?"
    if angle == "expansion":
        return "Would it be useful if I sent a short selection of options suited to the type of sites you're opening?"
    if angle == "procurement":
        return "Would you like me to send the relevant product options for a quick look?"
    if angle == "pain":
        return "Worth sending a concise overview of what we can cover in this category?"
    return "Would you be open to a quick look at the range that seems most relevant?"


def _confidence(tier: int, has_product: bool, intent: str, why_now: str) -> str:
    intent_l = (intent or "").lower()
    if tier <= 1 and has_product and (why_now or intent_l in ("high", "low")):
        return "high"
    if tier <= 1 and (why_now or intent_l in ("high", "low")):
        return "high"
    if tier <= 2 and (has_product or intent_l in ("high", "low") or why_now):
        return "medium"
    if tier == 3 and has_product and (intent_l in ("high", "low") or why_now):
        return "medium"
    return "low"


def build_outreach_brief(
    *,
    company_name: str,
    why_prospect: str = "",
    why_now: str = "",
    signals: Optional[List[Dict[str, Any]]] = None,
    matched_products: Optional[List[Dict[str, Any]]] = None,
    evidence: Optional[List[Dict[str, Any]]] = None,
    location: str = "",
    industry: str = "",
    recommended_approach: str = "",
    fit_summary: str = "",
    intent: str = "",
    seller_name: str = "Sales Team",
) -> Dict[str, Any]:
    """
    Internal brief for email generation + UI rationale.
    Only uses provided research — never fabricates company events.
    """
    signals = signals or []
    matched_products = matched_products or []
    evidence = evidence or []
    seller = (seller_name or "Sales Team").strip() or "Sales Team"
    company = (company_name or "there").strip() or "there"

    primary, source, tier = _pick_primary_signal(signals, why_now, why_prospect, evidence)
    product = _first_product(matched_products)
    confidence = _confidence(tier, bool(product["name"]), intent, why_now)
    angle = _select_angle(tier, primary, product["name"], intent)

    # Why you — grounded in ICP/fit copy, not invented
    why_you_bits = []
    if why_prospect:
        why_you_bits.append(why_prospect.strip()[:320])
    elif industry or location:
        bit = f"{company}"
        if industry:
            bit += f" operates in {industry}"
        if location:
            bit += f"{' and is based in' if industry else ' appears based in'} {location}"
        why_you_bits.append(bit + ".")
    if product["name"] and product["reasoning"]:
        why_you_bits.append(f"Catalog match: {product['name']} — {product['reasoning'][:180]}")
    elif product["name"]:
        why_you_bits.append(f"Catalog match: {product['name']}.")
    why_you = " ".join(why_you_bits)[:500]

    why_now_out = ""
    if why_now and why_now.strip() and tier <= 3:
        why_now_out = why_now.strip()[:280]
    elif primary and tier <= 2 and source != "why_prospect":
        why_now_out = primary[:280]

    pain = _pain_hypothesis(primary or why_now_out, angle, product["name"], confidence)
    value = _value_proposition(product, angle, seller)
    cta = _cta_for_angle(angle, confidence)

    credibility = ""
    if product["name"] and product["fit"].lower() == "high":
        credibility = f"{product['name']} is a high-fit match against their public materials."
    elif recommended_approach:
        credibility = recommended_approach.strip()[:200]

    word_target = "150-220" if confidence == "high" else "120-180"

    rationale = {
        "primary_signal": primary or why_you[:180],
        "signal_source": source,
        "signal_confidence": confidence,
        "signal_tier": tier,
        "pain_hypothesis": pain,
        "matched_product": product["name"] or "",
        "product_fit": product["fit"] or "",
        "value_proposition": value,
        "why_you": why_you,
        "why_now": why_now_out,
        "angle": angle,
        "cta_strategy": "low_friction_interest",
        "cta": cta,
        "credibility": credibility,
        "location": (location or "").strip(),
        "industry": (industry or "").strip(),
        "fit_summary": (fit_summary or "").strip(),
        "intent": (intent or "").strip(),
        "seller_name": seller,
        "company_name": company,
        "word_target": word_target,
    }
    return rationale


def brief_to_personalized_reason(brief: Dict[str, Any]) -> str:
    parts = []
    if brief.get("primary_signal"):
        parts.append(f"Signal: {brief['primary_signal'][:160]}")
    if brief.get("matched_product"):
        parts.append(f"Product: {brief['matched_product']}")
    if brief.get("angle"):
        parts.append(f"Approach: {brief['angle']}")
    if brief.get("signal_confidence"):
        parts.append(f"Confidence: {brief['signal_confidence']}")
    return " · ".join(parts) if parts else "Drafted from available company evidence."


def build_generation_prompt(brief: Dict[str, Any]) -> str:
    """Prompt for Gemini/Groq — commercially intelligent, evidence-bound."""
    company = brief["company_name"]
    seller = brief["seller_name"]
    confidence = brief.get("signal_confidence") or "low"
    angle = brief.get("angle") or "conservative"

    allowed_facts = [
        f"- Why this company: {brief.get('why_you') or 'Limited public fit evidence — stay conservative.'}",
    ]
    if brief.get("why_now"):
        allowed_facts.append(f"- Why now (verified/public signal): {brief['why_now']}")
    else:
        allowed_facts.append("- Why now: NONE — do not invent timing urgency or expansion.")
    if brief.get("primary_signal"):
        allowed_facts.append(f"- Primary signal to use (at most one): {brief['primary_signal']}")
    allowed_facts.append(f"- Pain hypothesis (hedged language only — may/likely/can/often): {brief.get('pain_hypothesis')}")
    if brief.get("matched_product"):
        allowed_facts.append(
            f"- Matched product: {brief['matched_product']} "
            f"(fit={brief.get('product_fit') or 'n/a'})"
        )
    else:
        allowed_facts.append("- Matched product: none named — refer only to the seller's category generally.")
    allowed_facts.append(f"- Value angle: {brief.get('value_proposition')}")
    if brief.get("credibility"):
        allowed_facts.append(f"- Credibility (only if true): {brief['credibility']}")
    allowed_facts.append(f"- Suggested CTA: {brief.get('cta')}")
    if brief.get("location"):
        allowed_facts.append(f"- Location (optional, not primary personalization): {brief['location']}")
    if brief.get("industry"):
        allowed_facts.append(f"- Industry context: {brief['industry']}")

    return f"""You are an experienced B2B salesperson writing for {seller}.
Draft ONE personalized cold email to {company}.

Return ONLY valid JSON with keys:
- subject (string)
- body (string, plain text email including greeting and sign-off as {seller})
- personalizedReason (string, one short line for internal UI)
- subjectCandidates (array of 3 short subject options; you still set "subject" to the best one)

STRATEGY
Pipeline: Research → Relevance → Business problem → Value → Credibility → Low-friction CTA.
Chosen angle: {angle}
Evidence confidence: {confidence}
Target length: about {brief.get('word_target', '120-180')} words. Quality over padding — every sentence must earn its place.

ALLOWED FACTS (use only these — never invent company events, customers, prices, certifications, delivery times, or stats):
{chr(10).join(allowed_facts)}

STRUCTURE
1) Subject: short, natural, non-clickbait; related to situation/product — not "amazing opportunity".
2) Opening (1–2 sentences): start with the strongest allowed business signal. Do NOT open with hope-you're-well, my name is, I came across your website, I was impressed, or congratulations.
3) Relevance / problem bridge: connect the signal to a plausible requirement using hedged language (may, likely, can become, often).
4) Value: why {seller} / the matched product could help — outcomes (consistency, procurement ease, reliability), not a feature dump.
5) Credibility: at most one concise line, only from allowed facts. Skip if nothing solid.
6) CTA: exactly ONE low-friction question (prefer the suggested CTA). No calendar link, no multi-ask, no hard 30-min meeting ask.

FORMATTING (plain text — critical for readability in Gmail)
- Separate every section with a blank line (two newlines). Never pack the whole pitch into one dense paragraph.
- Exact layout:
  Hi {company} team,
  <blank line>
  Opening paragraph (1–2 sentences)
  <blank line>
  Relevance / problem bridge (1–2 sentences)
  <blank line>
  Value paragraph (1–2 sentences; optional credibility here)
  <blank line>
  CTA question alone
  <blank line>
  Best regards,
  {seller}
- Prefer "Hi {company} team," over bare "Hello," when no contact first name is known.
- Do not use Markdown, bullets, or HTML.

HARD RULES
- Do not dump a list of scraped facts.
- Do not use Tier-4 fluff (founded year, "leading company") as the main hook.
- Do not sound like an AI template or mass mailer.
- No emoji, no exclamation spam, no jargon (synergy, revolutionize, game-changing, cutting-edge, leverage, seamless).
- If confidence is low, stay conservative and avoid fake urgency.
- Sign off as {seller}.
"""


def build_follow_up_prompt(
    *,
    company_name: str,
    why_prospect: str,
    prior_subject: str,
    prior_body: str,
    reply_summary: str,
    seller_name: str,
) -> str:
    mode = "reply" if (reply_summary or "").strip() else "silence"
    return f"""You are an experienced B2B salesperson for {seller_name}.
Draft a follow-up email to {company_name} as JSON with keys subject, body, personalizedReason.

Mode: {"respond to their reply" if mode == "reply" else "polite bump after no reply"}.
Prior subject: {prior_subject}
Prior body (excerpt): {(prior_body or "")[:600]}
Reply summary: {(reply_summary or "")[:500] or "(none)"}
Context: {(why_prospect or "")[:400]}

Rules:
- Subject should be Re: if not already.
- 80–140 words. One clear CTA.
- Use blank lines between greeting, each short paragraph, CTA, and sign-off — never one dense block.
- Prefer "Hi {company_name} team," over bare "Hello,".
- If they replied, address their point first; do not re-pitch blindly.
- If silence, briefly restate relevance without guilt or pressure.
- No AI clichés. Sign as {seller_name}.
"""


def heuristic_quality_check(draft: Dict[str, Any], brief: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Fast local QC. Returns (ok, issues)."""
    issues: List[str] = []
    body = (draft.get("body") or "").strip()
    subject = (draft.get("subject") or "").strip()
    if not subject:
        issues.append("missing_subject")
    if not body:
        issues.append("missing_body")
        return False, issues

    words = len(re.findall(r"\b\w+\b", body))
    if words < 70:
        issues.append("too_short")
    if words > 280:
        issues.append("too_long")

    low = body.lower()
    for opener in BANNED_OPENERS:
        if low.lstrip().startswith(opener) or f"\n{opener}" in low[:120]:
            issues.append(f"banned_opener:{opener}")
            break

    for cliche in AI_CLICHES:
        if cliche in low:
            issues.append(f"cliche:{cliche}")

    if body.count("?") > 2:
        issues.append("multiple_ctas")

    # Wall of text: greeting/sign-off aside, still one long block
    chunks = [c.strip() for c in re.split(r"\n\s*\n", body) if c.strip()]
    mid_chunks = [
        c for c in chunks
        if not re.match(r"(?i)^(hi|hello|dear)\b", c)
        and not re.match(r"(?i)^(best regards|kind regards|regards|best|thanks|sincerely)\b", c)
    ]
    if len(mid_chunks) <= 1 and len(mid_chunks[0] if mid_chunks else "") > 320:
        issues.append("wall_of_text")

    # Hallucination-ish: claims expansion when brief has no why_now / weak signal
    if brief.get("signal_confidence") == "low":
        if re.search(r"\b(you recently|your recent expansion|new locations? you're opening)\b", low):
            if not (brief.get("why_now") or "").strip():
                issues.append("fabricated_timing")

    product = (brief.get("matched_product") or "").lower()
    if product and product not in low and product.split()[0] not in low:
        # Soft — product name optional if category referenced
        pass

    major = {
        "missing_subject", "missing_body", "banned_opener", "fabricated_timing",
        "too_short", "multiple_ctas", "wall_of_text",
    }
    failed_major = any(
        i in major or i.startswith("banned_opener") or i.startswith("fabricated")
        for i in issues
    )
    # too_short is major; cliche alone is not
    ok = not failed_major and "too_short" not in issues
    # Recalculate: banned and fabricated and missing and too_short and multiple_ctas fail
    hard_fail = False
    for i in issues:
        if i in ("missing_subject", "missing_body", "too_short", "multiple_ctas", "fabricated_timing"):
            hard_fail = True
        if i.startswith("banned_opener"):
            hard_fail = True
    return (not hard_fail), issues


def render_fallback_email(brief: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic commercially-sound draft when LLM unavailable."""
    company = brief["company_name"]
    seller = brief["seller_name"]
    signal = (brief.get("why_now") or brief.get("primary_signal") or "").strip()
    product = (brief.get("matched_product") or "our products").strip()
    pain = brief.get("pain_hypothesis") or ""
    value = brief.get("value_proposition") or ""
    cta = brief.get("cta") or "Would it be useful if I sent over a few relevant options?"
    confidence = brief.get("signal_confidence") or "low"

    if signal and confidence != "low":
        opening = f"I saw that {company} — {signal.rstrip('.')}."
        if not opening.endswith("."):
            opening += "."
    elif signal:
        opening = (
            f"I've been reviewing {company} in connection with "
            f"{signal.rstrip('.')}."
        )
        if not opening.endswith("."):
            opening += "."
    else:
        opening = (
            f"I'm reaching out because {company} looks like a relevant fit for "
            f"what {seller} supplies — based on how they present their business publicly."
        )

    bridge = pain
    if bridge and not bridge[0].isupper():
        bridge = bridge[0].upper() + bridge[1:]

    mid = value
    if confidence == "low":
        mid = (
            f"{value}\n\n"
            "I don't want to over-assume on timing — if this category isn't active "
            "for you right now, feel free to ignore this note."
        )

    body = (
        f"Hi {company} team,\n\n"
        f"{opening}\n\n"
        f"{bridge}\n\n"
        f"{mid}\n\n"
        f"{cta}\n\n"
        f"Best regards,\n{seller}"
    )
    body = format_outreach_body(body, company_name=company, seller_name=seller)

    # Subject candidates
    subjects = []
    if brief.get("angle") == "expansion" and product:
        subjects.append(f"{product} for your growth plans")
    if product and company:
        subjects.append(f"{product} for {company}")
    if brief.get("angle") == "procurement":
        subjects.append(f"Sourcing options for {company}")
    subjects.append(f"Quick question for {company}")
    subjects = list(dict.fromkeys(s for s in subjects if s))[:3]
    subject = subjects[0] if subjects else f"Introduction — {seller}"

    return {
        "subject": subject[:140],
        "body": body,
        "personalizedReason": brief_to_personalized_reason(brief),
        "subjectCandidates": subjects,
        "outreachRationale": {
            "primary_signal": brief.get("primary_signal") or "",
            "signal_source": brief.get("signal_source") or "",
            "signal_confidence": confidence,
            "pain_hypothesis": brief.get("pain_hypothesis") or "",
            "matched_product": brief.get("matched_product") or "",
            "value_proposition": brief.get("value_proposition") or "",
            "cta_strategy": brief.get("cta_strategy") or "low_friction_interest",
            "angle": brief.get("angle") or "",
        },
    }
