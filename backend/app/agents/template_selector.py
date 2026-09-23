"""Pick the safest matching outreach template for a lead — never a wrong category."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(_norm(text)) if len(t) > 2}


def _specialize_block(lines: Sequence[str]) -> str:
    cleaned = [str(x).strip() for x in (lines or []) if str(x).strip()]
    if not cleaned:
        return ""
    return "We specialize in:\n" + "\n".join(f"• {line}" for line in cleaned)


def fill_outreach_template(
    *,
    subject: str,
    body: str,
    specialize_lines: Sequence[str] | None = None,
    vars: Dict[str, str] | None = None,
) -> Tuple[str, str]:
    """Replace {{placeholders}} in subject/body. Unknown keys left intact."""
    mapping = {k: (v if v is not None else "") for k, v in (vars or {}).items()}
    if "specialize" not in mapping:
        mapping["specialize"] = _specialize_block(specialize_lines or [])

    def repl(text: str) -> str:
        out = text or ""
        for key, val in mapping.items():
            for form in (f"{{{{{key}}}}}", f"{{{{{key.title()}}}}}", f"{{{{{key.upper()}}}}}"):
                out = out.replace(form, val)
            # common aliases
        out = out.replace("{{Company}}", mapping.get("company", ""))
        out = out.replace("{{COMPANY}}", mapping.get("company", ""))
        return out

    filled_subject = repl(subject).strip()
    filled_body = repl(body).strip()
    # Drop empty specialize placeholder lines if unused
    filled_body = re.sub(r"\n{3,}", "\n\n", filled_body)
    return filled_subject, filled_body


def build_lead_signals(
    *,
    company_name: str = "",
    industry: str = "",
    why_prospect: str = "",
    why_now: str = "",
    product_fit: Sequence[Dict[str, Any]] | None = None,
    catalog_products: Sequence[Dict[str, Any]] | None = None,
    fit_breakdown: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Extract category/product tokens used for template scoring."""
    fb = fit_breakdown or {}
    fits = list(product_fit or [])
    # Prefer High product fits
    fits_sorted = sorted(
        fits,
        key=lambda p: (
            0 if str(p.get("fitLevel") or p.get("fit_level") or "").lower() == "high" else 1,
            0 if str(p.get("fitLevel") or p.get("fit_level") or "").lower() == "medium" else 1,
        ),
    )
    top_names = [
        str(p.get("productName") or p.get("product_name") or "").strip()
        for p in fits_sorted
        if (p.get("productName") or p.get("product_name"))
    ]
    catalog = list(catalog_products or [])
    name_to_cat: Dict[str, str] = {}
    for p in catalog:
        n = _norm(str(p.get("name") or ""))
        c = str(p.get("category") or "").strip()
        if n and c:
            name_to_cat[n] = c

    matched_categories: List[str] = []
    for name in top_names:
        cat = name_to_cat.get(_norm(name))
        if cat and cat not in matched_categories:
            matched_categories.append(cat)
        # fuzzy: catalog name contained in fit name or vice versa
        if not cat:
            for cn, cc in name_to_cat.items():
                if cn and (_norm(name) in cn or cn in _norm(name)):
                    if cc not in matched_categories:
                        matched_categories.append(cc)
                    break

    discovery = str(fb.get("discoveryQuery") or fb.get("discovery_query") or "")
    blob = " ".join(
        [
            company_name,
            industry,
            why_prospect,
            why_now,
            discovery,
            " ".join(top_names),
            " ".join(matched_categories),
            " ".join(str(p.get("reasoning") or "") for p in fits_sorted[:5]),
        ]
    )
    return {
        "topProducts": top_names[:5],
        "matchedCategories": matched_categories,
        "tokens": _tokens(blob),
        "blob": _norm(blob),
        "industry": industry or "",
        "discoveryQuery": discovery,
    }


