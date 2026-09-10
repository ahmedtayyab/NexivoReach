import asyncio
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
CATALOG_CONCURRENCY = 4
CATALOG_BATCH_PAUSE = 0.4
CATALOG_LIMITS = httpx.Limits(max_connections=CATALOG_CONCURRENCY, max_keepalive_connections=CATALOG_CONCURRENCY)
CATALOG_MAX_PRODUCTS = 1500
CATALOG_MAX_LISTING_PAGES = 80
CATALOG_TIME_BUDGET_SEC = 90.0
CATALOG_WP_REST_MAX_PAGES = max(1, CATALOG_MAX_PRODUCTS // 100)


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
        name = re.split(r"\s[|\-–:]\s", title, maxsplit=1)[0].strip()
        name = re.sub(r"[®™]", "", name).strip() or title
        if _looks_like_article(name, url) or len(name) > 60:
            name = _brand_from_url(url) or name
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
    ) -> List[Dict[str, Any]]:
        """Run a wave of web searches (Maps only when the plan says so)."""
        exclude_domains = exclude_domains or set()
        merged: List[Dict[str, Any]] = []
        seen: set = set(exclude_domains)

        specs: List[Dict[str, Any]] = []
        for q in queries[:16]:
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
        for batch in results:
            if not isinstance(batch, list):
                continue
            for row in batch:
                website = (row.get("website") or "").strip()
                domain = _registrable_domain(website) if website else (row.get("company_name") or "").lower()
                if not domain or domain in seen:
                    continue
                seen.add(domain)
                merged.append(row)
                if len(merged) >= limit:
                    return merged
        return merged

    def _search_sync(self, query: str) -> List[Dict[str, str]]:
        for fn in (self._serper, self._brave, self._tavily, self._duckduckgo):
            try:
                hits = fn(query)
                if hits:
                    return hits
            except Exception:
                continue
        return []

    def _serper(self, query: str) -> List[Dict[str, str]]:
        if not settings.SERPER_API_KEY:
            return []
        with httpx.Client(timeout=20.0) as client:
            res = client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": settings.SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": query, "num": 20},
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

    async def scrape_homepage(self, url: str, limit: int = 8000) -> Dict[str, Any]:
        """Cheap single-page fetch for qualification. Does not crawl the shop catalog."""
        if not url or _should_skip(url):
            return {"text": "", "title": "", "url": url or "", "ok": False, "location": ""}
        try:
            async with httpx.AsyncClient(timeout=6.0, follow_redirects=True, headers=HEADERS) as client:
                res = await client.get(url)
                if res.status_code != 200 or not res.text:
                    return {"text": "", "title": "", "url": str(res.url), "ok": False, "location": ""}
                soup = BeautifulSoup(res.text, "html.parser")
                title = ""
                if soup.title and soup.title.get_text(strip=True):
                    title = soup.title.get_text(strip=True)[:160]
                meta = soup.find("meta", attrs={"name": "description"})
                desc = (meta.get("content") or "") if meta else ""
                # Location often lives in the footer — extract before we strip chrome
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
                return {
                    "text": text,
                    "title": title,
                    "url": str(res.url),
                    "ok": True,
                    "status": res.status_code,
                    "html": res.text,
                    "location": location,
                    "emails": emails,
                    "phones": phones,
                    "contact_urls": contact_urls,
                }
        except Exception:
            return {"text": "", "title": "", "url": url, "ok": False, "location": ""}

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
        seen_names: set[str] = set()
        budget = _CatalogBudget()

        def _merge(items: List[Dict[str, Any]]) -> int:
            added = 0
            for item in items:
                if budget.stop():
                    break
                key = (item.get("productUrl") or item.get("name") or "").strip().lower()
                name_key = (item.get("name") or "").strip().lower()
                if not key or key in seen_names:
                    continue
                if name_key and name_key in seen_names:
                    continue
                seen_names.add(key)
                if name_key:
                    seen_names.add(name_key)
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
                    self.catalog_truncated = budget.truncated
                    log.info(
                        "scrape_shop_catalog(%s): Shopify returned %d products truncated=%s",
                        url, len(products), budget.truncated,
                    )
                    return pages, products

                # 2) WordPress / WooCommerce REST (Alwasi-style)
                rest_products, _rest_err = await _fetch_wp_rest_products(fetcher, url, budget)
                # Missing/failed REST must fall through — do not abort the HTML cascade.
                if rest_products:
                    _merge(rest_products)
                    pages.append(
                        (urljoin(url, "/wp-json/wp/v2/product"), f"WP REST products: {len(rest_products)}")
                    )
                    self.catalog_truncated = budget.truncated
                    log.info(
                        "scrape_shop_catalog(%s): WP REST returned %d products truncated=%s",
                        url, len(products), budget.truncated,
                    )
                    return pages, products

                # 3) Homepage + sitemap product URLs + paginated listing pages
                try:
                    first = await fetcher.get(url)
                except Exception as exc:
                    log.warning("scrape_shop_catalog(%s): homepage fetch failed: %r", url, exc)
                    self.last_catalog_error = _connect_error_kind(exc)
                    return [], []
                if first.status_code != 200 or not first.text:
                    log.warning(
                        "scrape_shop_catalog(%s): homepage status=%s len=%d",
                        url, first.status_code, len(first.text or ""),
                    )
                    self.last_catalog_error = "unreachable" if first.status_code in (0, 403, 502, 503) else ""
                    return [], []

                html = first.text
                start_url = _CatalogFetcher.final_url(first, url)
                pages.append((start_url, _html_to_text(html)))
                budget.page_count += 1
                _merge(_shop_products(html, start_url, set()))

                # Sitemap product URLs (name-from-slug; no PDP fetch)
                if not budget.stop():
                    sitemap_urls = await _fetch_sitemap_product_urls(fetcher, start_url, budget)
                    if sitemap_urls:
                        pages.append((urljoin(start_url, "/sitemap.xml"), f"Sitemap product URLs: {len(sitemap_urls)}"))
                        _merge([_product_from_url(u, start_url) for u in sitemap_urls])

                # Listing / collection / category pages with pagination
                if not budget.stop():
                    listing_seeds = _listing_page_urls(html, start_url)
                    await _crawl_listing_pages(
                        fetcher, listing_seeds, pages, _merge, budget, seen_names
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


async def _fetch_sitemap_product_urls(
    fetcher: "_CatalogFetcher",
    site_url: str,
    budget: _CatalogBudget,
) -> List[str]:
    """Collect same-host product URLs from sitemap.xml (and one level of nested indexes)."""
    parsed = urlparse(site_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    seeds = [
        f"{root}/sitemap.xml",
        f"{root}/sitemap_index.xml",
        f"{root}/product-sitemap.xml",
        f"{root}/sitemap_products_1.xml",
    ]
    found: List[str] = []
    seen: set[str] = set()
    nested: List[str] = []

    async def _load(sm_url: str) -> tuple[List[str], List[str]]:
        try:
            res = await fetcher.get(sm_url)
        except Exception:
            return [], []
        if res.status_code != 200 or not (res.text or "").strip():
            return [], []
        return _parse_sitemap_xml(res.text, root)

    for seed in seeds:
        if budget.stop() or len(found) >= budget.room():
            break
        locs, children = await _load(seed)
        for loc in locs:
            if loc not in seen and _looks_like_product_url(loc):
                seen.add(loc)
                found.append(loc)
        for child in children:
            if child not in nested:
                nested.append(child)

    for child in nested[:20]:
        if budget.stop() or len(found) >= budget.room():
            break
        locs, _ = await _load(child)
        for loc in locs:
            if loc not in seen and _looks_like_product_url(loc):
                seen.add(loc)
                found.append(loc)
                if len(found) >= budget.room():
                    break
        await asyncio.sleep(CATALOG_BATCH_PAUSE)

    return found[: budget.room() or CATALOG_MAX_PRODUCTS]


def _parse_sitemap_xml(xml_text: str, root: str) -> tuple[List[str], List[str]]:
    locs: List[str] = []
    children: List[str] = []
    try:
        # Strip default namespaces so local tags resolve
        cleaned = re.sub(r'\sxmlns="[^"]+"', "", xml_text or "", count=1)
        root_el = ET.fromstring(cleaned)
    except ET.ParseError:
        return [], []
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


def _looks_like_product_url(url: str) -> bool:
    path = (urlparse(url).path or "").lower()
    if not path or path in {"/", ""}:
        return False
    if any(skip in path for skip in ("/cart", "/checkout", "/account", "/blogs/", "/pages/", "/collections/")):
        # collections are listings, not products
        if "/products/" in path:
            return True
        return False
    return bool(
        re.search(r"/products?/[^/]+", path)
        or "/product/" in path
        or re.search(r"/shop/[^/]+", path)
    )


def _product_from_url(product_url: str, site_url: str) -> Dict[str, Any]:
    path = (urlparse(product_url).path or "").strip("/")
    slug = path.split("/")[-1] if path else "product"
    name = slug.replace("-", " ").replace("_", " ").strip().title() or "Product"
    return {
        "name": name[:90],
        "category": _category_from_url(product_url),
        "description": name,
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
    return (preferred + rest)[:40]


async def _crawl_listing_pages(
    fetcher: "_CatalogFetcher",
    seeds: List[str],
    pages: List[tuple[str, str]],
    merge_fn,
    budget: _CatalogBudget,
    _seen_names: set[str],
) -> None:
    """Fetch listing pages and follow pagination until budget is exhausted."""
    queue: List[str] = list(seeds)
    visited: set[str] = set()

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
            # Only enqueue next pages when this page contributed products (or first listing)
            if added or found:
                for nxt in nexts:
                    nk = nxt.split("#")[0].rstrip("/").lower()
                    if nk not in visited:
                        queue.append(nxt)


def _pagination_urls(html: str, page_url: str) -> List[str]:
    """rel=next, /page/N/, ?page=N successors for the current listing page."""
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

    for link in soup.select('a[rel*="next"], link[rel*="next"]'):
        href = (link.get("href") or "").strip()
        if href:
            _add(href)

    for anchor in soup.select("a[href*='page']"):
        href = (anchor.get("href") or "").strip()
        label = anchor.get_text(" ", strip=True).lower()
        if not href:
            continue
        if re.search(r"[?&]page=\d+", href, re.I) or re.search(r"/page/\d+", href, re.I):
            if label in {"next", "older", ">", "»"} or re.fullmatch(r"\d+", label) or "next" in (anchor.get("class") or []):
                _add(href)
            elif re.search(r"/page/\d+/?$", href) or re.search(r"[?&]page=\d+", href):
                _add(href)

    # Synthetic next page when current URL already has a page marker
    parsed = urlparse(page_url)
    qs = parse_qs(parsed.query)
    if "page" in qs:
        try:
            cur = int((qs.get("page") or ["1"])[0])
        except ValueError:
            cur = 1
        qs["page"] = [str(cur + 1)]
        synthetic = urlunparse(parsed._replace(query=urlencode(qs, doseq=True)))
        _add(synthetic)
    else:
        m = re.search(r"/page/(\d+)/?$", parsed.path or "")
        if m:
            nxt_path = re.sub(r"/page/\d+/?$", f"/page/{int(m.group(1)) + 1}/", parsed.path)
            _add(urlunparse(parsed._replace(path=nxt_path)))
        elif soup.select("li.product, .product-card, .grid__item a[href*='/products/']"):
            # First listing page often has no page in URL — try page 2 patterns
            _add(urljoin(page_url if page_url.endswith("/") else page_url + "/", "page/2/"))
            q2 = dict(parse_qs(parsed.query))
            q2["page"] = ["2"]
            _add(urlunparse(parsed._replace(query=urlencode(q2, doseq=True))))

    return found[:6]


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
        "wear", "apparel", "parts", "goods",
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
            or path.rstrip("/").endswith("/shop")
            or path.rstrip("/").endswith("/store")
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
        or soup.select(".grid__item")
        or soup.select("article.product")
        or soup.select("[data-product-id]")
        or soup.select(".product")
    )

    def _append(name: str, href: str, blob: str, image_url: str, price: str) -> None:
        name = re.split(r"\s*Art\s*#", name, maxsplit=1)[0].strip()
        if not name or name.lower() in {"read more", "view product", "quick view", "sale"}:
            return
        sku_match = re.search(r"(AWE[-\s]?\d+)", blob, re.I)
        sku = sku_match.group(1).upper().replace(" ", "-") if sku_match else ""
        display = f"{name} ({sku})" if sku else name
        key = (href or display).lower()
        if key in seen or len(display) < 3:
            return
        seen.add(key)
        products.append({
            "name": display[:90],
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

    # Generic product-link harvest when theme cards were sparse
    if len(products) < 3:
        for anchor in soup.select("a[href*='/products/'], a[href*='/product/']"):
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
