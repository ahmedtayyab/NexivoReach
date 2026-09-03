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
from datetime import datetime, timezone
from typing import Any

from app.config import settings

log = logging.getLogger(__name__)

# ── Column definitions ──────────────────────────────────────────────────────

PRODUCT_HEADERS = [
    "ID", "Name", "Category", "Description",
    "Price", "MOQ", "Product URL", "Image", "Source Page", "In Stock", "Last Updated",
]

PROSPECT_HEADERS = [
    "ID", "Company Name", "Website", "Location", "Industry",
    "Company Size", "Fit Score", "Why This Prospect",
    "Recommended Approach", "Stage", "Discovered At", "Last Updated",
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
    tab_name = f"{company_name[:30]} - Products"
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
        image_cell = f'=IMAGE("{image_url}")' if image_url else ""
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

    # Fully replace the sheet content (clear + write header + all rows in one batch)
    # This is the fastest approach and avoids row-by-row API limits entirely.
    all_rows = [PRODUCT_HEADERS] + list(seen.values())

    # Resize sheet if needed
    if ws.row_count < len(all_rows) + 10:
        ws.resize(rows=len(all_rows) + 100)

    ws.clear()
    ws.update("A1", all_rows, value_input_option="USER_ENTERED")

    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
    return {"written": len(seen), "url": url, "tab": tab_name}


def sync_prospect(prospect: dict) -> dict:
    """
    Write/update a prospect row and append a timeline event.
    Returns {"written": True/False, "url": "..."}
    """
    client = _get_client()
    if client is None:
        return {"written": False, "error": "Sheets not configured"}

    sheet_id = settings.GOOGLE_SHEETS_SPREADSHEET_ID.strip()
    sh = client.open_by_key(sheet_id)

    # Prospects sheet
    ws = _get_or_create_sheet(sh, "Prospects", PROSPECT_HEADERS)
    row_data = [
        prospect.get("id", ""),
        prospect.get("company_name") or prospect.get("companyName", ""),
        prospect.get("website", ""),
        prospect.get("location", ""),
        prospect.get("industry", ""),
        prospect.get("company_size") or prospect.get("companySize", ""),
        str(prospect.get("fit_score") or prospect.get("fitScore", "")),
        prospect.get("why_this_prospect") or prospect.get("whyThisProspect", ""),
        prospect.get("recommended_approach") or prospect.get("recommendedApproach", ""),
        prospect.get("stage", "Qualified"),
        prospect.get("discovered_at") or prospect.get("discoveredAt", ""),
        _now(),
    ]
    website_key = prospect.get("website", "")
    row_idx = _find_row_by_key(ws, 3, website_key)  # col 3 = Website
    if row_idx:
        ws.update(f"A{row_idx}:L{row_idx}", [row_data], value_input_option="USER_ENTERED")
    else:
        ws.append_row(row_data, value_input_option="USER_ENTERED")

    # Timeline sheet
    tl = _get_or_create_sheet(sh, "Timeline", TIMELINE_HEADERS)
    company = prospect.get("company_name") or prospect.get("companyName", "")
    stage = prospect.get("stage", "Qualified")
    tl.append_row([
        prospect.get("id", ""),
        company,
        f"Stage → {stage}",
        prospect.get("recommended_approach") or prospect.get("recommendedApproach", ""),
        _now(),
    ], value_input_option="USER_ENTERED")

    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
    return {"written": True, "url": url}