def score_template(template: Dict[str, Any], signals: Dict[str, Any]) -> Tuple[float, str]:
    """
    Score a template against lead signals.
    Returns (score, reason). Score < threshold means "do not use".
    """
    cat = str(template.get("category") or "").strip()
    tags = [str(t).strip() for t in (template.get("tags") or []) if str(t).strip()]
    name = str(template.get("name") or "").strip()
    cat_n = _norm(cat)
    tag_norms = [_norm(t) for t in tags]
    lead_cats = [_norm(c) for c in (signals.get("matchedCategories") or [])]
    blob = signals.get("blob") or ""
    tokens: set[str] = set(signals.get("tokens") or set())

    score = 0.0
    reasons: List[str] = []

    # Strong: exact / containment match with catalog-derived category from productFit
    if cat_n and lead_cats:
        if cat_n in lead_cats:
            score += 100
            reasons.append(f"category matches product fit ({cat})")
        elif any(cat_n in lc or lc in cat_n for lc in lead_cats if lc):
            score += 80
            reasons.append(f"category overlaps product fit ({cat})")

    # Tags / category tokens in lead blob (product names, why, discovery query)
    cat_tokens = _tokens(cat)
    tag_hits = []
    for tn in tag_norms:
        if len(tn) < 3:
            continue
        if tn in blob or any(tn == tok or tn in tok or tok in tn for tok in tokens):
            tag_hits.append(tn)
    if tag_hits:
        score += 18 * min(len(tag_hits), 4)
        reasons.append(f"tags hit: {', '.join(tag_hits[:4])}")

    # Category word presence in lead text
    cat_token_hits = [t for t in cat_tokens if t in tokens or t in blob]
    if cat_token_hits and score < 80:
        score += 12 * min(len(cat_token_hits), 3)
        reasons.append(f"category words in lead: {', '.join(cat_token_hits[:3])}")

    # Name words (weak)
    name_hits = [t for t in _tokens(name) if t in tokens]
    if name_hits and score < 50:
        score += 5 * min(len(name_hits), 2)

    # Penalty: other lead categories strongly present that conflict
    # e.g. lead matchedCategories = boxing, template = weightlifting → don't boost
    if lead_cats and cat_n and cat_n not in lead_cats and not any(
        cat_n in lc or lc in cat_n for lc in lead_cats
    ):
        # If tags also don't hit, kill the score
        if not tag_hits:
            score = min(score, 15)
            reasons.append("blocked: lead product category differs")

    reason = "; ".join(reasons) if reasons else "weak match"
    return score, reason


# Minimum score to accept a template. Below this → AI fallback (never wrong category).
MIN_TEMPLATE_SCORE = 40


def select_outreach_template(
    templates: Sequence[Dict[str, Any]],
    signals: Dict[str, Any],
    *,
    min_score: float = MIN_TEMPLATE_SCORE,
) -> Optional[Dict[str, Any]]:
    """
    Pick the best template, or None if no safe match.
    Guarantees: when lead has clear product categories, never return a template
    whose category conflicts with all of them unless tags strongly hit.
    """
    if not templates:
        return None

    scored: List[Tuple[float, str, Dict[str, Any]]] = []
    for tpl in templates:
        if not (tpl.get("body") or "").strip():
            continue
        s, reason = score_template(tpl, signals)
        scored.append((s, reason, tpl))

    if not scored:
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_reason, best = scored[0]

    lead_cats = [_norm(c) for c in (signals.get("matchedCategories") or [])]
    best_cat = _norm(str(best.get("category") or ""))

    # Hard guard: if we know the lead's product category, reject mismatched winners
    if lead_cats and best_cat:
        aligned = best_cat in lead_cats or any(best_cat in lc or lc in best_cat for lc in lead_cats)
        if not aligned:
            # Allow only if tag score alone was very strong AND no competing aligned template
            aligned_candidates = [
                x for x in scored
                if _norm(str(x[2].get("category") or "")) in lead_cats
                or any(
                    _norm(str(x[2].get("category") or "")) in lc
                    or lc in _norm(str(x[2].get("category") or ""))
                    for lc in lead_cats
                )
            ]
            if aligned_candidates:
                best_score, best_reason, best = aligned_candidates[0]
            elif best_score < 70:
                return None

    if best_score < min_score:
        return None

    out = dict(best)
    out["_matchScore"] = best_score
    out["_matchReason"] = best_reason
    return out
