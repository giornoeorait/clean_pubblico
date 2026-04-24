"""Listini (PriceLists) + prezzi articoli per listino."""
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import (
    db, new_id, now_utc,
    get_current_user, require_roles, log_audit,
    tenant_scope, merge_scope, inject_tenant,
)

router = APIRouter(prefix="/listini", tags=["listini"])
_WRITE = ("admin", "contabilita")


class ListinoIn(BaseModel):
    nome: str = Field(..., min_length=1, max_length=120)
    tipo: str = Field(..., pattern="^(noleggio|lavaggio)$")
    descrizione: Optional[str] = ""
    attivo: bool = True


class ListinoPatch(BaseModel):
    nome: Optional[str] = None
    descrizione: Optional[str] = None
    attivo: Optional[bool] = None
    # tipo is NOT patchable (would break price references)


class PrezzoArticoloIn(BaseModel):
    articolo_id: str
    prezzo: float = Field(..., ge=0)


class PrezziBulkIn(BaseModel):
    items: List[PrezzoArticoloIn]


# --- CRUD Listino -----------------------------------------------------------
@router.get("")
async def list_listini(user: Dict = Depends(get_current_user), solo_attivi: bool = False):
    q: Dict[str, Any] = dict(tenant_scope(user))
    if solo_attivi:
        q["attivo"] = True
    return await db.listini.find(q, {"_id": 0}).sort("nome", 1).to_list(500)


@router.post("")
async def create_listino(body: ListinoIn, user: Dict = Depends(require_roles(*_WRITE))):
    doc = body.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = now_utc()
    doc["updated_at"] = doc["created_at"]
    inject_tenant(doc, user)
    await db.listini.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "listino", doc["id"])
    return doc


@router.get("/{lid}")
async def get_listino(lid: str, user: Dict = Depends(get_current_user)):
    doc = await db.listini.find_one(merge_scope(user, {"id": lid}), {"_id": 0})
    if not doc:
        raise HTTPException(404, "Listino non trovato")
    prezzi = await db.listini_prezzi.find(
        merge_scope(user, {"listino_id": lid}), {"_id": 0}
    ).to_list(5000)
    doc["prezzi"] = prezzi
    return doc


@router.patch("/{lid}")
async def update_listino(lid: str, body: ListinoPatch, user: Dict = Depends(require_roles(*_WRITE))):
    data = body.model_dump(exclude_unset=True)
    if not data:
        return {"ok": True}
    data["updated_at"] = now_utc()
    res = await db.listini.update_one(merge_scope(user, {"id": lid}), {"$set": data})
    if res.matched_count == 0:
        raise HTTPException(404, "Listino non trovato")
    await log_audit(user, "UPDATE", "listino", lid, data)
    return {"ok": True}


@router.delete("/{lid}")
async def delete_listino(lid: str, user: Dict = Depends(require_roles(*_WRITE))):
    # Referential integrity: block if assigned to clienti or DDT
    clienti_count = await db.clienti.count_documents(merge_scope(user, {"listino_id": lid}))
    if clienti_count > 0:
        raise HTTPException(409, f"Impossibile eliminare: {clienti_count} clienti associati al listino")
    ddt_count = await db.ddt.count_documents(merge_scope(user, {"listino_id": lid}))
    if ddt_count > 0:
        raise HTTPException(409, f"Impossibile eliminare: {ddt_count} D.D.T. usano questo listino")
    await db.listini.delete_one(merge_scope(user, {"id": lid}))
    await db.listini_prezzi.delete_many(merge_scope(user, {"listino_id": lid}))
    await log_audit(user, "DELETE", "listino", lid)
    return {"ok": True}


# --- Prezzi articoli --------------------------------------------------------
@router.get("/{lid}/prezzi")
async def list_prezzi(lid: str, user: Dict = Depends(get_current_user)):
    listino = await db.listini.find_one(merge_scope(user, {"id": lid}), {"_id": 0})
    if not listino:
        raise HTTPException(404, "Listino non trovato")
    articoli = await db.articoli.find(tenant_scope(user), {"_id": 0}).sort("descrizione", 1).to_list(5000)
    prezzi_map = {}
    async for p in db.listini_prezzi.find(merge_scope(user, {"listino_id": lid}), {"_id": 0}):
        prezzi_map[p["articolo_id"]] = p["prezzo"]
    # Default price source depends on listino type (noleggio vs lavaggio)
    tipo = listino.get("tipo") or "lavaggio"
    default_key = "prezzo_noleggio" if tipo == "noleggio" else "prezzo_lavaggio"
    rows = []
    for a in articoli:
        default_price = a.get(default_key) if a.get(default_key) else a.get("prezzo", 0)
        rows.append({
            "articolo_id": a["id"],
            "codice": a.get("codice", ""),
            "descrizione": a.get("descrizione", ""),
            "unita_misura": a.get("unita_misura", "pz"),
            "prezzo": prezzi_map.get(a["id"], None),
            "prezzo_default": float(default_price or 0),
        })
    return {"listino": {"id": listino["id"], "nome": listino.get("nome"), "tipo": tipo, "attivo": listino.get("attivo", True)}, "rows": rows}


@router.put("/{lid}/prezzi")
async def bulk_update_prezzi(lid: str, body: PrezziBulkIn, user: Dict = Depends(require_roles(*_WRITE))):
    listino = await db.listini.find_one(merge_scope(user, {"id": lid}), {"_id": 0})
    if not listino:
        raise HTTPException(404, "Listino non trovato")
    tid = user["tenant_id"]
    count = 0
    for it in body.items:
        await db.listini_prezzi.update_one(
            {"tenant_id": tid, "listino_id": lid, "articolo_id": it.articolo_id},
            {"$set": {
                "tenant_id": tid,
                "listino_id": lid,
                "articolo_id": it.articolo_id,
                "prezzo": it.prezzo,
                "updated_at": now_utc(),
            }},
            upsert=True,
        )
        count += 1
    await log_audit(user, "BULK_UPDATE", "listino_prezzi", lid, {"count": count})
    return {"ok": True, "updated": count}


# --- Helper cross-router ----------------------------------------------------
async def get_prezzo(tenant_id: str, listino_id: Optional[str], articolo_id: str) -> float:
    """Return the applicable price for an articolo in a listino (or default)."""
    if listino_id:
        p = await db.listini_prezzi.find_one(
            {"tenant_id": tenant_id, "listino_id": listino_id, "articolo_id": articolo_id}
        )
        if p and p.get("prezzo") is not None:
            return float(p["prezzo"])
    # fallback: prezzo default sull'articolo
    a = await db.articoli.find_one({"tenant_id": tenant_id, "id": articolo_id})
    return float((a or {}).get("prezzo", 0) or 0)
