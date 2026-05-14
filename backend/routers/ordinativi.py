"""Ordinativi clienti → trasformabili in DDT.

Due flussi:
 1. Interno: operatore crea ordinativo per un cliente
 2. Portale pubblico (no auth): il cliente stesso usa un link con token univoco

Schema:
  id, tenant_id, numero (ORD-YYYY-NNNNN)
  cliente_id, cliente_snapshot
  data_richiesta (datetime), data_consegna_richiesta (date ISO 'YYYY-MM-DD')
  righe: [{articolo_id, codice, descrizione, unita_misura, quantita, prezzo_unitario, totale}]
  totale (imponibile)
  stato: 'nuovo' | 'in_lavorazione' | 'convertito_ddt' | 'annullato'
  ddt_id, ddt_numero (se convertito)
  origine: 'interno' | 'portale'
  note_cliente, note_interne
"""
import secrets
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import (
    db, new_id, now_utc, next_seq,
    get_current_user, require_roles, tenant_scope, merge_scope, tenant_id_of, log_audit,
)

router = APIRouter(tags=["ordinativi"])
public_router = APIRouter(prefix="/public", tags=["portale-pubblico"])


# ---------- Schemas ----------
class RigaOrd(BaseModel):
    articolo_id: str
    quantita: float = Field(gt=0)


class OrdinativoIn(BaseModel):
    cliente_id: str
    data_consegna_richiesta: Optional[str] = None
    righe: List[RigaOrd]
    note_cliente: Optional[str] = ""
    note_interne: Optional[str] = ""


class OrdinativoPatch(BaseModel):
    data_consegna_richiesta: Optional[str] = None
    righe: Optional[List[RigaOrd]] = None
    note_interne: Optional[str] = None
    stato: Optional[Literal["nuovo", "in_lavorazione", "annullato"]] = None


class PortaleOrdIn(BaseModel):
    data_consegna_richiesta: str
    righe: List[RigaOrd]
    note_cliente: Optional[str] = ""


# ---------- Helpers ----------
async def _resolve_righe(tenant_id: str, cliente_id: str, righe: List[RigaOrd]) -> List[Dict]:
    cli = await db.clienti.find_one({"tenant_id": tenant_id, "id": cliente_id}, {"_id": 0})
    if not cli:
        raise HTTPException(404, "Cliente non trovato")
    listino_id = cli.get("listino_id")
    listino = None
    if listino_id:
        listino = await db.listini.find_one({"tenant_id": tenant_id, "id": listino_id}, {"_id": 0})
    tipo = (listino or {}).get("tipo", "lavaggio")
    default_key = "prezzo_noleggio" if tipo == "noleggio" else "prezzo_lavaggio"

    rows: List[Dict] = []
    for r in righe:
        a = await db.articoli.find_one({"tenant_id": tenant_id, "id": r.articolo_id}, {"_id": 0})
        if not a:
            raise HTTPException(400, f"Articolo {r.articolo_id} non disponibile")
        prezzo = None
        if listino_id:
            p_doc = await db.listini_prezzi.find_one({
                "tenant_id": tenant_id, "listino_id": listino_id, "articolo_id": r.articolo_id,
            }, {"_id": 0})
            if p_doc and p_doc.get("prezzo") is not None:
                prezzo = float(p_doc["prezzo"])
        if prezzo is None:
            prezzo = float(a.get(default_key) or a.get("prezzo") or 0)
        tot = round(prezzo * float(r.quantita), 2)
        rows.append({
            "articolo_id": r.articolo_id,
            "codice": a.get("codice", ""),
            "descrizione": a.get("descrizione", ""),
            "unita_misura": a.get("unita_misura", "pz"),
            "quantita": float(r.quantita),
            "prezzo_unitario": round(prezzo, 4),
            "totale": tot,
        })
    return rows


