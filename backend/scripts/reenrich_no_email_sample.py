"""Re-enrich a sample of prospects that currently have no email."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from sqlmodel import Session, select

from app.database.session import engine
from app.models.schemas import ProspectRecord
from app.services.enrichment import enrich_website


async def main() -> None:
    with Session(engine) as session:
        rows = session.exec(select(ProspectRecord).order_by(ProspectRecord.discovered_at.desc())).all()

    no_email = [
        r for r in rows
        if r.website and not (r.email or "").strip()
    ][:20]

    print(f"selected={len(no_email)} of {len(rows)} prospects without email")
    results = []
    for i, r in enumerate(no_email, 1):
        domain = (r.website or "").replace("https://", "").replace("http://", "").split("/")[0]
        t0 = time.perf_counter()
        try:
            found = await asyncio.wait_for(
                enrich_website(r.website, use_hunter=False, use_browser=False),
                timeout=35.0,
            )
        except Exception as exc:
            found = {
                "email": "",
                "emailStatus": "error",
                "emailSource": "",
                "telemetry": {"error": str(exc)[:120]},
            }
        dt = round(time.perf_counter() - t0, 2)
        row = {
            "domain": domain,
            "old_email_status": "not_found",
            "new_email_status": found.get("emailStatus") or ("found" if found.get("email") else "not_found"),
            "email": found.get("email") or "",
            "source": found.get("emailSource") or "",
            "sourceUrl": found.get("emailSourceUrl") or "",
            "pages_checked": found.get("pagesChecked") or (found.get("telemetry") or {}).get("pagesChecked"),
            "social_checked": (found.get("telemetry") or {}).get("socialLinksFound") or [],
            "facebook_checked": (found.get("telemetry") or {}).get("facebookChecked"),
            "homepage_rendered": (found.get("telemetry") or {}).get("homepageRendered"),
            "hunter_checked": False,
            "time_sec": dt,
        }
        results.append(row)
        print(f"[{i:02d}/{len(no_email)}] {domain}: {row['new_email_status']} {row['email']} ({row['source']}) {dt}s")

    found_n = sum(1 for r in results if r["email"])
    out = Path(__file__).resolve().parent / "contact_reenrich_sample.json"
    out.write_text(json.dumps({"found": found_n, "total": len(results), "rows": results}, indent=2), encoding="utf-8")
    print(f"\nSUMMARY recovered={found_n}/{len(results)} -> {out}")


if __name__ == "__main__":
    asyncio.run(main())
