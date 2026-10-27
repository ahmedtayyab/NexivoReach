"""
Free buyer lists that are not a search ranking.

Industry giants occupy the first pages of web search. Stockist locators and
trade-show exhibitor pages list independent shops and regional distributors —
the companies more likely to buy from a manufacturer. Each entry still goes
through the hunt's website read, country check, email fetch, and dedup.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from app.agents.serp_classifier import classify_page, extract_directory_companies
from app.services.business_sources import (
    USER_AGENT,
    BusinessCandidate,
    SourceStep,
    _clean,
    _host,
    resolve_company_website,
)

log = logging.getLogger(__name__)

# Own-shop hosts of brands we use as stockist seeds. Never saved as leads.
BRAND_HOSTS: Tuple[str, ...] = (
    "roguefitness.com", "gymreapers.com", "sbdapparel.com", "sbd.equipment",
    "rdxsports.com", "rdxsports.co.uk", "harbingerfitness.com", "rehband.com",
    "tuffwraps.com", "ironbullstrength.com", "nordiclifting.com", "cerberus-strength.com",
    "markbellslingshot.com", "gymshark.com", "hayabusa.com", "rdxsports.eu",
)

_LIFTING_BRANDS = (
    "SBD", "Gymreapers", "Rogue Fitness", "Harbinger", "Rehband",
    "Cerberus Strength", "TuffWraps", "Iron Bull Strength",
)
_BOXING_BRANDS = ("RDX", "Hayabusa", "Twins Special", "Fairtex", "Rival Boxing")
_FITNESS_BRANDS = ("Gymreapers", "RDX", "SBD", "Harbinger")

_STOCKIST_PATH = re.compile(
    r"/(stockists?|dealers?|distributors?|where-to-buy|find[-_]a[-_]dealer|"
    r"store[-_]locator|retailers|authorised[-_]dealers?|authorized[-_]dealers?)",
    re.I,
)

EXHIBITOR_URLS: Tuple[str, ...] = (
    "https://www.elevatearena.com/london/exhibitors/2026-exhibitors",
    "https://www.fibo.com/germany/en-gb/exhibitor-directory.html",
    "https://www.ispovo.com/en/exhibitors",
)


def stockist_brands(product: str) -> List[str]:
    blob = (product or "").lower()
    if any(w in blob for w in ("box", "fight", "mma", "glove", "martial")):
        return list(_BOXING_BRANDS)
    if any(w in blob for w in ("knee", "sleeve", "wrap", "strap", "belt", "hook", "grip", "lift")):
        return list(_LIFTING_BRANDS)
    return list(_FITNESS_BRANDS)


def is_stockist_page(url: str, title: str = "") -> bool:
    del title
    path = (urlparse(url or "").path or "").lower()
    return bool(_STOCKIST_PATH.search(path))


def stockist_query(brand: str, place: str) -> str:
    loc = _clean(place) or "worldwide"
    return _clean(f"{brand} stockists dealers {loc}")


def parse_list_cursor(raw: str) -> int:
    try:
        return max(0, int(json.loads(raw).get("i") if raw.startswith("{") else raw or 0))
    except Exception:
        try:
            return max(0, int(raw or 0))
        except Exception:
            return 0


def _candidates_from_html(html: str, page_url: str, limit: int = 20) -> List[BusinessCandidate]:
    links = extract_directory_companies(html, page_url, limit=limit)
    out: List[BusinessCandidate] = []
    seen: set[str] = set()
    for link in links:
        host = _host(link)
        if not host or host in seen:
            continue
        seen.add(host)
        out.append(BusinessCandidate(name="", website=link, source="stockists"))
    return out


def stockist_step(
    *,
    product: str,
    place: str,
    cursor: str,
    searcher: Callable[[str], List[Dict[str, str]]],
    client: Optional[httpx.Client] = None,
    fetch_html: Optional[Callable[[str], str]] = None,
) -> SourceStep:
    """
    One brand's dealer/stockist results. The brand shop is skipped.
    Independent shops and regional distributors on those pages are the leads.
    """
    brands = stockist_brands(product)
    index = parse_list_cursor(cursor)
    step = SourceStep(source="stockists", query=stockist_query(brands[index], place) if index < len(brands) else "")
    if index >= len(brands):
        step.exhausted = True
        step.note = "Every brand stockist search for this trade has been read."
        return step
    brand = brands[index]
    query = stockist_query(brand, place)
    step.query = query
    try:
        hits = searcher(query) or []
    except Exception as exc:
        step.next_cursor = str(index + 1)
        step.exhausted = (index + 1) >= len(brands)
        step.note = f"Stockist search for {brand} did not answer: {exc}"
        return step

    own = client is None and fetch_html is None
    client = client or (
        httpx.Client(timeout=12.0, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        if fetch_html is None else None
    )

    def _html(url: str) -> str:
        if fetch_html is not None:
            return fetch_html(url)
        try:
            res = client.get(url)
            if res.status_code != 200:
                return ""
            return res.text or ""
        except Exception:
            return ""

    found: List[BusinessCandidate] = []
    seen: set[str] = set()
    try:
        for hit in hits[:10]:
            url = str(hit.get("href") or "").strip()
            title = str(hit.get("title") or "")
            if not url.startswith("http"):
                continue
            host = _host(url)
            if not host or host in seen:
                continue
            page = classify_page(url, title)
            brand_own = any(host == h or host.endswith("." + h) for h in BRAND_HOSTS)
            if page["page_kind"] == "directory" or is_stockist_page(url) or brand_own:
                html = _html(url)
                for cand in _candidates_from_html(html, url):
                    h = _host(cand.website)
                    if h and h not in seen:
                        seen.add(h)
                        cand.source = "stockists"
                        found.append(cand)
                if page["page_kind"] != "company":
                    continue
            if page["page_kind"] != "company":
                continue
            seen.add(host)
            found.append(BusinessCandidate(
                name=_clean(title),
                website=url,
                source="stockists",
            ))
    finally:
        if own and client is not None:
            client.close()

    step.candidates = found
    step.next_cursor = str(index + 1)
    step.exhausted = (index + 1) >= len(brands)
    step.note = (
        f"Stockists: {brand} — {len(found)} company websites "
        f"(independent shops and regional dealers, not the brand itself)."
    )
    return step


def exhibitor_urls_for_plan(plan: Dict[str, Any]) -> List[str]:
    del plan
    return list(EXHIBITOR_URLS)


def extract_exhibitor_names(html: str, limit: int = 40) -> List[str]:
    """Company names printed on a show directory when outbound websites are missing."""
    if not html:
        return []
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return []
    soup = BeautifulSoup(html, "html.parser")
    names: List[str] = []
    seen: set[str] = set()
    skip = re.compile(
        r"^(exhibitors?|stand|hall|sponsor|media|register|contact|home|about|"
        r"floorplan|tickets?|dates?|visitors?)$",
        re.I,
    )
    for tag in soup.select("h2, h3, h4, a, [class*='exhibitor'], [class*='Exhibitor']"):
        text = _clean(tag.get_text(" ", strip=True))
        if not text or skip.match(text) or len(text) < 3 or len(text) > 70:
            continue
        if re.search(r"https?://|@|stand\s+[a-z]?\d", text, re.I):
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(text)
        if len(names) >= limit:
            break
    return names


def exhibitor_step(
    *,
    urls: List[str],
    cursor: str,
    searcher: Callable[[str], List[Dict[str, str]]],
    country_label: str = "",
    client: Optional[httpx.Client] = None,
    fetch_html: Optional[Callable[[str], str]] = None,
    prober: Optional[Callable[[str], str]] = None,
    resolve_limit: int = 12,
    pause_sec: float = 0.0,
) -> SourceStep:
    """One exhibitor directory page. The show site is never a lead."""
    import time

    index = parse_list_cursor(cursor)
    step = SourceStep(source="exhibitors", query=urls[index] if index < len(urls) else "")
    if index >= len(urls):
        step.exhausted = True
        step.note = "Every exhibitor list for this hunt has been read."
        return step
    url = urls[index]
    own = client is None and fetch_html is None
    client = client or (
        httpx.Client(timeout=15.0, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        if fetch_html is None else None
    )
    html = ""
    try:
        if fetch_html is not None:
            html = fetch_html(url) or ""
        else:
            res = client.get(url)
            step.requests_used = 1
            if res.status_code >= 400:
                step.next_cursor = str(index + 1)
                step.exhausted = (index + 1) >= len(urls)
                step.note = f"Exhibitor page did not load ({res.status_code}): {url}"
                return step
            html = res.text or ""
    except Exception as exc:
        step.next_cursor = str(index + 1)
        step.exhausted = (index + 1) >= len(urls)
        step.note = f"Exhibitor page did not answer: {exc}"
        return step
    finally:
        if own and client is not None:
            client.close()

    from_links = extract_directory_companies(html, url, limit=20)
    found: List[BusinessCandidate] = [
        BusinessCandidate(name="", website=link, source="exhibitors") for link in from_links
    ]
    if len(found) < 4:
        names = extract_exhibitor_names(html, limit=resolve_limit)
        resolved = 0
        for n, name in enumerate(names):
            if resolved >= resolve_limit:
                break
            if n:
                time.sleep(pause_sec)
            site = resolve_company_website(name, searcher, place_hint=country_label, prober=prober or (lambda _n: ""))
            if site:
                found.append(BusinessCandidate(name=name, website=site, address=country_label, source="exhibitors"))
                resolved += 1
        step.skipped_without_website = max(0, len(names) - resolved)

    step.candidates = found
    step.next_cursor = str(index + 1)
    step.exhausted = (index + 1) >= len(urls)
    step.note = f"Exhibitors listed {len(found)} companies on {url}."
    return step