def _cli_snapshot(cli: Dict) -> Dict:
    return {k: cli.get(k, "") for k in ("ragione_sociale", "denominazione_struttura", "indirizzo",
                                        "indirizzo_scarico", "partita_iva", "email", "telefono")}


async def _create_ordinativo(tenant_id: str, cli_id: str, body: RigaOrd | OrdinativoIn | PortaleOrdIn,
                             origine: str, data_consegna: Optional[str], note_cliente: str = "",
                             note_interne: str = "", created_by: Optional[str] = None) -> Dict:
    cli = await db.clienti.find_one({"tenant_id": tenant_id, "id": cli_id}, {"_id": 0})
    if not cli:
        raise HTTPException(404, "Cliente non trovato")
    rows = await _resolve_righe(tenant_id, cli_id, body.righe)
    tot = round(sum(r["totale"] for r in rows), 2)
    seq = await next_seq("ordinativo")
    oid = new_id()
    from core import format_numero
    numero = await format_numero("ordinativo", "ORD", seq)
    doc = {
        "id": oid, "tenant_id": tenant_id, "numero": numero,
        "cliente_id": cli_id, "cliente_snapshot": _cli_snapshot(cli),
        "data_richiesta": now_utc(),
        "data_consegna_richiesta": data_consegna,
        "righe": rows, "totale": tot,
        "stato": "nuovo",
        "ddt_id": None, "ddt_numero": None,
        "origine": origine,
        "note_cliente": note_cliente or "",
        "note_interne": note_interne or "",
        "created_at": now_utc(), "updated_at": now_utc(),
        "created_by": created_by,
    }
    await db.ordinativi.insert_one(doc)
    doc.pop("_id", None)
    return doc


# ---------- Internal endpoints ----------
@router.get("/ordinativi")
async def list_ord(
    cliente_id: Optional[str] = None, stato: Optional[str] = None,
    limit: int = 200, user: Dict = Depends(get_current_user),
):
    filt = dict(tenant_scope(user))
    if cliente_id: filt["cliente_id"] = cliente_id
    if stato: filt["stato"] = stato
    return await db.ordinativi.find(filt, {"_id": 0}).sort("created_at", -1).to_list(limit)


@router.get("/ordinativi/{oid}")
async def get_ord(oid: str, user: Dict = Depends(get_current_user)):
    doc = await db.ordinativi.find_one(merge_scope(user, {"id": oid}), {"_id": 0})
    if not doc: raise HTTPException(404, "Ordinativo non trovato")
    return doc


@router.post("/ordinativi")
async def create_ord(body: OrdinativoIn, user: Dict = Depends(require_roles("admin", "logistica", "contabilita"))):
    if not body.righe: raise HTTPException(400, "Righe obbligatorie")
    doc = await _create_ordinativo(
        tenant_id_of(user), body.cliente_id, body, "interno",
        body.data_consegna_richiesta, body.note_cliente or "", body.note_interne or "",
        created_by=user["id"],
    )
    await log_audit(user, "CREATE", "ordinativo", doc["id"], {"numero": doc["numero"]})
    return doc


@router.patch("/ordinativi/{oid}")
async def update_ord(oid: str, body: OrdinativoPatch, user: Dict = Depends(require_roles("admin", "logistica", "contabilita"))):
    cur = await db.ordinativi.find_one(merge_scope(user, {"id": oid}), {"_id": 0})
    if not cur: raise HTTPException(404, "Ordinativo non trovato")
    if cur["stato"] == "convertito_ddt":
        raise HTTPException(409, "Ordinativo già convertito in DDT")
    patch: Dict = {"updated_at": now_utc()}
    data = body.model_dump(exclude_unset=True)
    if data.get("righe") is not None:
        rows = await _resolve_righe(tenant_id_of(user), cur["cliente_id"], body.righe)
        patch["righe"] = rows
        patch["totale"] = round(sum(r["totale"] for r in rows), 2)
    for k in ("data_consegna_richiesta", "note_interne", "stato"):
        if k in data: patch[k] = data[k]
    await db.ordinativi.update_one(merge_scope(user, {"id": oid}), {"$set": patch})
    return await db.ordinativi.find_one(merge_scope(user, {"id": oid}), {"_id": 0})


