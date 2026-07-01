"""Users management (admin only)."""
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException
from core import db, new_id, now_utc, hash_password, require_roles, log_audit, tenant_scope, inject_tenant, merge_scope, enforce_quota, PERMISSION_SECTIONS
from schemas import UserCreate, PatchUserIn

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(user: Dict = Depends(require_roles("admin"))):
    """Lista utenti del tenant — esclude i superadmin (che non sono gestibili dall'admin di tenant)."""
    users = await db.users.find(
        {**tenant_scope(user), "role": {"$ne": "superadmin"}},
        {"_id": 0, "password_hash": 0},
    ).to_list(5000)
    return users


@router.post("")
async def create_user(body: UserCreate, user: Dict = Depends(require_roles("admin"))):
    await enforce_quota(user, "users")
    if await db.users.find_one({"email": body.email.lower()}):
        raise HTTPException(status_code=400, detail="Email già registrata")
    doc = {
        "id": new_id(),
        "email": body.email.lower(),
        "password_hash": hash_password(body.password),
        "name": body.name,
        "role": body.role,
        "cliente_id": body.cliente_id,
        "can_edit_dates": bool(body.can_edit_dates),
        "attivo": True,
        "created_at": now_utc(),
    }
    inject_tenant(doc, user)
    await db.users.insert_one(doc)
    await log_audit(user, "CREATE", "user", doc["id"], {"email": doc["email"]})
    doc.pop("password_hash", None)
    doc.pop("_id", None)
    return doc


@router.patch("/{uid}")
async def update_user(uid: str, body: PatchUserIn, user: Dict = Depends(require_roles("admin"))):
    target = await db.users.find_one(merge_scope(user, {"id": uid}), {"_id": 0})
    if not target:
        raise HTTPException(404, "Utente non trovato")
    if target.get("role") == "superadmin":
        raise HTTPException(403, "I superadmin non sono modificabili da questo pannello")
    data = body.model_dump(exclude_unset=True)
    if "password" in data and data["password"]:
        data["password_hash"] = hash_password(data.pop("password"))
    else:
        data.pop("password", None)
    # Sanifica `permissions`: accetta solo chiavi sezione conosciute e coerce boolean
    if "permissions" in data:
        raw = data.get("permissions") or {}
        clean: Dict[str, Dict[str, bool]] = {}
        for s in PERMISSION_SECTIONS:
            src = raw.get(s) or {}
            clean[s] = {
                "view": bool(src.get("view", False)),
                "edit": bool(src.get("edit", False)),
            }
        data["permissions"] = clean
    if not data:
        return {"ok": True}
    await db.users.update_one(merge_scope(user, {"id": uid}), {"$set": data})
    await log_audit(user, "UPDATE", "user", uid, data)
    return {"ok": True}


@router.delete("/{uid}")
async def delete_user(uid: str, hard: bool = False, user: Dict = Depends(require_roles("admin"))):
    """Soft-delete (default) o hard-delete dell'utente.

    Safety:
    - Non puoi eliminare/disattivare te stesso
    - Non puoi rimuovere l'ULTIMO admin attivo del tenant
    - I superadmin sono intoccabili
    """
    if uid == user["id"]:
        raise HTTPException(400, "Non puoi eliminare il tuo stesso account")

    target = await db.users.find_one(merge_scope(user, {"id": uid}), {"_id": 0})
    if not target:
        raise HTTPException(404, "Utente non trovato")
    if target.get("role") == "superadmin":
        raise HTTPException(403, "I superadmin non possono essere eliminati o disattivati")

    # Se è admin e stiamo per disattivarlo/eliminarlo, verifica che ci siano altri admin attivi
    if target.get("role") == "admin":
        from core import tenant_id_of as _tid
        n_admin = await db.users.count_documents({
            "tenant_id": _tid(user), "role": "admin", "attivo": True, "id": {"$ne": uid},
        })
        if n_admin == 0:
            raise HTTPException(400, "Impossibile rimuovere l'ultimo admin attivo del tenant")

    if hard:
        await db.users.delete_one(merge_scope(user, {"id": uid}))
        await log_audit(user, "DELETE", "user", uid, {"email": target.get("email")})
    else:
        await db.users.update_one(merge_scope(user, {"id": uid}), {"$set": {"attivo": False}})
        await log_audit(user, "DEACTIVATE", "user", uid, {"email": target.get("email")})
    return {"ok": True, "mode": "hard" if hard else "soft"}


@router.patch("/{uid}/riattiva")
async def riattiva_user(uid: str, user: Dict = Depends(require_roles("admin"))):
    target = await db.users.find_one(merge_scope(user, {"id": uid}), {"_id": 0})
    if not target:
        raise HTTPException(404, "Utente non trovato")
    if target.get("role") == "superadmin":
        raise HTTPException(403, "I superadmin non sono gestibili da questo pannello")
    await db.users.update_one(merge_scope(user, {"id": uid}), {"$set": {"attivo": True}})
    await log_audit(user, "REACTIVATE", "user", uid)
    return {"ok": True}
