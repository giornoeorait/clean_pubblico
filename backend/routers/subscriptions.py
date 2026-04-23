"""Stripe Subscriptions: checkout, customer portal, webhook, status polling.

Uses emergentintegrations.payments.stripe.checkout with STRIPE_API_KEY env var.
Since we use Checkout sessions (one-off or subscription), we store transaction
records in `payment_transactions` collection (mandatory per playbook).

Flow:
1. Frontend -> POST /api/subscriptions/checkout with {plan_id, billing_cycle}
2. Backend computes amount server-side, creates Stripe Checkout session
3. Frontend redirects to Stripe
4. Stripe redirects back to /billing?session_id={CHECKOUT_SESSION_ID}
5. Frontend polls /api/subscriptions/status/{session_id}
6. On success, tenant.stato is set to 'active' and limits are applied

Note: Since emergentintegrations Stripe Checkout doesn't natively handle
recurring subscriptions (it's mostly one-off), we model subscriptions as
"monthly renewable payments" and use webhook to sync status. Customer Portal
is skipped (requires Stripe full SDK) — we offer manual upgrade/renewal instead.
"""
import os
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core import (
    db, new_id, now_utc, get_current_user, log_audit, PLANS,
)

logger = logging.getLogger("cleantec.subscriptions")
router = APIRouter(tags=["subscriptions"])

STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")


def _stripe():
    """Lazy import to avoid hard-fail at module import when lib is missing."""
    if not STRIPE_API_KEY:
        raise HTTPException(503, "Stripe non configurato (manca STRIPE_API_KEY)")
    try:
        from emergentintegrations.payments.stripe.checkout import StripeCheckout
        return StripeCheckout
    except Exception as e:
        logger.error(f"Stripe import failed: {e}")
        raise HTTPException(503, "Integrazione Stripe non disponibile")


class CheckoutIn(BaseModel):
    plan_id: str  # starter | pro
    billing_cycle: str = Field("monthly", pattern="^(monthly|annual)$")
    origin_url: str  # from window.location.origin


