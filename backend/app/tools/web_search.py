import asyncio
import json
import re
import time
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings


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


class WebSearchTool:
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
                json={"q": query},
            )
            res.raise_for_status()
            data = res.json()
            return list(data.get("places") or data.get("organic") or [])

    async def hunt_leads(
        self,
        queries: List[Any],
        target_location: str = "",
        exclude_domains: Optional[set] = None,
        limit: int = 40,
        use_maps: bool = False,
    ) -> List[Dict[str, Any]]:
        """Run a wave of web searches (Maps only when the plan says so)."""
        exclude_domains = exclude_domains or set()
        merged: List[Dict[str, Any]] = []
        seen: set = set(exclude_domains)

        specs: List[Dict[str, Any]] = []
        for q in queries[:8]:
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
                json={"q": query, "num": 15},
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
                params={"q": query, "count": 10},
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
                json={"api_key": settings.TAVILY_API_KEY, "query": query, "max_results": 10},
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
                rows = list(ddgs.text(query, max_results=8))
                return [
                    {"title": r.get("title", ""), "href": r.get("href", ""), "body": r.get("body", "")}
                    for r in rows
                ]
        except Exception:
            pass
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                rows = list(ddgs.text(query, max_results=8))
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
        if not url or _should_skip(url):
            return [], []
        pages: List[tuple[str, str]] = []
        products: List[Dict[str, Any]] = []
        seen_names: set[str] = set()
        seen_pages: set[str] = set()
        started = time.monotonic()
        budget_s = 28.0
        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, headers=HEADERS) as client:
                first = await client.get(url)
                if first.status_code != 200 or not first.text:
                    return [], []
                start_url = str(first.url)
                html = first.text
                pages.append((start_url, _html_to_text(html, limit=18000)))
                seen_pages.add(start_url.rstrip("/").lower())
                products.extend(_extract_page_products(html, start_url, seen_names))

                # Prefer classic Woo category crawl when available (worked reliably before).
                woo_cats = [
                    u for u in _catalog_links(html, start_url)
                    if "/product-category/" in (urlparse(u).path or "").lower()
                ]
                if woo_cats:
                    extra_urls = woo_cats
                else:
                    extra_urls = _catalog_links(html, start_url)
                    if len(products) < 8:
                        extra_urls = _guess_catalog_paths(start_url) + extra_urls
                extra_urls = _prioritize_catalog_urls(extra_urls)
                # Keep crawl small so the API returns before platform timeouts
                max_extra = 12 if woo_cats else 10
                for extra in extra_urls[:max_extra]:
                    if time.monotonic() - started > budget_s:
                        break
                    if len(products) >= 80:
                        break
                    key = extra.rstrip("/").lower()
                    if key in seen_pages:
                        continue
                    seen_pages.add(key)
                    try:
                        res = await client.get(extra)
                        if res.status_code == 200 and res.text:
                            pages.append((str(res.url), _html_to_text(res.text, limit=18000)))
                            products.extend(_extract_page_products(res.text, str(res.url), seen_names))
                    except Exception:
                        continue
        except Exception:
            return pages, products
        return pages, products


def _html_to_text(html: str, limit: int = 12000) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    # Keep JSON-LD / Next data out of visible text path; parsed separately
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


_LISTING_PATH_HINTS = (
    "/product-category/", "/collections/", "/collection/", "/category/",
    "/categories/", "/shop/", "/store/", "/catalog/", "/catalogue/",
    "/products", "/w/", "/c/", "/men", "/women", "/kids", "/new",
)


