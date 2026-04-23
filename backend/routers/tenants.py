"""Tenant registration + profile + plans catalog (public + authenticated)."""
import os
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
    verification_token = new_id()
    user_doc = {
        "id": user_id,
        "email": email_norm,
        "password_hash": hash_password(body.password),
        "name": body.nome_admin.strip(),
        "role": "admin",
        "tenant_id": tenant_id,
        "attivo": True,
        "email_verified": False,
        "verification_token": verification_token,
        "verification_sent_at": now,
        "created_at": now,
    }
    await db.users.insert_one(user_doc)

    # Send verification email (SMTP if configured, stub fallback)
    from smtp_service import send_email
    frontend_base = os.environ.get("FRONTEND_URL", "").rstrip("/") or None
    try:
        request_url = str(request.base_url).rstrip("/")
        origin = request.headers.get("origin") or frontend_base or request_url
        verify_link = f"{origin}/verify?token={verification_token}"
        body_text = (
            f"Ciao {body.nome_admin},\n\n"
            f"Benvenuto in CleanTec! Conferma la tua email cliccando il link qui sotto:\n\n"
            f"{verify_link}\n\n"
            f"Il link scade in 48 ore.\n\n"
            f"— Il team CleanTec"
        )
        body_html = (
            f"<div style='font-family:system-ui,sans-serif;max-width:560px;margin:auto'>"
            f"<h2 style='color:#6366f1'>Benvenuto in CleanTec!</h2>"
            f"<p>Ciao <strong>{body.nome_admin}</strong>,</p>"
            f"<p>Grazie per esserti registrato. Conferma la tua email per attivare il tuo account:</p>"
            f"<p><a href='{verify_link}' style='display:inline-block;background:#6366f1;color:#fff;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:600'>Conferma email</a></p>"
            f"<p style='color:#64748b;font-size:13px'>Oppure copia e incolla: {verify_link}</p>"
            f"<p style='color:#64748b;font-size:12px;margin-top:32px'>— Il team CleanTec</p></div>"
        )
        await send_email(
            to=email_norm,
            subject="CleanTec — Conferma la tua email",
            body_text=body_text,
            body_html=body_html,
            context={"trigger": "verification_request", "user_id": user_id},
            tenant_id=tenant_id,
        )
    except Exception as e:
        import logging
        logging.getLogger("cleantec.email").error(f"Send verification failed: {e}")

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


# --- Email verification -----------------------------------------------------
class VerifyIn(BaseModel):
    token: str


@router.post("/auth/verify-email")
async def verify_email(body: VerifyIn):
    user = await db.users.find_one({"verification_token": body.token})
    if not user:
        raise HTTPException(400, "Token non valido o già utilizzato")
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"email_verified": True}, "$unset": {"verification_token": ""}},
    )
    return {"ok": True, "email": user["email"]}


@router.post("/auth/resend-verification")
async def resend_verification(user: Dict = Depends(get_current_user)):
    fresh = await db.users.find_one({"id": user["id"]})
    if not fresh:
        raise HTTPException(404, "Utente non trovato")
    if fresh.get("email_verified"):
        return {"ok": True, "already_verified": True}
    token = new_id()
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"verification_token": token, "verification_sent_at": now_utc()}},
    )
    from smtp_service import send_email
    frontend_base = os.environ.get("FRONTEND_URL", "").rstrip("/")
    verify_link = f"{frontend_base}/verify?token={token}" if frontend_base else f"/verify?token={token}"
    await send_email(
        to=fresh["email"],
        subject="CleanTec — Conferma la tua email",
        body_text=f"Ciao,\n\nConferma la tua email: {verify_link}\n\n— CleanTec",
        body_html=f"<p>Ciao,</p><p>Conferma la tua email: <a href='{verify_link}'>{verify_link}</a></p><p>— CleanTec</p>",
        context={"trigger": "verification_resend", "user_id": user["id"]},
        tenant_id=user["tenant_id"],
    )
    return {"ok": True}