@router.post("/subscriptions/checkout")
async def create_checkout(body: CheckoutIn, request: Request, user: Dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Solo l'admin può gestire l'abbonamento")
    plan = PLANS.get(body.plan_id)
    if not plan or body.plan_id == "enterprise":
        raise HTTPException(400, "Piano non valido")

    # Server-side pricing — never trust frontend
    monthly = float(plan["price_monthly"])
    annual_monthly = float(plan["price_annual"])
    if body.billing_cycle == "annual":
        amount = round(annual_monthly * 12, 2)  # charge whole year
    else:
        amount = monthly

    from emergentintegrations.payments.stripe.checkout import StripeCheckout, CheckoutSessionRequest

    base_url = body.origin_url.rstrip("/")
    webhook_url = f"{str(request.base_url).rstrip('/')}/api/webhook/stripe"
    success_url = f"{base_url}/billing?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{base_url}/billing?canceled=1"

    checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
    metadata = {
        "tenant_id": user["tenant_id"],
        "user_id": user["id"],
        "plan_id": body.plan_id,
        "billing_cycle": body.billing_cycle,
        "type": "subscription",
    }
    req = CheckoutSessionRequest(
        amount=amount,
        currency=plan["currency"],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata=metadata,
    )
    session = await checkout.create_checkout_session(req)

    # Mandatory: persist transaction record
    tx = {
        "id": new_id(),
        "tenant_id": user["tenant_id"],
        "user_id": user["id"],
        "user_email": user["email"],
        "session_id": session.session_id,
        "amount": amount,
        "currency": plan["currency"],
        "metadata": metadata,
        "plan_id": body.plan_id,
        "billing_cycle": body.billing_cycle,
        "status": "initiated",
        "payment_status": "pending",
        "created_at": now_utc(),
    }
    await db.payment_transactions.insert_one(tx)
    await log_audit(user, "CHECKOUT", "subscription", session.session_id, {"plan": body.plan_id, "cycle": body.billing_cycle})

    return {"url": session.url, "session_id": session.session_id}


@router.get("/subscriptions/status/{session_id}")
async def checkout_status(session_id: str, user: Dict = Depends(get_current_user)):
    """Poll Stripe for checkout status. Idempotent — safe to call repeatedly."""
    from emergentintegrations.payments.stripe.checkout import StripeCheckout

    tx = await db.payment_transactions.find_one({"session_id": session_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not tx:
        raise HTTPException(404, "Transazione non trovata")

    checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url="")
    stripe_status = await checkout.get_checkout_status(session_id)

    # If already processed, don't double-apply
    already_paid = tx.get("payment_status") == "paid"
    new_payment_status = stripe_status.payment_status
    new_status = stripe_status.status

    await db.payment_transactions.update_one(
        {"session_id": session_id},
        {"$set": {
            "status": new_status,
            "payment_status": new_payment_status,
            "updated_at": now_utc(),
        }},
    )

    if not already_paid and new_payment_status == "paid":
        # Activate subscription on the tenant
        plan_id = tx.get("plan_id", "starter")
        cycle = tx.get("billing_cycle", "monthly")
        period_days = 365 if cycle == "annual" else 30
        plan = PLANS.get(plan_id, PLANS["starter"])
        await db.tenants.update_one(
            {"id": user["tenant_id"]},
            {"$set": {
                "piano": plan_id,
                "stato": "active",
                "billing_cycle": cycle,
                "current_period_end": now_utc() + timedelta(days=period_days),
                "limits": dict(plan["limits"]),
                "updated_at": now_utc(),
            }},
        )
        await log_audit(user, "ACTIVATE", "subscription", session_id, {"plan": plan_id, "cycle": cycle})

    return {
        "session_id": session_id,
        "status": new_status,
        "payment_status": new_payment_status,
        "amount_total": stripe_status.amount_total,
        "currency": stripe_status.currency,
        "plan_id": tx.get("plan_id"),
    }


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """Stripe webhook — processes payment events and updates tenant/transactions."""
    from emergentintegrations.payments.stripe.checkout import StripeCheckout
    body_bytes = await request.body()
    signature = request.headers.get("Stripe-Signature", "")

    checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url="")
    try:
        evt = await checkout.handle_webhook(body_bytes, signature)
    except Exception as e:
        logger.error(f"Webhook verification failed: {e}")
        raise HTTPException(400, "Webhook non valido")

    tx = await db.payment_transactions.find_one({"session_id": evt.session_id}, {"_id": 0})
    if not tx:
        logger.warning(f"Webhook for unknown session {evt.session_id}")
        return {"ok": True}

    await db.payment_transactions.update_one(
        {"session_id": evt.session_id},
        {"$set": {
            "event_type": evt.event_type,
            "payment_status": evt.payment_status,
            "webhook_at": now_utc(),
        }},
    )

    if evt.payment_status == "paid" and tx.get("payment_status") != "paid":
        tenant_id = tx.get("tenant_id")
        plan_id = tx.get("plan_id", "starter")
        cycle = tx.get("billing_cycle", "monthly")
        period_days = 365 if cycle == "annual" else 30
        plan = PLANS.get(plan_id, PLANS["starter"])
        await db.tenants.update_one(
            {"id": tenant_id},
            {"$set": {
                "piano": plan_id,
                "stato": "active",
                "billing_cycle": cycle,
                "current_period_end": now_utc() + timedelta(days=period_days),
                "limits": dict(plan["limits"]),
                "updated_at": now_utc(),
            }},
        )

    return {"ok": True}


@router.get("/subscriptions/transactions")
async def my_transactions(user: Dict = Depends(get_current_user), limit: int = 50):
    if user["role"] != "admin":
        raise HTTPException(403, "Solo admin")
    items = await db.payment_transactions.find(
        {"tenant_id": user["tenant_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(limit)
    return items


@router.post("/subscriptions/cancel")
async def cancel_subscription(user: Dict = Depends(get_current_user)):
    """Mark subscription as canceled. Access remains until current_period_end."""
    if user["role"] != "admin":
        raise HTTPException(403, "Solo admin")
    tenant = await db.tenants.find_one({"id": user["tenant_id"]}, {"_id": 0})
    if not tenant:
        raise HTTPException(404, "Tenant non trovato")
    if tenant.get("stato") == "trial":
        raise HTTPException(400, "Non puoi cancellare un trial — basta non attivare l'abbonamento")
    if tenant.get("stato") != "active":
        raise HTTPException(400, f"Stato attuale '{tenant.get('stato')}': nulla da cancellare")
    await db.tenants.update_one(
        {"id": user["tenant_id"]},
        {"$set": {"stato": "canceled", "canceled_at": now_utc(), "updated_at": now_utc()}},
    )
    await log_audit(user, "CANCEL", "subscription", user["tenant_id"])
    return {"ok": True, "current_period_end": tenant.get("current_period_end")}


@router.post("/subscriptions/resume")
async def resume_subscription(user: Dict = Depends(get_current_user)):
    """Reactivate a canceled subscription if period still valid."""
    if user["role"] != "admin":
        raise HTTPException(403, "Solo admin")
    tenant = await db.tenants.find_one({"id": user["tenant_id"]}, {"_id": 0})
    if not tenant or tenant.get("stato") != "canceled":
        raise HTTPException(400, "Abbonamento non in stato 'canceled'")
    pe = tenant.get("current_period_end")
    if isinstance(pe, datetime):
        pe_aware = pe if pe.tzinfo else pe.replace(tzinfo=timezone.utc)
        if pe_aware <= now_utc():
            raise HTTPException(400, "Periodo scaduto — rinnova manualmente con un nuovo checkout")
    await db.tenants.update_one(
        {"id": user["tenant_id"]},
        {"$set": {"stato": "active", "updated_at": now_utc()}, "$unset": {"canceled_at": ""}},
    )
    await log_audit(user, "RESUME", "subscription", user["tenant_id"])
    return {"ok": True}
