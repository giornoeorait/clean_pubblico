"""Costi — FASE 4.

Categorie: personale | automezzi | utenze | prodotti.
Struttura flessibile: una sola collection `costi`, campi opzionali per categoria.
Include aggregazioni per dashboard/report (sommario per categoria + per mese).
"""
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException

from core import (
    db, new_id, now_utc,
    get_current_user, require_roles, require_permission,
    tenant_scope, merge_scope, tenant_id_of, inject_tenant, log_audit,
)
from schemas import CostoIn, PatchCostoIn

router = APIRouter(tags=["costi"])

VALID_CAT = {"personale", "automezzi", "utenze", "prodotti"}


@router.get("/costi")
async def list_costi(
    categoria: Optional[str] = None,
    mese_riferimento: Optional[str] = None,  # yyyy-mm
    anno: Optional[int] = None,
    fornitore_id: Optional[str] = None,
    limit: int = 1000,
    user: Dict = Depends(require_permission("costi", "view")),
):
    query: Dict = dict(tenant_scope(user))
    if categoria:
        if categoria not in VALID_CAT:
            raise HTTPException(400, f"Categoria non valida. Ammesse: {sorted(VALID_CAT)}")
        query["categoria"] = categoria
    if mese_riferimento:
        query["mese_riferimento"] = mese_riferimento
    elif anno:
        query["mese_riferimento"] = {"$regex": f"^{anno}-"}
    if fornitore_id:
        query["fornitore_id"] = fornitore_id
    return await db.costi.find(query, {"_id": 0}).sort("data", -1).to_list(limit)


@router.post("/costi")
async def create_costo(body: CostoIn, user: Dict = Depends(require_roles("admin", "contabilita"))):
    if body.categoria not in VALID_CAT:
        raise HTTPException(400, f"Categoria non valida. Ammesse: {sorted(VALID_CAT)}")
    # Verifica fornitore_id se fornito
    if body.fornitore_id:
        f = await db.fornitori.find_one(merge_scope(user, {"id": body.fornitore_id}), {"_id": 0})
        if not f:
            raise HTTPException(400, "Fornitore non trovato")
    doc = body.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = now_utc()
    doc["updated_at"] = doc["created_at"]
    inject_tenant(doc, user)
    await db.costi.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "costo", doc["id"], {"categoria": body.categoria, "importo": body.importo})
    return doc


@router.get("/costi/summary")
async def summary_costi(
    anno: Optional[int] = None,
    mese_riferimento: Optional[str] = None,
    user: Dict = Depends(require_permission("costi", "view")),
):
    """Aggregato: totale per categoria + totale per mese nell'anno selezionato."""
    match: Dict = dict(tenant_scope(user))
    if mese_riferimento:
        match["mese_riferimento"] = mese_riferimento
    elif anno:
        match["mese_riferimento"] = {"$regex": f"^{anno}-"}

    # Somma per categoria
    pipeline_cat = [
        {"$match": match},
        {"$group": {"_id": "$categoria", "totale": {"$sum": "$importo"}, "n": {"$sum": 1}}},
    ]
    by_cat: Dict[str, Dict] = {}
    async for r in db.costi.aggregate(pipeline_cat):
        by_cat[r["_id"]] = {"totale": round(r["totale"], 2), "n": r["n"]}

    # Somma per mese (ordinata)
    pipeline_mese = [
        {"$match": match},
        {"$group": {"_id": "$mese_riferimento", "totale": {"$sum": "$importo"}, "n": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    by_mese: List[Dict] = []
    async for r in db.costi.aggregate(pipeline_mese):
        by_mese.append({"mese": r["_id"], "totale": round(r["totale"], 2), "n": r["n"]})

    # Somma per categoria+mese (per grafico impilato)
    pipeline_stack = [
        {"$match": match},
        {"$group": {"_id": {"mese": "$mese_riferimento", "cat": "$categoria"}, "totale": {"$sum": "$importo"}}},
        {"$sort": {"_id.mese": 1}},
    ]
    stack: List[Dict] = []
    async for r in db.costi.aggregate(pipeline_stack):
        stack.append({"mese": r["_id"]["mese"], "categoria": r["_id"]["cat"], "totale": round(r["totale"], 2)})

    totale_gen = round(sum(c["totale"] for c in by_cat.values()), 2)
    return {
        "totale_generale": totale_gen,
        "per_categoria": {c: by_cat.get(c, {"totale": 0.0, "n": 0}) for c in VALID_CAT},
        "per_mese": by_mese,
        "stack": stack,
    }


@router.get("/costi/{cid}")
async def get_costo(cid: str, user: Dict = Depends(require_permission("costi", "view"))):
    doc = await db.costi.find_one(merge_scope(user, {"id": cid}), {"_id": 0})
    if not doc:
        raise HTTPException(404, "Costo non trovato")
    return doc


@router.patch("/costi/{cid}")
async def update_costo(cid: str, body: PatchCostoIn, user: Dict = Depends(require_roles("admin", "contabilita"))):
    data = body.model_dump(exclude_unset=True)
    if not data:
        return {"ok": True}
    if data.get("categoria") and data["categoria"] not in VALID_CAT:
        raise HTTPException(400, f"Categoria non valida. Ammesse: {sorted(VALID_CAT)}")
    if data.get("fornitore_id"):
        f = await db.fornitori.find_one(merge_scope(user, {"id": data["fornitore_id"]}), {"_id": 0})
        if not f:
            raise HTTPException(400, "Fornitore non trovato")
    data["updated_at"] = now_utc()
    res = await db.costi.update_one(merge_scope(user, {"id": cid}), {"$set": data})
    if res.matched_count == 0:
        raise HTTPException(404, "Costo non trovato")
    await log_audit(user, "UPDATE", "costo", cid, data)
    return {"ok": True}


@router.delete("/costi/{cid}")
async def delete_costo(cid: str, user: Dict = Depends(require_roles("admin", "contabilita"))):
    res = await db.costi.delete_one(merge_scope(user, {"id": cid}))
    if res.deleted_count == 0:
        raise HTTPException(404, "Costo non trovato")
    await log_audit(user, "DELETE", "costo", cid)
    return {"ok": True}
