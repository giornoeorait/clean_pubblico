"""Fatturazione (ERP billing)."""
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends
from core import db, new_id, now_utc, to_dt, get_current_user, require_roles, log_audit, next_seq, tenant_scope, merge_scope, inject_tenant
from schemas import FatturaIn, PatchFatturaIn

router = APIRouter(prefix="/fatture", tags=["billing"])


@router.get("")
async def list_fatture(user: Dict = Depends(get_current_user), cliente_id: Optional[str] = None, limit: int = 200):
    query: Dict[str, Any] = dict(tenant_scope(user))
    if cliente_id:
        query["cliente_id"] = cliente_id
    if user["role"] == "cliente" and user.get("cliente_id"):
        query["cliente_id"] = user["cliente_id"]
    return await db.fatture.find(query, {"_id": 0}).sort("data", -1).to_list(limit)


@router.post("")
async def create_fattura(body: FatturaIn, user: Dict = Depends(require_roles("admin", "contabilita"))):
    doc = body.model_dump()
    doc["id"] = new_id()
    seq = await next_seq("fattura")
    doc["numero"] = f"FT-{datetime.now().year}-{seq:05d}"
    imponibile = sum(r.get("totale", r.get("quantita", 0) * r.get("prezzo", 0)) for r in doc["righe"])
    iva = imponibile * doc["iva_pct"] / 100
    doc["imponibile"] = round(imponibile, 2)
    doc["iva"] = round(iva, 2)
    doc["totale"] = round(imponibile + iva, 2)
    doc["stato"] = "bozza"
    doc["data"] = to_dt(doc.get("data")) or now_utc()
    if doc.get("scadenza"):
        doc["scadenza"] = to_dt(doc["scadenza"])
    doc["created_at"] = now_utc()
    inject_tenant(doc, user)
    await db.fatture.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "fattura", doc["id"])
    return doc


@router.patch("/{fid}")
async def update_fattura(fid: str, body: PatchFatturaIn, user: Dict = Depends(require_roles("admin", "contabilita"))):
    data = body.model_dump(exclude_unset=True)
    if not data:
        return {"ok": True}
    for f in ("data", "scadenza"):
        if f in data and data[f] is not None:
            dt = to_dt(data[f])
            if dt is not None:
                data[f] = dt
    data["updated_at"] = now_utc()
    await db.fatture.update_one(merge_scope(user, {"id": fid}), {"$set": data})
    await log_audit(user, "UPDATE", "fattura", fid, {"stato": data.get("stato")})
    return {"ok": True}
