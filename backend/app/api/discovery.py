from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from uuid import uuid4
from datetime import datetime, timezone
from sqlmodel import Session, select
from app.models.schemas import ProspectRecord, AgentRunRecord, Business, User, DiscoveryJob
from app.database.session import engine
from app.api.deps import AuthUser, get_current_user, resolve_business_id
from app.api.serializers import prospect_to_frontend, run_to_frontend
from app.integrations import sheets as sheets_mod
from app.services import enrichment as enrich_mod
from urllib.parse import urlparse
import asyncio
import logging

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/discovery", tags=["discovery"])


class DiscoveryRunRequest(BaseModel):
    user_prompt: str = ""
    products: List[Dict[str, Any]] = []
    icp: Dict[str, Any] = {}
    business: Dict[str, Any] = {}
    # When true (default), return jobId immediately and run in background.
    async_mode: bool = True


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _domain(url: str) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _job_to_dict(job: DiscoveryJob, prospects: list | None = None) -> dict:
    return {
        "jobId": job.id,
        "status": job.status,
        "phase": job.phase,
        "progress": job.progress,
        "foundCount": job.found_count,
        "skippedExisting": job.skipped_existing,
        "error": job.error or None,
        "userPrompt": job.user_prompt,
        "createdAt": job.created_at,
        "updatedAt": job.updated_at,
        "completedAt": job.completed_at,
        "prospects": prospects if prospects is not None else [],
        "agentLogId": job.agent_log_id,
        "telemetry": job.telemetry or {},
    }


def _update_job(job_id: str, **fields: Any) -> None:
    with Session(engine) as session:
        job = session.get(DiscoveryJob, job_id)
        if not job:
            return
        for k, v in fields.items():
            setattr(job, k, v)
        job.updated_at = _now()
        session.add(job)
        session.commit()


def _sync_leads_job(business_id: str, prospects: list[dict]) -> None:
    try:
        with Session(engine) as session:
            biz = session.get(Business, business_id)
            sheet_id = sheets_mod.business_spreadsheet_id(biz)
            if not sheet_id:
                return
            owner = sheets_mod.owner_user(session, biz)
            if not sheets_mod.is_configured(owner):
                return
            from app.models.schemas import ProductItem

            product_rows = session.exec(
                select(ProductItem).where(ProductItem.business_id == business_id)
            ).all()
            products = [
                {"sourceUrl": r.source_url, "productUrl": r.product_url}
                for r in product_rows
                if r.source_url or r.product_url
            ]
            seller = sheets_mod.resolve_company_tab_name(biz, products, fallback="Company")
            sheets_mod.sync_leads(
                seller, prospects, spreadsheet_id=sheet_id, session=session, user=owner
            )
    except Exception as exc:
        log.warning("Sheets lead sync failed: %s", exc)


async def _auto_fill_contacts_job(prospect_ids: List[str]) -> None:
    if not prospect_ids:
        return
    sem = asyncio.Semaphore(5)

    async def one(pid: str) -> None:
        async with sem:
            try:
                with Session(engine) as session:
                    row = session.get(ProspectRecord, pid)
                    if not row or not (row.website or "").strip():
                        return
                    if (row.email or "").strip():
                        return
                    website = row.website
                    seed_email = row.email or ""
                    seed_phone = row.phone or ""
                    seed_contacts = list(row.contacts or [])
                found = await enrich_mod.enrich_website(
                    website,
                    seed_email=seed_email,
                    seed_phone=seed_phone,
                    seed_contacts=seed_contacts,
                    use_hunter=True,
                )
                if not found.get("found") and not found.get("phone"):
                    return
                with Session(engine) as session:
                    row = session.get(ProspectRecord, pid)
                    if not row:
                        return
                    if found.get("email"):
                        row.email = found["email"]
                    if found.get("phone"):
                        row.phone = found["phone"]
                    if found.get("contacts"):
                        row.contacts = found["contacts"]
                    timeline = list(row.agent_timeline or [])
                    src = ",".join(found.get("sources") or ["site"])
                    timeline.append(
                        {
                            "time": _now()[11:16],
                            "action": f"Auto-filled contacts ({src})",
                        }
                    )
                    row.agent_timeline = timeline
                    if row.outreach_draft and isinstance(row.outreach_draft, dict) and found.get("email"):
                        draft = dict(row.outreach_draft)
                        if not (draft.get("toEmail") or "").strip():
                            draft["toEmail"] = found["email"]
                            row.outreach_draft = draft
                    session.add(row)
                    session.commit()
            except Exception as exc:
                log.warning("Auto-fill contacts failed for %s: %s", pid, exc)

    await asyncio.gather(*[one(pid) for pid in prospect_ids])


