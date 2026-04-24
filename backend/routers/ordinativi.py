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
from datetime import datetime, timezone
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
    numero = f"ORD-{datetime.now(timezone.utc).year}-{seq:05d}"
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
    numero_ddt = f"DDT-{datetime.now(timezone.utc).year}-{ddt_seq:05d}"
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


@public_router.get("/portale/{token}")
async def portale_info(token: str):
    cli = await db.clienti.find_one({"portale_token": token}, {"_id": 0})
    if not cli: raise HTTPException(404, "Link non valido o revocato")
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
    cli = await db.clienti.find_one({"portale_token": token}, {"_id": 0})
    if not cli: raise HTTPException(404, "Link non valido")
    if not cli.get("attivo", True): raise HTTPException(403, "Account disattivato")
    if not body.righe: raise HTTPException(400, "Almeno una riga")
    doc = await _create_ordinativo(
        cli["tenant_id"], cli["id"], body, "portale",
        body.data_consegna_richiesta, body.note_cliente or "",
    )
    # Return minimal safe view
    return {
        "numero": doc["numero"],
        "totale": doc["totale"],
        "righe": doc["righe"],
        "data_consegna_richiesta": doc["data_consegna_richiesta"],
        "stato": doc["stato"],
    }
