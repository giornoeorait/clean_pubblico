"""Fatturazione (ERP billing)."""
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends
from core import db, new_id, now_utc, get_current_user, require_roles, log_audit, next_seq
from schemas import FatturaIn

router = APIRouter(prefix="/fatture", tags=["billing"])


@router.get("")
async def list_fatture(user: Dict = Depends(get_current_user), cliente_id: Optional[str] = None, limit: int = 200):
    query: Dict[str, Any] = {}
    if cliente_id:
        query["cliente_id"] = cliente_id
    # Optional filter: if a "cliente" portal user is wired in future, restrict to their invoices.
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
    doc["created_at"] = now_utc().isoformat()
    await db.fatture.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "fattura", doc["id"])
    return doc


@router.patch("/{fid}")
async def update_fattura(fid: str, body: Dict[str, Any], user: Dict = Depends(require_roles("admin", "contabilita"))):
    body.pop("_id", None)
    body["updated_at"] = now_utc().isoformat()
    await db.fatture.update_one({"id": fid}, {"$set": body})
    await log_audit(user, "UPDATE", "fattura", fid, body)
    return {"ok": True}
