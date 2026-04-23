"""Manutenzione: ticket guasti + interventi su macchine."""
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from core import (
    db, new_id, now_utc, to_dt,
    get_current_user, require_roles, log_audit, next_seq,
)
from schemas import TicketIn, PatchTicketIn, InterventoIn
from notifications import send_notification

router = APIRouter(tags=["manutenzione"])

_WRITE_ROLES = ("admin", "produzione")


async def _update_macchina_stato(macchina_id: str, new_stato: str):
    await db.macchine.update_one({"id": macchina_id}, {"$set": {"stato": new_stato, "updated_at": now_utc()}})


async def _recompute_ticket_totals(ticket_id: str):
    interventi = await db.interventi.find({"ticket_id": ticket_id}, {"_id": 0}).to_list(500)
    durata = sum(int(i.get("durata_min", 0) or 0) for i in interventi)
    costo = sum(float(i.get("costo", 0) or 0) for i in interventi)
    await db.tickets.update_one(
        {"id": ticket_id},
        {"$set": {
            "durata_totale_min": durata,
            "costo_totale": round(costo, 2),
            "interventi_count": len(interventi),
            "updated_at": now_utc(),
        }},
    )


# ---- Tickets -------------------------------------------------------------
@router.get("/tickets")
async def list_tickets(
    user: Dict = Depends(get_current_user),
    macchina_id: Optional[str] = None,
    stato: Optional[str] = None,
    priorita: Optional[str] = None,
    limit: int = 500,
):
    q: Dict[str, Any] = {}
    if macchina_id: q["macchina_id"] = macchina_id
    if stato: q["stato"] = stato
    if priorita: q["priorita"] = priorita
    return await db.tickets.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)


@router.post("/tickets")
async def create_ticket(body: TicketIn, user: Dict = Depends(require_roles(*_WRITE_ROLES))):
    macchina = await db.macchine.find_one({"id": body.macchina_id}, {"_id": 0})
    if not macchina:
        raise HTTPException(404, "Macchina non trovata")

    doc = body.model_dump()
    doc["id"] = new_id()
    seq = await next_seq("ticket")
    doc["numero"] = f"TKT-{datetime.now().year}-{seq:05d}"
    doc["macchina_codice"] = macchina.get("codice")
    doc["stato"] = "aperto"
    doc["segnalato_da"] = user["name"]
    doc["interventi_count"] = 0
    doc["durata_totale_min"] = 0
    doc["costo_totale"] = 0.0
    doc["created_at"] = now_utc()
    doc["updated_at"] = doc["created_at"]

    await db.tickets.insert_one(doc)
    doc.pop("_id", None)

    # If fermo_macchina, mark machine as "guasto"
    if body.fermo_macchina:
        await _update_macchina_stato(body.macchina_id, "guasto")

    await log_audit(user, "CREATE", "ticket", doc["id"], {"macchina": macchina.get("codice")})

    # Auto-notify responsabile manutenzione on critical tickets (best-effort)
    if body.priorita == "critica":
        import os
        alert_to = os.environ.get("MAINTENANCE_ALERT_PHONE")
        if alert_to and alert_to.startswith("+"):
            try:
                msg = f"CleanTec URGENTE: ticket {doc['numero']} CRITICO su macchina {macchina.get('codice')}. Tipo: {body.tipo}. {body.titolo}"
                await send_notification(
                    kind="sms", to=alert_to, body=msg,
                    context={"ticket_id": doc["id"], "macchina_id": body.macchina_id, "trigger": "ticket_critico"},
                    user=user,
                )
            except Exception:
                pass

    return doc


@router.get("/tickets/{tid}")
async def get_ticket(tid: str, user: Dict = Depends(get_current_user)):
    doc = await db.tickets.find_one({"id": tid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Ticket non trovato")
    doc["interventi"] = await db.interventi.find({"ticket_id": tid}, {"_id": 0}).sort("data_intervento", -1).to_list(200)
    return doc


@router.patch("/tickets/{tid}")
async def update_ticket(tid: str, body: PatchTicketIn, user: Dict = Depends(require_roles(*_WRITE_ROLES))):
    ticket = await db.tickets.find_one({"id": tid}, {"_id": 0})
    if not ticket:
        raise HTTPException(404, "Ticket non trovato")

    data = body.model_dump(exclude_unset=True)
    if not data:
        return {"ok": True}
    data["updated_at"] = now_utc()

    new_stato = data.get("stato")
    if new_stato in ("risolto", "chiuso") and ticket.get("stato") not in ("risolto", "chiuso"):
        data.setdefault("chiuso_at", now_utc())
        # If machine was marked guasto by this ticket, restore availability
        if ticket.get("fermo_macchina"):
            await _update_macchina_stato(ticket["macchina_id"], "disponibile")
    elif new_stato == "in_lavorazione" and data.get("fermo_macchina") is True:
        await _update_macchina_stato(ticket["macchina_id"], "guasto")

    await db.tickets.update_one({"id": tid}, {"$set": data})
    await log_audit(user, "UPDATE", "ticket", tid, {"stato": new_stato})
    return {"ok": True}


@router.delete("/tickets/{tid}")
async def delete_ticket(tid: str, user: Dict = Depends(require_roles("admin"))):
    await db.interventi.delete_many({"ticket_id": tid})
    await db.tickets.delete_one({"id": tid})
    await log_audit(user, "DELETE", "ticket", tid)
    return {"ok": True}


# ---- Interventi sul ticket ----------------------------------------------
@router.get("/tickets/{tid}/interventi")
async def list_interventi(tid: str, user: Dict = Depends(get_current_user)):
    return await db.interventi.find({"ticket_id": tid}, {"_id": 0}).sort("data_intervento", -1).to_list(500)


@router.post("/tickets/{tid}/interventi")
async def add_intervento(tid: str, body: InterventoIn, user: Dict = Depends(require_roles(*_WRITE_ROLES))):
    ticket = await db.tickets.find_one({"id": tid})
    if not ticket:
        raise HTTPException(404, "Ticket non trovato")

    doc = body.model_dump()
    doc["id"] = new_id()
    doc["ticket_id"] = tid
    doc["macchina_id"] = ticket.get("macchina_id")
    doc["data_intervento"] = to_dt(doc.get("data_intervento")) or now_utc()
    doc["created_at"] = now_utc()
    await db.interventi.insert_one(doc)
    doc.pop("_id", None)

    await _recompute_ticket_totals(tid)

    # Auto-transition: first intervento → in_lavorazione
    if ticket.get("stato") == "aperto":
        await db.tickets.update_one({"id": tid}, {"$set": {"stato": "in_lavorazione", "updated_at": now_utc()}})

    await log_audit(user, "CREATE", "intervento", doc["id"], {"ticket": tid})
    return doc


# ---- Storico manutenzione per macchina ----------------------------------
@router.get("/macchine/{mid}/storico-manutenzione")
async def storico_macchina(mid: str, user: Dict = Depends(get_current_user), limit: int = 200):
    tickets = await db.tickets.find({"macchina_id": mid}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {
        "totale": len(tickets),
        "aperti": sum(1 for t in tickets if t["stato"] in ("aperto", "in_lavorazione")),
        "risolti": sum(1 for t in tickets if t["stato"] in ("risolto", "chiuso")),
        "costo_totale": round(sum(float(t.get("costo_totale", 0) or 0) for t in tickets), 2),
        "durata_totale_min": sum(int(t.get("durata_totale_min", 0) or 0) for t in tickets),
        "tickets": tickets,
    }
