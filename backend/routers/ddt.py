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
    quantita: int = Field(..., gt=0)
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
    docs = await db.ddt.find(q, {"_id": 0}).sort("data", -1).to_list(limit)
    return await _enrich_cliente_denominazione(docs, user)


async def _enrich_cliente_denominazione(docs: list, user: Dict) -> list:
    """Add `cliente_denominazione` on each doc by joining with db.clienti (legacy data fix)."""
    missing_ids = list({d.get("cliente_id") for d in docs
                       if d.get("cliente_id") and not d.get("cliente_denominazione")})
    if not missing_ids:
        return docs
    cur = db.clienti.find(
        {"tenant_id": user["tenant_id"], "id": {"$in": missing_ids}},
        {"_id": 0, "id": 1, "denominazione_struttura": 1},
    )
    by_id: Dict[str, str] = {}
    async for c in cur:
        by_id[c["id"]] = c.get("denominazione_struttura") or ""
    for d in docs:
        if not d.get("cliente_denominazione"):
            d["cliente_denominazione"] = by_id.get(d.get("cliente_id"), "")
    return docs


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
    from core import format_numero
    doc = {
        "id": new_id(),
        "numero": await format_numero("ddt", "DDT", seq),
        "cliente_id": body.cliente_id,
        "cliente_nome": cliente.get("ragione_sociale", ""),
        "cliente_denominazione": cliente.get("denominazione_struttura", ""),
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


@router.get("/{did}/pdf")
async def ddt_pdf(did: str, user: Dict = Depends(get_current_user)):
    from fastapi import Response
    from pdf_service import generate_ddt_pdf
    from routers.company import load_company_for_tenant
    ddt_doc = await db.ddt.find_one(merge_scope(user, {"id": did}), {"_id": 0})
    if not ddt_doc:
        raise HTTPException(404, "DDT non trovato")
    cliente = await db.clienti.find_one(merge_scope(user, {"id": ddt_doc["cliente_id"]}), {"_id": 0}) or {}
    company = await load_company_for_tenant(user["tenant_id"])
    pdf = generate_ddt_pdf(ddt_doc, cliente, company)
    filename = f"{ddt_doc.get('numero', 'DDT')}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


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

    # Se questo DDT è stato generato da un ordinativo, riportiamo l'ordinativo a "nuovo"
    # in modo che torni editabile dall'utente.
    linked_ord = await db.ordinativi.find_one(
        merge_scope(user, {"ddt_id": did}), {"_id": 0, "id": 1, "numero": 1}
    )
    if linked_ord:
        await db.ordinativi.update_one(
            {"id": linked_ord["id"], "tenant_id": existing.get("tenant_id")},
            {"$set": {"stato": "nuovo", "ddt_id": None, "ddt_numero": None, "updated_at": now_utc()}},
        )

    await log_audit(user, "DELETE", "ddt", did, {"reverted_ordinativo": (linked_ord or {}).get("numero")})
    return {"ok": True, "reverted_ordinativo": (linked_ord or {}).get("numero")}