@router.delete("/ordinativi/{oid}")
async def delete_ord(oid: str, user: Dict = Depends(require_roles("admin", "logistica", "contabilita"))):
    cur = await db.ordinativi.find_one(merge_scope(user, {"id": oid}), {"_id": 0})
    if not cur: raise HTTPException(404, "Ordinativo non trovato")
    if cur["stato"] == "convertito_ddt":
        raise HTTPException(409, "Ordinativo già convertito — impossibile eliminare")
    await db.ordinativi.delete_one(merge_scope(user, {"id": oid}))
    return {"ok": True}


@router.post("/ordinativi/{oid}/converti-ddt")
async def converti_ddt(oid: str, user: Dict = Depends(require_roles("admin", "logistica", "contabilita"))):
    cur = await db.ordinativi.find_one(merge_scope(user, {"id": oid}), {"_id": 0})
    if not cur: raise HTTPException(404, "Ordinativo non trovato")
    if cur["stato"] == "convertito_ddt":
        raise HTTPException(409, f"Già convertito in {cur.get('ddt_numero')}")
    if cur["stato"] == "annullato":
        raise HTTPException(400, "Ordinativo annullato")
    cli = await db.clienti.find_one(merge_scope(user, {"id": cur["cliente_id"]}), {"_id": 0})
    if not cli: raise HTTPException(404, "Cliente mancante")
    # Crea DDT
    ddt_seq = await next_seq("ddt")
    did = new_id()
    from core import format_numero
    numero_ddt = await format_numero("ddt", "DDT", ddt_seq)
    ddt_doc = {
        "id": did, "tenant_id": tenant_id_of(user), "numero": numero_ddt,
        "cliente_id": cur["cliente_id"], "cliente_nome": cli.get("ragione_sociale", ""),
        "listino_id": cli.get("listino_id"),
        "data": now_utc(),
        "note": f"Generato da {cur['numero']}" + (f" · {cur.get('note_cliente', '')}" if cur.get("note_cliente") else ""),
        "righe": cur["righe"], "imponibile": cur["totale"],
        "stato_fatturazione": "non_fatturato",
        "fattura_id": None, "fattura_numero": None,
        "created_at": now_utc(), "updated_at": now_utc(),
        "origine_ordinativo_id": cur["id"], "origine_ordinativo_numero": cur["numero"],
    }
    await db.ddt.insert_one(ddt_doc)
    await db.ordinativi.update_one(merge_scope(user, {"id": oid}), {"$set": {
        "stato": "convertito_ddt", "ddt_id": did, "ddt_numero": numero_ddt, "updated_at": now_utc(),
    }})
    await log_audit(user, "CONVERT", "ordinativo", oid, {"ddt": numero_ddt})
    return await db.ordinativi.find_one(merge_scope(user, {"id": oid}), {"_id": 0})


# ---------- Portale pubblico (no auth) ----------
@router.post("/clienti/{cid}/portale-token")
async def genera_portale_token(cid: str, user: Dict = Depends(require_roles("admin"))):
    """Genera (o rigenera) il token del portale pubblico per un cliente."""
    cli = await db.clienti.find_one(merge_scope(user, {"id": cid}), {"_id": 0})
    if not cli: raise HTTPException(404, "Cliente non trovato")
    token = secrets.token_urlsafe(24)  # 32 char URL-safe
    await db.clienti.update_one(merge_scope(user, {"id": cid}), {"$set": {
        "portale_token": token, "portale_token_created_at": now_utc(),
    }})
    await log_audit(user, "CREATE", "portale_token", cid)
    return {"token": token, "url_path": f"/ordina/{token}"}


