"""Operations: Ritiri, Lotti (traceability), Lavorazioni, Consegne, Non-conformità."""
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from core import (
    db, new_id, now_utc, STATI_LOTTO,
    get_current_user, require_roles, log_audit, next_seq,
)
from schemas import (
    RitiroIn, LottoIn, CambiaStatoIn, LavorazioneIn, ConsegnaIn, NonConformitaIn,
    PatchConsegnaIn, PatchLavorazioneIn, PatchNonConformitaIn,
)

router = APIRouter(tags=["operations"])


# ---- Ritiri --------------------------------------------------------------
@router.get("/ritiri")
async def list_ritiri(user: Dict = Depends(get_current_user), limit: int = 200):
    return await db.ritiri.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)


@router.post("/ritiri")
async def create_ritiro(body: RitiroIn, user: Dict = Depends(require_roles("admin", "logistica", "produzione"))):
    doc = body.model_dump()
    doc["id"] = new_id()
    seq = await next_seq("ritiro")
    doc["numero"] = f"RIT-{datetime.now().year}-{seq:05d}"
    doc["stato"] = "creato"
    doc["created_at"] = now_utc().isoformat()
    await db.ritiri.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "ritiro", doc["id"])
    return doc


@router.get("/ritiri/{rid}")
async def get_ritiro(rid: str, user: Dict = Depends(get_current_user)):
    doc = await db.ritiri.find_one({"id": rid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Ritiro non trovato")
    doc["lotti"] = await db.lotti.find({"ritiro_id": rid}, {"_id": 0}).to_list(1000)
    return doc


# ---- Lotti (tracciabilità) -----------------------------------------------
@router.get("/lotti")
async def list_lotti(
    user: Dict = Depends(get_current_user),
    stato: Optional[str] = None,
    cliente_id: Optional[str] = None,
    limit: int = 500,
):
    query: Dict[str, Any] = {}
    if stato:
        query["stato_corrente"] = stato
    if cliente_id:
        query["cliente_id"] = cliente_id
    return await db.lotti.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)


@router.post("/lotti")
async def create_lotto(body: LottoIn, user: Dict = Depends(require_roles("admin", "produzione", "logistica"))):
    doc = body.model_dump()
    doc["id"] = new_id()
    seq = await next_seq("lotto")
    doc["numero"] = f"LOT-{datetime.now().year}-{seq:06d}"
    doc["stato_corrente"] = "ritirato"
    doc["storico_stati"] = [{
        "stato": "ritirato",
        "timestamp": now_utc().isoformat(),
        "operatore": user["name"],
        "note": "Creato all'accettazione",
        "esito": "ok",
    }]
    doc["created_at"] = now_utc().isoformat()
    await db.lotti.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "lotto", doc["id"])
    return doc


@router.post("/lotti/{lid}/cambia-stato")
async def cambia_stato_lotto(
    lid: str,
    body: CambiaStatoIn,
    user: Dict = Depends(require_roles("admin", "produzione", "qualita", "logistica")),
):
    if body.nuovo_stato not in STATI_LOTTO:
        raise HTTPException(400, f"Stato non valido. Ammessi: {STATI_LOTTO}")
    lotto = await db.lotti.find_one({"id": lid})
    if not lotto:
        raise HTTPException(404, "Lotto non trovato")
    entry = {
        "stato": body.nuovo_stato,
        "timestamp": now_utc().isoformat(),
        "operatore": user["name"],
        "macchina_id": body.macchina_id,
        "note": body.note,
        "esito": body.esito,
    }
    await db.lotti.update_one(
        {"id": lid},
        {"$set": {"stato_corrente": body.nuovo_stato}, "$push": {"storico_stati": entry}},
    )
    await log_audit(user, "STATE_CHANGE", "lotto", lid, entry)
    return {"ok": True, "nuovo_stato": body.nuovo_stato}


