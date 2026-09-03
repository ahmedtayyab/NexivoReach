"""
Google Sheets integration for NexivoReach.

Uses a service-account credential (JSON) shared with a spreadsheet.
Two worksheets are managed automatically:
  • Products   — one row per product (keyed on name+category)
  • Prospects  — one row per prospect (keyed on website) + a Timeline tab

Environment variables (set in backend/.env):
  GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON  – the full service-account JSON (one line)
  GOOGLE_SHEETS_SPREADSHEET_ID        – the spreadsheet ID from the URL
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.tools.web_search import display_name_from_url, site_display_name_from_url, _registrable_domain

log = logging.getLogger(__name__)

# ── Column definitions ──────────────────────────────────────────────────────

PRODUCT_HEADERS = [
    "ID", "Name", "Category", "Description",
    "Price", "MOQ", "Product URL", "Image", "Source Page", "In Stock", "Last Updated",
]

LEAD_HEADERS = [
    "Seller Company", "Lead Name", "Website", "Phone", "Location",
    "Industry", "Source", "Status", "Next action", "Fit Score",
    "Why", "Discovered", "Last Updated",
]

TIMELINE_HEADERS = [
    "Prospect ID", "Company Name", "Event", "Detail", "Timestamp",
]


# ── Lazy client ─────────────────────────────────────────────────────────────

_client: Any = None  # gspread.Client or None


def _get_client():
    """Return a cached, authenticated gspread client (or None if not configured)."""
    global _client
    if _client is not None:
        return _client

    raw = (settings.GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON or "").strip()
    if not raw:
        return None

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        info = json.loads(raw)
        scopes = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        _client = gspread.authorize(creds)
        log.info("Google Sheets client authenticated (%s)", info.get("client_email"))
        return _client
    except Exception as exc:
        log.warning("Google Sheets auth failed: %s", exc)
        return None


def is_configured() -> bool:
    return bool(
        settings.GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON.strip()
        and settings.GOOGLE_SHEETS_SPREADSHEET_ID.strip()
    )


def connection_status() -> dict:
    if not is_configured():
        return {"connected": False, "reason": "not_configured"}
    client = _get_client()
    if client is None:
        return {"connected": False, "reason": "auth_failed"}
    try:
        sh = client.open_by_key(settings.GOOGLE_SHEETS_SPREADSHEET_ID.strip())
        return {"connected": True, "spreadsheet_title": sh.title, "url": f"https://docs.google.com/spreadsheets/d/{sh.id}"}
    except Exception as exc:
        return {"connected": False, "reason": str(exc)}


# ── Internal helpers ─────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _get_or_create_sheet(spreadsheet, title: str, headers: list[str]):
    """Return worksheet with given title, creating it if needed and ensuring headers."""
    try:
        ws = spreadsheet.worksheet(title)
    except Exception:
        ws = spreadsheet.add_worksheet(title=title, rows=1000, cols=len(headers))

    # Ensure header row
    existing = ws.row_values(1)
    if existing != headers:
        ws.clear()
        ws.append_row(headers, value_input_option="USER_ENTERED")
    return ws


def _find_row_by_key(ws, col_index: int, key: str) -> int | None:
    """Return 1-based row index where column col_index equals key, or None."""
    col_values = ws.col_values(col_index)
    for i, val in enumerate(col_values[1:], start=2):  # skip header
        if val == key:
            return i
    return None


def _sanitize_tab_label(name: str) -> str:
    for char in (":", "\\", "/", "?", "*", "[", "]"):
        name = name.replace(char, " ")
    return re.sub(r"\s+", " ", name).strip()[:30] or "Catalog"


def _collect_catalog_urls(business: Any | None, products: list[dict]) -> list[str]:
    urls: list[str] = []
    seen_domains: set[str] = set()
    if business is not None:
        website = (getattr(business, "website", None) or "").strip()
        if website:
            dom = _registrable_domain(website)
            if dom:
                seen_domains.add(dom)
                urls.append(website)
    for p in products:
        for key in ("sourceUrl", "source_url", "productUrl", "product_url"):
            raw = (p.get(key) or "").strip()
            if not raw:
                continue
            dom = _registrable_domain(raw)
            if dom and dom in seen_domains:
                break
            if dom:
                seen_domains.add(dom)
                urls.append(raw)
            break
    return urls


def resolve_company_tab_name(business: Any | None, products: list[dict]) -> str:
    """
    Tab label for the products sheet: company profile name, else website title/domain.
    """
    profile_name = ""
    if business is not None:
        profile_name = (getattr(business, "name", None) or "").strip()
    generic = {"", "my company", "company", "untitled", "business"}
    if profile_name and profile_name.lower() not in generic:
        return _sanitize_tab_label(profile_name)

    for url in _collect_catalog_urls(business, products):
        label = site_display_name_from_url(url)
        if label:
            return _sanitize_tab_label(label)

    for url in _collect_catalog_urls(business, products):
        label = display_name_from_url(url)
        if label:
            return _sanitize_tab_label(label)

    return "Catalog"


# ── Public API ───────────────────────────────────────────────────────────────

def sync_products(company_name: str, products: list[dict]) -> dict:
    """
    Write/update products to a per-company worksheet named '<Company> — Products'.
    Upserts on Name+Category key.
    Uses a single batch write — 2 API calls regardless of product count.
    Returns {"written": N, "url": "..."}
    """
    client = _get_client()
    if client is None:
        return {"written": 0, "error": "Sheets not configured"}

    sheet_id = settings.GOOGLE_SHEETS_SPREADSHEET_ID.strip()
    sh = client.open_by_key(sheet_id)
    tab_name = f"{_sanitize_tab_label(company_name)} - Products"
    ws = _get_or_create_sheet(sh, tab_name, PRODUCT_HEADERS)

    now = _now()

    # Build new rows from products (dedupe by name+category in memory)
    seen: dict[str, list] = {}
    for p in products:
        name = (p.get("name") or "").strip()
        category = (p.get("category") or "").strip()
        if not name:
            continue
        key = f"{name}|{category}"
        image_url = p.get("imageUrl") or p.get("image_url") or ""
        # Plain URL is more reliable than =IMAGE() for large catalogs (284+ rows).
        image_cell = image_url
        in_stock = p.get("inStock") if p.get("inStock") is not None else p.get("in_stock")
        in_stock_str = ("Yes" if in_stock else "No") if in_stock is not None else ""
        seen[key] = [
            p.get("id", ""),
            name,
            category,
            p.get("description", ""),
            p.get("price", "") or "",
            p.get("moq", "") or "",
            p.get("productUrl") or p.get("product_url") or "",
            image_cell,
            p.get("sourceUrl") or p.get("source_url") or "",
            in_stock_str,
            now,
        ]

    data_rows = list(seen.values())
    total_rows = len(data_rows) + 1  # + header

    if ws.row_count < total_rows + 10:
        ws.resize(rows=total_rows + 100, cols=len(PRODUCT_HEADERS))

    ws.clear()
    ws.update("A1", [PRODUCT_HEADERS], value_input_option="USER_ENTERED")

    # Chunk writes to stay under Google Sheets payload / rate limits on Render.
    chunk_size = 75
    written = 0
    for start in range(0, len(data_rows), chunk_size):
        chunk = data_rows[start : start + chunk_size]
        row_start = start + 2  # 1-based, skip header
        row_end = row_start + len(chunk) - 1
        cell_range = f"A{row_start}:K{row_end}"
        ws.update(cell_range, chunk, value_input_option="USER_ENTERED")
        written += len(chunk)

    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
    log.info("Synced %s products to sheet tab %s", written, tab_name)
    return {"written": written, "url": url, "tab": tab_name}


def sync_leads(seller_name: str, prospects: list[dict]) -> dict:
    """
    Upsert leads onto a per-seller tab: '<Seller> - Leads'.
    Separate from the product catalog tab. Includes seller company name on every row.
    Dedupes on Website, then Lead Name.
    """
    client = _get_client()
    if client is None:
        return {"written": 0, "error": "Sheets not configured"}

    sheet_id = settings.GOOGLE_SHEETS_SPREADSHEET_ID.strip()
    sh = client.open_by_key(sheet_id)
    seller = _sanitize_tab_label(seller_name or "Company")
    tab_name = f"{seller} - Leads"
    ws = _get_or_create_sheet(sh, tab_name, LEAD_HEADERS)
    now = _now()

    existing = ws.get_all_values()
    index_by_web: dict[str, int] = {}
    index_by_name: dict[str, int] = {}
    for idx, row in enumerate(existing[1:], start=2):
        web = (row[2] if len(row) > 2 else "").strip().lower()
        name = (row[1] if len(row) > 1 else "").strip().lower()
        if web:
            index_by_web[web] = idx
        if name:
            index_by_name[name] = idx

    updates: list[tuple[str, list]] = []
    appends: list[list] = []
    for p in prospects:
        name = (p.get("company_name") or p.get("companyName") or "").strip()
        website = (p.get("website") or "").strip()
        if not name:
            continue
        stage = p.get("stage") or "To contact"
        next_action = {
            "To contact": "First outreach",
            "Contacted": "Wait for reply / follow up",
            "Replied": "Human reply needed",
            "Re-contact": "Follow up this week",
            "Denied": "Do not pitch again",
            "Avoid": "Do not contact",
            "Meeting": "Prepare meeting",
            "Won": "Onboard",
        }.get(stage, "Review")
        row_data = [
            seller_name or seller,
            name,
            website,
            p.get("phone") or "",
            p.get("location") or "",
            p.get("industry") or "",
            p.get("source") or "web",
            stage,
            next_action,
            str(p.get("fit_score") or p.get("fitScore") or ""),
            (p.get("why_this_prospect") or p.get("whyThisProspect") or "")[:300],
            p.get("discovered_at") or p.get("discoveredAt") or "",
            now,
        ]
        match = index_by_web.get(website.lower()) if website else None
        if not match:
            match = index_by_name.get(name.lower())
        if match:
            updates.append((f"A{match}:M{match}", row_data))
        else:
            appends.append(row_data)

    for cell_range, row_data in updates:
        ws.update(cell_range, [row_data], value_input_option="USER_ENTERED")
    if appends:
        needed = ws.row_count + len(appends)
        if ws.row_count < needed + 10:
            ws.resize(rows=needed + 50, cols=len(LEAD_HEADERS))
        for start in range(0, len(appends), 75):
            chunk = appends[start : start + 75]
            ws.append_rows(chunk, value_input_option="USER_ENTERED")

    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
    written = len(updates) + len(appends)
    log.info("Synced %s leads to %s", written, tab_name)
    return {"written": written, "url": url, "tab": tab_name}


def sync_prospect(prospect: dict) -> dict:
    """Single-lead wrapper — writes to that seller's Leads tab."""
    seller = prospect.get("seller_name") or prospect.get("sellerName") or "Company"
    return sync_leads(seller, [prospect])