@router.delete("/clienti/{cid}/portale-token")
async def revoca_portale_token(cid: str, user: Dict = Depends(require_roles("admin"))):
    await db.clienti.update_one(merge_scope(user, {"id": cid}), {
        "$unset": {"portale_token": "", "portale_token_created_at": ""}
    })
    return {"ok": True}


class InviaLinkIn(BaseModel):
    tipo: Literal["self_service", "diretto"] = "self_service"
    to_override: Optional[str] = None
    base_url: Optional[str] = None  # origin del frontend (es. https://app.cleantec.it)


@router.post("/clienti/{cid}/invia-link-portale")
async def invia_link_portale(cid: str, body: InviaLinkIn,
                             user: Dict = Depends(require_roles("admin", "contabilita"))):
    """Invia via email al cliente il link al portale (self-service o diretto)."""
    from smtp_service import send_email, is_smtp_configured

    cli = await db.clienti.find_one(merge_scope(user, {"id": cid}), {"_id": 0})
    if not cli:
        raise HTTPException(404, "Cliente non trovato")
    if not cli.get("attivo", True):
        raise HTTPException(400, "Cliente disattivato")

    to_email = (body.to_override or cli.get("email") or "").strip()
    if not to_email or "@" not in to_email:
        raise HTTPException(400, "Email cliente mancante o non valida — aggiorna l'anagrafica")

    company = await db.company.find_one({"tenant_id": cli["tenant_id"]}, {"_id": 0}) or {}

    if body.tipo == "diretto":
        token = cli.get("portale_token")
        if not token:
            # genera al volo se mancante
            token = secrets.token_urlsafe(24)
            await db.clienti.update_one(merge_scope(user, {"id": cid}),
                                        {"$set": {"portale_token": token, "portale_token_created_at": now_utc()}})
        link_path = f"/ordina/{token}"
        link_label = "link diretto al catalogo"
    else:
        link_path = "/portale"
        link_label = "link al portale (accedi con la tua P.IVA o Codice Fiscale)"

    # URL completo: priority a base_url passato dal frontend, poi company.sito
    base = (body.base_url or company.get("sito") or "").rstrip("/")
    full_url = (base + link_path) if base else link_path

    subject = f"Il tuo link per gli ordini · {company.get('nome') or company.get('ragione_sociale') or 'CleanTec'}"
    body_text = (
        f"Gentile {cli.get('ragione_sociale')},\n\n"
        f"di seguito il {link_label} per inviare facilmente un nuovo ordinativo:\n\n"
        f"  {full_url}\n\n"
        f"{'Il link è personale e valido fino a revoca.' if body.tipo == 'diretto' else 'Apri il link e identificati con P.IVA o Codice Fiscale per accedere al tuo catalogo personalizzato.'}\n\n"
        f"Cordiali saluti,\n"
        f"{company.get('nome') or company.get('ragione_sociale') or 'CleanTec'}"
    )
    body_html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#1e293b;line-height:1.5;max-width:560px;margin:auto;padding:24px;">
      <h2 style="color:#4F46E5;margin:0 0 16px;">Il tuo link per gli ordini</h2>
      <p>Gentile <b>{cli.get('ragione_sociale')}</b>,</p>
      <p>di seguito il {link_label}:</p>
      <p style="margin:24px 0;">
        <a href="{full_url}" style="background:#4F46E5;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;display:inline-block;font-weight:600;">Apri portale ordini</a>
      </p>
      <p style="font-size:12px;color:#64748b;">Oppure copia questo link nel browser:<br/><code style="word-break:break-all;">{full_url}</code></p>
      <p style="font-size:12px;color:#94a3b8;margin-top:24px;">{'Il link è personale e valido fino a revoca.' if body.tipo == 'diretto' else 'Identificati con la tua P.IVA o Codice Fiscale per accedere al catalogo.'}</p>
      <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0;"/>
      <p style="font-size:11px;color:#94a3b8;">{company.get('nome') or 'CleanTec'} · {company.get('email') or ''}</p>
    </body></html>
    """

    smtp_ok = await is_smtp_configured()
    event = await send_email(
        to=to_email, subject=subject, body_text=body_text, body_html=body_html,
        context={"trigger": "invio_link_portale", "cliente_id": cid, "tipo": body.tipo},
        tenant_id=cli["tenant_id"],
    )

    await log_audit(user, "EMAIL_SEND", "cliente", cid,
                    {"to": to_email, "tipo": body.tipo, "smtp_configured": smtp_ok, "status": event.get("status")})

    return {
        "ok": True,
        "to": to_email,
        "tipo": body.tipo,
        "url": full_url,
        "smtp_configured": smtp_ok,
        "status": event.get("status"),
        "provider": event.get("provider"),
        "message": ("Email inviata con successo" if event.get("status") == "sent"
                    else "SMTP non configurato: link salvato nei log (stub)" if event.get("status") == "logged"
                    else f"Invio fallito: {event.get('error', 'errore sconosciuto')}"),
    }


@public_router.get("/portale/{token}")
async def portale_info(token: str):
    cli = await _resolve_portale_token(token)
    if not cli: raise HTTPException(404, "Link non valido o scaduto")
    if not cli.get("attivo", True): raise HTTPException(403, "Account disattivato")
    # Load company (branding della lavanderia madre) e articoli
    tenant_id = cli["tenant_id"]
    company = await db.company.find_one({"tenant_id": tenant_id}, {"_id": 0}) or {}
    listino_id = cli.get("listino_id")
    listino = None
    prezzi_map: Dict[str, float] = {}
    if listino_id:
        listino = await db.listini.find_one({"tenant_id": tenant_id, "id": listino_id}, {"_id": 0})
        async for p in db.listini_prezzi.find({"tenant_id": tenant_id, "listino_id": listino_id}, {"_id": 0}):
            prezzi_map[p["articolo_id"]] = p["prezzo"]
    tipo = (listino or {}).get("tipo", "lavaggio")
    default_key = "prezzo_noleggio" if tipo == "noleggio" else "prezzo_lavaggio"
    articoli_raw = await db.articoli.find(
        {"tenant_id": tenant_id, "attivo": True}, {"_id": 0}
    ).sort("descrizione", 1).to_list(500)
    articoli = []
    for a in articoli_raw:
        prezzo = prezzi_map.get(a["id"]) if prezzi_map else None
        if prezzo is None:
            prezzo = float(a.get(default_key) or a.get("prezzo") or 0)
        articoli.append({
            "id": a["id"], "codice": a.get("codice", ""),
            "descrizione": a.get("descrizione", ""),
            "unita_misura": a.get("unita_misura", "pz"),
            "prezzo": round(float(prezzo), 2),
        })
    return {
        "cliente": {
            "ragione_sociale": cli.get("ragione_sociale"),
            "denominazione_struttura": cli.get("denominazione_struttura") or cli.get("ragione_sociale"),
            "indirizzo_scarico": cli.get("indirizzo_scarico") or cli.get("indirizzo"),
        },
        "fornitore": {
            "nome": company.get("nome") or "",
            "ragione_sociale": company.get("ragione_sociale") or "",
            "email": company.get("email") or "",
            "telefono": company.get("telefono") or "",
        },
        "listino": {"nome": (listino or {}).get("nome"), "tipo": tipo} if listino else None,
        "articoli": articoli,
    }


@public_router.post("/portale/{token}/ordinativo")
async def portale_crea_ordinativo(token: str, body: PortaleOrdIn):
    cli = await _resolve_portale_token(token)
    if not cli: raise HTTPException(404, "Link non valido")
    if not cli.get("attivo", True): raise HTTPException(403, "Account disattivato")
    if not body.righe: raise HTTPException(400, "Almeno una riga")
    doc = await _create_ordinativo(
        cli["tenant_id"], cli["id"], body, "portale",
        body.data_consegna_richiesta, body.note_cliente or "",
    )
    return {
        "numero": doc["numero"],
        "totale": doc["totale"],
        "righe": doc["righe"],
        "data_consegna_richiesta": doc["data_consegna_richiesta"],
        "stato": doc["stato"],
    }


# ---------- Portale self-service: lookup per P.IVA/CF ----------
class PortaleLookupIn(BaseModel):
    identificativo: str = Field(min_length=4, max_length=32)  # P.IVA (11) o CF (16)


async def _resolve_portale_token(token: str) -> Optional[Dict]:
    """Cerca il cliente collegato al token: prima nei token statici (clienti.portale_token),
    poi nelle sessioni effimere (portale_sessions con expires_at futuro)."""
    cli = await db.clienti.find_one({"portale_token": token}, {"_id": 0})
    if cli:
        return cli
    sess = await db.portale_sessions.find_one({"token": token}, {"_id": 0})
    if not sess:
        return None
    exp = sess.get("expires_at")
    if exp:
        # Mongo restituisce datetime naive; rendi naive anche il riferimento
        ref = now_utc().replace(tzinfo=None) if hasattr(now_utc(), "tzinfo") and now_utc().tzinfo else now_utc()
        exp_n = exp.replace(tzinfo=None) if getattr(exp, "tzinfo", None) else exp
        if exp_n < ref:
            return None
    return await db.clienti.find_one({"id": sess["cliente_id"], "tenant_id": sess["tenant_id"]}, {"_id": 0})


@public_router.post("/portale/lookup")
async def portale_lookup(body: PortaleLookupIn):
    """Cliente self-service: inserisce P.IVA o CF, riceve un session_token effimero (TTL 1h).

    Ricerca esatta su `partita_iva` OR `codice_fiscale` cross-tenant.
    Anti-enumeration: stesso 404 per non-trovato e disattivato.
    Rate-limit: max 10 lookup falliti per identificativo nei 60s precedenti (mitigazione brute-force).
    """
    ident = (body.identificativo or "").strip().upper()
    if not ident:
        raise HTTPException(400, "Identificativo richiesto")

    # Rate-limit semplice: conta i tentativi falliti recenti per questo identificativo
    cutoff = now_utc() - timedelta(seconds=60)
    fails_recent = await db.portale_lookup_failed.count_documents({
        "identificativo": ident,
        "at": {"$gte": cutoff.replace(tzinfo=None)},
    })
    if fails_recent >= 10:
        raise HTTPException(429, "Troppi tentativi. Riprova tra qualche minuto.")

    cli = await db.clienti.find_one({
        "$or": [
            {"partita_iva": ident},
            {"codice_fiscale": ident},
        ],
    }, {"_id": 0})
    if not cli or not cli.get("attivo", True):
        # Log tentativo fallito per rate-limit
        await db.portale_lookup_failed.insert_one({
            "identificativo": ident,
            "at": now_utc().replace(tzinfo=None),
        })
        raise HTTPException(404, "Nessun cliente trovato con questo identificativo")

    token = secrets.token_urlsafe(24)
    expires = now_utc() + timedelta(hours=1)
    await db.portale_sessions.insert_one({
        "token": token,
        "tenant_id": cli["tenant_id"],
        "cliente_id": cli["id"],
        "created_at": now_utc(),
        "expires_at": expires,
    })
    return {
        "token": token,
        "cliente": {
            "ragione_sociale": cli.get("ragione_sociale"),
            "denominazione_struttura": cli.get("denominazione_struttura") or cli.get("ragione_sociale"),
            "indirizzo": cli.get("indirizzo"),
        },
        "url_path": f"/ordina/{token}",
        "expires_at": expires.isoformat(),
    }
