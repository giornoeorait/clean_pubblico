"""Coda di stampa DDT reale: job persistenti + Print Bridge locale (IPP/RAW 9100) + fallback PrintHand."""
import ipaddress
import re
import secrets
from typing import Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel

from core import db, new_id, now_utc, get_current_user, require_roles, tenant_scope, tenant_id_of, log_audit

router = APIRouter(tags=["print"])

STATI = ("pending", "sending", "printed", "failed", "manual_required")
_HOST_RE = re.compile(r"^[a-zA-Z0-9.-]{1,253}$")


def _valid_host(ip: str) -> bool:
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return bool(_HOST_RE.match(ip)) and ".." not in ip


async def _printer_cfg(tenant_id: str) -> Dict:
    doc = await db.company.find_one({"tenant_id": tenant_id}, {"_id": 0, "stampa": 1}) or {}
    return (doc.get("stampa") or {}).get("stampante_ddt") or {}


async def _bridge_online(tenant_id: str) -> bool:
    doc = await db.company.find_one({"tenant_id": tenant_id}, {"_id": 0, "stampa": 1}) or {}
    seen = (doc.get("stampa") or {}).get("bridge_last_seen")
    if not seen:
        return False
    return (now_utc() - (seen if seen.tzinfo else seen.replace(tzinfo=now_utc().tzinfo))).total_seconds() < 60


# ------------------------- Config stampante (admin) -------------------------
class StampanteDDTIn(BaseModel):
    ip: str = ""
    porta: int = 631
    protocollo: str = "ipp"  # ipp | raw
    formato: str = "A4"
    colore: bool = False
    copie: int = 1
    fronte_retro: bool = False
    vassoio: str = ""


@router.put("/stampante-ddt")
async def put_stampante(body: StampanteDDTIn, user: Dict = Depends(require_roles("admin"))):
    if body.ip and not _valid_host(body.ip.strip()):
        raise HTTPException(422, "Indirizzo IP/host non valido")
    if not (1 <= body.porta <= 65535):
        raise HTTPException(422, "Porta non valida (1-65535)")
    if body.protocollo not in ("ipp", "raw"):
        raise HTTPException(422, "Protocollo non valido (ipp o raw)")
    if not (1 <= body.copie <= 10):
        raise HTTPException(422, "Copie: da 1 a 10")
    cfg = body.model_dump()
    cfg["ip"] = cfg["ip"].strip()
    await db.company.update_one(tenant_scope(user), {"$set": {"stampa.stampante_ddt": cfg}}, upsert=True)
    await log_audit(user, "UPDATE", "stampante_ddt", tenant_id_of(user), cfg)
    return cfg


@router.get("/stampante-ddt")
async def get_stampante(user: Dict = Depends(get_current_user)):
    tenant_id = tenant_id_of(user)
    cfg = await _printer_cfg(tenant_id)
    out = {**StampanteDDTIn().model_dump(), **cfg}
    out["bridge_online"] = await _bridge_online(tenant_id)
    out["configurata"] = bool(cfg.get("ip"))
    if user.get("role") in ("admin", "superadmin"):
        doc = await db.company.find_one({"tenant_id": tenant_id}, {"_id": 0, "stampa": 1}) or {}
        out["bridge_token"] = (doc.get("stampa") or {}).get("bridge_token") or ""
        seen = (doc.get("stampa") or {}).get("bridge_last_seen")
        out["bridge_last_seen"] = seen.isoformat() if seen else None
    return out


@router.post("/stampante-ddt/bridge-token")
async def rigenera_token(user: Dict = Depends(require_roles("admin"))):
    token = secrets.token_urlsafe(32)
    await db.company.update_one(tenant_scope(user), {"$set": {"stampa.bridge_token": token}}, upsert=True)
    await log_audit(user, "UPDATE", "bridge_token", tenant_id_of(user), {})
    return {"bridge_token": token}


# ------------------------- Job di stampa -------------------------
class JobIn(BaseModel):
    ddt_id: Optional[str] = None
    tipo: str = "stampa"  # stampa | test | check
    modalita: Optional[str] = None  # None=diretta, "manuale"=PrintHand


def _job_view(j: Dict) -> Dict:
    j.pop("tenant_id", None)
    return j


@router.post("/print-jobs")
async def crea_job(body: JobIn, user: Dict = Depends(require_roles("admin", "logistica", "contabilita", "produzione"))):
    tenant_id = tenant_id_of(user)
    if body.tipo not in ("stampa", "test", "check"):
        raise HTTPException(422, "tipo non valido")
    ddt = None
    if body.tipo == "stampa":
        if not body.ddt_id:
            raise HTTPException(422, "ddt_id richiesto")
        ddt = await db.ddt.find_one({"tenant_id": tenant_id, "id": body.ddt_id}, {"_id": 0, "id": 1, "numero": 1})
        if not ddt:
            raise HTTPException(404, "DDT non trovato")
        # Idempotenza: se esiste già un job attivo per questo DDT, restituiscilo
        existing = await db.print_jobs.find_one(
            {"tenant_id": tenant_id, "ddt_id": body.ddt_id, "stato": {"$in": ["pending", "sending"]}}, {"_id": 0})
        if existing:
            return _job_view(existing)
    if body.modalita == "manuale":
        stato = "manual_required"
    else:
        cfg = await _printer_cfg(tenant_id)
        if not cfg.get("ip"):
            raise HTTPException(422, "Stampante DDT non configurata")
        stato = "pending"
    cfg = await _printer_cfg(tenant_id)
    job = {
        "id": new_id(), "tenant_id": tenant_id, "tipo": body.tipo,
        "ddt_id": (ddt or {}).get("id"), "ddt_numero": (ddt or {}).get("numero"),
        "stato": stato, "tentativi": 0, "errore": None,
        "printer_ip": cfg.get("ip"), "protocollo": cfg.get("protocollo"),
        "device": None, "richiesto_da": user.get("email"),
        "created_at": now_utc(), "updated_at": now_utc(),
    }
    await db.print_jobs.insert_one({**job})
    job.pop("_id", None)
    return _job_view(job)


