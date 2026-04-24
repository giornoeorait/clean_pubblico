"""Fornitori + DDT ricevuti + Fatture passive.

Flusso speculare a Clienti/DDT/Fatture ma per gli acquisti:
  Fornitori → DDT fornitore → Fattura fornitore (passiva).

Numerazione interna:
  - DDT fornitore: FORN-DDT-YYYY-NNNNN (contatore interno, NON il numero del fornitore)
  - Fattura fornitore: FORN-FT-YYYY-NNNNN
Tutti i documenti memorizzano `numero_fornitore` come riferimento originale ricevuto.
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException

from core import (
    db, new_id, now_utc, next_seq,
    get_current_user, require_roles,
    tenant_scope, merge_scope, tenant_id_of, inject_tenant, log_audit,
)
from schemas import (
    FornitoreIn, PatchFornitoreIn,
    DdtFornitoreIn, PatchDdtFornitoreIn,
    FatturaFornitoreIn, PatchFatturaFornitoreIn,
)

router = APIRouter(tags=["fornitori"])


# ---------- Helpers ----------
def _calc_righe(righe: List) -> float:
    return round(sum(float(r.quantita) * float(r.prezzo_unitario) for r in righe), 2)


def _righe_to_docs(righe: List) -> List[Dict]:
    out = []
    for r in righe:
        tot = round(float(r.quantita) * float(r.prezzo_unitario), 2)
        out.append({
            "descrizione": r.descrizione,
            "quantita": float(r.quantita),
            "unita_misura": r.unita_misura,
            "prezzo_unitario": round(float(r.prezzo_unitario), 4),
            "totale": tot,
        })
    return out


async def _fornitore_or_404(tenant_id: str, fid: str) -> Dict:
    f = await db.fornitori.find_one({"tenant_id": tenant_id, "id": fid}, {"_id": 0})
    if not f:
        raise HTTPException(404, "Fornitore non trovato")
    return f


def _forn_snapshot(f: Dict) -> Dict:
    return {k: f.get(k, "") for k in ("ragione_sociale", "partita_iva", "indirizzo", "email", "telefono", "codice_sdi", "pec", "iban")}


# ======================== FORNITORI CRUD ========================

@router.get("/fornitori")
async def list_fornitori(q: Optional[str] = None, categoria: Optional[str] = None, limit: int = 500,
                         user: Dict = Depends(get_current_user)):
    query: Dict = dict(tenant_scope(user))
    if categoria:
        query["categoria"] = categoria
    if q:
        query["$or"] = [
            {"ragione_sociale": {"$regex": q, "$options": "i"}},
            {"partita_iva": {"$regex": q, "$options": "i"}},
        ]
    return await db.fornitori.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)


@router.post("/fornitori")
async def create_fornitore(body: FornitoreIn, user: Dict = Depends(require_roles("admin", "contabilita"))):
    doc = body.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = now_utc()
    doc["updated_at"] = doc["created_at"]
    inject_tenant(doc, user)
    await db.fornitori.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "fornitore", doc["id"])
    return doc


@router.get("/fornitori/{fid}")
async def get_fornitore(fid: str, user: Dict = Depends(get_current_user)):
    return await _fornitore_or_404(tenant_id_of(user), fid)


@router.patch("/fornitori/{fid}")
async def patch_fornitore(fid: str, body: PatchFornitoreIn,
                          user: Dict = Depends(require_roles("admin", "contabilita"))):
    data = body.model_dump(exclude_unset=True)
    if not data:
        return {"ok": True}
    data["updated_at"] = now_utc()
    res = await db.fornitori.update_one(merge_scope(user, {"id": fid}), {"$set": data})
    if res.matched_count == 0:
        raise HTTPException(404, "Fornitore non trovato")
    await log_audit(user, "UPDATE", "fornitore", fid, data)
    return {"ok": True}


@router.delete("/fornitori/{fid}")
async def delete_fornitore(fid: str, user: Dict = Depends(require_roles("admin"))):
    # Verifica assenza documenti collegati
    n_ddt = await db.ddt_fornitore.count_documents(merge_scope(user, {"fornitore_id": fid}))
    n_ft = await db.fatture_fornitore.count_documents(merge_scope(user, {"fornitore_id": fid}))
    if n_ddt or n_ft:
        raise HTTPException(409, f"Fornitore ha documenti collegati: {n_ddt} DDT, {n_ft} fatture")
    await db.fornitori.delete_one(merge_scope(user, {"id": fid}))
    await log_audit(user, "DELETE", "fornitore", fid)
    return {"ok": True}


@router.get("/fornitori/{fid}/profilo")
async def fornitore_profilo(fid: str, user: Dict = Depends(get_current_user)):
    tenant_id = tenant_id_of(user)
    f = await _fornitore_or_404(tenant_id, fid)
    ddts = await db.ddt_fornitore.find(
        {"tenant_id": tenant_id, "fornitore_id": fid}, {"_id": 0}
    ).sort("data", -1).to_list(500)
    fatture = await db.fatture_fornitore.find(
        {"tenant_id": tenant_id, "fornitore_id": fid}, {"_id": 0}
    ).sort("data", -1).to_list(500)
    tot_spesa = sum(ft.get("totale", 0) for ft in fatture)
    tot_pagato = sum(ft.get("totale", 0) for ft in fatture if ft.get("stato_pagamento") == "pagata")
    tot_da_pagare = sum(ft.get("totale", 0) for ft in fatture if ft.get("stato_pagamento") == "da_pagare")
    return {
        "fornitore": f,
        "ddts": ddts,
        "fatture": fatture,
        "stats": {
            "ddt_totali": len(ddts),
            "fatture_totali": len(fatture),
            "spesa_totale": round(tot_spesa, 2),
            "pagato_totale": round(tot_pagato, 2),
            "da_pagare_totale": round(tot_da_pagare, 2),
        },
    }


# ======================== DDT FORNITORE CRUD ========================

@router.get("/ddt-fornitore")
async def list_ddt_forn(fornitore_id: Optional[str] = None, limit: int = 300,
                        user: Dict = Depends(get_current_user)):
    query: Dict = dict(tenant_scope(user))
    if fornitore_id:
        query["fornitore_id"] = fornitore_id
    return await db.ddt_fornitore.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)


@router.post("/ddt-fornitore")
async def create_ddt_forn(body: DdtFornitoreIn,
                          user: Dict = Depends(require_roles("admin", "logistica", "contabilita"))):
    tenant_id = tenant_id_of(user)
    if not body.righe:
        raise HTTPException(400, "Almeno una riga obbligatoria")
    f = await _fornitore_or_404(tenant_id, body.fornitore_id)
    seq = await next_seq("ddt_fornitore")
    numero = f"FORN-DDT-{datetime.now(timezone.utc).year}-{seq:05d}"
    righe = _righe_to_docs(body.righe)
    tot = round(sum(r["totale"] for r in righe), 2)
    doc = {
        "id": new_id(),
        "tenant_id": tenant_id,
        "numero": numero,
        "fornitore_id": f["id"],
        "fornitore_snapshot": _forn_snapshot(f),
        "numero_fornitore": body.numero_fornitore,
        "data": body.data,
        "righe": righe,
        "totale": tot,
        "note": body.note or "",
        "stato_fatturazione": "non_fatturato",
        "fattura_fornitore_id": None,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    await db.ddt_fornitore.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "ddt_fornitore", doc["id"], {"numero": numero})
    return doc


@router.patch("/ddt-fornitore/{did}")
async def patch_ddt_forn(did: str, body: PatchDdtFornitoreIn,
                         user: Dict = Depends(require_roles("admin", "logistica", "contabilita"))):
    cur = await db.ddt_fornitore.find_one(merge_scope(user, {"id": did}), {"_id": 0})
    if not cur:
        raise HTTPException(404, "DDT non trovato")
    if cur.get("stato_fatturazione") == "fatturato":
        raise HTTPException(409, "DDT già collegato a fattura")
    data = body.model_dump(exclude_unset=True)
    patch: Dict = {"updated_at": now_utc()}
    if "righe" in data and body.righe is not None:
        righe = _righe_to_docs(body.righe)
        patch["righe"] = righe
        patch["totale"] = round(sum(r["totale"] for r in righe), 2)
    for k in ("numero_fornitore", "data", "note"):
        if k in data:
            patch[k] = data[k]
    await db.ddt_fornitore.update_one(merge_scope(user, {"id": did}), {"$set": patch})
    await log_audit(user, "UPDATE", "ddt_fornitore", did, patch)
    return await db.ddt_fornitore.find_one(merge_scope(user, {"id": did}), {"_id": 0})


@router.delete("/ddt-fornitore/{did}")
async def delete_ddt_forn(did: str, user: Dict = Depends(require_roles("admin", "contabilita"))):
    cur = await db.ddt_fornitore.find_one(merge_scope(user, {"id": did}), {"_id": 0})
    if not cur:
        raise HTTPException(404, "DDT non trovato")
    if cur.get("stato_fatturazione") == "fatturato":
        raise HTTPException(409, "DDT collegato a fattura — impossibile eliminare")
    await db.ddt_fornitore.delete_one(merge_scope(user, {"id": did}))
    await log_audit(user, "DELETE", "ddt_fornitore", did)
    return {"ok": True}


# ======================== FATTURE FORNITORE CRUD ========================

@router.get("/fatture-fornitore")
async def list_ft_forn(
    fornitore_id: Optional[str] = None, stato_pagamento: Optional[str] = None,
    limit: int = 300, user: Dict = Depends(get_current_user),
):
    query: Dict = dict(tenant_scope(user))
    if fornitore_id:
        query["fornitore_id"] = fornitore_id
    if stato_pagamento:
        query["stato_pagamento"] = stato_pagamento
    return await db.fatture_fornitore.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)


@router.get("/fatture-fornitore/ddt-fatturabili/{fornitore_id}")
async def ddt_fatturabili(fornitore_id: str, user: Dict = Depends(get_current_user)):
    """DDT fornitore non ancora inclusi in una fattura passiva."""
    return await db.ddt_fornitore.find(
        merge_scope(user, {"fornitore_id": fornitore_id, "stato_fatturazione": "non_fatturato"}),
        {"_id": 0},
    ).sort("data", -1).to_list(500)


@router.post("/fatture-fornitore")
async def create_ft_forn(body: FatturaFornitoreIn,
                         user: Dict = Depends(require_roles("admin", "contabilita"))):
    tenant_id = tenant_id_of(user)
    f = await _fornitore_or_404(tenant_id, body.fornitore_id)

    # Se ddt_fornitore_ids passati: aggrega le loro righe, verifica tenant + non fatturati
    ddt_docs: List[Dict] = []
    righe_agg: List[Dict] = []
    if body.ddt_fornitore_ids:
        async for d in db.ddt_fornitore.find(
            {"tenant_id": tenant_id, "id": {"$in": body.ddt_fornitore_ids}, "fornitore_id": f["id"]},
            {"_id": 0},
        ):
            if d.get("stato_fatturazione") == "fatturato":
                raise HTTPException(409, f"DDT {d.get('numero')} già fatturato")
            ddt_docs.append(d)
            righe_agg.extend(d.get("righe", []))
        if len(ddt_docs) != len(body.ddt_fornitore_ids):
            raise HTTPException(400, "Alcuni DDT non trovati o di altro fornitore")
    # Altrimenti usa righe inline
    if body.righe:
        righe_agg.extend(_righe_to_docs(body.righe))

    if not righe_agg:
        raise HTTPException(400, "La fattura deve contenere almeno una riga o un DDT")

    imponibile = round(sum(r.get("totale", 0) for r in righe_agg), 2)
    iva = round(imponibile * (body.iva_perc / 100.0), 2)
    totale = round(imponibile + iva, 2)

    seq = await next_seq("fattura_fornitore")
    numero = f"FORN-FT-{datetime.now(timezone.utc).year}-{seq:05d}"

    doc = {
        "id": new_id(),
        "tenant_id": tenant_id,
        "numero": numero,
        "fornitore_id": f["id"],
        "fornitore_snapshot": _forn_snapshot(f),
        "numero_fornitore": body.numero_fornitore,
        "data": body.data,
        "data_scadenza": body.data_scadenza,
        "ddt_fornitore_ids": [d["id"] for d in ddt_docs],
        "ddt_fornitore_numeri": [d.get("numero") for d in ddt_docs],
        "righe": righe_agg,
        "imponibile": imponibile,
        "iva_perc": body.iva_perc,
        "iva": iva,
        "totale": totale,
        "stato_pagamento": "da_pagare",
        "data_pagamento": None,
        "note": body.note or "",
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    await db.fatture_fornitore.insert_one(doc)
    # Marca i DDT come fatturati
    if ddt_docs:
        await db.ddt_fornitore.update_many(
            {"tenant_id": tenant_id, "id": {"$in": [d["id"] for d in ddt_docs]}},
            {"$set": {
                "stato_fatturazione": "fatturato",
                "fattura_fornitore_id": doc["id"],
                "fattura_fornitore_numero": numero,
                "updated_at": now_utc(),
            }},
        )
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "fattura_fornitore", doc["id"], {"numero": numero})
    return doc


@router.patch("/fatture-fornitore/{fid}")
async def patch_ft_forn(fid: str, body: PatchFatturaFornitoreIn,
                        user: Dict = Depends(require_roles("admin", "contabilita"))):
    cur = await db.fatture_fornitore.find_one(merge_scope(user, {"id": fid}), {"_id": 0})
    if not cur:
        raise HTTPException(404, "Fattura non trovata")
    data = body.model_dump(exclude_unset=True)
    patch: Dict = {"updated_at": now_utc()}
    if "righe" in data and body.righe is not None:
        if cur.get("ddt_fornitore_ids"):
            raise HTTPException(409, "Impossibile modificare righe: fattura generata da DDT")
        righe = _righe_to_docs(body.righe)
        patch["righe"] = righe
        imponibile = round(sum(r["totale"] for r in righe), 2)
        iva_perc = data.get("iva_perc", cur.get("iva_perc", 22.0))
        iva = round(imponibile * (iva_perc / 100.0), 2)
        patch["imponibile"] = imponibile
        patch["iva"] = iva
        patch["totale"] = round(imponibile + iva, 2)
    for k in ("numero_fornitore", "data", "data_scadenza", "note", "iva_perc"):
        if k in data and k not in patch:
            patch[k] = data[k]
    # Se iva_perc cambia e non abbiamo ricalcolato sopra (caso DDT-linked), ricalcola iva/totale
    if "iva_perc" in data and "iva" not in patch:
        imponibile = cur.get("imponibile", 0)
        new_iva = round(imponibile * (float(data["iva_perc"]) / 100.0), 2)
        patch["iva"] = new_iva
        patch["totale"] = round(imponibile + new_iva, 2)
    if "stato_pagamento" in data:
        patch["stato_pagamento"] = data["stato_pagamento"]
        if data["stato_pagamento"] == "pagata":
            patch["data_pagamento"] = now_utc()
        elif data["stato_pagamento"] == "da_pagare":
            patch["data_pagamento"] = None
    await db.fatture_fornitore.update_one(merge_scope(user, {"id": fid}), {"$set": patch})
    await log_audit(user, "UPDATE", "fattura_fornitore", fid, patch)
    return await db.fatture_fornitore.find_one(merge_scope(user, {"id": fid}), {"_id": 0})


@router.patch("/fatture-fornitore/{fid}/paga")
async def paga_ft_forn(fid: str, user: Dict = Depends(require_roles("admin", "contabilita"))):
    cur = await db.fatture_fornitore.find_one(merge_scope(user, {"id": fid}), {"_id": 0})
    if not cur:
        raise HTTPException(404, "Fattura non trovata")
    if cur.get("stato_pagamento") == "pagata":
        raise HTTPException(409, "Già contrassegnata pagata")
    await db.fatture_fornitore.update_one(merge_scope(user, {"id": fid}), {"$set": {
        "stato_pagamento": "pagata",
        "data_pagamento": now_utc(),
        "updated_at": now_utc(),
    }})
    await log_audit(user, "PAY", "fattura_fornitore", fid)
    return await db.fatture_fornitore.find_one(merge_scope(user, {"id": fid}), {"_id": 0})


@router.delete("/fatture-fornitore/{fid}")
async def delete_ft_forn(fid: str, user: Dict = Depends(require_roles("admin"))):
    cur = await db.fatture_fornitore.find_one(merge_scope(user, {"id": fid}), {"_id": 0})
    if not cur:
        raise HTTPException(404, "Fattura non trovata")
    # Riapri i DDT collegati
    if cur.get("ddt_fornitore_ids"):
        await db.ddt_fornitore.update_many(
            merge_scope(user, {"id": {"$in": cur["ddt_fornitore_ids"]}}),
            {"$set": {
                "stato_fatturazione": "non_fatturato",
                "fattura_fornitore_id": None,
                "fattura_fornitore_numero": None,
                "updated_at": now_utc(),
            }},
        )
    await db.fatture_fornitore.delete_one(merge_scope(user, {"id": fid}))
    await log_audit(user, "DELETE", "fattura_fornitore", fid)
    return {"ok": True}
