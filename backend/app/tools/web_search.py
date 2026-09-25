import asyncio
import gzip
import html as html_lib
import logging
import re
import time
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings

log = logging.getLogger(__name__)

# Shared hosts (CSF/LFD, Imunify360) auto-ban IPs that burst. Stay under their radar.
CATALOG_CONCURRENCY = 5
CATALOG_BATCH_PAUSE = 0.35
CATALOG_LIMITS = httpx.Limits(max_connections=CATALOG_CONCURRENCY, max_keepalive_connections=CATALOG_CONCURRENCY)
CATALOG_MAX_PRODUCTS = 5000
CATALOG_MAX_LISTING_PAGES = 250
CATALOG_TIME_BUDGET_SEC = 300.0
CATALOG_WP_REST_MAX_PAGES = max(1, CATALOG_MAX_PRODUCTS // 100)
# Only skip the HTML cascade when a platform API already returned a sizable catalog.
CATALOG_API_MIN_TRUST = 100
CATALOG_SITEMAP_NEST_LIMIT = 120
CATALOG_LISTING_SEED_CAP = 120
CATALOG_PAGINATION_CAP = 80
CATALOG_EMPTY_PAGE_STREAK = 3  # stop a listing branch after N consecutive empty pages
CATALOG_LINK_HARVEST_IF_BELOW = 10_000  # always union link harvest with card parse
CATALOG_MAX_PAGE_PROBE = 60  # synthesize page URLs up to this when UI reveals max page


SKIP_DOMAINS = {
    "wikipedia.org",
    "wikimedia.org",
    "youtube.com",
    "youtu.be",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "reddit.com",
    "pinterest.com",
    "tiktok.com",
    "duckduckgo.com",
    "google.com",
    "bing.com",
    "yahoo.com",
    "example.com",
    "example.org",
    "example.net",
    "medium.com",
    "quora.com",
    "linkedin.com",
}

ARTICLE_HINTS = (
    "/blog",
    "/news",
    "/knowledge",
    "/article",
    "/guide",
    "/resources",
    "/insights",
    "/learn",
    "/wiki",
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _registrable_domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _should_skip(url: str) -> bool:
    host = _registrable_domain(url)
    if not host:
        return True
    return any(host == d or host.endswith("." + d) for d in SKIP_DOMAINS)


def _looks_like_article(title: str, url: str) -> bool:
    path = (urlparse(url).path or "").lower()
    if any(hint in path for hint in ARTICLE_HINTS):
        return True
    if path.count("/") >= 3 and len(path) > 24:
        return True
    return bool(re.match(r"^(guide|how to|complete|what is|top \d+|best )\b", title or "", re.I))


def _brand_from_url(url: str) -> str:
    host = _registrable_domain(url)
    if not host:
        return ""
    slug = host.split(".")[0]
    return slug.replace("-", " ").title()


def display_name_from_url(url: str) -> str:
    """Human label from domain slug, e.g. alwasi-ent.com → Alwasi Ent."""
    return _brand_from_url(url)


def site_display_name_from_url(url: str) -> str:
    """
    Best-effort company name from a website: og:site_name / <title>, then domain slug.
    """
    if not (url or "").strip():
        return ""
    try:
        with httpx.Client(timeout=8.0, follow_redirects=True, headers=HEADERS) as client:
            root = urljoin(url.strip(), "/")
            res = client.get(root)
            if res.status_code == 200 and res.text:
                soup = BeautifulSoup(res.text, "html.parser")
                og = soup.find("meta", property="og:site_name")
                if og and og.get("content"):
                    label = og.get("content", "").strip()
                    if label:
                        return re.sub(r"[®™]", "", label).strip()[:80]
                title = soup.find("title")
                if title and title.get_text(strip=True):
                    t = title.get_text(strip=True)
                    t = re.split(r"\s[|\-–:]\s", t, maxsplit=1)[0].strip()
                    t = re.sub(r"[®™]", "", t).strip()
                    if t and not _looks_like_article(t, root):
                        return t[:80]
    except Exception:
        pass
    return display_name_from_url(url)


_GENERIC_TITLE_PARTS = frozenset({
    "home", "homepage", "home page", "welcome", "index", "shop", "store", "products",
    "catalog", "catalogue", "about", "about us", "contact", "contact us", "wholesale",
    "online store", "official site", "official website", "main page", "untitled",
})


def _company_name_from_title(title: str, url: str) -> str:
    """
    'Home | Martial Arts Supermarket' → 'Martial Arts Supermarket'.
    Generic page words never become a company name; fall back to the domain.
    """
    parts = [
        re.sub(r"[®™]", "", p).strip()
        for p in re.split(r"\s[|\-–:—]\s", title or "")
    ]
    parts = [p for p in parts if p]
    for part in parts:
        low = part.lower().strip(" .!")
        if low in _GENERIC_TITLE_PARTS:
            continue
        if re.fullmatch(r"(home|welcome|shop|store)\s*(page)?", low):
            continue
        if _looks_like_article(part, url) or len(part) > 60:
            continue
        return part
    return _brand_from_url(url) or (parts[0] if parts else title)


def results_to_companies(results: List[Dict[str, str]], target_location: str = "") -> List[Dict[str, Any]]:
    prefer = [target_location] if target_location else None
    companies: List[Dict[str, Any]] = []
    seen = set()
    for item in results:
        url = (item.get("href") or item.get("link") or item.get("url") or "").strip()
        title = (item.get("title") or "").strip()
        snippet = (item.get("body") or item.get("snippet") or item.get("description") or "").strip()
        if not url or not title or _should_skip(url):
            continue
        domain = _registrable_domain(url)
        if domain in seen:
            continue
        seen.add(domain)
        name = _company_name_from_title(title, url)
        path = urlparse(url).path.rstrip("/")
        homepage_bonus = 1 if path in ("", "/en", "/de", "/fr", "/about", "/about-us") else 0
        article_penalty = 1 if _looks_like_article(title, url) else 0
        companies.append({
            "company_name": name[:120],
            "website": url,
            "location": _location_from_text(f"{title} {snippet}", "", prefer_places=prefer),
            "industry": "",
            "snippet": snippet[:500],
            "title": title,
            "_rank": homepage_bonus - article_penalty,
        })
    companies.sort(key=lambda row: row.get("_rank", 0), reverse=True)
    for row in companies:
        row.pop("_rank", None)
    return companies


def _location_from_text(text: str, fallback: str = "", prefer_places: Optional[List[str]] = None) -> str:
    from app.agents.geo import format_location_display

    found = format_location_display(text or "", prefer_places=prefer_places)
    if found:
        return found[:80]
    # Never stamp the hunt country onto empty locations.
    return (fallback or "").strip()[:80]


class _CatalogBudget:
    """Wall-clock + product + listing-page caps for one extract-url scrape."""

    def __init__(
        self,
        *,
        max_products: int = CATALOG_MAX_PRODUCTS,
        max_pages: int = CATALOG_MAX_LISTING_PAGES,
        time_budget_sec: float = CATALOG_TIME_BUDGET_SEC,
    ) -> None:
        self.max_products = max_products
        self.max_pages = max_pages
        self.deadline = time.monotonic() + time_budget_sec
        self.product_count = 0
        self.page_count = 0
        self.truncated = False

    def expired(self) -> bool:
        if time.monotonic() >= self.deadline:
            self.truncated = True
            return True
        return False

    def products_full(self) -> bool:
        if self.product_count >= self.max_products:
            self.truncated = True
            return True
        return False

    def pages_full(self) -> bool:
        if self.page_count >= self.max_pages:
            self.truncated = True
            return True
        return False

    def stop(self) -> bool:
        return self.expired() or self.products_full() or self.pages_full()

    def room(self) -> int:
        return max(0, self.max_products - self.product_count)


class WebSearchTool:
    def __init__(self) -> None:
        # Set by scrape_shop_catalog so callers can tell "site unreachable" from "no products".
        self.last_catalog_error: str = ""
        self.catalog_truncated: bool = False

    def name(self) -> str:
        return "WebSearchTool"

    async def search_companies(self, query: str, target_location: str = "") -> List[Dict[str, Any]]:
        q = (query or "").strip()
        if target_location and target_location.lower() not in q.lower():
            q = f"{q} {target_location}".strip()
        if not q:
            return []
        raw = await asyncio.to_thread(self._search_sync, q)
        return results_to_companies(raw, target_location)

    async def search_maps(self, query: str, target_location: str = "") -> List[Dict[str, Any]]:
        """Google Maps / Places via Serper when SERPER_API_KEY is set."""
        q = (query or "").strip()
        if target_location and target_location.lower() not in q.lower():
            q = f"{q} {target_location}".strip()
        if not q or not settings.SERPER_API_KEY:
            return []
        try:
            places = await asyncio.to_thread(self._serper_maps, q)
        except Exception:
            return []
        leads: List[Dict[str, Any]] = []
        seen = set()
        for p in places:
            name = (p.get("title") or "").strip()
            website = (p.get("website") or p.get("link") or "").strip()
            address = (p.get("address") or "").strip()
            phone = (p.get("phoneNumber") or p.get("phone") or "").strip()
            key = _registrable_domain(website) if website else name.lower()
            if not name or key in seen:
                continue
            if website and _should_skip(website):
                continue
            seen.add(key)
            leads.append({
                "company_name": name[:120],
                "website": website,
                "location": address or "",
                "industry": "",
                "snippet": (p.get("type") or p.get("category") or "")[:500],
                "title": name,
                "phone": phone,
                "source": "maps",
            })
        return leads

    def _serper_maps(self, query: str) -> List[Dict[str, Any]]:
        with httpx.Client(timeout=20.0) as client:
            res = client.post(
                "https://google.serper.dev/maps",
                headers={"X-API-KEY": settings.SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": query, "num": 20},
            )
            res.raise_for_status()
            data = res.json()
            return list(data.get("places") or data.get("organic") or [])

    async def hunt_leads(
        self,
        queries: List[Any],
        target_location: str = "",
        exclude_domains: Optional[set] = None,
        limit: int = 140,
        use_maps: bool = False,
        max_queries: int = 36,
    ) -> List[Dict[str, Any]]:
        """Run a wave of web searches (Maps only when the plan says so)."""
        exclude_domains = exclude_domains or set()
        merged: List[Dict[str, Any]] = []
        seen: set = set(exclude_domains)

        specs: List[Dict[str, Any]] = []
        for q in queries[: max(1, max_queries)]:
            if isinstance(q, str):
                specs.append({"query": q, "use_maps": use_maps, "pool": "", "family": ""})
            elif isinstance(q, dict):
                specs.append(q)
            else:
                specs.append({
                    "query": getattr(q, "query", ""),
                    "use_maps": bool(getattr(q, "use_maps", use_maps)),
                    "pool": getattr(q, "pool", ""),
                    "family": getattr(q, "family", ""),
                })

        async def run_one(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
            q = (spec.get("query") or "").strip()
            if not q:
                return []
            maps_on = bool(spec.get("use_maps") or use_maps)
            web_task = self.search_companies(q, target_location)
            if maps_on:
                web, maps = await asyncio.gather(
                    web_task,
                    self.search_maps(q, target_location),
                    return_exceptions=True,
                )
            else:
                web = await web_task
                maps = []
            out: List[Dict[str, Any]] = []
            if isinstance(maps, list):
                for row in maps:
                    row.setdefault("source", "maps")
                    row["discovery_query"] = q
                    row["discovery_pool"] = spec.get("pool") or "maps_local"
                    out.append(row)
            if isinstance(web, list):
                for row in web:
                    row.setdefault("source", "web")
                    row["discovery_query"] = q
                    row["discovery_pool"] = spec.get("pool") or spec.get("family") or "web"
                    out.append(row)
            return out

        results = await asyncio.gather(*[run_one(s) for s in specs], return_exceptions=True)
        # Round-robin across query batches so early products (e.g. straps) don't
        # exhaust the global limit before wrist wraps / knee sleeves are merged.
        batches: List[List[Dict[str, Any]]] = []
        for batch in results:
            if isinstance(batch, list) and batch:
                batches.append(batch)
        if not batches:
            return merged

        # One lead per company, but remember every search job that found it.
        kept_by_domain: Dict[str, Dict[str, Any]] = {}

        def _remember_match(domain: str, row: Dict[str, Any]) -> None:
            kept = kept_by_domain.get(domain)
            if not kept:
                return
            dq = (row.get("discovery_query") or "").strip()
            matches = kept.setdefault("discovery_queries", [])
            if dq and dq not in matches:
                matches.append(dq)

        per_query_cap = max(16, min(20, (limit // max(len(batches), 1)) + 6))
        cursors = [0] * len(batches)
        progressed = True
        while progressed and len(merged) < limit:
            progressed = False
            for i, batch in enumerate(batches):
                if len(merged) >= limit:
                    break
                taken = 0
                while cursors[i] < len(batch) and taken < 5 and len(merged) < limit:
                    if cursors[i] >= per_query_cap:
                        break
                    row = batch[cursors[i]]
                    cursors[i] += 1
                    website = (row.get("website") or "").strip()
                    domain = _registrable_domain(website) if website else (row.get("company_name") or "").lower()
                    if not domain:
                        continue
                    if domain in seen:
                        _remember_match(domain, row)
                        continue
                    seen.add(domain)
                    row["discovery_queries"] = [row.get("discovery_query") or ""]
                    kept_by_domain[domain] = row
                    merged.append(row)
                    taken += 1
                    progressed = True
        # Second pass: fill remaining slots from any leftover hits
        for batch in batches:
            for row in batch:
                website = (row.get("website") or "").strip()
                domain = _registrable_domain(website) if website else (row.get("company_name") or "").lower()
                if not domain:
                    continue
                if domain in seen:
                    _remember_match(domain, row)
                    continue
                if len(merged) >= limit:
                    continue
                seen.add(domain)
                row["discovery_queries"] = [row.get("discovery_query") or ""]
                kept_by_domain[domain] = row
                merged.append(row)
        return merged

    def _search_sync(self, query: str, page: int = 1) -> List[Dict[str, str]]:
        # Prefer Serper when configured — avoid stacking 20s timeouts across providers.
        ordered = []
        if settings.SERPER_API_KEY:
            ordered.append(lambda q: self._serper(q, page=page))
        for fn in (self._brave, self._tavily, self._duckduckgo):
            if fn not in ordered:
                # Non-Serper providers: only page 1 (no reliable pagination)
                if page > 1:
                    continue
                ordered.append(fn)
        for fn in ordered:
            try:
                hits = fn(query)
                if hits:
                    return hits
            except Exception:
                continue
        return []

    async def search_organic_page(
        self,
        query: str,
        *,
        page: int = 1,
        num: int = 10,
    ) -> List[Dict[str, str]]:
        """Fetch one Google organic page. Serper supports page; others return page 1 only."""
        page = max(1, int(page or 1))
        num = max(1, min(int(num or 10), 100))
        return await asyncio.to_thread(self._search_sync_paged, query, page, num)

    def _search_sync_paged(self, query: str, page: int, num: int) -> List[Dict[str, str]]:
        if settings.SERPER_API_KEY:
            try:
                hits = self._serper(query, page=page, num=num)
                if hits:
                    return hits
            except Exception:
                pass
        if page > 1:
            return []
        return self._search_sync(query, page=1)

    def _serper(self, query: str, page: int = 1, num: int = 20) -> List[Dict[str, str]]:
        if not settings.SERPER_API_KEY:
            return []
        with httpx.Client(timeout=15.0) as client:
            res = client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": settings.SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": query, "num": max(1, min(num, 100)), "page": max(1, page)},
            )
            res.raise_for_status()
            organic = res.json().get("organic") or []
            return [
                {"title": r.get("title", ""), "href": r.get("link", ""), "body": r.get("snippet", "")}
                for r in organic
            ]

    def _brave(self, query: str) -> List[Dict[str, str]]:
        if not settings.BRAVE_SEARCH_API_KEY:
            return []
        with httpx.Client(timeout=20.0) as client:
            res = client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"X-Subscription-Token": settings.BRAVE_SEARCH_API_KEY, "Accept": "application/json"},
                params={"q": query, "count": 20},
            )
            res.raise_for_status()
            web = ((res.json().get("web") or {}).get("results")) or []
            return [
                {"title": r.get("title", ""), "href": r.get("url", ""), "body": r.get("description", "")}
                for r in web
            ]

    def _tavily(self, query: str) -> List[Dict[str, str]]:
        if not settings.TAVILY_API_KEY:
            return []
        with httpx.Client(timeout=20.0) as client:
            res = client.post(
                "https://api.tavily.com/search",
                json={"api_key": settings.TAVILY_API_KEY, "query": query, "max_results": 15},
            )
            res.raise_for_status()
            return [
                {"title": r.get("title", ""), "href": r.get("url", ""), "body": r.get("content", "")}
                for r in res.json().get("results") or []
            ]

    def _duckduckgo(self, query: str) -> List[Dict[str, str]]:
        try:
            from ddgs import DDGS
            with DDGS() as ddgs:
                rows = list(ddgs.text(query, max_results=15))
                return [
                    {"title": r.get("title", ""), "href": r.get("href", ""), "body": r.get("body", "")}
                    for r in rows
                ]
        except Exception:
            pass
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                rows = list(ddgs.text(query, max_results=15))
                return [
                    {"title": r.get("title", ""), "href": r.get("href", ""), "body": r.get("body", "")}
                    for r in rows
                ]
        except Exception:
            pass
        return self._duckduckgo_html(query)

    def _duckduckgo_html(self, query: str) -> List[Dict[str, str]]:
        with httpx.Client(timeout=20.0, follow_redirects=True, headers=HEADERS) as client:
            res = client.post("https://html.duckduckgo.com/html/", data={"q": query})
            res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        hits: List[Dict[str, str]] = []
        for result in soup.select(".result"):
            link = result.select_one("a.result__a")
            snippet = result.select_one(".result__snippet")
            if not link or not link.get("href"):
                continue
            hits.append({
                "title": link.get_text(" ", strip=True),
                "href": link.get("href"),
                "body": snippet.get_text(" ", strip=True) if snippet else "",
            })
        return hits

    async def scrape_homepage(
        self,
        url: str,
        limit: int = 8000,
        client: Optional[httpx.AsyncClient] = None,
        keep_html: bool = True,
    ) -> Dict[str, Any]:
        """Cheap single-page fetch for qualification. Does not crawl the shop catalog."""
        if not url or _should_skip(url):
            return {"text": "", "title": "", "url": url or "", "ok": False, "location": ""}
        try:
            async def _get(c: httpx.AsyncClient) -> Dict[str, Any]:
                res = await c.get(url, headers=HEADERS, timeout=5.0)
                if res.status_code != 200 or not res.text:
                    return {"text": "", "title": "", "url": str(res.url), "ok": False, "location": ""}
                soup = BeautifulSoup(res.text, "html.parser")
                title = ""
                if soup.title and soup.title.get_text(strip=True):
                    title = soup.title.get_text(strip=True)[:160]
                meta = soup.find("meta", attrs={"name": "description"})
                desc = (meta.get("content") or "") if meta else ""
                location = _location_from_html(res.text)
                emails: List[str] = []
                phones: List[str] = []
                contact_urls: List[str] = []
                try:
                    from app.tools.contact_finder import _extract_from_html, _domain as _cf_domain
                    contact_bits = _extract_from_html(res.text, str(res.url), _cf_domain(str(res.url)))
                    emails = list(contact_bits.get("emails") or [])
                    phones = list(contact_bits.get("phones") or [])
                    contact_urls = list(contact_bits.get("contact_urls") or [])
                except Exception:
                    pass
                text = _html_to_text(res.text, limit=limit)
                if desc:
                    text = f"{desc}\n{text}"[:limit]
                if not location:
                    location = _location_from_text(f"{title} {desc} {text}")
                out = {
                    "text": text,
                    "title": title,
                    "url": str(res.url),
                    "ok": True,
                    "status": res.status_code,
                    "location": location,
                    "emails": emails,
                    "phones": phones,
                    "contact_urls": contact_urls,
                }
                if keep_html:
                    out["html"] = res.text
                return out

            if client is not None:
                return await _get(client)
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=True, headers=HEADERS) as own:
                return await _get(own)
        except Exception:
            return {"text": "", "title": "", "url": url, "ok": False, "location": ""}

    async def scrape_relevance_pages(
        self,
        url: str,
        *,
        limit: int = 8000,
        client: Optional[httpx.AsyncClient] = None,
    ) -> Dict[str, Any]:
        """
        Homepage plus one catalog-ish page when the homepage is thin.
        Used so AI can see /products or /catalog before rejecting a distributor.
        """
        from urllib.parse import urljoin, urlparse

        home = await self.scrape_homepage(url, limit=min(limit, 5000), client=client, keep_html=True)
        if not home.get("ok"):
            home.pop("html", None)
            return home

        text = (home.get("text") or "").strip()
        html = home.pop("html", "") or ""
        base = home.get("url") or url
        pages = [base]
        contact_urls = list(home.get("contact_urls") or [])

        # Prefer linked catalog/shop paths from the homepage, else common guesses.
        candidates: List[str] = []
        try:
            soup = BeautifulSoup(html, "html.parser") if html else None
            if soup:
                for a in soup.find_all("a", href=True):
                    href = (a.get("href") or "").strip()
                    low = href.lower()
                    if any(p in low for p in (
                        "/products", "/product", "/catalog", "/shop", "/collections",
                        "/equipment", "/wholesale", "/store",
                    )):
                        full = urljoin(base, href)
                        if urlparse(full).netloc == urlparse(base).netloc:
                            candidates.append(full.split("#")[0])
                    if len(candidates) >= 6:
                        break
        except Exception:
            pass
        root = f"{urlparse(base).scheme}://{urlparse(base).netloc}"
        for path in (
            "/products", "/catalog", "/shop", "/collections", "/equipment", "/wholesale",
        ):
            candidates.append(f"{root}{path}")

        seen = {base.rstrip("/").lower()}
        extra_url = ""
        for cand in candidates:
            key = cand.rstrip("/").lower()
            if key in seen or _should_skip(cand):
                continue
            seen.add(key)
            extra_url = cand
            break

        # Only fetch catalog when homepage is short or generic
        need_catalog = len(text) < 1200 or not any(
            w in text.lower()
            for w in (
                "distributor", "wholesale", "importer", "fitness", "gym", "sport",
                "strength", "martial", "lifting", "strap", "belt", "wrap", "sleeve", "hook",
            )
        )
        if extra_url and need_catalog:
            try:
                async def _get_extra(c: httpx.AsyncClient) -> Optional[str]:
                    res = await c.get(extra_url, headers=HEADERS, timeout=5.0)
                    if res.status_code != 200 or not res.text:
                        return None
                    return _html_to_text(res.text, limit=3500)

                if client is not None:
                    extra_text = await _get_extra(client)
                else:
                    async with httpx.AsyncClient(
                        timeout=5.0, follow_redirects=True, headers=HEADERS
                    ) as own:
                        extra_text = await _get_extra(own)
                if extra_text:
                    text = f"{text}\n\n{extra_text}"[:limit]
                    pages.append(extra_url)
            except Exception:
                pass

        home["text"] = text
        home["pages"] = pages
        home["contact_urls"] = contact_urls
        home.pop("html", None)
        return home

    async def scrape_for_qualify(self, url: str, limit: int = 14000) -> Dict[str, Any]:
        """Homepage plus up to 2 signal pages (about / news / careers) for Intent evidence."""
        home = await self.scrape_homepage(url, limit=min(limit, 9000))
        if not home.get("ok"):
            home.pop("html", None)
            return home

        base = home.get("url") or url
        html = home.pop("html", "") or ""
        secondary = _signal_page_urls(html, base)[:2]
        if not secondary:
            secondary = _guess_signal_paths(base)[:2]

        chunks = [home.get("text") or ""]
        pages = [base]
        if secondary:
            try:
                async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=HEADERS) as client:
                    for extra in secondary:
                        try:
                            res = await client.get(extra)
                            if res.status_code != 200 or not res.text:
                                continue
                            chunks.append(_html_to_text(res.text, limit=4500))
                            pages.append(str(res.url))
                        except Exception:
                            continue
            except Exception:
                pass

        combined = "\n\n".join(c for c in chunks if c)[:limit]
        return {
            "text": combined,
            "title": home.get("title") or "",
            "url": base,
            "ok": True,
            "pages": pages,
            "status": home.get("status"),
        }

    async def scrape_shop_catalog(self, url: str) -> tuple[List[tuple[str, str]], List[Dict[str, Any]]]:
        """
        Catalog extract cascade:
        Shopify products.json → Woo WP REST → sitemap + paginated listing HTML.
        """
        self.last_catalog_error = ""
        self.catalog_truncated = False
        if not url or _should_skip(url):
            return [], []
        pages: List[tuple[str, str]] = []
        products: List[Dict[str, Any]] = []
        seen_urls: set[str] = set()
        budget = _CatalogBudget()

        def _merge(items: List[Dict[str, Any]]) -> int:
            """Dedupe by product URL only — repeated titles are normal across variants."""
            added = 0
            for item in items:
                if budget.stop():
                    break
                url_key = (item.get("productUrl") or "").strip().lower().rstrip("/")
                if not url_key:
                    # Fall back to name only when no URL exists
                    url_key = f"name:{(item.get('name') or '').strip().lower()}"
                if not url_key or url_key in seen_urls or url_key == "name:":
                    continue
                seen_urls.add(url_key)
                products.append(item)
                budget.product_count += 1
                added += 1
            return added

        try:
            async with httpx.AsyncClient(
                timeout=20.0, follow_redirects=True, headers=HEADERS, limits=CATALOG_LIMITS
            ) as client:
                fetcher = _CatalogFetcher(client)

                # 1) Shopify JSON API — full catalogs without HTML crawl
                shopify_products = await _fetch_shopify_products(fetcher, url, budget)
                if shopify_products:
                    _merge(shopify_products)
                    pages.append(
                        (urljoin(url, "/products.json"), f"Shopify products.json: {len(shopify_products)}")
                    )
                    # Healthy Shopify API already paginated to exhaustion — skip HTML.
                    if len(products) >= CATALOG_API_MIN_TRUST or budget.stop():
                        self.catalog_truncated = budget.truncated
                        log.info(
                            "scrape_shop_catalog(%s): Shopify returned %d products truncated=%s",
                            url, len(products), budget.truncated,
                        )
                        return pages, products
                    log.info(
                        "scrape_shop_catalog(%s): Shopify thin (%d) — continuing HTML cascade",
                        url, len(products),
                    )

                # 2) WooCommerce Store API + WordPress REST
                store_products = await _fetch_wc_store_products(fetcher, url, budget)
                if store_products:
                    _merge(store_products)
                    pages.append(
                        (urljoin(url, "/wp-json/wc/store/v1/products"), f"Woo Store API: {len(store_products)}")
                    )
                    if len(products) >= CATALOG_API_MIN_TRUST or budget.stop():
                        self.catalog_truncated = budget.truncated
                        log.info(
                            "scrape_shop_catalog(%s): Woo Store API returned %d products truncated=%s",
                            url, len(products), budget.truncated,
                        )
                        return pages, products

                rest_products, _rest_err = await _fetch_wp_rest_products(fetcher, url, budget)
                if rest_products:
                    _merge(rest_products)
                    pages.append(
                        (urljoin(url, "/wp-json/wp/v2/product"), f"WP REST products: {len(rest_products)}")
                    )
                    if len(products) >= CATALOG_API_MIN_TRUST or budget.stop():
                        self.catalog_truncated = budget.truncated
                        log.info(
                            "scrape_shop_catalog(%s): WP REST returned %d products truncated=%s",
                            url, len(products), budget.truncated,
                        )
                        return pages, products
                    log.info(
                        "scrape_shop_catalog(%s): WP REST thin (%d) — continuing HTML cascade",
                        url, len(products),
                    )

                # 3) Homepage + robots/sitemap product URLs + paginated listing pages
                try:
                    first = await fetcher.get(url)
                except Exception as exc:
                    log.warning("scrape_shop_catalog(%s): homepage fetch failed: %r", url, exc)
                    self.last_catalog_error = _connect_error_kind(exc)
                    return pages, products
                if first.status_code != 200 or not first.text:
                    log.warning(
                        "scrape_shop_catalog(%s): homepage status=%s len=%d",
                        url, first.status_code, len(first.text or ""),
                    )
                    self.last_catalog_error = "unreachable" if first.status_code in (0, 403, 502, 503) else ""
                    return pages, products

                html = first.text
                start_url = _CatalogFetcher.final_url(first, url)
                pages.append((start_url, _html_to_text(html)))
                budget.page_count += 1
                _merge(_shop_products(html, start_url, set()))
                _merge(_jsonld_products(html, start_url))

                # Sitemap product URLs (name-from-slug; no PDP fetch)
                if not budget.stop():
                    sitemap_urls = await _fetch_sitemap_product_urls(fetcher, start_url, budget)
                    if sitemap_urls:
                        pages.append((urljoin(start_url, "/sitemap.xml"), f"Sitemap product URLs: {len(sitemap_urls)}"))
                        _merge([_product_from_url(u, start_url) for u in sitemap_urls])

                # Listing / collection / category pages with pagination
                if not budget.stop():
                    listing_seeds = _augment_listing_seeds(_listing_page_urls(html, start_url), start_url)
                    home_key = start_url.split("#")[0].rstrip("/").lower()
                    if not any(s.split("#")[0].rstrip("/").lower() == home_key for s in listing_seeds):
                        if _pagination_urls(html, start_url) or len(_shop_products(html, start_url, set())) >= 3:
                            listing_seeds = [start_url, *listing_seeds]
                    await _crawl_listing_pages(
                        fetcher, listing_seeds, pages, _merge, budget, seen_urls
                    )

                self.catalog_truncated = budget.truncated
                log.info(
                    "scrape_shop_catalog(%s): HTML cascade scanned %d pages, %d products truncated=%s",
                    url, len(pages), len(products), budget.truncated,
                )
        except Exception as exc:
            log.warning("scrape_shop_catalog(%s): aborted: %r", url, exc)
            self.last_catalog_error = _connect_error_kind(exc)
            self.catalog_truncated = budget.truncated
            return pages, products
        return pages, products


class _CatalogFetcher:
    """
    GET wrapper that relays through the Cloudflare Worker when a host blocks our IP.

    The first transport failure flips the whole scrape to proxy mode, so we pay the
    connect timeout once rather than on every page.
    """

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self.proxy_url = (settings.SCRAPE_PROXY_URL or "").strip()
        self.proxy_token = (settings.SCRAPE_PROXY_TOKEN or "").strip()
        self.using_proxy = False

    async def get(self, url: str, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
        if self.using_proxy:
            return await self._via_proxy(url, params)
        try:
            return await self.client.get(url, params=params)
        except httpx.TransportError as exc:
            if not self.proxy_url:
                raise
            log.info("Direct fetch of %s failed (%r); relaying through proxy", url, exc)
            self.using_proxy = True
            return await self._via_proxy(url, params)

    async def _via_proxy(self, url: str, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
        target = str(httpx.URL(url, params=params)) if params else url
        headers = {"X-Proxy-Token": self.proxy_token} if self.proxy_token else {}
        return await self.client.get(self.proxy_url, params={"url": target}, headers=headers)

    @staticmethod
    def final_url(response: httpx.Response, fallback: str) -> str:
        """Real upstream URL — response.url points at the Worker when proxied."""
        return response.headers.get("X-Proxy-Final-Url") or str(response.url) or fallback


def _connect_error_kind(exc: Exception) -> str:
    """Classify a transport failure so the UI can say 'unreachable' instead of 'no products'."""
    if isinstance(exc, (httpx.ConnectTimeout, httpx.ConnectError)):
        return "unreachable"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.TransportError):
        return "unreachable"
    return ""


async def _fetch_shopify_products(
    fetcher: "_CatalogFetcher",
    site_url: str,
    budget: _CatalogBudget,
) -> List[Dict[str, Any]]:
    """Paginate /products.json when the shop exposes Shopify's public catalog API."""
    parsed = urlparse(site_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    endpoint = f"{root}/products.json"
    products: List[Dict[str, Any]] = []
    page = 1
    try:
        while not budget.stop():
            res = await fetcher.get(endpoint, params={"limit": 250, "page": page})
            if res.status_code != 200:
                if page == 1:
                    log.info("Shopify %s: status=%s", endpoint, res.status_code)
                break
            try:
                payload = res.json()
            except Exception as exc:
                log.info("Shopify %s: non-JSON (%r)", endpoint, exc)
                break
            rows = payload.get("products") if isinstance(payload, dict) else None
            if not isinstance(rows, list) or not rows:
                break
            for raw in rows:
                if budget.products_full():
                    break
                mapped = _shopify_row_to_product(raw, root)
                if mapped:
                    products.append(mapped)
            if len(rows) < 250:
                break
            page += 1
            await asyncio.sleep(CATALOG_BATCH_PAUSE)
    except Exception as exc:
        log.info("Shopify %s: request failed: %r", endpoint, exc)
        return []
    if products:
        log.info("Shopify %s: fetched %d products across %d page(s)", endpoint, len(products), page)
    return products


def _shopify_row_to_product(raw: dict, root: str) -> Dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    handle = (raw.get("handle") or "").strip()
    name = (raw.get("title") or "").strip()
    if not name:
        return None
    body = raw.get("body_html") or ""
    description = BeautifulSoup(str(body), "html.parser").get_text(" ", strip=True)[:180]
    product_type = (raw.get("product_type") or "").strip()
    tags = raw.get("tags") or ""
    if isinstance(tags, list):
        tags = ", ".join(str(t) for t in tags)
    category = product_type or (str(tags).split(",")[0].strip() if tags else "") or "Uncategorized"
    link = f"{root}/products/{handle}" if handle else root
    image_url = ""
    images = raw.get("images") or []
    if isinstance(images, list) and images:
        first_img = images[0] if isinstance(images[0], dict) else {}
        image_url = (first_img.get("src") or "").strip()
    if not image_url:
        image = raw.get("image") or {}
        if isinstance(image, dict):
            image_url = (image.get("src") or "").strip()
    price = ""
    variants = raw.get("variants") or []
    if isinstance(variants, list) and variants and isinstance(variants[0], dict):
        price = str(variants[0].get("price") or "").strip()
    return {
        "name": name[:90],
        "category": category[:80] or "Uncategorized",
        "description": description or name,
        "productUrl": link,
        "imageUrl": image_url,
        "price": price[:40],
        "source_url": root,
    }


async def _fetch_wp_rest_products(
    fetcher: "_CatalogFetcher",
    site_url: str,
    budget: _CatalogBudget | None = None,
) -> tuple[List[Dict[str, Any]], str]:
    """
    Fetch all products via WordPress REST API when exposed (common on Woo shops).

    Returns (products, transport_error_kind). Callers should fall through to HTML
    when products are empty — a failed REST probe must not abort the cascade.
    """
    budget = budget or _CatalogBudget()
    parsed = urlparse(site_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    endpoint = f"{root}/wp-json/wp/v2/product"
    products: List[Dict[str, Any]] = []
    try:
        first = await fetcher.get(endpoint, params={"per_page": 100, "page": 1})
        if first.status_code != 200:
            log.info("WP REST %s: status=%s", endpoint, first.status_code)
            return [], ""
        try:
            rows = first.json()
        except Exception as exc:
            log.info("WP REST %s: non-JSON body (%r)", endpoint, exc)
            return [], ""
        if not isinstance(rows, list) or not rows:
            log.info("WP REST %s: empty payload", endpoint)
            return [], ""
        products.extend(_wp_rest_rows_to_products(rows, site_url))
        total_pages = int(first.headers.get("X-WP-TotalPages") or 1)
        total_pages = max(1, min(total_pages, CATALOG_WP_REST_MAX_PAGES))
        remaining = list(range(2, total_pages + 1))
        for i in range(0, len(remaining), CATALOG_CONCURRENCY):
            if budget.stop():
                break
            if i:
                await asyncio.sleep(CATALOG_BATCH_PAUSE)
            reqs = [
                fetcher.get(endpoint, params={"per_page": 100, "page": page})
                for page in remaining[i : i + CATALOG_CONCURRENCY]
            ]
            results = await asyncio.gather(*reqs, return_exceptions=True)
            for res in results:
                if isinstance(res, Exception) or getattr(res, "status_code", 0) != 200:
                    continue
                try:
                    more = res.json()
                except Exception:
                    continue
                if isinstance(more, list):
                    products.extend(_wp_rest_rows_to_products(more, site_url))
                if len(products) >= budget.max_products:
                    budget.truncated = True
                    break
    except Exception as exc:
        log.info("WP REST %s: request failed: %r", endpoint, exc)
        return [], _connect_error_kind(exc)
    if len(products) > budget.max_products:
        budget.truncated = True
        products = products[: budget.max_products]
    return products, ""


def _wp_rest_rows_to_products(rows: list, site_url: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        title_raw = raw.get("title") or {}
        if isinstance(title_raw, dict):
            name = title_raw.get("rendered") or ""
        else:
            name = str(title_raw or "")
        name = BeautifulSoup(name, "html.parser").get_text(" ", strip=True)
        name = html_lib.unescape(name).strip()
        if not name:
            continue
        link = (raw.get("link") or "").strip() or site_url
        slug = (raw.get("slug") or "").strip()
        excerpt_raw = raw.get("excerpt") or {}
        if isinstance(excerpt_raw, dict):
            excerpt = excerpt_raw.get("rendered") or ""
        else:
            excerpt = str(excerpt_raw or "")
        excerpt = BeautifulSoup(excerpt, "html.parser").get_text(" ", strip=True)
        content_raw = raw.get("content") or {}
        if isinstance(content_raw, dict):
            content = content_raw.get("rendered") or ""
        else:
            content = str(content_raw or "")
        content_text = BeautifulSoup(content, "html.parser").get_text(" ", strip=True)
        blob = f"{excerpt} {content_text} {slug}"
        sku_match = re.search(r"(AWE[-\s]?\d+)", blob, re.I)
        sku = sku_match.group(1).upper().replace(" ", "-") if sku_match else ""
        # Titles often repeat across variants — keep names unique for the UI merge-by-name
        if sku:
            display = f"{name} ({sku})"
        elif slug:
            display = f"{name} ({slug})"
        else:
            display = f"{name} #{raw.get('id')}"
        out.append({
            "name": display[:90],
            "category": _category_from_url(link),
            "description": (excerpt or content_text or name)[:180],
            "productUrl": link,
            "imageUrl": "",
            "price": "",
            "source_url": site_url,
        })
    return out


async def _fetch_wc_store_products(
    fetcher: "_CatalogFetcher",
    site_url: str,
    budget: _CatalogBudget,
) -> List[Dict[str, Any]]:
    """Paginate WooCommerce Store API when publicly exposed (no auth required on many shops)."""
    parsed = urlparse(site_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    endpoint = f"{root}/wp-json/wc/store/v1/products"
    products: List[Dict[str, Any]] = []
    page = 1
    try:
        while not budget.stop():
            res = await fetcher.get(endpoint, params={"per_page": 100, "page": page})
            if res.status_code != 200:
                if page == 1:
                    log.info("Woo Store API %s: status=%s", endpoint, res.status_code)
                break
            try:
                rows = res.json()
            except Exception:
                break
            if not isinstance(rows, list) or not rows:
                break
            for raw in rows:
                if not isinstance(raw, dict):
                    continue
                name = BeautifulSoup(str(raw.get("name") or ""), "html.parser").get_text(" ", strip=True)
                if not name:
                    continue
                permalink = (raw.get("permalink") or "").strip() or site_url
                prices = raw.get("prices") if isinstance(raw.get("prices"), dict) else {}
                price = ""
                if prices:
                    amount = prices.get("price") or prices.get("regular_price") or ""
                    currency = prices.get("currency_code") or prices.get("currency_symbol") or ""
                    if amount:
                        try:
                            price = f"{currency} {float(amount) / 100:.2f}".strip()
                        except (TypeError, ValueError):
                            price = f"{currency} {amount}".strip()
                images = raw.get("images") if isinstance(raw.get("images"), list) else []
                image_url = ""
                if images and isinstance(images[0], dict):
                    image_url = (images[0].get("src") or "").strip()
                slug = (raw.get("slug") or "").strip()
                display = f"{name} ({slug})" if slug and slug.lower() not in name.lower() else name
                products.append({
                    "name": display[:90],
                    "category": _category_from_url(permalink),
                    "description": name[:180],
                    "productUrl": permalink,
                    "imageUrl": image_url,
                    "price": price[:40],
                    "source_url": site_url,
                })
                if len(products) >= budget.max_products:
                    budget.truncated = True
                    break
            if len(rows) < 100:
                break
            page += 1
            await asyncio.sleep(CATALOG_BATCH_PAUSE)
    except Exception as exc:
        log.info("Woo Store API %s: failed: %r", endpoint, exc)
        return []
    return products[: budget.max_products]


async def _robots_sitemap_urls(fetcher: "_CatalogFetcher", site_url: str) -> List[str]:
    """Read Sitemap: directives from robots.txt — the most reliable discovery entry point."""
    parsed = urlparse(site_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    robots_url = f"{root}/robots.txt"
    out: List[str] = []
    try:
        res = await fetcher.get(robots_url)
    except Exception:
        return []
    if res.status_code != 200 or not (res.text or "").strip():
        return []
    for line in (res.text or "").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        if raw.lower().startswith("sitemap:"):
            loc = raw.split(":", 1)[1].strip()
            if loc:
                out.append(loc)
    return out


async def _fetch_sitemap_product_urls(
    fetcher: "_CatalogFetcher",
    site_url: str,
    budget: _CatalogBudget,
) -> List[str]:
    """Collect same-host product URLs from robots.txt sitemaps + common sitemap paths."""
    parsed = urlparse(site_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    seeds = await _robots_sitemap_urls(fetcher, site_url)
    for path in (
        "/sitemap.xml",
        "/sitemap_index.xml",
        "/wp-sitemap.xml",
        "/sitemap-index.xml",
        "/product-sitemap.xml",
        "/product_sitemap.xml",
        "/sitemap_products_1.xml",
        "/sitemap-products.xml",
        "/sitemap/sitemap.xml",
    ):
        candidate = f"{root}{path}"
        if candidate not in seeds:
            seeds.append(candidate)

    found: List[str] = []
    seen: set[str] = set()
    nested: List[str] = []
    visited_sitemaps: set[str] = set()

    async def _load(sm_url: str) -> tuple[List[str], List[str], bool]:
        """Returns locs, children, is_product_sitemap."""
        try:
            res = await fetcher.get(sm_url)
        except Exception:
            return [], [], False
        if res.status_code != 200:
            return [], [], False
        body = res.content or b""
        text = ""
        lower_url = sm_url.lower()
        ctype = (res.headers.get("content-type") or "").lower()
        if lower_url.endswith(".gz") or "gzip" in ctype or body[:2] == b"\x1f\x8b":
            try:
                text = gzip.decompress(body).decode("utf-8", errors="ignore")
            except Exception:
                try:
                    text = (res.text or "")
                except Exception:
                    return [], [], False
        else:
            text = res.text or ""
        if not text.strip():
            return [], [], False
        locs, children = _parse_sitemap_xml(text, root)
        is_product_sm = bool(
            re.search(r"product", sm_url, re.I)
            or re.search(r"product", text[:2000], re.I)
        )
        return locs, children, is_product_sm

    for seed in seeds:
        if budget.stop() or len(found) >= budget.room():
            break
        key = seed.split("#")[0].rstrip("/").lower()
        if key in visited_sitemaps:
            continue
        visited_sitemaps.add(key)
        locs, children, is_product_sm = await _load(seed)
        for loc in locs:
            if loc in seen:
                continue
            if is_product_sm:
                if _looks_like_non_product_url(loc):
                    continue
            elif not _looks_like_product_url(loc):
                continue
            seen.add(loc)
            found.append(loc)
        for child in children:
            if child in nested:
                continue
            if re.search(r"product", child, re.I):
                nested.insert(0, child)
            else:
                nested.append(child)

    for child in nested[:CATALOG_SITEMAP_NEST_LIMIT]:
        if budget.stop() or len(found) >= budget.room():
            break
        key = child.split("#")[0].rstrip("/").lower()
        if key in visited_sitemaps:
            continue
        visited_sitemaps.add(key)
        locs, grandkids, is_product_sm = await _load(child)
        for loc in locs:
            if loc in seen:
                continue
            if is_product_sm or re.search(r"product", child, re.I):
                if _looks_like_non_product_url(loc):
                    continue
            elif not _looks_like_product_url(loc):
                continue
            seen.add(loc)
            found.append(loc)
            if len(found) >= budget.room():
                break
        for gk in grandkids:
            if gk not in nested and len(nested) < CATALOG_SITEMAP_NEST_LIMIT * 2:
                nested.append(gk)
        await asyncio.sleep(CATALOG_BATCH_PAUSE)

    return found[: budget.room() or CATALOG_MAX_PRODUCTS]


def _parse_sitemap_xml(xml_text: str, root: str) -> tuple[List[str], List[str]]:
    locs: List[str] = []
    children: List[str] = []
    try:
        cleaned = re.sub(r'\sxmlns="[^"]+"', "", xml_text or "", count=1)
        root_el = ET.fromstring(cleaned)
    except ET.ParseError:
        # Fallback: regex locs when XML is messy
        for m in re.finditer(r"<loc>\s*([^<\s]+)\s*</loc>", xml_text or "", re.I):
            loc = m.group(1).strip()
            if loc.lower().endswith((".xml", ".xml.gz")):
                children.append(loc)
            elif _registrable_domain(loc) == _registrable_domain(root):
                locs.append(loc.split("#")[0].rstrip("/") or loc)
        return locs, children
    tag = (root_el.tag or "").lower()
    if tag.endswith("sitemapindex"):
        for sm in root_el.findall("sitemap"):
            loc = (sm.findtext("loc") or "").strip()
            if loc:
                children.append(loc)
        return [], children
    for url_el in root_el.findall("url"):
        loc = (url_el.findtext("loc") or "").strip()
        if loc and _registrable_domain(loc) == _registrable_domain(root):
            locs.append(loc.split("#")[0].rstrip("/") or loc)
    return locs, children


def _looks_like_non_product_url(url: str) -> bool:
    path = (urlparse(url).path or "").lower()
    if not path or path in {"/", ""}:
        return True
    skip = (
        "/cart", "/checkout", "/account", "/blogs/", "/blog/", "/pages/",
        "/collections/", "/product-category/", "/cart/", "/wp-admin",
        "/tag/", "/author/", "/search", "/wishlist", "/compare",
    )
    if any(s in path for s in skip):
        # Shopify PDP under collections is still a product
        if "/products/" in path:
            return False
        return True
    if path.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".css", ".js")):
        return True
    return False


def _looks_like_product_url(url: str) -> bool:
    path = (urlparse(url).path or "").lower()
    if _looks_like_non_product_url(url) and "/products/" not in path:
        return False
    return bool(
        re.search(r"/products?/[^/]+", path)
        or "/product/" in path
        or re.search(r"/shop/[^/]+/[^/]+", path)
        or re.search(r"/shop/[^/]+/?$", path)
        or re.search(r"/item/[^/]+", path)
        or re.search(r"/p/[^/]+", path)
        or re.search(r"/goods/[^/]+", path)
        or re.search(r"/catalog/product", path)
        or re.search(r"/dp/[A-Z0-9]+", path, re.I)
        or re.search(r"/p-[^/]+", path)
        or re.search(r"/\d{4,}/?$", path)  # numeric product ids
    )


def _jsonld_products(html: str, site_url: str) -> List[Dict[str, Any]]:
    """Extract Product / ItemList entries from JSON-LD blocks."""
    import json

    soup = BeautifulSoup(html or "", "html.parser")
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def _add(name: str, link: str, image: str = "", price: str = "") -> None:
        name = (name or "").strip()
        link = (link or "").strip()
        if not name:
            return
        key = (link or name).lower()
        if key in seen:
            return
        seen.add(key)
        out.append({
            "name": name[:90],
            "category": _category_from_url(link or site_url),
            "description": name[:180],
            "productUrl": link or site_url,
            "imageUrl": image or "",
            "price": (price or "")[:40],
            "source_url": site_url,
        })

    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            node = stack.pop(0)
            if isinstance(node, list):
                stack.extend(node)
                continue
            if not isinstance(node, dict):
                continue
            typ = node.get("@type") or ""
            types = typ if isinstance(typ, list) else [typ]
            types_l = [str(t).lower() for t in types]
            if "product" in types_l:
                offers = node.get("offers")
                price = ""
                if isinstance(offers, dict):
                    price = str(offers.get("price") or "")
                elif isinstance(offers, list) and offers and isinstance(offers[0], dict):
                    price = str(offers[0].get("price") or "")
                image = node.get("image")
                if isinstance(image, list):
                    image = image[0] if image else ""
                if isinstance(image, dict):
                    image = image.get("url") or ""
                _add(
                    str(node.get("name") or ""),
                    str(node.get("url") or node.get("@id") or ""),
                    str(image or ""),
                    price,
                )
            if "itemlist" in types_l:
                for el in node.get("itemListElement") or []:
                    if isinstance(el, dict):
                        item = el.get("item") if isinstance(el.get("item"), dict) else el
                        if isinstance(item, dict):
                            stack.append(item)
            for key in ("@graph", "mainEntity", "hasOfferCatalog"):
                child = node.get(key)
                if child:
                    stack.append(child)
    return out


def _product_from_url(product_url: str, site_url: str) -> Dict[str, Any]:
    slug = (urlparse(product_url).path or "").rstrip("/").split("/")[-1]
    name = slug.replace("-", " ").replace("_", " ").strip().title() or "Product"
    return {
        "name": name[:90],
        "category": _category_from_url(product_url),
        "description": name[:180],
        "productUrl": product_url,
        "imageUrl": "",
        "price": "",
        "source_url": site_url,
    }


def _listing_page_urls(html: str, base_url: str) -> List[str]:
    """Collection / category / shop listing seeds (not individual PDPs)."""
    links = _catalog_links(html, base_url)
    out: List[str] = []
    seen = set()
    for link in links:
        path = (urlparse(link).path or "").lower()
        if _looks_like_product_url(link) and "/product-category/" not in path and "/collections/" not in path:
            continue
        if link in seen:
            continue
        seen.add(link)
        out.append(link)
    # Prefer Woo categories + Shopify collections
    preferred = [u for u in out if "/product-category/" in u or "/collections/" in u or "/shop" in u]
    rest = [u for u in out if u not in preferred]
    return (preferred + rest)[:CATALOG_LISTING_SEED_CAP]


def _augment_listing_seeds(seeds: List[str], site_url: str) -> List[str]:
    """Append common shop entry points when homepage nav is thin or theme-specific."""
    parsed = urlparse(site_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    probes = (
        f"{root}/shop",
        f"{root}/shop/",
        f"{root}/store",
        f"{root}/store/",
        f"{root}/products",
        f"{root}/products/",
        f"{root}/collections",
        f"{root}/collections/all",
        f"{root}/catalog",
        f"{root}/catalog/",
        f"{root}/all-products",
        f"{root}/product-category",
        f"{root}/categories",
        f"{root}/category",
        f"{root}/shop/page/1/",
        f"{root}/shop/?orderby=menu_order",
    )
    out = list(seeds)
    seen = {u.split("#")[0].rstrip("/").lower() for u in out}
    for probe in probes:
        key = probe.split("#")[0].rstrip("/").lower()
        if key not in seen:
            seen.add(key)
            out.append(probe)
    return out[:CATALOG_LISTING_SEED_CAP]


async def _crawl_listing_pages(
    fetcher: "_CatalogFetcher",
    seeds: List[str],
    pages: List[tuple[str, str]],
    merge_fn,
    budget: _CatalogBudget,
    _seen_urls: set[str],
) -> None:
    """Fetch listing pages and follow pagination until budget is exhausted."""
    queue: List[str] = list(seeds)
    visited: set[str] = set()
    empty_streak_by_branch: dict[str, int] = {}

    def _branch_key(u: str) -> str:
        parsed = urlparse(u)
        path = re.sub(r"/page/\d+/?$", "/", (parsed.path or "/"))
        qs = parse_qs(parsed.query)
        qs.pop("page", None)
        qs.pop("paged", None)
        return f"{parsed.netloc}{path}?{urlencode({k: qs[k] for k in sorted(qs)}, doseq=True)}"

    while queue and not budget.stop():
        batch = []
        while queue and len(batch) < CATALOG_CONCURRENCY:
            url = queue.pop(0)
            key = url.split("#")[0].rstrip("/").lower()
            if key in visited:
                continue
            visited.add(key)
            batch.append(url)
        if not batch:
            break
        if budget.page_count:
            await asyncio.sleep(CATALOG_BATCH_PAUSE)

        async def _one(u: str) -> tuple[str, str, list, list[str]]:
            try:
                res = await fetcher.get(u)
                if res.status_code != 200 or not res.text:
                    return "", "", [], []
                page_url = _CatalogFetcher.final_url(res, u)
                found = _shop_products(res.text, page_url, set())
                found.extend(_jsonld_products(res.text, page_url))
                nexts = _pagination_urls(res.text, page_url)
                return page_url, _html_to_text(res.text, limit=16000), found, nexts
            except Exception:
                return "", "", [], []

        results = await asyncio.gather(*[_one(u) for u in batch])
        for page_url, text, found, nexts in results:
            if budget.stop():
                break
            if page_url and text:
                pages.append((page_url, text))
                budget.page_count += 1
            added = merge_fn(found)
            branch = _branch_key(page_url or "")
            if added or found:
                empty_streak_by_branch[branch] = 0
            else:
                empty_streak_by_branch[branch] = empty_streak_by_branch.get(branch, 0) + 1
            # Keep paginating through a few empty pages (lazy themes / wrong selector
            # on page 1), then stop that listing branch.
            if empty_streak_by_branch.get(branch, 0) <= CATALOG_EMPTY_PAGE_STREAK:
                for nxt in nexts:
                    nk = nxt.split("#")[0].rstrip("/").lower()
                    if nk not in visited:
                        queue.append(nxt)


def _pagination_urls(html: str, page_url: str) -> List[str]:
    """rel=next, /page/N/, ?page=N, ?paged=N, load-more successors for the current listing page."""
    soup = BeautifulSoup(html or "", "html.parser")
    found: List[str] = []
    seen = set()
    host = _registrable_domain(page_url)

    def _add(candidate: str) -> None:
        absolute = urljoin(page_url, candidate).split("#")[0]
        if not absolute or _registrable_domain(absolute) != host:
            return
        key = absolute.rstrip("/").lower()
        if key in seen or key == page_url.rstrip("/").lower():
            return
        seen.add(key)
        found.append(absolute)

    for link in soup.select(
        'a[rel*="next"], link[rel*="next"], '
        "a.next, a.page-numbers.next, .woocommerce-pagination a.next, "
        ".pagination a.next, .nav-links a.next, a[class*='next']"
    ):
        href = (link.get("href") or "").strip()
        if href:
            _add(href)

    for anchor in soup.select("a[href*='page'], a[href*='paged']"):
        href = (anchor.get("href") or "").strip()
        label = anchor.get_text(" ", strip=True).lower()
        classes = " ".join(anchor.get("class") or []).lower()
        if not href:
            continue
        pageish = (
            re.search(r"[?&]page=\d+", href, re.I)
            or re.search(r"[?&]paged=\d+", href, re.I)
            or re.search(r"/page/\d+", href, re.I)
        )
        if not pageish:
            continue
        if (
            label in {"next", "older", ">", "»", "load more", "show more", "view more"}
            or "next" in classes
            or "load-more" in classes
            or "loadmore" in classes
            or re.fullmatch(r"\d+", label)
            or re.search(r"/page/\d+/?$", href)
            or re.search(r"[?&](?:page|paged)=\d+", href)
        ):
            _add(href)

    # Load-more / infinite-scroll style controls
    for node in soup.select(
        "a[class*='load-more'], a[class*='loadmore'], button[class*='load-more'], "
        "a[data-next], a[data-page], [data-next-url], [data-href]"
    ):
        href = (
            (node.get("href") or "").strip()
            or (node.get("data-next") or "").strip()
            or (node.get("data-next-url") or "").strip()
            or (node.get("data-href") or "").strip()
            or (node.get("data-page") or "").strip()
        )
        if href and href.startswith(("http", "/", "?")):
            _add(href)

    # Highest page number visible in links / labels / "Page X of Y"
    max_page = 1
    for anchor in soup.select("a[href*='page'], a[href*='paged'], .page-numbers, .pagination a, nav a"):
        href = (anchor.get("href") or "").strip()
        label = (anchor.get_text(" ", strip=True) or "").strip()
        for pattern in (r"[?&]page=(\d+)", r"[?&]paged=(\d+)", r"/page/(\d+)"):
            m = re.search(pattern, href, re.I)
            if m:
                max_page = max(max_page, int(m.group(1)))
        if re.fullmatch(r"\d+", label):
            max_page = max(max_page, int(label))
    of_match = re.search(
        r"(?:page\s+)?(\d+)\s*(?:of|/)\s*(\d+)",
        soup.get_text(" ", strip=True)[:2500],
        re.I,
    )
    if of_match:
        max_page = max(max_page, int(of_match.group(2)))
    max_page = min(max_page, CATALOG_MAX_PAGE_PROBE)

    def _page_url(n: int) -> None:
        """Build listing URL for page N using the current URL's pagination style."""
        if n <= 1:
            return
        p = urlparse(page_url)
        path = p.path or "/"
        qs_now = parse_qs(p.query)
        if "paged" in qs_now or soup.select(".woocommerce-pagination, .page-numbers"):
            qs_paged = dict(qs_now)
            qs_paged.pop("page", None)
            qs_paged["paged"] = [str(n)]
            _add(urlunparse(p._replace(query=urlencode(qs_paged, doseq=True))))
        if "page" in qs_now or not re.search(r"/page/\d+", path):
            qs_page = dict(qs_now)
            qs_page.pop("paged", None)
            qs_page["page"] = [str(n)]
            _add(urlunparse(p._replace(query=urlencode(qs_page, doseq=True))))
        if re.search(r"/page/\d+/?$", path):
            nxt_path = re.sub(r"/page/\d+/?$", f"/page/{n}/", path)
            _add(urlunparse(p._replace(path=nxt_path)))
        else:
            base = page_url if page_url.endswith("/") else page_url + "/"
            _add(urljoin(base, f"page/{n}/"))

    # Synthetic next page when current URL already has a page marker
    parsed = urlparse(page_url)
    qs = parse_qs(parsed.query)
    try:
        cur_page = int((qs.get("page") or qs.get("paged") or ["1"])[0])
    except ValueError:
        cur_page = 1
    path_m = re.search(r"/page/(\d+)/?$", parsed.path or "")
    if path_m:
        cur_page = max(cur_page, int(path_m.group(1)))

    if "page" in qs:
        qs_next = dict(qs)
        qs_next["page"] = [str(cur_page + 1)]
        _add(urlunparse(parsed._replace(query=urlencode(qs_next, doseq=True))))
    elif "paged" in qs:
        qs_next = dict(qs)
        qs_next["paged"] = [str(cur_page + 1)]
        _add(urlunparse(parsed._replace(query=urlencode(qs_next, doseq=True))))
    elif path_m:
        nxt_path = re.sub(r"/page/\d+/?$", f"/page/{cur_page + 1}/", parsed.path)
        _add(urlunparse(parsed._replace(path=nxt_path)))
    elif soup.select(
        "li.product, .product-card, .product-item, .product-grid-item, "
        ".grid__item a[href*='/products/'], .wc-block-grid__product, [data-product-id]"
    ):
        # First listing page often has no page in URL — try common page-2 patterns
        _add(urljoin(page_url if page_url.endswith("/") else page_url + "/", "page/2/"))
        q2 = dict(qs)
        q2["page"] = ["2"]
        _add(urlunparse(parsed._replace(query=urlencode(q2, doseq=True))))
        q3 = dict(qs)
        q3["paged"] = ["2"]
        _add(urlunparse(parsed._replace(query=urlencode(q3, doseq=True))))

    # When the UI exposes "… 48", enqueue a window of page URLs so we do not
    # depend solely on clicking Next one page at a time.
    if max_page > 2:
        for n in range(cur_page + 1, max_page + 1):
            _page_url(n)

    return found[:CATALOG_PAGINATION_CAP]


def _html_to_text(html: str, limit: int = 12000) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "form"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())[:limit]


def _location_from_html(html: str) -> str:
    """Prefer address-looking footer / contact blocks for a display location."""
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    chunks: List[str] = []
    for sel in ("footer", "[class*='footer']", "[id*='footer']", "[class*='address']", "[itemprop='address']"):
        for node in soup.select(sel)[:4]:
            t = node.get_text(" ", strip=True)
            if t and len(t) > 8:
                chunks.append(t[:400])
    if not chunks:
        chunks.append(soup.get_text(" ", strip=True)[:2500])
    return _location_from_text(" ".join(chunks))


SIGNAL_LINK_HINTS = (
    "about", "about-us", "our-story", "our-company", "company", "who-we-are",
    "news", "press", "media", "blog", "insights", "careers", "jobs", "join",
    "sourcing", "suppliers", "become-a-supplier", "vendors", "partners",
    "wholesale", "b2b",
)


def _signal_page_urls(html: str, base_url: str) -> List[str]:
    """Same-domain links that often carry Intent evidence."""
    soup = BeautifulSoup(html or "", "html.parser")
    base_host = _registrable_domain(base_url)
    scored: List[tuple[int, str]] = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        href = (anchor.get("href") or "").strip()
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        absolute = urljoin(base_url, href).split("#")[0].rstrip("/") or urljoin(base_url, href)
        if _registrable_domain(absolute) != base_host or absolute in seen:
            continue
        path = (urlparse(absolute).path or "").lower().strip("/")
        label = anchor.get_text(" ", strip=True).lower()
        blob = f"{path} {label}"
        score = sum(1 for h in SIGNAL_LINK_HINTS if h in blob)
        if score <= 0:
            continue
        # Prefer shallow signal pages over deep product URLs
        if path.count("/") > 2 and not any(h in path for h in ("news", "press", "blog", "about")):
            continue
        seen.add(absolute)
        scored.append((score, absolute))
    scored.sort(key=lambda x: (-x[0], len(x[1])))
    return [u for _, u in scored]


def _guess_signal_paths(base_url: str) -> List[str]:
    root = (base_url or "").rstrip("/")
    if not root:
        return []
    return [
        f"{root}/about",
        f"{root}/about-us",
        f"{root}/news",
        f"{root}/press",
        f"{root}/careers",
        f"{root}/blog",
    ]


def _catalog_links(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    found: List[str] = []
    seen = set()
    keywords = (
        "product", "catalog", "category", "shop", "collection", "store",
        "item", "range", "series", "solutions", "equipment", "supplies",
        "wear", "apparel", "parts", "goods", "all-products", "merchandise",
    )
    for anchor in soup.find_all("a", href=True):
        href = (anchor.get("href") or "").strip()
        label = anchor.get_text(" ", strip=True).lower()
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        absolute = urljoin(base_url, href).split("#")[0].rstrip("/") or urljoin(base_url, href)
        host = _registrable_domain(absolute)
        if host != _registrable_domain(base_url) or absolute in seen:
            continue
        path = (urlparse(absolute).path or "").lower()
        is_listing = (
            "/product-category/" in path
            or "/collections/" in path
            or "/catalog" in path
            or path.rstrip("/").endswith("/shop")
            or path.rstrip("/").endswith("/store")
            or path.rstrip("/").endswith("/products")
            or any(key in path or key in label for key in keywords)
        )
        if not is_listing:
            continue
        # Skip individual PDPs in the seed list
        if re.search(r"/products?/[^/]+", path) and "/product-category/" not in path:
            continue
        if "/product/" in path and "/product-category/" not in path:
            continue
        seen.add(absolute)
        found.append(absolute)
    return found


def _shop_products(html: str, page_url: str, seen: set) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html or "", "html.parser")
    category = _category_from_url(page_url)
    products: List[Dict[str, Any]] = []

    cards = (
        soup.select("li.product")
        or soup.select(".product-card")
        or soup.select(".product-item")
        or soup.select(".product-grid-item")
        or soup.select(".grid__item")
        or soup.select("li.wc-block-grid__product")
        or soup.select(".wc-block-grid__product")
        or soup.select("article.product")
        or soup.select("[data-product-id]")
        or soup.select("[class*='ProductCard']")
        or soup.select("[class*='product-card']")
        or soup.select(".product")
    )

    def _append(name: str, href: str, blob: str, image_url: str, price: str) -> None:
        name = re.split(r"\s*(?:Art\s*#|SKU\s*[:#]?)\s*", name, maxsplit=1, flags=re.I)[0].strip()
        if not name or name.lower() in {"read more", "view product", "quick view", "sale"}:
            return
        # Prefer URL for uniqueness; titles often repeat across color/size variants
        key = (href or name).lower().rstrip("/")
        if key in seen or len(name) < 3:
            return
        seen.add(key)
        products.append({
            "name": name[:90],
            "category": category,
            "description": (blob or name)[:180],
            "productUrl": href or page_url,
            "imageUrl": image_url,
            "price": price[:40],
            "source_url": page_url,
        })

    for card in cards:
        link = (
            card.select_one("a[href*='/product/']")
            or card.select_one("a[href*='/products/']")
            or card.select_one("a[href*='/item/']")
            or card.select_one("a[href*='/p/']")
            or card.select_one("a[href*='/goods/']")
            or card.select_one("a[href*='/shop/']")
            or card.select_one("a[href]")
        )
        href = (link.get("href") if link else "") or ""
        if href:
            href = urljoin(page_url, href)
        heading = ""
        for sel in (
            "h2", "h3", "h4",
            ".woocommerce-loop-product__title",
            ".product-title",
            ".card__heading",
            ".full-unstyled-link",
        ):
            node = card.select_one(sel)
            if node and node.get_text(" ", strip=True):
                heading = node.get_text(" ", strip=True)
                break
        blob = re.sub(r"\s+", " ", card.get_text(" ", strip=True))
        blob = re.sub(r"\s*Read more\s*", " ", blob, flags=re.I).strip()
        name = heading or (link.get_text(" ", strip=True) if link else "")

        image_url = ""
        img_tag = card.select_one("img")
        if img_tag:
            srcset = img_tag.get("srcset") or img_tag.get("data-srcset") or ""
            if srcset:
                candidates = [s.strip().split()[0] for s in srcset.split(",") if s.strip()]
                if candidates:
                    image_url = urljoin(page_url, candidates[-1])
            if not image_url:
                src = img_tag.get("src") or img_tag.get("data-src") or img_tag.get("data-lazy-src") or ""
                if src and not src.startswith("data:"):
                    image_url = urljoin(page_url, src)

        price_node = card.select_one(".price, .price__regular, .money, [data-product-price]")
        price = price_node.get_text(" ", strip=True) if price_node else ""
        _append(name, href, blob, image_url, price)

    # Generic product-link harvest when theme cards were sparse/partial
    if len(products) < CATALOG_LINK_HARVEST_IF_BELOW:
        for anchor in soup.select(
            "a[href*='/products/'], a[href*='/product/'], a[href*='/item/'], "
            "a[href*='/shop/'], a[href*='/p/'], a[href*='/goods/'], a[href*='/catalog/']"
        ):
            href = urljoin(page_url, (anchor.get("href") or "").strip())
            path = (urlparse(href).path or "").lower()
            if not _looks_like_product_url(href):
                continue
            if "/product-category/" in path or "/collections/" in path:
                continue
            name = anchor.get_text(" ", strip=True)
            if not name or len(name) < 3:
                # Try nearby heading / image alt
                parent = anchor.find_parent(["li", "div", "article"])
                if parent:
                    h = parent.select_one("h2, h3, h4")
                    if h:
                        name = h.get_text(" ", strip=True)
            if not name:
                name = path.rstrip("/").split("/")[-1].replace("-", " ").title()
            img = ""
            parent = anchor.find_parent(["li", "div", "article"])
            img_tag = anchor.select_one("img")
            if not img_tag and parent:
                img_tag = parent.select_one("img")
            if img_tag:
                src = img_tag.get("src") or img_tag.get("data-src") or ""
                if src and not str(src).startswith("data:"):
                    img = urljoin(page_url, src)
            _append(name, href, name, img, "")

    return products


def _category_from_url(url: str) -> str:
    path = (urlparse(url).path or "").strip("/")
    parts = [p for p in path.split("/") if p and p != "product-category"]
    if not parts:
        return "Uncategorized"
    slug = parts[0].replace("-", " ").replace("and", "&")
    return slug.title()
