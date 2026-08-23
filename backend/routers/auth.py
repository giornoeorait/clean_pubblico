"""Auth routes."""
from typing import Dict
from fastapi import APIRouter, HTTPException, Depends, Response
from core import db, verify_password, create_access_token, clean_doc, get_current_user, DEMO_TENANT_ID, resolve_permissions
from schemas import LoginIn

router = APIRouter(prefix="/auth", tags=["auth"])


def _enrich_user(user: Dict) -> Dict:
    """Aggiunge permessi risolti (default ruolo + override utente) al payload."""
    user["permissions_resolved"] = resolve_permissions(user)
    return user


@router.post("/login")
async def login(body: LoginIn, response: Response):
    email = body.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    if not user.get("attivo", True):
        raise HTTPException(status_code=403, detail="Utente disattivato")
    tenant_id = user.get("tenant_id") or DEMO_TENANT_ID  # legacy fallback
    token = create_access_token(user["id"], user["email"], user["role"], tenant_id)
    cookie_max_age = 7776000 if user["role"] == "produzione" else 43200  # 90gg totem / 12h standard
    response.set_cookie(
        key="access_token", value=token, httponly=True, secure=False,
        samesite="lax", max_age=cookie_max_age, path="/",
    )
    clean_doc(user)
    _enrich_user(user)
    # Enrich with tenant basic info
    tenant = await db.tenants.find_one({"id": tenant_id}, {"_id": 0, "piano": 1, "stato": 1, "nome": 1, "trial_ends_at": 1})
    return {"user": user, "token": token, "tenant": tenant}


@router.post("/logout")
async def logout(response: Response, user: Dict = Depends(get_current_user)):
    response.delete_cookie(key="access_token", path="/")
    return {"ok": True}


@router.get("/me")
async def auth_me(user: Dict = Depends(get_current_user)):
    return _enrich_user(user)
