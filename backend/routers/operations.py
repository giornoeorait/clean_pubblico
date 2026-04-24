"""Operations: Ritiri, Consegne (solo — lotti/MES/qualità rimossi nel refactor ERP/DDT)."""
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from core import (
    db, new_id, now_utc, to_dt,
    get_current_user, require_roles, log_audit, next_seq,
    tenant_scope, merge_scope, inject_tenant,
)
from schemas import RitiroIn, ConsegnaIn, PatchConsegnaIn
from notifications import send_notification

router = APIRouter(tags=["operations"])


@router.get("/ritiri")
async def list_ritiri(user: Dict = Depends(get_current_user), limit: int = 200):
    return await db.ritiri.find(tenant_scope(user), {"_id": 0}).sort("created_at", -1).to_list(limit)


@router.post("/ritiri")
async def create_ritiro(body: RitiroIn, user: Dict = Depends(require_roles("admin", "logistica", "produzione"))):
    doc = body.model_dump()
    doc["id"] = new_id()
    seq = await next_seq("ritiro")
    doc["numero"] = f"RIT-{datetime.now().year}-{seq:05d}"
    doc["stato"] = "creato"
    doc["data_ritiro"] = to_dt(doc.get("data_ritiro")) or now_utc()
    doc["created_at"] = now_utc()
    inject_tenant(doc, user)
    await db.ritiri.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "ritiro", doc["id"])
    return doc


@router.get("/ritiri/{rid}")
async def get_ritiro(rid: str, user: Dict = Depends(get_current_user)):
    doc = await db.ritiri.find_one(merge_scope(user, {"id": rid}), {"_id": 0})
    if not doc:
        raise HTTPException(404, "Ritiro non trovato")
    return doc


# --- Consegne (logistica) -------------------------------------------------
@router.get("/consegne")
async def list_consegne(user: Dict = Depends(get_current_user), limit: int = 200):
    query: Dict[str, Any] = dict(tenant_scope(user))
    if user["role"] == "cliente" and user.get("cliente_id"):
        query["cliente_id"] = user["cliente_id"]
    return await db.consegne.find(query, {"_id": 0}).sort("data_prevista", -1).to_list(limit)


@router.post("/consegne")
async def create_consegna(body: ConsegnaIn, user: Dict = Depends(require_roles("admin", "logistica"))):
    doc = body.model_dump()
    doc["id"] = new_id()
    seq = await next_seq("consegna")
    doc["numero"] = f"CON-{datetime.now().year}-{seq:05d}"
    doc["stato"] = "pianificata"
    doc["data_prevista"] = to_dt(doc.get("data_prevista")) or now_utc()
    doc["created_at"] = now_utc()
    inject_tenant(doc, user)
    await db.consegne.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "consegna", doc["id"])
    return doc


@router.patch("/consegne/{cid}")
async def update_consegna(cid: str, body: PatchConsegnaIn, user: Dict = Depends(require_roles("admin", "logistica"))):
    data = body.model_dump(exclude_unset=True)
    if not data:
        return {"ok": True}
    for f in ("data_prevista", "data_consegna_effettiva"):
        if f in data and data[f] is not None:
            dt = to_dt(data[f])
            if dt is not None:
                data[f] = dt
    data["updated_at"] = now_utc()
    if data.get("stato") == "consegnata" and "data_consegna_effettiva" not in data:
        data["data_consegna_effettiva"] = now_utc()
    await db.consegne.update_one(merge_scope(user, {"id": cid}), {"$set": data})
    await log_audit(user, "UPDATE", "consegna", cid, {"stato": data.get("stato")})

    new_stato = data.get("stato")
    if new_stato in ("in_transito", "consegnata"):
        try:
            consegna = await db.consegne.find_one(merge_scope(user, {"id": cid}), {"_id": 0})
            if consegna and consegna.get("cliente_id"):
                cliente = await db.clienti.find_one(merge_scope(user, {"id": consegna["cliente_id"]}), {"_id": 0})
                phone = (cliente or {}).get("telefono", "").strip()
                if phone and phone.startswith("+"):
                    tpl = "consegna_in_transito" if new_stato == "in_transito" else "consegna_completata"
                    nome = (cliente or {}).get("ragione_sociale", "")
                    msg = {
                        "consegna_in_transito": f"Ciao {nome}! La tua consegna {consegna.get('numero')} è in transito. - CleanTec",
                        "consegna_completata": f"Consegna {consegna.get('numero')} effettuata con successo. Grazie! - CleanTec",
                    }[tpl]
                    await send_notification(
                        kind="sms", to=phone, body=msg,
                        context={"cliente_id": consegna["cliente_id"], "consegna_id": cid, "trigger": tpl, "tenant_id": user["tenant_id"]},
                        user=user,
                    )
        except Exception:
            pass
    return {"ok": True}
