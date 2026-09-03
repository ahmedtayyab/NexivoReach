import asyncio
import re
from typing import List, Dict, Any
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
            "location": _location_from_text(f"{title} {snippet}", target_location),
            "industry": "",
            "snippet": snippet[:500],
            "_rank": homepage_bonus - article_penalty,
        })
    companies.sort(key=lambda row: row.get("_rank", 0), reverse=True)
    for row in companies:
        row.pop("_rank", None)
    return companies


def _location_from_text(text: str, fallback: str = "") -> str:
    blob = text or ""
    # Keep this list as geography hints, not a product vertical.
    places = [
        "United Arab Emirates", "UAE", "Dubai", "Abu Dhabi", "Sharjah",
        "Saudi Arabia", "Riyadh", "Jeddah", "Qatar", "Doha", "Kuwait", "Oman", "Bahrain",
        "United States", "USA", "United Kingdom", "UK", "Germany", "France", "Netherlands",
        "India", "Pakistan", "China", "Singapore", "Malaysia", "Australia", "Canada",
        "Berlin", "London", "New York", "Chicago", "Toronto", "Sydney",
    ]
    found = [p for p in places if re.search(rf"\b{re.escape(p)}\b", blob, re.I)]
    if found:
        return ", ".join(dict.fromkeys(found) )[:80]
    return fallback or "Unknown"


class WebSearchTool:
    def name(self) -> str:
        return "WebSearchTool"

    async def search_companies(self, query: str, target_location: str = "") -> List[Dict[str, Any]]:
        q = (query or "").strip()
        if target_location and target_location.lower() not in q.lower():
            q = f"{q} {target_location}".strip()
        if q and "official" not in q.lower():
            q = f"{q} company official website"
        if not q:
            return []
        raw = await asyncio.to_thread(self._search_sync, q)
        return results_to_companies(raw, target_location)

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
                json={"q": query, "num": 10},
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

    async def scrape_site_content(self, url: str) -> str:
        pages = await self.scrape_catalog_pages(url)
        return pages[0][1] if pages else ""

    async def scrape_catalog_pages(self, url: str) -> List[tuple[str, str]]:
        pages, _ = await self.scrape_shop_catalog(url)
        return pages

    async def scrape_shop_catalog(self, url: str) -> tuple[List[tuple[str, str]], List[Dict[str, Any]]]:
        if not url or _should_skip(url):
            return [], []
        pages: List[tuple[str, str]] = []
        products: List[Dict[str, Any]] = []
        seen_names: set[str] = set()
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=HEADERS) as client:
                first = await client.get(url)
                if first.status_code != 200 or not first.text:
                    return [], []
                html = first.text
                pages.append((str(first.url), _html_to_text(html)))
                products.extend(_shop_products(html, str(first.url), seen_names))
                extra_urls = [item for item in _catalog_links(html, str(first.url)) if "/product-category/" in item]
                extra_urls.sort()
                for extra in extra_urls[:30]:
                    try:
                        res = await client.get(extra)
                        if res.status_code == 200 and res.text:
                            pages.append((str(res.url), _html_to_text(res.text, limit=16000)))
                            products.extend(_shop_products(res.text, str(res.url), seen_names))
                    except Exception:
                        continue
        except Exception:
            return pages, products
        return pages, products


def _html_to_text(html: str, limit: int = 12000) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "form"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())[:limit]


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
        if "/product-category/" in path or any(key in path or key in label for key in keywords):
            if "/product/" in path and "/product-category/" not in path:
                continue
            seen.add(absolute)
            found.append(absolute)
    return found


def _shop_products(html: str, page_url: str, seen: set) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html or "", "html.parser")
    category = _category_from_url(page_url)
    products: List[Dict[str, Any]] = []
    cards = soup.select("li.product") or soup.select(".product")
    for card in cards:
        link = card.select_one("a[href*='/product/']")
        href = (link.get("href") if link else "") or ""
        heading = ""
        for sel in ("h2", "h3", ".woocommerce-loop-product__title", ".product-title"):
            node = card.select_one(sel)
            if node and node.get_text(" ", strip=True):
                heading = node.get_text(" ", strip=True)
                break
        blob = re.sub(r"\s+", " ", card.get_text(" ", strip=True))
        blob = re.sub(r"\s*Read more\s*", " ", blob, flags=re.I).strip()
        sku_match = re.search(r"(AWE[-\s]?\d+)", blob, re.I)
        name = heading or (link.get_text(" ", strip=True) if link else "")
        name = re.split(r"\s*Art\s*#", name, maxsplit=1)[0].strip()
        if not name or name.lower() in {"read more", "view product"}:
            continue
        sku = sku_match.group(1).upper().replace(" ", "-") if sku_match else ""
        display = f"{name} ({sku})" if sku else name
        key = href.lower() or display.lower()
        if key in seen or len(display) < 3:
            continue
        seen.add(key)

        # ── Image extraction ──────────────────────────────────────────────
        image_url = ""
        img_tag = card.select_one("img")
        if img_tag:
            # Try srcset first (highest-res thumbnail), then src, then data-src (lazy)
            srcset = img_tag.get("srcset") or img_tag.get("data-srcset") or ""
            if srcset:
                # srcset format: "url1 300w, url2 600w" — take last (largest)
                candidates = [s.strip().split()[0] for s in srcset.split(",") if s.strip()]
                if candidates:
                    image_url = urljoin(page_url, candidates[-1])
            if not image_url:
                src = img_tag.get("src") or img_tag.get("data-src") or img_tag.get("data-lazy-src") or ""
                if src and not src.startswith("data:"):  # skip base64 placeholders
                    image_url = urljoin(page_url, src)

        price_node = card.select_one(".price")
        price = price_node.get_text(" ", strip=True)[:40] if price_node else ""

        products.append({
            "name": display[:90],
            "category": category,
            "description": blob[:180],
            "productUrl": href or page_url,
            "imageUrl": image_url,
            "price": price,
            "source_url": page_url,
        })
    return products


def _category_from_url(url: str) -> str:
    path = (urlparse(url).path or "").strip("/")
    parts = [p for p in path.split("/") if p and p != "product-category"]
    if not parts:
        return "Uncategorized"
    slug = parts[0].replace("-", " ").replace("and", "&")
    return slug.title()
