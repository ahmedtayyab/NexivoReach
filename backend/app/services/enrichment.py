"""Contact enrichment: site scrape first, optional Hunter.io when configured."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.tools.contact_finder import discover_contacts
from app.tools.web_search import WebSearchTool

log = logging.getLogger(__name__)


def _domain(url: str) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


async def hunter_domain_search(domain: str) -> dict[str, Any]:
    """Return {email, contacts[]} from Hunter domain search, or empty."""
    key = (settings.HUNTER_API_KEY or "").strip()
    if not key or not domain:
        return {"email": "", "contacts": [], "provider": "hunter", "skipped": True}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://api.hunter.io/v2/domain-search",
                params={"domain": domain, "api_key": key, "limit": 5},
            )
            if resp.status_code >= 400:
                log.warning("Hunter domain-search %s: %s", resp.status_code, resp.text[:200])
                return {"email": "", "contacts": [], "provider": "hunter", "error": resp.status_code}
            data = resp.json().get("data") or {}
            emails = data.get("emails") or []
            contacts: list[dict] = []
            best = ""
            for row in emails:
                val = (row.get("value") or "").strip()
                if not val or "@" not in val:
                    continue
                if not best:
                    best = val
                contacts.append(
                    {
                        "type": "email",
                        "value": val,
                        "label": (row.get("type") or "Email").title(),
                        "source": "hunter",
                        "sourceUrl": f"hunter://domain/{domain}",
                        "evidence": "Hunter.io domain search",
                        "role": row.get("position") or row.get("type") or "general",
                    }
                )
            return {"email": best, "contacts": contacts, "provider": "hunter"}
    except Exception as exc:
        log.warning("Hunter enrich failed: %s", exc)
        return {"email": "", "contacts": [], "provider": "hunter", "error": str(exc)}


async def enrich_website(
    website: str,
    *,
    seed_email: str = "",
    seed_phone: str = "",
    seed_contacts: list | None = None,
    use_hunter: bool = True,
    use_browser: bool = True,
) -> dict[str, Any]:
    """
    Enrich a company website for public contact emails/phones.

    Pipeline: static site crawl → optional browser render → social → Hunter.
    Returns email + provenance (emailSource, emailEvidence, telemetry).
    """
    website = (website or "").strip()
    sources: list[str] = []
    email = (seed_email or "").strip()
    phone = (seed_phone or "").strip()
    contacts = list(seed_contacts or [])
    site_text = ""
    location = ""
    email_source = ""
    email_source_url = ""
    email_evidence = ""
    email_status = "not_found"
    telemetry: dict[str, Any] = {}

    if not website:
        return {
            "email": email,
            "phone": phone,
            "contacts": contacts,
            "sources": sources,
            "found": bool(email),
            "site_text": "",
            "location": "",
            "emailSource": "",
            "emailSourceUrl": "",
            "emailEvidence": "",
            "emailStatus": "website_unreachable",
            "telemetry": telemetry,
        }

    tool = WebSearchTool()
    page: dict = {}
    try:
        page = await tool.scrape_homepage(website, limit=8000, keep_html=True)
    except Exception as exc:
        log.warning("Enrich homepage scrape failed: %s", exc)

    if isinstance(page, dict):
        site_text = page.get("text") or ""
        location = page.get("location") or ""
        if page.get("emails") and not email:
            email = (page.get("emails") or [""])[0] or email

    found = await discover_contacts(
        website=website,
        homepage_html=(page.get("html") or "")[:400000] if isinstance(page, dict) else "",
        homepage_text=site_text,
        homepage_url=(page.get("url") if isinstance(page, dict) else None) or website,
        seed_phone=phone,
        seed_emails=list((page.get("emails") or []) if isinstance(page, dict) else []),
        use_browser=use_browser,
    )
    telemetry = dict(found.get("telemetry") or {})
    email_status = found.get("emailStatus") or "not_found"
    if found.get("email"):
        email = found["email"]
        email_source = found.get("emailSource") or "homepage"
        email_source_url = found.get("emailSourceUrl") or website
        email_evidence = found.get("emailEvidence") or email
        sources.append(email_source or "site")
        email_status = "found"
    if found.get("phone"):
        phone = found["phone"] or phone
    for c in found.get("contacts") or []:
        if isinstance(c, dict):
            contacts.append(c)

    if use_hunter and not email:
        telemetry["hunterChecked"] = True
        hunter = await hunter_domain_search(_domain(website))
        if hunter.get("skipped"):
            telemetry["hunterChecked"] = False
        elif hunter.get("email"):
            email = hunter["email"]
            email_source = "hunter"
            email_source_url = f"hunter://domain/{_domain(website)}"
            email_evidence = "Hunter.io domain search"
            sources.append("hunter")
            contacts = list(hunter.get("contacts") or []) + contacts
            email_status = "found"
        else:
            email_status = "hunter_no_match" if not hunter.get("skipped") else (
                found.get("emailStatus") or "not_found"
            )

    # Dedupe contacts by type+value
    seen: set[str] = set()
    deduped: list[dict] = []
    for c in contacts:
        if not isinstance(c, dict):
            continue
        key = f"{(c.get('type') or '').lower()}:{(c.get('value') or '').strip().lower()}"
        if not c.get("value") or key in seen:
            continue
        seen.add(key)
        deduped.append(c)

    if email and not any(
        isinstance(c, dict) and c.get("type") == "email" and (c.get("value") or "").lower() == email.lower()
        for c in deduped
    ):
        deduped.insert(
            0,
            {
                "type": "email",
                "value": email,
                "label": "Email",
                "source": email_source or (sources[-1] if sources else "site"),
                "sourceUrl": email_source_url,
                "evidence": email_evidence,
                "role": "general",
            },
        )

    return {
        "email": email,
        "phone": phone,
        "contacts": deduped,
        "sources": sources,
        "found": bool(email),
        "hunterConfigured": bool((settings.HUNTER_API_KEY or "").strip()),
        "site_text": site_text,
        "location": location,
        "emailSource": email_source,
        "emailSourceUrl": email_source_url,
        "emailEvidence": email_evidence,
        "emailStatus": email_status if email else (email_status or "not_found"),
        "telemetry": telemetry,
        "pagesChecked": found.get("pagesChecked") or telemetry.get("pagesChecked") or 0,
    }
