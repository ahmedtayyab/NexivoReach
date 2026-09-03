import asyncio
import re
from typing import List, Dict, Any
from urllib.parse import urlparse

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
        if not url or _should_skip(url):
            return []
        pages: List[tuple[str, str]] = []
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=HEADERS) as client:
                first = await client.get(url)
                if first.status_code != 200 or not first.text:
                    return []
                html = first.text
                pages.append((str(first.url), _html_to_text(html)))
                extra_urls = _catalog_links(html, str(first.url))[:4]
                for extra in extra_urls:
                    try:
                        res = await client.get(extra)
                        if res.status_code == 200 and res.text:
                            pages.append((str(res.url), _html_to_text(res.text)))
                    except Exception:
                        continue
        except Exception:
            return pages
        return pages


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "form"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())[:8000]


def _catalog_links(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    found: List[str] = []
    seen = set()
    keywords = ("product", "catalog", "category", "shop", "collection", "glove", "fitness", "sport")
    for anchor in soup.find_all("a", href=True):
        href = (anchor.get("href") or "").strip()
        label = anchor.get_text(" ", strip=True).lower()
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        absolute = httpx.URL(base_url).join(href).human_repr()
        host = _registrable_domain(absolute)
        if host != _registrable_domain(base_url) or absolute in seen:
            continue
        path = (urlparse(absolute).path or "").lower()
        if any(key in path or key in label for key in keywords):
            seen.add(absolute)
            found.append(absolute)
    return found
