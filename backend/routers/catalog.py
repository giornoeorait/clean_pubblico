"""Anagrafiche: Clienti, Articoli, Macchine."""
from typing import Dict, Any, Optional, Type
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from core import db, new_id, now_utc, to_dt, get_current_user, require_roles, log_audit, tenant_scope, merge_scope, inject_tenant
from schemas import (
    ClienteIn, ArticoloIn, MacchinaIn,
    PatchClienteIn, PatchArticoloIn, PatchMacchinaIn,
)

router = APIRouter(tags=["catalog"])

# Fields that must be stored as BSON datetime (not string)
_DATE_FIELDS_BY_COLL = {
    "clienti": set(),
    "articoli": set(),
    "macchine": {"manutenzione_prossima"},
}


def _coerce_dates(coll_name: str, data: Dict[str, Any]) -> None:
    for f in _DATE_FIELDS_BY_COLL.get(coll_name, ()):
        if f in data and data[f] is not None:
            dt = to_dt(data[f])
            if dt is not None:
                data[f] = dt


def _register(path: str, coll_name: str, Model: Type[BaseModel], PatchModel: Type[BaseModel],
              entity: str, write_roles):
    coll = db[coll_name]

    @router.get(f"/{path}")
    async def list_all(user: Dict = Depends(get_current_user), q: Optional[str] = None, limit: int = 500):
        query: Dict[str, Any] = dict(tenant_scope(user))
        if q:
            query["$or"] = [
                {"descrizione": {"$regex": q, "$options": "i"}},
                {"codice": {"$regex": q, "$options": "i"}},
                {"ragione_sociale": {"$regex": q, "$options": "i"}},
            ]
        items = await coll.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
        return items

    @router.post(f"/{path}")
    async def create_one(body: Model, user: Dict = Depends(require_roles(*write_roles))):
        doc = body.model_dump()
        _coerce_dates(coll_name, doc)
        doc["id"] = new_id()
        doc["created_at"] = now_utc()
        doc["updated_at"] = doc["created_at"]
        inject_tenant(doc, user)
        await coll.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(user, "CREATE", entity, doc["id"])
        return doc

    @router.get(f"/{path}/{{item_id}}")
    async def get_one(item_id: str, user: Dict = Depends(get_current_user)):
        doc = await coll.find_one(merge_scope(user, {"id": item_id}), {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail=f"{entity} non trovato")
        return doc

    @router.patch(f"/{path}/{{item_id}}")
    async def update_one(item_id: str, body: PatchModel, user: Dict = Depends(require_roles(*write_roles))):
        data = body.model_dump(exclude_unset=True)
        if not data:
            return {"ok": True}
        _coerce_dates(coll_name, data)
        data["updated_at"] = now_utc()
        res = await coll.update_one(merge_scope(user, {"id": item_id}), {"$set": data})
        if res.matched_count == 0:
            raise HTTPException(status_code=404, detail=f"{entity} non trovato")
        await log_audit(user, "UPDATE", entity, item_id, data)
        return {"ok": True}

    @router.delete(f"/{path}/{{item_id}}")
    async def delete_one(item_id: str, user: Dict = Depends(require_roles(*write_roles))):
        await coll.delete_one(merge_scope(user, {"id": item_id}))
        await log_audit(user, "DELETE", entity, item_id)
        return {"ok": True}


_register("clienti", "clienti", ClienteIn, PatchClienteIn, "cliente", ("admin", "contabilita"))
_register("articoli", "articoli", ArticoloIn, PatchArticoloIn, "articolo", ("admin", "contabilita"))
_register("macchine", "macchine", MacchinaIn, PatchMacchinaIn, "macchina", ("admin", "produzione"))
