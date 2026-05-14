"""Offerte commerciali & Preventivi → convertibili in Contratto.

Flusso: bozza → (invio/editing) → accettata → contratto (nuovo progressivo CT).

Schema offerte:
  id, tenant_id, numero (OF-YYYY-NNNNN)
  cliente_id, cliente_snapshot {ragione_sociale, indirizzo, partita_iva, codice_fiscale, email, telefono, pec, codice_sdi}
  listino_id (opzionale, lookup iniziale)
  durata_mesi (int)
  data_creazione (datetime), data_scadenza (date ISO)
  righe: [{articolo_id, codice, descrizione, unita_misura, quantita,
           prezzo_unitario, sconto_perc, sconto_eur, prezzo_finale, totale}]
  imponibile, sconto_totale
  termini_condizioni: [{titolo, testo}]
  stato: "bozza" | "inviata" | "accettata" | "rifiutata" | "contratto"
  contratto_numero (CT-YYYY-NNNNN), contratto_data
  note
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional, Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import (
    db, new_id, now_utc, next_seq,
    get_current_user, require_roles, tenant_scope, merge_scope, tenant_id_of, log_audit,
)

router = APIRouter(tags=["offerte"])


# ---------- Schemas ----------
class TermineCondizione(BaseModel):
    titolo: str
    testo: str


class RigaOfferta(BaseModel):
    articolo_id: str
    quantita: float = Field(ge=0.01)
    sconto_perc: float = Field(default=0.0, ge=0, le=100)
    sconto_eur: float = Field(default=0.0, ge=0)


class OffertaIn(BaseModel):
    cliente_id: str
    listino_id: Optional[str] = None
    durata_mesi: int = Field(default=12, ge=1, le=120)
    data_scadenza: Optional[str] = None   # ISO date 'YYYY-MM-DD'
    note: Optional[str] = ""
    termini_condizioni: List[TermineCondizione] = Field(default_factory=list)
    righe: List[RigaOfferta]


class OffertaPatch(BaseModel):
    durata_mesi: Optional[int] = Field(default=None, ge=1, le=120)
    data_scadenza: Optional[str] = None
    note: Optional[str] = None
    termini_condizioni: Optional[List[TermineCondizione]] = None
    righe: Optional[List[RigaOfferta]] = None
    stato: Optional[Literal["bozza", "inviata", "accettata", "rifiutata"]] = None


# ---------- Helpers ----------
async def _resolve_righe(user: Dict, cliente_id: str, listino_id: Optional[str], righe: List[RigaOfferta]) -> List[Dict]:
    """Risolve prezzi dal listino (o da prezzo articolo) e calcola totali riga con sconti."""
    cliente = await db.clienti.find_one(merge_scope(user, {"id": cliente_id}), {"_id": 0})
    if not cliente:
        raise HTTPException(404, "Cliente non trovato")
    effective_listino_id = listino_id or cliente.get("listino_id")
    listino = None
    if effective_listino_id:
        listino = await db.listini.find_one(merge_scope(user, {"id": effective_listino_id}), {"_id": 0})
    tipo = (listino or {}).get("tipo", "lavaggio")
    default_key = "prezzo_noleggio" if tipo == "noleggio" else "prezzo_lavaggio"

    resolved: List[Dict] = []
    for r in righe:
        art = await db.articoli.find_one(merge_scope(user, {"id": r.articolo_id}), {"_id": 0})
        if not art:
            raise HTTPException(400, f"Articolo {r.articolo_id} non trovato")
        prezzo = None
        if effective_listino_id:
            p_doc = await db.listini_prezzi.find_one(merge_scope(user, {
                "listino_id": effective_listino_id, "articolo_id": r.articolo_id,
            }), {"_id": 0})
            if p_doc and p_doc.get("prezzo") is not None:
                prezzo = float(p_doc["prezzo"])
        if prezzo is None:
            prezzo = float(art.get(default_key) or art.get("prezzo") or 0)

        # Applica sconto: prima percentuale, poi valore fisso
        prezzo_finale = prezzo * (1 - r.sconto_perc / 100.0) - r.sconto_eur
        prezzo_finale = max(0.0, round(prezzo_finale, 4))
        totale = round(prezzo_finale * r.quantita, 2)
        resolved.append({
            "articolo_id": r.articolo_id,
            "codice": art.get("codice", ""),
            "descrizione": art.get("descrizione", ""),
            "unita_misura": art.get("unita_misura", "pz"),
            "quantita": float(r.quantita),
            "prezzo_unitario": round(prezzo, 4),
            "sconto_perc": float(r.sconto_perc),
            "sconto_eur": float(r.sconto_eur),
            "prezzo_finale": prezzo_finale,
            "totale": totale,
        })
    return resolved


def _client_snapshot(cli: Dict) -> Dict:
    keys = ["ragione_sociale", "denominazione_struttura", "indirizzo", "indirizzo_scarico",
            "partita_iva", "codice_fiscale", "email", "telefono", "pec", "codice_sdi"]
    return {k: cli.get(k, "") for k in keys}


# ---------- Endpoints ----------
@router.get("/offerte")
async def list_offerte(
    cliente_id: Optional[str] = None,
    stato: Optional[str] = None,
    limit: int = 200,
    user: Dict = Depends(get_current_user),
):
    filt = dict(tenant_scope(user))
    if cliente_id:
        filt["cliente_id"] = cliente_id
    if stato:
        filt["stato"] = stato
    rows = await db.offerte.find(filt, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return rows


@router.get("/offerte/{oid}")
async def get_offerta(oid: str, user: Dict = Depends(get_current_user)):
    doc = await db.offerte.find_one(merge_scope(user, {"id": oid}), {"_id": 0})
    if not doc:
        raise HTTPException(404, "Offerta non trovata")
    return doc


@router.post("/offerte")
async def create_offerta(body: OffertaIn, user: Dict = Depends(require_roles("admin", "contabilita"))):
    if not body.righe:
        raise HTTPException(400, "Almeno una riga è obbligatoria")
    cliente = await db.clienti.find_one(merge_scope(user, {"id": body.cliente_id}), {"_id": 0})
    if not cliente:
        raise HTTPException(404, "Cliente non trovato")
    rows = await _resolve_righe(user, body.cliente_id, body.listino_id, body.righe)
    imponibile = round(sum(r["totale"] for r in rows), 2)
    sconto_totale = round(sum((r["prezzo_unitario"] - r["prezzo_finale"]) * r["quantita"] for r in rows), 2)

    seq = await next_seq("offerta")
    oid = new_id()
    from core import format_numero
    numero = await format_numero("offerta", "OF", seq)
    doc = {
        "id": oid,
        "tenant_id": tenant_id_of(user),
        "numero": numero,
        "cliente_id": body.cliente_id,
        "cliente_snapshot": _client_snapshot(cliente),
        "listino_id": body.listino_id or cliente.get("listino_id"),
        "durata_mesi": body.durata_mesi,
        "data_creazione": now_utc(),
        "data_scadenza": body.data_scadenza,
        "righe": rows,
        "imponibile": imponibile,
        "sconto_totale": sconto_totale,
        "termini_condizioni": [t.model_dump() for t in body.termini_condizioni],
        "stato": "bozza",
        "contratto_numero": None,
        "contratto_data": None,
        "note": body.note or "",
        "created_at": now_utc(),
        "updated_at": now_utc(),
        "created_by": user["id"],
    }
    await db.offerte.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "offerta", oid, {"numero": numero})
    return doc


@router.patch("/offerte/{oid}")
async def update_offerta(oid: str, body: OffertaPatch, user: Dict = Depends(require_roles("admin", "contabilita"))):
    current = await db.offerte.find_one(merge_scope(user, {"id": oid}), {"_id": 0})
    if not current:
        raise HTTPException(404, "Offerta non trovata")
    if current["stato"] == "contratto":
        raise HTTPException(409, "Offerta già convertita in contratto — non modificabile")
    patch: Dict = {}
    data = body.model_dump(exclude_unset=True)
    if "righe" in data and data["righe"] is not None:
        rows = await _resolve_righe(user, current["cliente_id"], current.get("listino_id"), body.righe)
        patch["righe"] = rows
        patch["imponibile"] = round(sum(r["totale"] for r in rows), 2)
        patch["sconto_totale"] = round(sum((r["prezzo_unitario"] - r["prezzo_finale"]) * r["quantita"] for r in rows), 2)
    for k in ("durata_mesi", "data_scadenza", "note", "stato"):
        if k in data:
            patch[k] = data[k]
    if "termini_condizioni" in data and data["termini_condizioni"] is not None:
        patch["termini_condizioni"] = [t.model_dump() for t in body.termini_condizioni]
    patch["updated_at"] = now_utc()
    await db.offerte.update_one(merge_scope(user, {"id": oid}), {"$set": patch})
    await log_audit(user, "UPDATE", "offerta", oid, {"fields": list(patch.keys())})
    doc = await db.offerte.find_one(merge_scope(user, {"id": oid}), {"_id": 0})
    return doc


@router.post("/offerte/{oid}/converti-contratto")
async def converti_contratto(oid: str, user: Dict = Depends(require_roles("admin", "contabilita"))):
    current = await db.offerte.find_one(merge_scope(user, {"id": oid}), {"_id": 0})
    if not current:
        raise HTTPException(404, "Offerta non trovata")
    if current["stato"] == "contratto":
        raise HTTPException(409, f"Già convertita in contratto {current.get('contratto_numero')}")
    if current["stato"] == "rifiutata":
        raise HTTPException(400, "Offerta rifiutata — impossibile convertire")
    seq = await next_seq("contratto")
    from core import format_numero
    cn = await format_numero("contratto", "CT", seq)
    await db.offerte.update_one(merge_scope(user, {"id": oid}), {"$set": {
        "stato": "contratto",
        "contratto_numero": cn,
        "contratto_data": now_utc(),
        "updated_at": now_utc(),
    }})
    await log_audit(user, "CONVERT", "offerta", oid, {"contratto": cn})
    return await db.offerte.find_one(merge_scope(user, {"id": oid}), {"_id": 0})


@router.delete("/offerte/{oid}")
async def delete_offerta(oid: str, user: Dict = Depends(require_roles("admin", "contabilita"))):
    current = await db.offerte.find_one(merge_scope(user, {"id": oid}), {"_id": 0})
    if not current:
        raise HTTPException(404, "Offerta non trovata")
    if current["stato"] == "contratto":
        raise HTTPException(409, "Contratto attivo — non eliminabile")
    await db.offerte.delete_one(merge_scope(user, {"id": oid}))
    await log_audit(user, "DELETE", "offerta", oid)
    return {"ok": True}


@router.get("/offerte/{oid}/pdf")
async def offerta_pdf(oid: str, tipo: str = "offerta", user: Dict = Depends(get_current_user)):
    """tipo = 'offerta' | 'contratto' (contratto solo se stato=contratto)."""
    from fastapi import Response
    from pdf_service import generate_offerta_pdf
    from routers.company import load_company_for_tenant
    doc = await db.offerte.find_one(merge_scope(user, {"id": oid}), {"_id": 0})
    if not doc:
        raise HTTPException(404, "Offerta non trovata")
    if tipo == "contratto" and doc.get("stato") != "contratto":
        raise HTTPException(400, "Offerta non ancora convertita in contratto")
    cliente = await db.clienti.find_one(merge_scope(user, {"id": doc["cliente_id"]}), {"_id": 0}) or {}
    company = await load_company_for_tenant(user["tenant_id"])
    pdf = generate_offerta_pdf(doc, cliente, company, as_contratto=(tipo == "contratto"))
    numero = doc.get("contratto_numero") if tipo == "contratto" else doc.get("numero")
    filename = f"{numero or 'Offerta'}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ---------- Termini & Condizioni template library ----------
class TermineTemplateIn(BaseModel):
    titolo: str = Field(min_length=1, max_length=200)
    testo: str = Field(min_length=1)


@router.get("/termini-templates")
async def list_termini_templates(user: Dict = Depends(require_roles("admin", "contabilita"))):
    docs = await db.termini_templates.find(tenant_scope(user), {"_id": 0}).sort("titolo", 1).to_list(200)
    return docs


@router.post("/termini-templates")
async def create_termini_template(body: TermineTemplateIn, user: Dict = Depends(require_roles("admin"))):
    tid = new_id()
    doc = {
        "id": tid, "tenant_id": tenant_id_of(user),
        "titolo": body.titolo.strip(), "testo": body.testo.strip(),
        "created_at": now_utc(), "updated_at": now_utc(),
    }
    await db.termini_templates.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/termini-templates/{tid}")
async def delete_termini_template(tid: str, user: Dict = Depends(require_roles("admin"))):
    await db.termini_templates.delete_one(merge_scope(user, {"id": tid}))
    return {"ok": True}
