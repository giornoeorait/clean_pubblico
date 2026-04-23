"""Superadmin router: cross-tenant SaaS operations metrics + SMTP config."""
from datetime import timedelta, datetime, timezone
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from core import db, now_utc, get_current_user, PLANS
from smtp_service import get_smtp_config, save_smtp_config, send_email, is_smtp_configured

router = APIRouter(prefix="/admin", tags=["superadmin"])


def _require_super(user: Dict[str, Any]):
    if user.get("role") != "superadmin":
        raise HTTPException(403, "Solo superadmin")
    return user


def _monthly_revenue(tenant: Dict[str, Any]) -> float:
    plan = PLANS.get(tenant.get("piano", "starter"), PLANS["starter"])
    cycle = tenant.get("billing_cycle", "monthly")
    return float(plan["price_annual"] if cycle == "annual" else plan["price_monthly"])


@router.get("/stats")
async def stats(user: Dict = Depends(get_current_user)):
    _require_super(user)
    today = now_utc()
    month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    tenants = await db.tenants.find({"is_demo": {"$ne": True}}, {"_id": 0}).to_list(10000)
    total = len(tenants)
    by_stato: Dict[str, int] = {}
    by_piano: Dict[str, int] = {}
    mrr = 0.0
    for t in tenants:
        by_stato[t.get("stato", "trial")] = by_stato.get(t.get("stato", "trial"), 0) + 1
        by_piano[t.get("piano", "starter")] = by_piano.get(t.get("piano", "starter"), 0) + 1
        if t.get("stato") == "active":
            mrr += _monthly_revenue(t)

    # Trial conversion: active signed up in last 90d / trials started in last 90d
    d90 = today - timedelta(days=90)
    trials_90d = 0
    actives_90d = 0
    for t in tenants:
        ca = t.get("created_at")
        if not isinstance(ca, datetime):
            continue
        ca_aware = ca if ca.tzinfo else ca.replace(tzinfo=timezone.utc)
        if ca_aware > d90:
            trials_90d += 1
            if t.get("stato") == "active":
                actives_90d += 1
    conv_rate = round((actives_90d / trials_90d * 100) if trials_90d else 0, 1)

    # New signups this month
    new_this_month = 0
    for t in tenants:
        ca = t.get("created_at")
        if not isinstance(ca, datetime):
            continue
        ca_aware = ca if ca.tzinfo else ca.replace(tzinfo=timezone.utc)
        if ca_aware >= month_start:
            new_this_month += 1

    # Revenue this month (sum of paid transactions)
    paid_txs = await db.payment_transactions.find(
        {"payment_status": "paid", "created_at": {"$gte": month_start}}, {"_id": 0}
    ).to_list(10000)
    revenue_month = sum(tx.get("amount", 0) for tx in paid_txs)

    return {
        "total_tenants": total,
        "mrr": round(mrr, 2),
        "arr": round(mrr * 12, 2),
        "by_stato": by_stato,
        "by_piano": by_piano,
        "new_signups_month": new_this_month,
        "trial_conversion_90d_pct": conv_rate,
        "revenue_this_month": round(revenue_month, 2),
        "paid_transactions_month": len(paid_txs),
    }


@router.get("/tenants")
async def list_tenants(user: Dict = Depends(get_current_user), piano: Optional[str] = None, stato: Optional[str] = None, limit: int = 500):
    _require_super(user)
    q: Dict[str, Any] = {"is_demo": {"$ne": True}}
    if piano: q["piano"] = piano
    if stato: q["stato"] = stato
    tenants = await db.tenants.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    # Enrich with user count and last activity
    for t in tenants:
        t["users_count"] = await db.users.count_documents({"tenant_id": t["id"], "attivo": True})
        last = await db.audit_log.find_one({"tenant_id": t["id"]}, {"_id": 0, "timestamp": 1}, sort=[("timestamp", -1)])
        t["last_activity"] = last.get("timestamp") if last else None
        t["mrr_contribution"] = _monthly_revenue(t) if t.get("stato") == "active" else 0.0
    return tenants


@router.get("/transactions")
async def all_transactions(user: Dict = Depends(get_current_user), limit: int = 200):
    _require_super(user)
    return await db.payment_transactions.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)


@router.patch("/tenants/{tid}")
async def update_tenant_as_super(tid: str, body: Dict[str, Any], user: Dict = Depends(get_current_user)):
    _require_super(user)
    allowed = {"piano", "stato", "limits", "is_demo"}
    data = {k: v for k, v in body.items() if k in allowed}
    if not data:
        raise HTTPException(400, "Nessun campo valido")
    data["updated_at"] = now_utc()
    res = await db.tenants.update_one({"id": tid}, {"$set": data})
    if res.matched_count == 0:
        raise HTTPException(404, "Tenant non trovato")
    await db.audit_log.insert_one({
        "id": __import__("uuid").uuid4().hex,
        "tenant_id": tid,
        "user_id": user["id"], "user_email": user["email"],
        "azione": "SUPER_UPDATE", "entita": "tenant", "entita_id": tid,
        "dettagli": data,
        "timestamp": now_utc(),
    })
    return {"ok": True}


# ---- SMTP configuration ---------------------------------------------------
class SmtpConfigIn(BaseModel):
    host: Optional[str] = Field(None, max_length=200)
    port: Optional[int] = Field(None, ge=1, le=65535)
    username: Optional[str] = Field(None, max_length=200)
    password: Optional[str] = Field(None, max_length=500)  # only updated if non-empty
    from_email: Optional[EmailStr] = None
    from_name: Optional[str] = Field(None, max_length=100)
    use_tls: Optional[bool] = None  # STARTTLS
    use_ssl: Optional[bool] = None  # implicit SSL
    enabled: Optional[bool] = None


class SmtpTestIn(BaseModel):
    to: EmailStr


@router.get("/smtp-config")
async def smtp_config(user: Dict = Depends(get_current_user)):
    _require_super(user)
    cfg = await get_smtp_config() or {}
    # Never reveal password to client
    safe = {k: v for k, v in cfg.items() if k != "password"}
    safe["password_set"] = bool(cfg.get("password"))
    safe["configured"] = await is_smtp_configured()
    return safe


@router.patch("/smtp-config")
async def update_smtp_config(body: SmtpConfigIn, user: Dict = Depends(get_current_user)):
    _require_super(user)
    data = body.model_dump(exclude_unset=True)
    cfg = await save_smtp_config(data, user)
    safe = {k: v for k, v in (cfg or {}).items() if k != "password"}
    safe["password_set"] = bool((cfg or {}).get("password"))
    return safe


@router.post("/smtp-test")
async def smtp_test(body: SmtpTestIn, user: Dict = Depends(get_current_user)):
    _require_super(user)
    if not await is_smtp_configured():
        raise HTTPException(400, "SMTP non configurato o disabilitato")
    result = await send_email(
        to=body.to,
        subject="CleanTec — Test SMTP",
        body_text="Questa è un'email di test inviata dal pannello SaaS CleanTec.\n\nSe leggi questo messaggio, il server SMTP è configurato correttamente.",
        body_html="<p>Questa è un'email di test inviata dal pannello <strong>SaaS CleanTec</strong>.</p><p>Se leggi questo messaggio, il server SMTP è configurato correttamente. ✓</p>",
        context={"trigger": "smtp_test", "by": user["email"]},
    )
    return result


@router.get("/email-events")
async def list_email_events(user: Dict = Depends(get_current_user), limit: int = 100):
    _require_super(user)
    return await db.email_events.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
