"""Notifications router: send SMS/WhatsApp + storico + template engine."""
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, get_current_user, require_roles, log_audit, tenant_scope, inject_tenant
from notifications import send_notification, is_twilio_enabled

router = APIRouter(tags=["notifications"])


# --- Templates ----------------------------------------------------------------
TEMPLATES = {
    "consegna_in_transito": "Ciao {nome}! La tua consegna {numero} è in transito. Arrivo previsto oggi. - CleanTec",
    "consegna_completata": "Consegna {numero} effettuata con successo. Grazie per averci scelto! - CleanTec",
    "ritiro_programmato": "Il ritiro {numero} è programmato per {data}. Tieni pronta la biancheria. - CleanTec",
    "ticket_critico": "ATTENZIONE: ticket manutenzione CRITICO {numero} aperto sulla macchina {macchina}. Intervento urgente.",
    "lotto_pronto": "Il tuo lotto {numero} ({kg}kg) è pronto per la consegna. - CleanTec",
    "scorta_bassa": "Scorta bassa: {codice} ({descrizione}) — disponibili {qta} {um}. Riordinare.",
}


class SendIn(BaseModel):
    kind: str = Field(..., description="sms | whatsapp")
    to: str
    body: Optional[str] = None
    template: Optional[str] = None
    template_vars: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None


@router.get("/notifications/status")
async def status():
    return {
        "twilio_enabled": is_twilio_enabled(),
        "templates": list(TEMPLATES.keys()),
    }


@router.get("/notifications")
async def list_notifications(user: Dict = Depends(get_current_user), limit: int = 200):
    q: Dict[str, Any] = dict(tenant_scope(user))
    if user["role"] == "cliente" and user.get("cliente_id"):
        q["context.cliente_id"] = user["cliente_id"]
    return await db.notifications.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)


@router.post("/notifications/send")
async def send(body: SendIn, user: Dict = Depends(require_roles("admin", "logistica", "produzione", "qualita"))):
    text = body.body
    if not text and body.template:
        tpl = TEMPLATES.get(body.template)
        if not tpl:
            raise HTTPException(400, f"Template sconosciuto: {body.template}")
        try:
            text = tpl.format(**(body.template_vars or {}))
        except KeyError as e:
            raise HTTPException(400, f"Variabile template mancante: {e}")
    if not text:
        raise HTTPException(400, "body oppure template richiesto")

    try:
        record = await send_notification(
            kind=body.kind,
            to=body.to,
            body=text,
            context=body.context,
            user=user,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    await log_audit(user, "SEND", body.kind, record["id"], {"to": body.to, "status": record["status"]})
    return record


@router.delete("/notifications/{nid}")
async def delete_notification(nid: str, user: Dict = Depends(require_roles("admin"))):
    res = await db.notifications.delete_one({"id": nid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Notifica non trovata")
    await log_audit(user, "DELETE", "notification", nid)
    return {"ok": True}