@router.get("/print-jobs/{jid}")
async def get_job(jid: str, user: Dict = Depends(get_current_user)):
    j = await db.print_jobs.find_one({"tenant_id": tenant_id_of(user), "id": jid}, {"_id": 0})
    if not j:
        raise HTTPException(404, "Job non trovato")
    return _job_view(j)


@router.post("/print-jobs/{jid}/retry")
async def retry_job(jid: str, user: Dict = Depends(require_roles("admin", "logistica", "contabilita", "produzione"))):
    scope = {"tenant_id": tenant_id_of(user), "id": jid}
    j = await db.print_jobs.find_one(scope, {"_id": 0})
    if not j:
        raise HTTPException(404, "Job non trovato")
    if j["stato"] == "sending":
        return _job_view(j)
    await db.print_jobs.update_one(scope, {"$set": {"stato": "pending", "errore": None, "updated_at": now_utc(),
                                                    "richiesto_da": user.get("email")},
                                           "$inc": {"tentativi": 1}})
    return _job_view(await db.print_jobs.find_one(scope, {"_id": 0}))


@router.post("/print-jobs/{jid}/segna-manuale")
async def segna_manuale(jid: str, user: Dict = Depends(require_roles("admin", "logistica", "contabilita", "produzione"))):
    scope = {"tenant_id": tenant_id_of(user), "id": jid}
    await db.print_jobs.update_one(scope, {"$set": {"stato": "manual_required", "updated_at": now_utc()}})
    j = await db.print_jobs.find_one(scope, {"_id": 0})
    if not j:
        raise HTTPException(404, "Job non trovato")
    return _job_view(j)


@router.get("/print-bridge/script")
async def bridge_script(user: Dict = Depends(require_roles("admin"))):
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "cleantec_print_bridge.py")
    with open(path, "rb") as f:
        content = f.read()
    return Response(content=content, media_type="text/x-python",
                    headers={"Content-Disposition": 'attachment; filename="cleantec_print_bridge.py"'})


# ------------------------- API per il Print Bridge locale -------------------------
async def _bridge_tenant(token: Optional[str]) -> str:
    if not token:
        raise HTTPException(401, "Token bridge mancante")
    doc = await db.company.find_one({"stampa.bridge_token": token}, {"_id": 0, "tenant_id": 1})
    if not doc:
        raise HTTPException(401, "Token bridge non valido")
    return doc["tenant_id"]


@router.get("/print-bridge/poll")
async def bridge_poll(x_bridge_token: Optional[str] = Header(None), device: Optional[str] = None):
    tenant_id = await _bridge_tenant(x_bridge_token)
    await db.company.update_one({"tenant_id": tenant_id}, {"$set": {"stampa.bridge_last_seen": now_utc()}})
    j = await db.print_jobs.find_one_and_update(
        {"tenant_id": tenant_id, "stato": "pending"},
        {"$set": {"stato": "sending", "updated_at": now_utc(), "device": device or "bridge"}},
        sort=[("created_at", 1)],
    )
    if not j:
        return {"job": None}
    cfg = await _printer_cfg(tenant_id)
    return {"job": {"id": j["id"], "tipo": j["tipo"], "ddt_numero": j.get("ddt_numero"), "printer": cfg}}


@router.get("/print-bridge/jobs/{jid}/pdf")
async def bridge_pdf(jid: str, x_bridge_token: Optional[str] = Header(None)):
    tenant_id = await _bridge_tenant(x_bridge_token)
    j = await db.print_jobs.find_one({"tenant_id": tenant_id, "id": jid}, {"_id": 0})
    if not j:
        raise HTTPException(404, "Job non trovato")
    from pdf_service import generate_ddt_pdf, generate_test_page_pdf
    if j["tipo"] == "test" or not j.get("ddt_id"):
        company = await db.company.find_one({"tenant_id": tenant_id}, {"_id": 0}) or {}
        pdf = generate_test_page_pdf(company)
    else:
        ddt = await db.ddt.find_one({"tenant_id": tenant_id, "id": j["ddt_id"]}, {"_id": 0})
        if not ddt:
            raise HTTPException(404, "DDT non trovato")
        cliente = await db.clienti.find_one({"tenant_id": tenant_id, "id": ddt.get("cliente_id")}, {"_id": 0}) or {}
        company = await db.company.find_one({"tenant_id": tenant_id}, {"_id": 0}) or {}
        pdf = generate_ddt_pdf(ddt, cliente, company)
    return Response(content=pdf, media_type="application/pdf")


class BridgeStatus(BaseModel):
    stato: str
    errore: Optional[str] = None


@router.post("/print-bridge/jobs/{jid}/status")
async def bridge_status(jid: str, body: BridgeStatus, x_bridge_token: Optional[str] = Header(None)):
    tenant_id = await _bridge_tenant(x_bridge_token)
    if body.stato not in ("printed", "failed"):
        raise HTTPException(422, "stato non valido")
    await db.print_jobs.update_one(
        {"tenant_id": tenant_id, "id": jid},
        {"$set": {"stato": body.stato, "errore": (body.errore or None), "updated_at": now_utc()},
         "$inc": {"tentativi": 1}})
    return {"ok": True}
