"""Magazzino: articoli consumabili (detergenti, DPI, chimici) con scorte minime e allarmi."""
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from core import db, new_id, now_utc, to_dt, get_current_user, require_roles, log_audit
from schemas import MagazzinoIn, PatchMagazzinoIn, MovimentoIn

router = APIRouter(prefix="/magazzino", tags=["magazzino"])

_WRITE_ROLES = ("admin", "produzione", "contabilita")
_MOV_ROLES = ("admin", "produzione", "logistica")


def _compute_flags(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Add scorta_stato + scadenza_stato flags for alarms."""
    scorta = float(doc.get("scorta_attuale", 0) or 0)
    minima = float(doc.get("scorta_minima", 0) or 0)
    if scorta <= 0:
        doc["scorta_stato"] = "esaurita"
    elif scorta <= minima:
        doc["scorta_stato"] = "bassa"
    else:
        doc["scorta_stato"] = "ok"

    sc = doc.get("scadenza")
    if sc:
        if isinstance(sc, str):
            sc_dt = to_dt(sc)
        else:
            sc_dt = sc if getattr(sc, "tzinfo", None) else (sc.replace(tzinfo=timezone.utc) if hasattr(sc, "replace") else None)
        if sc_dt:
            delta_days = (sc_dt - now_utc()).days
            if delta_days < 0:
                doc["scadenza_stato"] = "scaduto"
            elif delta_days <= 30:
                doc["scadenza_stato"] = "prossima"
            else:
                doc["scadenza_stato"] = "ok"
        else:
            doc["scadenza_stato"] = "ok"
    else:
        doc["scadenza_stato"] = "na"
    doc["in_allarme"] = doc["scorta_stato"] in ("bassa", "esaurita") or doc["scadenza_stato"] in ("prossima", "scaduto")
    return doc


# ---- CRUD articoli magazzino ---------------------------------------------
@router.get("")
async def list_magazzino(
    user: Dict = Depends(get_current_user),
    categoria: Optional[str] = None,
    solo_allarmi: bool = False,
    limit: int = 500,
):
    q: Dict[str, Any] = {}
    if categoria:
        q["categoria"] = categoria
    items = await db.magazzino.find(q, {"_id": 0}).sort("codice", 1).to_list(limit)
    items = [_compute_flags(it) for it in items]
    if solo_allarmi:
        items = [it for it in items if it["in_allarme"]]
    return items


@router.get("/allarmi")
async def allarmi(user: Dict = Depends(get_current_user)):
    items = await db.magazzino.find({}, {"_id": 0}).to_list(500)
    items = [_compute_flags(it) for it in items]
    allarmi = [it for it in items if it["in_allarme"]]
    return {
        "totale": len(allarmi),
        "scorta_bassa": sum(1 for it in allarmi if it["scorta_stato"] == "bassa"),
        "scorta_esaurita": sum(1 for it in allarmi if it["scorta_stato"] == "esaurita"),
        "scadenza_prossima": sum(1 for it in allarmi if it["scadenza_stato"] == "prossima"),
        "scaduti": sum(1 for it in allarmi if it["scadenza_stato"] == "scaduto"),
        "items": allarmi,
    }


@router.post("")
async def create_magazzino(body: MagazzinoIn, user: Dict = Depends(require_roles(*_WRITE_ROLES))):
    doc = body.model_dump()
    if doc.get("scadenza"):
        dt = to_dt(doc["scadenza"])
        doc["scadenza"] = dt if dt is not None else None
    doc["id"] = new_id()
    doc["created_at"] = now_utc()
    doc["updated_at"] = doc["created_at"]
    await db.magazzino.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "magazzino", doc["id"])
    return _compute_flags(doc)


@router.get("/{item_id}")
async def get_magazzino(item_id: str, user: Dict = Depends(get_current_user)):
    doc = await db.magazzino.find_one({"id": item_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Articolo magazzino non trovato")
    return _compute_flags(doc)


@router.patch("/{item_id}")
async def update_magazzino(item_id: str, body: PatchMagazzinoIn, user: Dict = Depends(require_roles(*_WRITE_ROLES))):
    data = body.model_dump(exclude_unset=True)
    if not data:
        return {"ok": True}
    if "scadenza" in data and data["scadenza"] is not None:
        dt = to_dt(data["scadenza"])
        data["scadenza"] = dt
    data["updated_at"] = now_utc()
    res = await db.magazzino.update_one({"id": item_id}, {"$set": data})
    if res.matched_count == 0:
        raise HTTPException(404, "Articolo non trovato")
    await log_audit(user, "UPDATE", "magazzino", item_id, {"keys": list(data.keys())})
    return {"ok": True}


@router.delete("/{item_id}")
async def delete_magazzino(item_id: str, user: Dict = Depends(require_roles(*_WRITE_ROLES))):
    await db.magazzino.delete_one({"id": item_id})
    await log_audit(user, "DELETE", "magazzino", item_id)
    return {"ok": True}


# ---- Movimenti di carico / scarico / rettifica ---------------------------
@router.post("/{item_id}/movimento")
async def add_movimento(item_id: str, body: MovimentoIn, user: Dict = Depends(require_roles(*_MOV_ROLES))):
    if body.tipo not in ("carico", "scarico", "rettifica"):
        raise HTTPException(400, "tipo ammesso: carico | scarico | rettifica")
    if body.quantita < 0:
        raise HTTPException(400, "quantita deve essere >= 0")

    articolo = await db.magazzino.find_one({"id": item_id})
    if not articolo:
        raise HTTPException(404, "Articolo non trovato")

    if body.tipo == "carico":
        new_scorta = float(articolo.get("scorta_attuale", 0)) + body.quantita
        await db.magazzino.update_one({"id": item_id}, {"$inc": {"scorta_attuale": body.quantita}, "$set": {"updated_at": now_utc()}})
    elif body.tipo == "scarico":
        new_scorta = float(articolo.get("scorta_attuale", 0)) - body.quantita
        await db.magazzino.update_one({"id": item_id}, {"$inc": {"scorta_attuale": -body.quantita}, "$set": {"updated_at": now_utc()}})
    else:  # rettifica
        new_scorta = body.quantita
        await db.magazzino.update_one({"id": item_id}, {"$set": {"scorta_attuale": body.quantita, "updated_at": now_utc()}})

    mov_doc = {
        "id": new_id(),
        "articolo_id": item_id,
        "articolo_codice": articolo.get("codice"),
        "tipo": body.tipo,
        "quantita": body.quantita,
        "motivo": body.motivo,
        "lotto_fornitore": body.lotto_fornitore,
        "note": body.note,
        "operatore_id": user["id"],
        "operatore_nome": user["name"],
        "scorta_prima": float(articolo.get("scorta_attuale", 0)),
        "scorta_dopo": new_scorta,
        "timestamp": now_utc(),
    }
    await db.magazzino_movimenti.insert_one(mov_doc)
    mov_doc.pop("_id", None)
    await log_audit(user, body.tipo.upper(), "magazzino", item_id, {"qta": body.quantita, "new_stock": new_scorta})
    return mov_doc


@router.get("/{item_id}/movimenti")
async def list_movimenti(item_id: str, user: Dict = Depends(get_current_user), limit: int = 200):
    return await db.magazzino_movimenti.find(
        {"articolo_id": item_id}, {"_id": 0}
    ).sort("timestamp", -1).to_list(limit)
