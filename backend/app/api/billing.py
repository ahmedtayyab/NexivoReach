"""Stripe Checkout / Customer Portal / webhooks → User.plan."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import AuthUser, get_current_user
from app.config import effective_app_url, settings
from app.database.session import engine
from app.models.schemas import User

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/billing", tags=["billing"])


def _stripe():
    if not (settings.STRIPE_SECRET_KEY or "").strip():
        return None
    try:
        import stripe
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Stripe package not installed") from exc
    stripe.api_key = settings.STRIPE_SECRET_KEY.strip()
    return stripe


def _price_map() -> dict[str, str]:
    return {
        (settings.STRIPE_PRICE_PRO or "").strip(): "pro",
        (settings.STRIPE_PRICE_GROWTH or "").strip(): "growth",
    }


def billing_configured() -> bool:
    return bool(
        (settings.STRIPE_SECRET_KEY or "").strip()
        and ((settings.STRIPE_PRICE_PRO or "").strip() or (settings.STRIPE_PRICE_GROWTH or "").strip())
    )


@router.get("/status")
def billing_status(user: AuthUser = Depends(get_current_user)):
    with Session(engine) as session:
        row = session.get(User, user.id)
        return {
            "configured": billing_configured(),
            "plan": (row.plan if row else None) or "pilot",
            "planStatus": (row.plan_status if row else None) or "none",
            "hasCustomer": bool(row and row.stripe_customer_id),
            "prices": {
                "pro": bool((settings.STRIPE_PRICE_PRO or "").strip()),
                "growth": bool((settings.STRIPE_PRICE_GROWTH or "").strip()),
            },
        }


class CheckoutBody(BaseModel):
    plan: str  # pro | growth


@router.post("/checkout")
def create_checkout(body: CheckoutBody, user: AuthUser = Depends(get_current_user)):
    stripe = _stripe()
    if not stripe or not billing_configured():
        raise HTTPException(
            status_code=503,
            detail="Self-serve billing is not configured yet. Open Support and ask for a plan upgrade.",
        )
    plan = (body.plan or "").strip().lower()
    price = {
        "pro": (settings.STRIPE_PRICE_PRO or "").strip(),
        "growth": (settings.STRIPE_PRICE_GROWTH or "").strip(),
    }.get(plan, "")
    if not price:
        raise HTTPException(status_code=400, detail="Unknown plan — choose pro or growth")

    with Session(engine) as session:
        row = session.get(User, user.id)
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        customer_id = row.stripe_customer_id
        if not customer_id:
            customer = stripe.Customer.create(email=row.email, name=row.name or row.email, metadata={"userId": row.id})
            customer_id = customer["id"]
            row.stripe_customer_id = customer_id
            session.add(row)
            session.commit()

    app_url = effective_app_url()
    session_obj = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price, "quantity": 1}],
        success_url=f"{app_url}/#integrations?billing=success",
        cancel_url=f"{app_url}/#integrations?billing=cancel",
        metadata={"userId": user.id, "plan": plan},
        allow_promotion_codes=True,
    )
    return {"url": session_obj["url"], "sessionId": session_obj["id"]}


@router.post("/portal")
def create_portal(user: AuthUser = Depends(get_current_user)):
    stripe = _stripe()
    if not stripe or not (settings.STRIPE_SECRET_KEY or "").strip():
        raise HTTPException(status_code=503, detail="Billing portal is not configured")
    with Session(engine) as session:
        row = session.get(User, user.id)
        if not row or not row.stripe_customer_id:
            raise HTTPException(status_code=400, detail="No billing customer yet — upgrade first")
        portal = stripe.billing_portal.Session.create(
            customer=row.stripe_customer_id,
            return_url=f"{effective_app_url()}/#integrations",
        )
        return {"url": portal["url"]}


def _apply_plan(session: Session, user_id: str, plan: str, status: str, sub_id: str | None = None) -> None:
    row = session.get(User, user_id)
    if not row:
        return
    if plan in ("free", "pilot", "pro", "growth"):
        row.plan = plan
    row.plan_status = status
    if sub_id:
        row.stripe_subscription_id = sub_id
    session.add(row)
    session.commit()


@router.post("/webhook")
async def stripe_webhook(request: Request):
    stripe = _stripe()
    if not stripe:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    secret = (settings.STRIPE_WEBHOOK_SECRET or "").strip()
    try:
        if secret:
            event = stripe.Webhook.construct_event(payload, sig, secret)
        else:
            # Dev fallback — do not use in production without webhook secret.
            import json

            event = json.loads(payload)
    except Exception as exc:
        log.warning("Stripe webhook verify failed: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid webhook") from exc

    etype = event.get("type") if isinstance(event, dict) else event["type"]
    data = event.get("data", {}).get("object", {}) if isinstance(event, dict) else event["data"]["object"]

    with Session(engine) as session:
        if etype == "checkout.session.completed":
            user_id = (data.get("metadata") or {}).get("userId") or ""
            plan = (data.get("metadata") or {}).get("plan") or "pro"
            sub_id = data.get("subscription")
            customer = data.get("customer")
            if user_id:
                row = session.get(User, user_id)
                if row and customer:
                    row.stripe_customer_id = customer
                    session.add(row)
                _apply_plan(session, user_id, plan, "active", sub_id)
        elif etype in ("customer.subscription.updated", "customer.subscription.deleted"):
            sub_id = data.get("id")
            status_raw = data.get("status") or ""
            price_id = ""
            try:
                items = (data.get("items") or {}).get("data") or []
                if items:
                    price_id = ((items[0].get("price") or {}).get("id")) or ""
            except Exception:
                price_id = ""
            plan = _price_map().get(price_id, "")
            row = session.exec(select(User).where(User.stripe_subscription_id == sub_id)).first()
            if not row and data.get("customer"):
                row = session.exec(select(User).where(User.stripe_customer_id == data.get("customer"))).first()
            if row:
                mapped_status = "canceled" if etype.endswith("deleted") or status_raw in ("canceled", "unpaid") else "active"
                if status_raw == "past_due":
                    mapped_status = "past_due"
                next_plan = plan or (row.plan if mapped_status == "active" else "pilot")
                if mapped_status == "canceled":
                    next_plan = "pilot"
                _apply_plan(session, row.id or "", next_plan, mapped_status, sub_id)

    return {"ok": True}
