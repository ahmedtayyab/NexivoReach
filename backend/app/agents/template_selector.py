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
    # Blank line after the intro so bullets stay a real list in plain-text email
    return "We specialize in:\n\n" + "\n".join(f"• {line}" for line in cleaned)


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
    filled_body = re.sub(r",{2,}", ",", filled_body)
    filled_body = re.sub(r"\s+:", ":", filled_body)
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
    Score a template against lead signals using tags, product keywords, and specialize lines.
    Category is a weak hint only — never required.
    """
    cat = str(template.get("category") or "").strip()
    tags = [str(t).strip() for t in (template.get("tags") or []) if str(t).strip()]
    name = str(template.get("name") or "").strip()
    specialize = [
        str(x).strip()
        for x in (template.get("specializeLines") or template.get("specialize_lines") or [])
        if str(x).strip()
    ]
    body = str(template.get("body") or "")
    cat_n = _norm(cat)
    tag_norms = [_norm(t) for t in tags]
    specialize_norms = [_norm(s) for s in specialize]
    lead_cats = [_norm(c) for c in (signals.get("matchedCategories") or [])]
    top_products = [_norm(p) for p in (signals.get("topProducts") or []) if p]
    blob = signals.get("blob") or ""
    tokens: set[str] = set(signals.get("tokens") or set())

    score = 0.0
    reasons: List[str] = []

    # Strong: tags / specialize product phrases in lead products or text
    tag_hits = []
    for tn in tag_norms + specialize_norms:
        if len(tn) < 3:
            continue
        if tn in blob or any(tn == tok or tn in tok or tok in tn for tok in tokens):
            tag_hits.append(tn)
        elif any(tn in tp or tp in tn for tp in top_products if tp):
            tag_hits.append(tn)
    if tag_hits:
        score += 28 * min(len(tag_hits), 5)
        reasons.append(f"tags/products hit: {', '.join(tag_hits[:4])}")

    # Soft: category label overlaps product fit (optional)
    if cat_n and lead_cats:
        if cat_n in lead_cats:
            score += 35
            reasons.append(f"category matches product fit ({cat})")
        elif any(cat_n in lc or lc in cat_n for lc in lead_cats if lc):
            score += 20
            reasons.append(f"category overlaps product fit ({cat})")

    cat_tokens = _tokens(cat)
    cat_token_hits = [t for t in cat_tokens if t in tokens or t in blob]
    if cat_token_hits and score < 60:
        score += 10 * min(len(cat_token_hits), 3)
        reasons.append(f"keywords in lead: {', '.join(cat_token_hits[:3])}")

    name_hits = [t for t in _tokens(name) if t in tokens]
    if name_hits and score < 50:
        score += 5 * min(len(name_hits), 2)

    # Body product nouns (e.g. straps, wraps) vs lead
    body_tokens = _tokens(re.sub(r"\{\{[^}]+\}\}", " ", body))
    body_hits = [t for t in body_tokens if len(t) >= 4 and (t in tokens or t in blob)]
    if body_hits and score < 70:
        score += 4 * min(len(set(body_hits)), 4)

    # Soft penalty only when tags clearly conflict and nothing hit
    if lead_cats and cat_n and tag_hits == []:
        aligned = cat_n in lead_cats or any(cat_n in lc or lc in cat_n for lc in lead_cats)
        if not aligned and cat_tokens and not any(t in tokens for t in cat_tokens):
            score = min(score, 25)
            reasons.append("weak keyword overlap")

    reason = "; ".join(reasons) if reasons else "weak match"
    return score, reason


# Minimum score to accept a template. Below this → AI fallback (never wrong product).
MIN_TEMPLATE_SCORE = 35


def select_outreach_template(
    templates: Sequence[Dict[str, Any]],
    signals: Dict[str, Any],
    *,
    min_score: float = MIN_TEMPLATE_SCORE,
) -> Optional[Dict[str, Any]]:
    """
    Pick the best template by tags / product keywords, or None if no safe match.
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

    if best_score < min_score:
        return None

    out = dict(best)
    out["_matchScore"] = best_score
    out["_matchReason"] = best_reason
    return out
