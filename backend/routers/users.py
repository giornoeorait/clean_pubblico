"""Users management (admin only)."""
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from core import db, new_id, now_utc, hash_password, require_roles, log_audit
from schemas import UserCreate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(user: Dict = Depends(require_roles("admin"))):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(5000)
    return users


@router.post("")
async def create_user(body: UserCreate, user: Dict = Depends(require_roles("admin"))):
    if await db.users.find_one({"email": body.email.lower()}):
        raise HTTPException(status_code=400, detail="Email già registrata")
    doc = {
        "id": new_id(),
        "email": body.email.lower(),
        "password_hash": hash_password(body.password),
        "name": body.name,
        "role": body.role,
        "cliente_id": body.cliente_id,
        "attivo": True,
        "created_at": now_utc().isoformat(),
    }
    await db.users.insert_one(doc)
    await log_audit(user, "CREATE", "user", doc["id"], {"email": doc["email"]})
    doc.pop("password_hash", None)
    doc.pop("_id", None)
    return doc


@router.patch("/{uid}")
async def update_user(uid: str, body: Dict[str, Any], user: Dict = Depends(require_roles("admin"))):
    body.pop("_id", None)
    if "password" in body and body["password"]:
        body["password_hash"] = hash_password(body.pop("password"))
    else:
        body.pop("password", None)
    await db.users.update_one({"id": uid}, {"$set": body})
    await log_audit(user, "UPDATE", "user", uid, body)
    return {"ok": True}


@router.delete("/{uid}")
async def delete_user(uid: str, user: Dict = Depends(require_roles("admin"))):
    await db.users.update_one({"id": uid}, {"$set": {"attivo": False}})
    await log_audit(user, "DEACTIVATE", "user", uid)
    return {"ok": True}
