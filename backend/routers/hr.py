"""Dipendenti + Automezzi + generazione stipendi ricorrenti."""
from datetime import datetime, timezone
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import (
    db, new_id, now_utc,
    get_current_user, require_roles,
    tenant_scope, merge_scope, tenant_id_of, inject_tenant, log_audit,
)
from schemas import DipendenteIn, PatchDipendenteIn, AutomezzoIn, PatchAutomezzoIn

router = APIRouter(tags=["hr"])


# ============== DIPENDENTI ==============

@router.get("/dipendenti")
async def list_dip(attivo: Optional[bool] = None, user: Dict = Depends(get_current_user)):
    q: Dict = dict(tenant_scope(user))
    if attivo is not None:
        q["attivo"] = attivo
    return await db.dipendenti.find(q, {"_id": 0}).sort("nome", 1).to_list(500)


@router.post("/dipendenti")
async def create_dip(body: DipendenteIn, user: Dict = Depends(require_roles("admin", "contabilita"))):
    doc = body.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = now_utc()
    doc["updated_at"] = doc["created_at"]
    inject_tenant(doc, user)
    await db.dipendenti.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "dipendente", doc["id"], {"nome": body.nome})
    return doc


@router.patch("/dipendenti/{did}")
async def patch_dip(did: str, body: PatchDipendenteIn, user: Dict = Depends(require_roles("admin", "contabilita"))):
    data = body.model_dump(exclude_unset=True)
    if not data:
        return {"ok": True}
    data["updated_at"] = now_utc()
    res = await db.dipendenti.update_one(merge_scope(user, {"id": did}), {"$set": data})
    if res.matched_count == 0:
        raise HTTPException(404, "Dipendente non trovato")
    await log_audit(user, "UPDATE", "dipendente", did, data)
    return {"ok": True}


@router.delete("/dipendenti/{did}")
async def delete_dip(did: str, user: Dict = Depends(require_roles("admin"))):
    res = await db.dipendenti.delete_one(merge_scope(user, {"id": did}))
    if res.deleted_count == 0:
        raise HTTPException(404, "Dipendente non trovato")
    await log_audit(user, "DELETE", "dipendente", did)
    return {"ok": True}


class GeneraStipendiIn(BaseModel):
    mese_riferimento: str  # yyyy-mm
    data_imputazione: Optional[str] = None  # yyyy-mm-dd, default 27 del mese


@router.post("/dipendenti/genera-stipendi")
async def genera_stipendi(body: GeneraStipendiIn, user: Dict = Depends(require_roles("admin", "contabilita"))):
    """Crea voce costo_personale per ogni dipendente attivo nel mese indicato. Idempotente.

    Controlla se esiste già un costo con categoria=personale + dipendente_nome + mese_riferimento
    con tipo_rapporto=stipendio: se sì, skip (non duplica).
    """
    import re
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", body.mese_riferimento):
        raise HTTPException(400, "mese_riferimento deve essere yyyy-mm")
    data_imp = body.data_imputazione or f"{body.mese_riferimento}-27"
    tenant_id = tenant_id_of(user)
    attivi = await db.dipendenti.find(
        {"tenant_id": tenant_id, "attivo": True}, {"_id": 0}
    ).to_list(500)

    creati: List[Dict] = []
    skippati: List[str] = []
    for d in attivi:
        stip = float(d.get("stipendio_mensile") or 0)
        if stip <= 0:
            continue
        # Check duplicato
        exists = await db.costi.find_one({
            "tenant_id": tenant_id,
            "categoria": "personale",
            "mese_riferimento": body.mese_riferimento,
            "dipendente_nome": d["nome"],
            "tipo_rapporto": "stipendio",
        }, {"_id": 0})
        if exists:
            skippati.append(d["nome"])
            continue
        costo = {
            "id": new_id(),
            "tenant_id": tenant_id,
            "categoria": "personale",
            "data": data_imp,
            "mese_riferimento": body.mese_riferimento,
            "descrizione": f"Stipendio {d['nome']} · {body.mese_riferimento}",
            "importo": stip,
            "dipendente_id": d["id"],
            "dipendente_nome": d["nome"],
            "ore_lavorate": d.get("ore_contrattuali"),
            "tipo_rapporto": "stipendio",
            "note": "Generato automaticamente",
            "created_at": now_utc(),
            "updated_at": now_utc(),
        }
        await db.costi.insert_one(costo)
        costo.pop("_id", None)
        creati.append({"dipendente": d["nome"], "importo": stip, "costo_id": costo["id"]})

    await log_audit(user, "CREATE", "stipendi_batch", body.mese_riferimento,
                    {"n_creati": len(creati), "n_skippati": len(skippati)})
    return {
        "mese_riferimento": body.mese_riferimento,
        "data_imputazione": data_imp,
        "n_creati": len(creati),
        "n_skippati": len(skippati),
        "creati": creati,
        "skippati": skippati,
    }


# ============== AUTOMEZZI ==============

@router.get("/automezzi")
async def list_auto(attivo: Optional[bool] = None, user: Dict = Depends(get_current_user)):
    q: Dict = dict(tenant_scope(user))
    if attivo is not None:
        q["attivo"] = attivo
    return await db.automezzi.find(q, {"_id": 0}).sort("targa", 1).to_list(500)


@router.post("/automezzi")
async def create_auto(body: AutomezzoIn, user: Dict = Depends(require_roles("admin", "contabilita"))):
    # targa unica per tenant
    dup = await db.automezzi.find_one(merge_scope(user, {"targa": body.targa}), {"_id": 0})
    if dup:
        raise HTTPException(409, f"Targa {body.targa} già presente")
    doc = body.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = now_utc()
    doc["updated_at"] = doc["created_at"]
    inject_tenant(doc, user)
    await db.automezzi.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "automezzo", doc["id"], {"targa": body.targa})
    return doc


@router.patch("/automezzi/{aid}")
async def patch_auto(aid: str, body: PatchAutomezzoIn, user: Dict = Depends(require_roles("admin", "contabilita"))):
    data = body.model_dump(exclude_unset=True)
    if not data:
        return {"ok": True}
    data["updated_at"] = now_utc()
    res = await db.automezzi.update_one(merge_scope(user, {"id": aid}), {"$set": data})
    if res.matched_count == 0:
        raise HTTPException(404, "Automezzo non trovato")
    await log_audit(user, "UPDATE", "automezzo", aid, data)
    return {"ok": True}


@router.delete("/automezzi/{aid}")
async def delete_auto(aid: str, user: Dict = Depends(require_roles("admin"))):
    res = await db.automezzi.delete_one(merge_scope(user, {"id": aid}))
    if res.deleted_count == 0:
        raise HTTPException(404, "Automezzo non trovato")
    await log_audit(user, "DELETE", "automezzo", aid)
    return {"ok": True}
