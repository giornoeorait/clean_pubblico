"""DDT (Documenti di Trasporto) — nucleo ERP di consegna."""
from datetime import datetime
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import (
    db, new_id, now_utc, to_dt,
    get_current_user, require_roles, log_audit, next_seq,
    tenant_scope, merge_scope, inject_tenant,
)
from routers.listini import get_prezzo

router = APIRouter(prefix="/ddt", tags=["ddt"])
_WRITE = ("admin", "logistica", "contabilita")


class DDTRigaIn(BaseModel):
    articolo_id: str
    quantita: float = Field(..., gt=0)
    prezzo_unitario: Optional[float] = None  # se None: auto da listino


class DDTIn(BaseModel):
    cliente_id: str
    data: Optional[str] = None
    note: Optional[str] = ""
    righe: List[DDTRigaIn]


class DDTPatch(BaseModel):
    data: Optional[str] = None
    note: Optional[str] = None
    righe: Optional[List[DDTRigaIn]] = None


async def _compute_righe(tenant_id: str, listino_id: Optional[str], righe: List[DDTRigaIn]) -> (List[Dict[str, Any]], float):
    """Return enriched rows with auto-pricing + imponibile total."""
    out = []
    total = 0.0
    for r in righe:
        prezzo = r.prezzo_unitario if r.prezzo_unitario is not None else await get_prezzo(tenant_id, listino_id, r.articolo_id)
        articolo = await db.articoli.find_one({"tenant_id": tenant_id, "id": r.articolo_id}, {"_id": 0})
        if not articolo:
            raise HTTPException(400, f"Articolo {r.articolo_id} non trovato")
        riga_tot = round(prezzo * r.quantita, 2)
        out.append({
            "articolo_id": r.articolo_id,
            "codice": articolo.get("codice", ""),
            "descrizione": articolo.get("descrizione", ""),
            "unita_misura": articolo.get("unita_misura", "pz"),
            "quantita": r.quantita,
            "prezzo_unitario": round(prezzo, 4),
            "totale": riga_tot,
        })
        total += riga_tot
    return out, round(total, 2)


# --- CRUD DDT ---------------------------------------------------------------
@router.get("")
async def list_ddt(
    user: Dict = Depends(get_current_user),
    cliente_id: Optional[str] = None,
    stato_fatturazione: Optional[str] = None,  # non_fatturato | fatturato
    limit: int = 500,
):
    q: Dict[str, Any] = dict(tenant_scope(user))
    if cliente_id: q["cliente_id"] = cliente_id
    if stato_fatturazione: q["stato_fatturazione"] = stato_fatturazione
    if user["role"] == "cliente" and user.get("cliente_id"):
        q["cliente_id"] = user["cliente_id"]
    return await db.ddt.find(q, {"_id": 0}).sort("data", -1).to_list(limit)


@router.post("")
async def create_ddt(body: DDTIn, user: Dict = Depends(require_roles(*_WRITE))):
    cliente = await db.clienti.find_one(merge_scope(user, {"id": body.cliente_id}), {"_id": 0})
    if not cliente:
        raise HTTPException(400, "Cliente non trovato")
    if not body.righe:
        raise HTTPException(400, "Almeno una riga richiesta")

    listino_id = cliente.get("listino_id") or None
    righe, imponibile = await _compute_righe(user["tenant_id"], listino_id, body.righe)

    seq = await next_seq("ddt")
    doc = {
        "id": new_id(),
        "numero": f"DDT-{datetime.now().year}-{seq:05d}",
        "cliente_id": body.cliente_id,
        "cliente_nome": cliente.get("ragione_sociale", ""),
        "listino_id": listino_id,
        "data": to_dt(body.data) or now_utc(),
        "note": body.note or "",
        "righe": righe,
        "imponibile": imponibile,
        "stato_fatturazione": "non_fatturato",
        "fattura_id": None,
        "fattura_numero": None,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    inject_tenant(doc, user)
    await db.ddt.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "ddt", doc["id"], {"cliente": cliente.get("ragione_sociale")})
    return doc


@router.get("/{did}")
async def get_ddt(did: str, user: Dict = Depends(get_current_user)):
    doc = await db.ddt.find_one(merge_scope(user, {"id": did}), {"_id": 0})
    if not doc:
        raise HTTPException(404, "DDT non trovato")
    return doc


@router.patch("/{did}")
async def update_ddt(did: str, body: DDTPatch, user: Dict = Depends(require_roles(*_WRITE))):
    existing = await db.ddt.find_one(merge_scope(user, {"id": did}), {"_id": 0})
    if not existing:
        raise HTTPException(404, "DDT non trovato")
    if existing.get("stato_fatturazione") == "fatturato":
        raise HTTPException(409, "DDT già fatturato: non modificabile")

    data = body.model_dump(exclude_unset=True)
    if "data" in data and data["data"]:
        data["data"] = to_dt(data["data"]) or now_utc()
    if body.righe is not None:
        righe, imp = await _compute_righe(user["tenant_id"], existing.get("listino_id"), body.righe)
        data["righe"] = righe
        data["imponibile"] = imp
    data["updated_at"] = now_utc()
    await db.ddt.update_one(merge_scope(user, {"id": did}), {"$set": data})
    await log_audit(user, "UPDATE", "ddt", did)
    return {"ok": True}


@router.delete("/{did}")
async def delete_ddt(did: str, user: Dict = Depends(require_roles(*_WRITE))):
    existing = await db.ddt.find_one(merge_scope(user, {"id": did}), {"_id": 0})
    if not existing:
        raise HTTPException(404, "DDT non trovato")
    if existing.get("stato_fatturazione") == "fatturato":
        raise HTTPException(409, "DDT fatturato non può essere eliminato")
    await db.ddt.delete_one(merge_scope(user, {"id": did}))
    await log_audit(user, "DELETE", "ddt", did)
    return {"ok": True}
