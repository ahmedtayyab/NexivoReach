"""Turn a hunt's exact lines into a few extra buyer searches in the same category."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Dict, List

log = logging.getLogger(__name__)

_ROLE = re.compile(r"\b(distributors?|wholesalers?|importers?)\b", re.I)
_JUNK_QUERY = re.compile(r"\b(best|top\s+\d+|review|reviews|guide|blog|how to)\b", re.I)
_MAX_EXTRA = 8


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _already_has_place(query: str, place: str) -> bool:
    text = query.lower()
    if place.lower() in text:
        return True
    head = place.split(",")[0].strip().lower()
    return bool(head) and head in text


def sanitize_category_queries(
    raw: List[str],
    *,
    location: str,
    existing: List[str],
) -> List[str]:
    """Keep buyer queries only. Drop listicles and lines the user already typed."""
    place = _clean(location)
    seen = {_clean(item).lower() for item in existing if _clean(item)}
    out: List[str] = []
    for item in raw or []:
        query = _clean(str(item))
        query = re.sub(r"^[\"']+|[\"']+$", "", query)
        if not query or _JUNK_QUERY.search(query) or not _ROLE.search(query):
            continue
        if place and not _already_has_place(query, place):
            query = f"{query} {place}"
        key = query.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(query)
        if len(out) >= _MAX_EXTRA:
            break
    return out


def _fallback_queries(lines: List[str], location: str) -> List[str]:
    """Used when the model is unavailable. Stays inside wholesale buyer wording."""
    blob = " ".join(lines).lower()
    place = _clean(location)
    tail = f" {place}" if place else ""
    seeds: List[str] = []
    if any(word in blob for word in ("weightlift", "strength", "gym", "fitness", "accessory", "equipment")):
        seeds = [
            f"fitness equipment distributors{tail}",
            f"gym accessories wholesalers{tail}",
            f"strength training equipment importers{tail}",
            f"sports equipment distributors{tail}",
        ]
    elif any(word in blob for word in ("boxing", "mma", "martial")):
        seeds = [
            f"boxing equipment distributors{tail}",
            f"martial arts equipment wholesalers{tail}",
            f"combat sports equipment importers{tail}",
        ]
    return sanitize_category_queries(seeds, location=place, existing=lines)


async def expand_category_queries(lines: List[str], location: str) -> Dict[str, object]:
    """
    One model call. Original lines are not replaced.
    Returns {"category": str, "queries": list[str]}.
    """
    clean_lines = [_clean(line) for line in lines if _clean(line)]
    place = _clean(location)
    if not clean_lines:
        return {"category": "", "queries": []}

    prompt = (
        "A manufacturer is hunting B2B buyers. Read the hunt lines and the location.\n"
        "Return JSON with keys category (short trade name) and queries (array of strings).\n"
        "queries: 5 to 8 searches a buyer researcher would type for the SAME category, "
        "even when the wording differs from the lines.\n"
        "Each query must end with the location and must include distributor, wholesaler, or importer.\n"
        "Do not repeat the original lines. No reviews, blogs, guides, or 'best' lists.\n\n"
        f"Location: {place or '(none)'}\n"
        "Lines:\n"
        + "\n".join(f"- {line}" for line in clean_lines[:48])
    )
    parsed: Dict[str, object] = {}
    try:
        from app.providers.factory import get_ai_provider
        from app.providers.json_util import parse_json_payload

        provider = get_ai_provider()
        raw = ""
        if getattr(provider, "available", False) and hasattr(provider, "_complete"):
            raw = await asyncio.wait_for(asyncio.to_thread(provider._complete, prompt), timeout=20.0)
        elif getattr(provider, "available", False) and hasattr(provider, "_generate"):
            raw = await asyncio.wait_for(asyncio.to_thread(provider._generate, prompt), timeout=20.0)
        if raw:
            loaded = parse_json_payload(raw)
            if isinstance(loaded, dict):
                parsed = loaded
    except Exception as exc:
        log.warning("Category query expansion failed: %s", exc)

    category = _clean(str(parsed.get("category") or ""))
    raw_queries = parsed.get("queries") if isinstance(parsed.get("queries"), list) else []
    queries = sanitize_category_queries(
        [str(item) for item in raw_queries],
        location=place,
        existing=clean_lines,
    )
    if not queries:
        queries = _fallback_queries(clean_lines, place)
        if queries and not category:
            category = "related buyers"
    return {"category": category, "queries": queries}
