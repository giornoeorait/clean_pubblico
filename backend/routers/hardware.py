"""Hardware ingestion router: barcode scanners, scales, RFID readers.

Endpoints accept simple REST payloads from on-prem hardware bridges
(e.g., a small daemon reading a USB scale or COM port scanner).
All events are persisted to db.hardware_events for audit/replay.
"""
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, new_id, now_utc, get_current_user, require_roles, log_audit

router = APIRouter(tags=["hardware"])

_WRITE = ("admin", "produzione", "logistica")


class ScanIn(BaseModel):
    code: str = Field(..., description="Barcode / QR content")
    device_id: Optional[str] = None
    station: Optional[str] = None  # es. "accettazione-1"
    action: Optional[str] = "lookup"  # lookup | receive | ship


class ScaleIn(BaseModel):
    peso_kg: float = Field(..., gt=0)
    lotto_id: Optional[str] = None
    ritiro_id: Optional[str] = None
    device_id: Optional[str] = None
    station: Optional[str] = None
    stable: bool = True


class RfidIn(BaseModel):
    tag: str
    articolo_id: Optional[str] = None
    lotto_id: Optional[str] = None
    device_id: Optional[str] = None
    station: Optional[str] = None


async def _log_event(kind: str, payload: Dict[str, Any], user: Dict, extra: Optional[Dict] = None) -> Dict[str, Any]:
    event = {
        "id": new_id(),
        "kind": kind,
        "payload": payload,
        "extra": extra or {},
        "operatore": user["name"],
        "created_at": now_utc(),
    }
    await db.hardware_events.insert_one(event)
    event.pop("_id", None)
    return event


@router.get("/hardware/events")
async def list_events(user: Dict = Depends(get_current_user), kind: Optional[str] = None, limit: int = 200):
    q: Dict[str, Any] = {}
    if kind:
        q["kind"] = kind
    return await db.hardware_events.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)


# --- Barcode ----------------------------------------------------------------
@router.post("/hardware/scan")
async def barcode_scan(body: ScanIn, user: Dict = Depends(require_roles(*_WRITE))):
    """Resolve a scanned code against lotti (numero), articoli (codice/barcode), consegne, ritiri."""
    code = body.code.strip()
    matched: Dict[str, Any] = {"code": code, "match": None, "entity": None}

    lotto = await db.lotti.find_one({"$or": [{"numero": code}, {"id": code}]}, {"_id": 0})
    if lotto:
        matched["match"] = "lotto"
        matched["entity"] = lotto
    else:
        articolo = await db.articoli.find_one({"$or": [{"codice": code}, {"barcode": code}]}, {"_id": 0})
        if articolo:
            matched["match"] = "articolo"
            matched["entity"] = articolo
        else:
            consegna = await db.consegne.find_one({"numero": code}, {"_id": 0})
            if consegna:
                matched["match"] = "consegna"
                matched["entity"] = consegna
            else:
                ritiro = await db.ritiri.find_one({"numero": code}, {"_id": 0})
                if ritiro:
                    matched["match"] = "ritiro"
                    matched["entity"] = ritiro

    await _log_event("barcode", body.model_dump(), user, {"match": matched["match"]})
    await log_audit(user, "SCAN", matched["match"] or "unknown", code)
    if not matched["match"]:
        raise HTTPException(404, f"Nessun riscontro per codice: {code}")
    return matched


# --- Scale / Bilancia -------------------------------------------------------
@router.post("/hardware/scale")
async def scale_reading(body: ScaleIn, user: Dict = Depends(require_roles(*_WRITE))):
    """Peso letto dalla bilancia. Se lotto_id, aggiorna kg_effettivi."""
    applied_to = None
    if body.lotto_id:
        res = await db.lotti.update_one(
            {"id": body.lotto_id},
            {"$set": {"peso_kg": body.peso_kg, "peso_letto_at": now_utc()}},
        )
        if res.matched_count == 0:
            raise HTTPException(404, "Lotto non trovato")
        applied_to = {"type": "lotto", "id": body.lotto_id}
    elif body.ritiro_id:
        res = await db.ritiri.update_one(
            {"id": body.ritiro_id},
            {"$set": {"peso_totale_kg": body.peso_kg, "peso_letto_at": now_utc()}},
        )
        if res.matched_count == 0:
            raise HTTPException(404, "Ritiro non trovato")
        applied_to = {"type": "ritiro", "id": body.ritiro_id}

    event = await _log_event("scale", body.model_dump(), user, {"applied_to": applied_to})
    await log_audit(user, "SCALE_READ", applied_to["type"] if applied_to else "free", str(applied_to or body.device_id), {"kg": body.peso_kg})
    return {"ok": True, "peso_kg": body.peso_kg, "applied_to": applied_to, "event_id": event["id"]}


# --- RFID -------------------------------------------------------------------
@router.post("/hardware/rfid")
async def rfid_read(body: RfidIn, user: Dict = Depends(require_roles(*_WRITE))):
    """Tag RFID letto (singolo/batch). Persiste e aggiorna contatore rfid_reads su articolo."""
    if body.articolo_id:
        await db.articoli.update_one(
            {"id": body.articolo_id},
            {"$inc": {"rfid_reads": 1}, "$set": {"last_rfid_tag": body.tag, "last_rfid_at": now_utc()}},
        )
    event = await _log_event("rfid", body.model_dump(), user)
    await log_audit(user, "RFID_READ", "articolo" if body.articolo_id else "tag", body.tag)
    return {"ok": True, "tag": body.tag, "event_id": event["id"]}


class RfidBatchIn(BaseModel):
    tags: List[str]
    station: Optional[str] = None
    lotto_id: Optional[str] = None


@router.post("/hardware/rfid/batch")
async def rfid_batch(body: RfidBatchIn, user: Dict = Depends(require_roles(*_WRITE))):
    """Batch: lettura multipla (es. passaggio gate). Ritorna conteggio."""
    if not body.tags:
        raise HTTPException(400, "Lista tags vuota")
    seen = list({t.strip() for t in body.tags if t and t.strip()})
    event = await _log_event("rfid_batch", {"tags": seen, "station": body.station, "lotto_id": body.lotto_id}, user, {"count": len(seen)})
    if body.lotto_id:
        await db.lotti.update_one(
            {"id": body.lotto_id},
            {"$set": {"rfid_tags": seen, "rfid_count": len(seen), "rfid_read_at": now_utc()}},
        )
    await log_audit(user, "RFID_BATCH", "lotto" if body.lotto_id else "gate", body.lotto_id or body.station or "-", {"count": len(seen)})
    return {"ok": True, "count": len(seen), "tags": seen, "event_id": event["id"]}