@router.get("/lotti/{lid}")
async def get_lotto(lid: str, user: Dict = Depends(get_current_user)):
    doc = await db.lotti.find_one({"id": lid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Lotto non trovato")
    return doc


# ---- Lavorazioni (MES) ---------------------------------------------------
@router.get("/lavorazioni")
async def list_lavorazioni(user: Dict = Depends(get_current_user), stato: Optional[str] = None, limit: int = 500):
    query: Dict[str, Any] = {}
    if stato:
        query["stato"] = stato
    return await db.lavorazioni.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)


@router.post("/lavorazioni")
async def create_lavorazione(body: LavorazioneIn, user: Dict = Depends(require_roles("admin", "produzione"))):
    doc = body.model_dump()
    doc["id"] = new_id()
    doc["stato"] = "pending"
    doc["operatore_id"] = user["id"]
    doc["operatore_nome"] = user["name"]
    doc["created_at"] = now_utc().isoformat()
    await db.lavorazioni.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "lavorazione", doc["id"])
    return doc


@router.patch("/lavorazioni/{lid}")
async def update_lavorazione(lid: str, body: PatchLavorazioneIn, user: Dict = Depends(require_roles("admin", "produzione"))):
    data = body.model_dump(exclude_unset=True)
    if not data:
        return {"ok": True}
    data["updated_at"] = now_utc().isoformat()
    if data.get("stato") == "in_corso" and "inizio" not in data:
        data["inizio"] = now_utc().isoformat()
    if data.get("stato") == "completato" and "fine" not in data:
        data["fine"] = now_utc().isoformat()
    await db.lavorazioni.update_one({"id": lid}, {"$set": data})
    await log_audit(user, "UPDATE", "lavorazione", lid, data)
    return {"ok": True}


# ---- Consegne (logistica) ------------------------------------------------
@router.get("/consegne")
async def list_consegne(user: Dict = Depends(get_current_user), limit: int = 200):
    return await db.consegne.find({}, {"_id": 0}).sort("data_prevista", -1).to_list(limit)


@router.post("/consegne")
async def create_consegna(body: ConsegnaIn, user: Dict = Depends(require_roles("admin", "logistica"))):
    doc = body.model_dump()
    doc["id"] = new_id()
    seq = await next_seq("consegna")
    doc["numero"] = f"CON-{datetime.now().year}-{seq:05d}"
    doc["stato"] = "pianificata"
    doc["created_at"] = now_utc().isoformat()
    await db.consegne.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "consegna", doc["id"])
    return doc


@router.patch("/consegne/{cid}")
async def update_consegna(cid: str, body: PatchConsegnaIn, user: Dict = Depends(require_roles("admin", "logistica"))):
    data = body.model_dump(exclude_unset=True)
    if not data:
        return {"ok": True}
    data["updated_at"] = now_utc().isoformat()
    # Track real delivery date when transitioning to "consegnata" for real punctuality KPI
    if data.get("stato") == "consegnata":
        data.setdefault("data_consegna_effettiva", now_utc().date().isoformat())
    await db.consegne.update_one({"id": cid}, {"$set": data})
    await log_audit(user, "UPDATE", "consegna", cid, data)
    return {"ok": True}


# ---- Non-conformità ------------------------------------------------------
@router.get("/non-conformita")
async def list_nc(user: Dict = Depends(get_current_user), limit: int = 200):
    return await db.non_conformita.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)


@router.post("/non-conformita")
async def create_nc(body: NonConformitaIn, user: Dict = Depends(require_roles("admin", "qualita", "produzione"))):
    doc = body.model_dump()
    doc["id"] = new_id()
    doc["stato"] = "aperta"
    doc["segnalato_da"] = user["name"]
    doc["created_at"] = now_utc().isoformat()
    await db.non_conformita.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "non_conformita", doc["id"])
    return doc


@router.patch("/non-conformita/{nid}")
async def update_nc(nid: str, body: PatchNonConformitaIn, user: Dict = Depends(require_roles("admin", "qualita"))):
    data = body.model_dump(exclude_unset=True)
    if not data:
        return {"ok": True}
    data["updated_at"] = now_utc().isoformat()
    await db.non_conformita.update_one({"id": nid}, {"$set": data})
    await log_audit(user, "UPDATE", "non_conformita", nid, data)
    return {"ok": True}