def _catalog_links(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    found: List[str] = []
    seen = set()
    keywords = (
        "product", "catalog", "catalogue", "category", "shop", "collection", "store",
        "item", "range", "series", "solutions", "equipment", "supplies",
        "wear", "apparel", "parts", "goods", "shoes", "clothing", "new",
        "men", "women", "kids", "sale",
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
        # Skip obvious single PDPs when looking for listing pages
        if _looks_like_pdp(path) and not any(h in path for h in ("/product-category/", "/collections/")):
            continue
        if any(h in path for h in _LISTING_PATH_HINTS) or any(key in path or key in label for key in keywords):
            seen.add(absolute)
            found.append(absolute)
    return found


def _guess_catalog_paths(base_url: str) -> List[str]:
    parsed = urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    if not root:
        return []
    return [
        f"{root}/shop",
        f"{root}/products",
        f"{root}/collections/all",
        f"{root}/collections",
        f"{root}/catalog",
        f"{root}/w/new",
        f"{root}/w/mens-shoes",
        f"{root}/w/womens-shoes",
        f"{root}/men",
        f"{root}/women",
    ]


def _prioritize_catalog_urls(urls: List[str]) -> List[str]:
    def score(u: str) -> tuple:
        path = (urlparse(u).path or "").lower()
        rank = 0
        if any(h in path for h in ("/product-category/", "/collections/", "/shop", "/w/", "/products")):
            rank -= 10
        if _looks_like_pdp(path):
            rank += 20
        return (rank, len(path), u)

    return sorted(dict.fromkeys(urls), key=score)


def _looks_like_pdp(path: str) -> bool:
    path = (path or "").lower()
    if "/product-category/" in path or "/collections/" in path:
        return False
    if re.search(r"/product/[^/]+/?$", path):
        return True
    if re.search(r"/products/[^/]+/?$", path):
        return True
    # Nike-style PDP: /t/slug-...
    if re.search(r"/t/[a-z0-9-]+", path):
        return True
    return False


def _extract_page_products(html: str, page_url: str, seen: set) -> List[Dict[str, Any]]:
    """Combine Woo cards, JSON-LD, optional Next.js data, and product link grids."""
    products: List[Dict[str, Any]] = []
    # Woo / generic cards first (historically reliable)
    products.extend(_shop_products(html, page_url, seen))
    products.extend(_jsonld_products(html, page_url, seen))
    # Only parse embedded app JSON when present — never scan arbitrary JS bundles
    if "__NEXT_DATA__" in (html or "") or 'id="__NEXT_DATA__"' in (html or ""):
        products.extend(_embedded_json_products(html, page_url, seen))
    # Link-grid fill-in when still thin (Nike /t/, Shopify /products/)
    if len(products) < 12:
        products.extend(_product_link_grid(html, page_url, seen))
    return products


def _add_product(
    products: List[Dict[str, Any]],
    seen: set,
    *,
    name: str,
    page_url: str,
    category: str = "",
    description: str = "",
    product_url: str = "",
    image_url: str = "",
    price: str = "",
    allow_listing_url: bool = False,
) -> None:
    name = re.sub(r"\s+", " ", (name or "")).strip()
    name = re.split(r"\s*Art\s*#", name, maxsplit=1)[0].strip()
    if not name or len(name) < 3 or len(name) > 120:
        return
    lowered = name.lower()
    if lowered in {
        "read more", "view product", "shop now", "buy now", "nike", "home",
        "shoes", "men", "women", "kids", "new", "sale", "shop", "products",
        "clothing", "apparel", "accessories", "sportswear",
    }:
        return
    product_path = (urlparse(product_url or page_url).path or "").lower()
    # Skip category/listing titles that aren't real PDPs (unless Woo card fallback)
    if (
        not allow_listing_url
        and product_url
        and not _looks_like_pdp(product_path)
        and (product_url or "").rstrip("/").lower() == (page_url or "").rstrip("/").lower()
    ):
        return
    # Deduplicate by name for listing-url fallbacks so one category page doesn't collapse cards
    key = (product_url or "").lower() if _looks_like_pdp(product_path) else f"name:{(name or '').lower()}"
    if not key.strip():
        key = f"name:{lowered}"
    if key in seen:
        return
    seen.add(key)
    products.append({
        "name": name[:90],
        "category": category or _category_from_url(page_url),
        "description": (description or name)[:180],
        "productUrl": product_url or page_url,
        "imageUrl": image_url or "",
        "price": (price or "")[:40],
        "source_url": page_url,
    })


def _jsonld_products(html: str, page_url: str, seen: set) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html or "", "html.parser")
    products: List[Dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        types = node.get("@type") or node.get("type") or ""
        if isinstance(types, list):
            type_set = {str(t).lower() for t in types}
        else:
            type_set = {str(types).lower()}

        if "itemlist" in type_set:
            for el in node.get("itemListElement") or []:
                walk(el.get("item") if isinstance(el, dict) else el)
        if "product" in type_set or "productgroup" in type_set:
            name = node.get("name") or ""
            url = node.get("url") or node.get("@id") or ""
            if isinstance(url, dict):
                url = url.get("@id") or ""
            image = node.get("image") or ""
            if isinstance(image, list) and image:
                image = image[0]
            if isinstance(image, dict):
                image = image.get("url") or image.get("contentUrl") or ""
            offers = node.get("offers") or {}
            if isinstance(offers, list) and offers:
                offers = offers[0]
            price = ""
            if isinstance(offers, dict):
                price = str(offers.get("price") or offers.get("lowPrice") or "")
                if price and offers.get("priceCurrency"):
                    price = f"{offers.get('priceCurrency')} {price}".strip()
            _add_product(
                products,
                seen,
                name=str(name),
                page_url=page_url,
                description=str(node.get("description") or "")[:180],
                product_url=urljoin(page_url, str(url)) if url else page_url,
                image_url=urljoin(page_url, str(image)) if image else "",
                price=price,
            )
        for key in ("@graph", "mainEntity", "hasVariant", "isVariantOf"):
            if key in node:
                walk(node.get(key))

    for script in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = (script.string or script.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        walk(data)
    return products


def _walk_for_productish(obj: Any, out: List[Dict[str, str]], depth: int = 0) -> None:
    if depth > 8 or len(out) >= 100:
        return
    if isinstance(obj, list):
        for item in obj[:80]:
            _walk_for_productish(item, out, depth + 1)
        return
    if not isinstance(obj, dict):
        return
    name = obj.get("title") or obj.get("fullTitle") or obj.get("productName") or obj.get("name") or ""
    url = obj.get("url") or obj.get("pdpUrl") or obj.get("productUrl") or obj.get("slug") or ""
    image = (
        obj.get("imageUrl")
        or obj.get("image")
        or (obj.get("images") or [None])[0]
        or ""
    )
    if isinstance(image, dict):
        image = image.get("url") or image.get("src") or ""
    price = ""
    for key in ("price", "currentPrice", "salePrice", "amount"):
        val = obj.get(key)
        if val is None and isinstance(obj.get("price"), dict):
            val = obj["price"].get("currentPrice") or obj["price"].get("amount")
        if val is not None and str(val).strip():
            price = str(val)
            break
    # Likely a product card if it has a title and product-ish URL/id
    pid = obj.get("productId") or obj.get("styleColor") or obj.get("sku") or obj.get("id")
    if name and (url or pid) and isinstance(name, str) and 3 < len(name) < 120:
        out.append({
            "name": name,
            "url": str(url or ""),
            "image": str(image or ""),
            "price": price,
            "description": str(obj.get("subtitle") or obj.get("description") or "")[:180],
        })
    for val in list(obj.values())[:40]:
        if isinstance(val, (dict, list)):
            _walk_for_productish(val, out, depth + 1)


def _embedded_json_products(html: str, page_url: str, seen: set) -> List[Dict[str, Any]]:
    """Pull products from __NEXT_DATA__ only (safe). Avoid scanning large JS bundles."""
    soup = BeautifulSoup(html or "", "html.parser")
    products: List[Dict[str, Any]] = []
    node = soup.find("script", id="__NEXT_DATA__")
    if not node:
        return products
    raw = (node.string or node.get_text() or "").strip()
    if not raw or len(raw) > 2_000_000:
        return products
    try:
        data = json.loads(raw)
    except Exception:
        return products

    found: List[Dict[str, str]] = []
    _walk_for_productish(data, found)

    for item in found:
        href = item.get("url") or ""
        if href and not href.startswith("http"):
            if href.startswith("/"):
                href = urljoin(page_url, href)
            else:
                href = urljoin(page_url, f"/t/{href}" if "/" not in href else href)
        _add_product(
            products,
            seen,
            name=item.get("name") or "",
            page_url=page_url,
            description=item.get("description") or "",
            product_url=href,
            image_url=urljoin(page_url, item["image"]) if item.get("image") else "",
            price=item.get("price") or "",
        )
    return products


def _shop_products(html: str, page_url: str, seen: set) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html or "", "html.parser")
    category = _category_from_url(page_url)
    products: List[Dict[str, Any]] = []
    # WooCommerce first (li.product), then other card patterns — avoid one giant .product wrapper
    cards = soup.select("li.product")
    if not cards:
        cards = soup.select(
            "li.product-item, .product-card, .product-item, "
            "[data-product-id], [data-productid]"
        )
    if not cards:
        cards = [
            c for c in soup.select(".product")
            if len(c.get_text(" ", strip=True) or "") < 600
            and (
                c.select_one("a[href*='/product/']")
                or c.select_one("a[href*='/products/']")
                or c.select_one("h2, h3, .woocommerce-loop-product__title, .product-title")
            )
        ]
    for card in cards:
        link = (
            card.select_one("a[href*='/product/']")
            or card.select_one("a[href*='/products/']")
            or card.select_one("a[href*='/t/']")
            or card.select_one("a[href]")
        )
        href = (link.get("href") if link else "") or ""
        if href:
            href = urljoin(page_url, href)
        heading = ""
        for sel in (
            "h2", "h3", "h4",
            ".woocommerce-loop-product__title", ".product-title",
            ".product-card__title", "[data-testid='product-card__link']",
            ".card-title", ".product-name",
        ):
            node = card.select_one(sel)
            if node and node.get_text(" ", strip=True):
                heading = node.get_text(" ", strip=True)
                break
        if not heading and link:
            heading = (
                (link.get("aria-label") or "")
                or link.get_text(" ", strip=True)
            )
        blob = re.sub(r"\s+", " ", card.get_text(" ", strip=True))
        blob = re.sub(r"\s*Read more\s*", " ", blob, flags=re.I).strip()
        sku_match = re.search(r"(AWE[-\s]?\d+)", blob, re.I)
        name = heading
        name = re.split(r"\s*Art\s*#", name, maxsplit=1)[0].strip()
        if not name or name.lower() in {"read more", "view product"}:
            img_tag = card.select_one("img")
            if img_tag:
                name = (img_tag.get("alt") or "").strip()
        if not name or name.lower() in {"read more", "view product"}:
            continue
        sku = sku_match.group(1).upper().replace(" ", "-") if sku_match else ""
        display = f"{name} ({sku})" if sku else name

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

        price_node = card.select_one(".price, [data-testid='product-price'], .product-price")
        price = price_node.get_text(" ", strip=True)[:40] if price_node else ""

        # Woo cards always keep product even if href is the category page fallback
        product_url = href if href and _looks_like_pdp(urlparse(href).path or "") else (href or "")
        if not product_url and href:
            product_url = href
        _add_product(
            products,
            seen,
            name=display,
            page_url=page_url,
            category=category,
            description=blob[:180],
            product_url=product_url or href or f"{page_url}#{len(seen)}",
            image_url=image_url,
            price=price,
            allow_listing_url=True,
        )
    return products


def _product_link_grid(html: str, page_url: str, seen: set) -> List[Dict[str, Any]]:
    """Fallback: collect product PDP links and use link text / img alt as names."""
    soup = BeautifulSoup(html or "", "html.parser")
    products: List[Dict[str, Any]] = []
    for anchor in soup.select("a[href*='/product/'], a[href*='/products/'], a[href*='/t/']"):
        href = (anchor.get("href") or "").strip()
        if not href:
            continue
        absolute = urljoin(page_url, href).split("#")[0]
        path = (urlparse(absolute).path or "").lower()
        if not _looks_like_pdp(path):
            continue
        name = (
            (anchor.get("aria-label") or "").strip()
            or anchor.get_text(" ", strip=True)
        )
        if not name or len(name) < 3:
            img = anchor.select_one("img")
            if img:
                name = (img.get("alt") or "").strip()
        if not name:
            # slug → title
            slug = path.rstrip("/").split("/")[-1]
            name = re.sub(r"[-_]+", " ", slug)
            name = re.sub(r"\b(mens|womens|kids|shoes|shoe)\b", "", name, flags=re.I)
            name = re.sub(r"\s+", " ", name).strip().title()
        image_url = ""
        img = anchor.select_one("img")
        if img:
            src = img.get("src") or img.get("data-src") or ""
            if src and not src.startswith("data:"):
                image_url = urljoin(page_url, src)
        _add_product(
            products,
            seen,
            name=name,
            page_url=page_url,
            product_url=absolute,
            image_url=image_url,
        )
        if len(products) >= 60:
            break
    return products


def _category_from_url(url: str) -> str:
    path = (urlparse(url).path or "").strip("/")
    parts = [p for p in path.split("/") if p and p not in ("product-category", "collections", "w", "t", "products", "product")]
    if not parts:
        return "Uncategorized"
    slug = parts[0].replace("-", " ").replace("and", "&")
    return slug.title()