async def _execute_discovery_job(job_id: str, user_id: str, business_id: str, req: DiscoveryRunRequest) -> None:
    _update_job(job_id, status="running", phase="Planning search intents…", progress=4)
    try:
        with Session(engine) as session:
            biz = session.get(Business, business_id)
            business_payload = req.business or {}
            if biz:
                business_payload = {
                    "name": biz.name,
                    "website": biz.website,
                    "description": biz.description,
                    "primaryCategories": biz.primary_categories or [],
                    "targetMarkets": biz.target_markets or [],
                    **business_payload,
                }

        from app.services.paginated_discovery import run_paginated_discovery

        res = await run_paginated_discovery(
            job_id=job_id,
            user_id=user_id,
            business_id=business_id,
            user_prompt=req.user_prompt,
            products=req.products or [],
            icp=req.icp or {},
            business=business_payload,
        )

        saved_front = list(res.get("prospects") or [])
        saved_ids = [p.get("id") for p in saved_front if p.get("id")]
        telemetry = res.get("telemetry") or {}

        # Finish leftover emails while the job is still alive
        missing_ids = [
            p.get("id")
            for p in saved_front
            if p.get("id") and p.get("website") and not (p.get("email") or "").strip()
        ]
        if missing_ids:
            _update_job(
                job_id,
                status="running",
                phase=f"Finding emails for {len(missing_ids)} leads…",
                progress=96,
                found_count=len(saved_front),
                result_prospect_ids=saved_ids,
                telemetry=telemetry,
            )
            try:
                await asyncio.wait_for(
                    _auto_fill_contacts_job(missing_ids[:120]),
                    timeout=150.0,
                )
            except asyncio.TimeoutError:
                log.warning("Contact enrich timed out for job %s", job_id)
            with Session(engine) as session:
                refreshed: List[Dict[str, Any]] = []
                for pid in saved_ids:
                    row = session.get(ProspectRecord, pid)
                    if row:
                        refreshed.append(prospect_to_frontend(row))
                if refreshed:
                    saved_front = refreshed

        # Ensure job marked complete (paginated runner usually already did)
        with Session(engine) as session:
            job = session.get(DiscoveryJob, job_id)
            if job and job.status != "completed":
                job.status = "completed"
                job.phase = job.phase or "Done"
                job.progress = 100
                job.found_count = len(saved_front)
                job.result_prospect_ids = saved_ids
                job.completed_at = _now()
                job.updated_at = _now()
                session.add(job)
                session.commit()
            elif job:
                job.found_count = max(job.found_count, len(saved_front))
                job.result_prospect_ids = saved_ids or job.result_prospect_ids
                session.add(job)
                session.commit()

        if saved_front:
            _sync_leads_job(business_id, saved_front)
    except Exception as exc:
        log.exception("Discovery job %s failed", job_id)
        _update_job(
            job_id,
            status="failed",
            phase="Failed",
            progress=100,
            error=str(exc)[:500],
            completed_at=_now(),
        )


@router.get("/limits")
def discovery_limits(user: AuthUser = Depends(get_current_user)):
    """Public (authenticated) hunt caps — shown in Find buyers UI."""
    from app.services import app_settings as app_set

    return app_set.get_hunt_settings()


