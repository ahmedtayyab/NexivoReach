"""Admin-tunable app settings stored in the database (with env defaults)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from sqlmodel import Session, select

from app.config import settings
from app.database.session import engine
from app.models.schemas import AppSetting

KEY_LEADS_PER_RUN = "hunt.leads_per_run"
KEY_MAX_PAGES_PER_INTENT = "hunt.max_pages_per_intent"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_setting(key: str, default: str = "") -> str:
    try:
        with Session(engine) as session:
            row = session.get(AppSetting, key)
            if row and (row.value or "").strip() != "":
                return row.value.strip()
    except Exception:
        # Table may not exist yet before init_db / create_all
        pass
    return default


def set_setting(key: str, value: str) -> None:
    try:
        with Session(engine) as session:
            row = session.get(AppSetting, key)
            if not row:
                row = AppSetting(key=key, value=str(value), updated_at=_now())
            else:
                row.value = str(value)
                row.updated_at = _now()
            session.add(row)
            session.commit()
    except Exception:
        pass


def _int_setting(key: str, default: int, *, lo: int, hi: int) -> int:
    raw = get_setting(key, str(default))
    try:
        n = int(str(raw).strip())
    except (TypeError, ValueError):
        n = default
    return max(lo, min(hi, n))


def hunt_leads_per_run() -> int:
    return _int_setting(
        KEY_LEADS_PER_RUN,
        int(settings.HUNT_LEADS_PER_RUN or 40),
        lo=5,
        hi=200,
    )


def hunt_max_pages_per_intent() -> int:
    return _int_setting(
        KEY_MAX_PAGES_PER_INTENT,
        int(settings.HUNT_MAX_PAGES_PER_INTENT or 10),
        lo=1,
        hi=50,
    )


def get_hunt_settings() -> Dict[str, Any]:
    leads = hunt_leads_per_run()
    pages = hunt_max_pages_per_intent()
    return {
        "leadsPerRun": leads,
        "maxPagesPerIntent": pages,
        "defaults": {
            "leadsPerRun": int(settings.HUNT_LEADS_PER_RUN or 40),
            "maxPagesPerIntent": int(settings.HUNT_MAX_PAGES_PER_INTENT or 10),
        },
    }


def update_hunt_settings(
    *,
    leads_per_run: int | None = None,
    max_pages_per_intent: int | None = None,
) -> Dict[str, Any]:
    if leads_per_run is not None:
        set_setting(KEY_LEADS_PER_RUN, str(max(5, min(200, int(leads_per_run)))))
    if max_pages_per_intent is not None:
        set_setting(KEY_MAX_PAGES_PER_INTENT, str(max(1, min(50, int(max_pages_per_intent)))))
    return get_hunt_settings()


def leads_per_intent_share(leads_per_run: int, intent_count: int) -> int:
    """Split the run cap evenly across hunt lines (ceil, at least 1)."""
    n = max(1, int(intent_count or 1))
    cap = max(1, int(leads_per_run or 1))
    return max(1, (cap + n - 1) // n)
