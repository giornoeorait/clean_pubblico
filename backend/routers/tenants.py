"""Tenant registration + profile + plans catalog (public + authenticated)."""
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from core import (
    db, new_id, now_utc, hash_password, create_access_token, verify_password,
    get_current_user, get_tenant, PLANS, TRIAL_DAYS, log_audit,
)

router = APIRouter(tags=["tenants"])


# --- Schemas -----------------------------------------------------------------
class RegisterIn(BaseModel):
    nome_azienda: str = Field(..., min_length=2, max_length=120)
    partita_iva: Optional[str] = ""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=120)
    nome_admin: str = Field(..., min_length=2, max_length=80)
    piano: str = Field("starter")  # starter | pro | enterprise (contattaci)


def _slugify(s: str) -> str:
    import re
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:40] or new_id()[:8]


# --- Public: plans catalog ---------------------------------------------------
@router.get("/plans")
async def list_plans():
    """Public catalog — used by landing / pricing page."""
    return {"plans": list(PLANS.values()), "trial_days": TRIAL_DAYS}


# --- Public: register new tenant --------------------------------------------
@router.post("/tenants/register")
async def register_tenant(body: RegisterIn, request: Request):
    email_norm = body.email.lower().strip()
    piano = body.piano.lower().strip()

    if piano not in PLANS:
        raise HTTPException(400, f"Piano non valido: {piano}")
    if piano == "enterprise":
        raise HTTPException(400, "Enterprise richiede contatto commerciale")

    # Rate limit naive: no more than 5 registrations per minute per IP
    ip = request.client.host if request.client else "unknown"
    recent = await db.register_attempts.count_documents({
        "ip": ip,
        "ts": {"$gte": now_utc() - timedelta(minutes=1)},
    })
    if recent >= 5:
        raise HTTPException(429, "Troppi tentativi. Riprova tra un minuto.")
    await db.register_attempts.insert_one({"id": new_id(), "ip": ip, "email": email_norm, "ts": now_utc()})

    existing = await db.users.find_one({"email": email_norm})
    if existing:
        raise HTTPException(400, "Email già registrata")

    plan = PLANS[piano]
    now = now_utc()
    trial_ends = now + timedelta(days=TRIAL_DAYS)

    # Generate unique slug
    base_slug = _slugify(body.nome_azienda)
    slug = base_slug
    suffix = 1
    while await db.tenants.find_one({"slug": slug}):
        suffix += 1
        slug = f"{base_slug}-{suffix}"

    tenant_id = new_id()
    tenant_doc = {
        "id": tenant_id,
        "slug": slug,
        "nome": body.nome_azienda.strip(),
        "partita_iva": (body.partita_iva or "").strip(),
        "email_admin": email_norm,
        "piano": piano,
        "stato": "trial",
        "trial_ends_at": trial_ends,
        "current_period_end": None,
        "stripe_customer_id": None,
        "stripe_subscription_id": None,
        "limits": dict(plan["limits"]),
        "usage": {"users": 1, "lotti_this_month": 0, "sms_this_month": 0, "last_reset": now},
        "created_at": now,
        "updated_at": now,
    }
    await db.tenants.insert_one(tenant_doc)

    # Admin user
    user_id = new_id()
    user_doc = {
        "id": user_id,
        "email": email_norm,
        "password_hash": hash_password(body.password),
        "name": body.nome_admin.strip(),
        "role": "admin",
        "tenant_id": tenant_id,
        "attivo": True,
        "email_verified": False,
        "created_at": now,
    }
    await db.users.insert_one(user_doc)

    token = create_access_token(user_id, email_norm, "admin", tenant_id)

    await db.audit_log.insert_one({
        "id": new_id(),
        "user_id": user_id, "user_email": email_norm,
        "tenant_id": tenant_id,
        "azione": "REGISTER", "entita": "tenant", "entita_id": tenant_id,
        "dettagli": {"piano": piano, "nome_azienda": body.nome_azienda},
        "timestamp": now,
    })

    tenant_doc.pop("_id", None)
    user_doc.pop("password_hash", None)
    user_doc.pop("_id", None)
    return {
        "user": user_doc,
        "tenant": tenant_doc,
        "token": token,
        "trial_days": TRIAL_DAYS,
        "trial_ends_at": trial_ends.isoformat(),
    }


# --- Authenticated: current tenant info --------------------------------------
@router.get("/tenants/me")
async def current_tenant(user: Dict = Depends(get_current_user)):
    tenant = await get_tenant(user)
    # live user count
    user_count = await db.users.count_documents({"tenant_id": tenant["id"], "attivo": True})
    tenant["usage"] = {**tenant.get("usage", {}), "users": user_count}

    plan = PLANS.get(tenant.get("piano", "starter"), PLANS["starter"])
    # compute trial days remaining
    days_left = None
    if tenant.get("stato") == "trial" and tenant.get("trial_ends_at"):
        ends = tenant["trial_ends_at"]
        if ends.tzinfo is None:
            ends = ends.replace(tzinfo=timezone.utc)
        delta = (ends - now_utc()).total_seconds() / 86400.0
        days_left = max(0, round(delta, 1))

    return {
        "tenant": tenant,
        "plan": plan,
        "trial_days_left": days_left,
    }


# --- Authenticated: update tenant meta (admin only) --------------------------
class TenantUpdateIn(BaseModel):
    nome: Optional[str] = None
    partita_iva: Optional[str] = None


@router.patch("/tenants/me")
async def update_tenant(body: TenantUpdateIn, user: Dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Solo l'admin del tenant può modificare i dati aziendali")
    data = body.model_dump(exclude_unset=True)
    if not data:
        return {"ok": True}
    data["updated_at"] = now_utc()
    await db.tenants.update_one({"id": user["tenant_id"]}, {"$set": data})
    await log_audit(user, "UPDATE", "tenant", user["tenant_id"], data)
    return {"ok": True}