@router.get("/runs")
def list_runs(request: Request, user: AuthUser = Depends(get_current_user)):
    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        rows = session.exec(
            select(AgentRunRecord)
            .where(AgentRunRecord.business_id == business_id)
            .order_by(AgentRunRecord.timestamp.desc())
        ).all()
        return [run_to_frontend(r) for r in rows]


@router.get("/jobs")
def list_discovery_jobs(
    request: Request,
    user: AuthUser = Depends(get_current_user),
    limit: int = 12,
):
    """Recent hunts for this workspace — used for re-run presets."""
    cap = max(1, min(int(limit or 12), 30))
    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        rows = session.exec(
            select(DiscoveryJob)
            .where(DiscoveryJob.business_id == business_id)
            .order_by(DiscoveryJob.created_at.desc())
            .limit(cap)
        ).all()
        out = []
        for job in rows:
            item = _job_to_dict(job)
            payload = job.request_payload or {}
            item["requestPayload"] = {
                "user_prompt": payload.get("user_prompt") or job.user_prompt or "",
            }
            out.append(item)
        return out


@router.get("/jobs/{job_id}")
def get_discovery_job(job_id: str, request: Request, user: AuthUser = Depends(get_current_user)):
    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        job = session.get(DiscoveryJob, job_id)
        if not job or job.business_id != business_id:
            raise HTTPException(status_code=404, detail="Hunt job not found")
        prospects = []
        agent_log = None
        if job.status == "completed" and job.result_prospect_ids:
            for pid in job.result_prospect_ids:
                row = session.get(ProspectRecord, pid)
                if row:
                    prospects.append(prospect_to_frontend(row))
        if job.agent_log_id:
            ar = session.get(AgentRunRecord, job.agent_log_id)
            if ar:
                agent_log = run_to_frontend(ar)
        payload = _job_to_dict(job, prospects)
        payload["agent_log"] = agent_log
        return payload


@router.post("/run")
async def run_discovery_agent(
    req: DiscoveryRunRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user: AuthUser = Depends(get_current_user),
):
    with Session(engine) as session:
        db_user = session.get(User, user.id)
        if not db_user and user.id == "local":
            from app.api.deps import ensure_default_business

            ensure_default_business(session, user)
            db_user = session.get(User, user.id)
        if db_user:
            from app.services import access as access_mod

            access_mod.consume_usage(session, db_user, "hunt")
        business_id = resolve_business_id(request, user, session)

        job_id = f"job-{uuid4().hex[:12]}"
        job = DiscoveryJob(
            id=job_id,
            user_id=user.id,
            business_id=business_id,
            status="queued",
            phase="Queued",
            progress=2,
            user_prompt=(req.user_prompt or "").strip(),
            request_payload={
                "user_prompt": req.user_prompt,
                "products": req.products,
                "icp": req.icp,
                "business": req.business,
            },
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(job)
        session.commit()

    if req.async_mode:
        # create_task keeps the hunt alive independently of the HTTP response lifecycle
        asyncio.create_task(_execute_discovery_job(job_id, user.id, business_id, req))
        return {
            "jobId": job_id,
            "status": "queued",
            "phase": "Queued",
            "progress": 2,
            "async": True,
        }

    await _execute_discovery_job(job_id, user.id, business_id, req)
    with Session(engine) as session:
        job = session.get(DiscoveryJob, job_id)
        if not job:
            raise HTTPException(status_code=500, detail="Job missing after run")
        prospects = []
        if job.result_prospect_ids:
            for pid in job.result_prospect_ids:
                row = session.get(ProspectRecord, pid)
                if row:
                    prospects.append(prospect_to_frontend(row))
        agent_log = None
        if job.agent_log_id:
            ar = session.get(AgentRunRecord, job.agent_log_id)
            if ar:
                agent_log = run_to_frontend(ar)
        return {
            "jobId": job_id,
            "async": False,
            "prospects": prospects,
            "foundCount": job.found_count,
            "skippedExisting": job.skipped_existing,
            "agent_log": agent_log,
            "prospect": prospects[0] if prospects else None,
            "status": job.status,
            "error": job.error or None,
        }
