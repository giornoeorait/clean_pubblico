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
import re
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Literal
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
    quantita: int = Field(gt=0)


class OrdinativoIn(BaseModel):
    cliente_id: str
    data_consegna_richiesta: Optional[str] = None
    righe: List[RigaOrd]
    note_cliente: Optional[str] = ""
    note_interne: Optional[str] = ""
    ordine_di_prova: bool = False


class OrdinativoPatch(BaseModel):
    data_consegna_richiesta: Optional[str] = None
    righe: Optional[List[RigaOrd]] = None
    note_interne: Optional[str] = None
    stato: Optional[Literal["nuovo", "in_lavorazione", "annullato"]] = None


class ProduzionePatch(BaseModel):
    operatore: Optional[str] = None
    stato: Optional[Literal["in_lavorazione"]] = None
    righe_eseguite: Optional[List[bool]] = None
    righe_conteggio: Optional[List[float]] = None


class PortaleOrdIn(BaseModel):
    data_consegna_richiesta: str
    righe: List[RigaOrd]
    note_cliente: Optional[str] = ""
    ritiro_lavanderia: Optional[bool] = False  # ordini < 50€ → cliente ritira in lavanderia


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

        # Validazione vincolo multiplo
        multiplo = int(a.get("multiplo_quantita") or 1)
        if multiplo > 1:
            q = float(r.quantita)
            if q != int(q) or int(q) % multiplo != 0:
                raise HTTPException(
                    400,
                    f"'{a.get('descrizione') or a.get('codice') or 'articolo'}': "
                    f"la quantità deve essere un multiplo di {multiplo} (richiesti: {int(q) if q == int(q) else q})."
                )

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
            "multiplo_imballaggio": int(a.get("multiplo_imballaggio") or 1),
            "prezzo_unitario": round(prezzo, 4),
            "totale": tot,
        })
    return rows


def _cli_snapshot(cli: Dict) -> Dict:
    return {k: cli.get(k, "") for k in ("ragione_sociale", "denominazione_struttura", "indirizzo",
                                        "indirizzo_scarico", "partita_iva", "email", "telefono")}


async def _create_ordinativo(tenant_id: str, cli_id: str, body: RigaOrd | OrdinativoIn | PortaleOrdIn,
                             origine: str, data_consegna: Optional[str], note_cliente: str = "",
                             note_interne: str = "", created_by: Optional[str] = None,
                             ritiro_lavanderia: bool = False, ordine_di_prova: bool = False) -> Dict:
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
        "ritiro_lavanderia": bool(ritiro_lavanderia),
        "ordine_di_prova": bool(ordine_di_prova),
        "created_at": now_utc(), "updated_at": now_utc(),
        "created_by": created_by,
    }
    await db.ordinativi.insert_one(doc)
    doc.pop("_id", None)

    # Notifica email a destinatari configurati (best-effort, non blocca creazione)
    try:
        await _notify_new_order(tenant_id, doc, cli)
    except Exception:
        pass
    # Conferma ordine al CLIENTE (email cliente) — best-effort. SKIP se ordine di prova.
    if ordine_di_prova:
        await db.ordinativi.update_one(
            {"id": doc["id"]},
            {"$set": {"client_email_last_status": "skipped",
                      "client_email_last_error": "Ordine di prova: nessuna email inviata alla struttura"}})
        return doc
    try:
        cres = await _send_order_confirmation_to_client(tenant_id, doc, cli)
        entry = {
            "at": now_utc(),
            "by": "system",
            "to": cres.get("to"),
            "status": cres.get("status"),
            "error": cres.get("error"),
            "recipients_count": cres.get("recipients_count", 0),
        }
        await db.ordinativi.update_one(
            {"id": doc["id"]},
            {
                "$push": {"client_emails_sent": entry},
                "$set": {
                    "client_email_last_status": cres.get("status"),
                    "client_email_last_at": now_utc(),
                    "client_email_last_to": cres.get("to"),
                    "client_email_last_error": cres.get("error"),
                },
            },
        )
    except Exception:
        pass
    return doc


async def _notify_new_order(tenant_id: str, ord_doc: Dict, cliente: Dict) -> None:
    """Best-effort: invia email a tutti i destinatari configurati per le notifiche ordini."""
    company = await db.company.find_one({"tenant_id": tenant_id}, {"_id": 0}) or {}
    n = company.get("order_notifications") or {}
    if not n.get("enabled", True):
        return
    recipients = [r for r in (n.get("recipients") or []) if r]
    if not recipients:
        return
    from smtp_service import send_email
    azienda = company.get("nome") or company.get("ragione_sociale") or tenant_id
    cli_label = (cliente.get("denominazione_struttura")
                 or cliente.get("ragione_sociale") or "Cliente sconosciuto")
    righe = ord_doc.get("righe") or []
    righe_text = "\n".join(
        f"  · {r.get('descrizione') or r.get('codice') or '—'} × {int(r['quantita']) if r['quantita'] == int(r['quantita']) else r['quantita']}"
        for r in righe
    ) or "  (nessuna riga)"
    data_consegna = ord_doc.get("data_consegna_richiesta") or "non specificata"
    totale = ord_doc.get("totale", 0)
    origine_label = "Portale Self-Service" if ord_doc.get("origine") == "portale" else "Inserimento interno"
    subject = f"[CleanTec] Nuovo ordine {ord_doc.get('numero')} · {cli_label}"
    text = (
        f"Nuovo ordine ricevuto per il tenant \"{azienda}\".\n\n"
        f"Numero      : {ord_doc.get('numero')}\n"
        f"Cliente     : {cli_label}\n"
        f"Origine     : {origine_label}\n"
        f"Consegna    : {data_consegna}\n"
        f"Totale      : € {totale:.2f}\n\n"
        f"Articoli:\n{righe_text}\n\n"
    )
    note_c = (ord_doc.get("note_cliente") or "").strip()
    if note_c:
        text += f"Note cliente:\n{note_c}\n\n"
    text += "— CleanTec (notifica automatica)"
    for r in recipients:
        try:
            await send_email(
                to=r, subject=subject, body_text=text,
                tenant_id=tenant_id, context={"type": "new_order", "numero": ord_doc.get("numero")},
            )
        except Exception:
            # Skip individual failures
            pass


async def _send_order_confirmation_to_client(tenant_id: str, ord_doc: Dict, cliente: Dict) -> Dict[str, Any]:
    """Invia al CLIENTE (indirizzo `email` in anagrafica) la conferma dell'ordine
    con riepilogo articoli, data consegna, totale e eventuale ritiro-lavanderia.

    Legge SOLO il campo `email` dell'anagrafica cliente (il campo `pec` è riservato
    alla fatturazione elettronica e non deve essere usato per invii commerciali).
    Supporta indirizzi multipli separati da virgola, punto-virgola o whitespace.
    Ritorna dict {status, to, error}. status='skipped' se nessuna email valida.
    """
    # Raccolta candidati email dal solo campo `email` (esclusa la PEC)
    raw_email = (cliente.get("email") or "").strip()
    # Split su virgola, punto-virgola, newline, whitespace
    parts = re.split(r"[,;\s]+", raw_email)
    recipients: List[str] = []
    seen = set()
    for p in parts:
        p = p.strip().strip("<>").strip()
        if not p or "@" not in p or "." not in p.split("@")[-1]:
            continue
        low = p.lower()
        if low in seen:
            continue
        seen.add(low)
        recipients.append(p)

    if not recipients:
        return {"status": "skipped", "to": "", "error": "Nessuna email valida nell'anagrafica cliente (campo 'email' vuoto o non valido)"}

    from smtp_service import send_email
    cli_label = (cliente.get("denominazione_struttura")
                 or cliente.get("ragione_sociale") or "Cliente")
    righe = ord_doc.get("righe") or []

    def _qty_fmt(q):
        try:
            qn = float(q)
            return int(qn) if qn == int(qn) else qn
        except Exception:
            return q

    righe_lines = "\n".join(
        f"  · {r.get('descrizione') or r.get('codice') or '—'} × {_qty_fmt(r.get('quantita'))}"
        for r in righe
    ) or "  (nessuna riga)"

    d_consegna = ord_doc.get("data_consegna_richiesta") or "non specificata"
    if hasattr(d_consegna, "strftime"):
        d_consegna_str = d_consegna.strftime("%d/%m/%Y")
    else:
        try:
            d_consegna_str = str(d_consegna)[:10]
            if len(d_consegna_str) == 10 and d_consegna_str[4] == "-":
                y, m, d = d_consegna_str.split("-")
                d_consegna_str = f"{d}/{m}/{y}"
        except Exception:
            d_consegna_str = str(d_consegna)

    totale = ord_doc.get("totale", 0)
    numero = ord_doc.get("numero")
    ritiro_lav = ord_doc.get("ritiro_lavanderia", False)
    note_c = (ord_doc.get("note_cliente") or "").strip()

    subject = f"Conferma ordine {numero} - CleanTec"
    lines = [
        f"Gentile {cli_label},",
        "",
        "la ringraziamo per il suo ordine.",
        "Le confermiamo di aver ricevuto le seguenti richieste:",
        "",
        f"Numero ordine: {numero}",
        f"Data consegna richiesta: {d_consegna_str}",
        "",
        "Articoli:",
        righe_lines,
        "",
        f"Totale stimato: € {float(totale):.2f}",
    ]
    if ritiro_lav:
        lines += ["", "L'ordine sarà ritirato in lavanderia."]
    if note_c:
        lines += ["", f"Note: {note_c}"]
    lines += ["", "Cordiali saluti,", "CleanTec"]
    body_text = "\n".join(lines)

    # Invia a ciascun destinatario (uno alla volta per tracciare gli esiti)
    last_status = "logged"
    sent_ok = False
    failures = []
    for r in recipients:
        try:
            event = await send_email(
                to=r,
                subject=subject,
                body_text=body_text,
                tenant_id=tenant_id,
                context={"type": "order_confirmation_to_client", "numero": numero, "ordinativo_id": ord_doc.get("id")},
            )
            st = event.get("status", "logged")
            if st == "sent":
                sent_ok = True
                last_status = "sent"
            elif st == "logged":
                if last_status != "sent":
                    last_status = "logged"
            else:  # failed
                failures.append(f"{r}: {event.get('error') or 'invio fallito'}")
                if last_status != "sent":
                    last_status = "failed"
        except Exception as e:
            failures.append(f"{r}: {str(e)[:200]}")
            if last_status != "sent":
                last_status = "failed"

    return {
        "status": last_status,
        "to": ", ".join(recipients),
        "sent_ok": sent_ok,
        "recipients_count": len(recipients),
        "error": " · ".join(failures) if failures and not sent_ok else None,
    }


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


@router.get("/ordinativi/recap")
async def ordinativi_recap(user: Dict = Depends(get_current_user)):
    """Riepilogo cumulativo articoli ancora da lavorare.
    Considera SOLO ordinativi con stato `nuovo` o `in_lavorazione` (cioè aperti,
    non evasi, non trasformati in DDT, non annullati).
    Quando un ordinativo viene convertito in DDT il suo stato passa a
    `convertito_ddt` e quindi viene escluso automaticamente da questo recap.
    """
    filt = {**tenant_scope(user), "stato": {"$in": ["nuovo", "in_lavorazione"]}}
    ords = await db.ordinativi.find(filt, {"_id": 0}).to_list(5000)

    agg: Dict[str, Dict[str, Any]] = {}
    earliest_by_aid: Dict[str, Any] = {}
    nuovo_cnt = 0
    in_lav_cnt = 0
    for o in ords:
        st = o.get("stato")
        if st == "nuovo":
            nuovo_cnt += 1
        elif st == "in_lavorazione":
            in_lav_cnt += 1
        o_date = o.get("data_richiesta") or o.get("created_at")
        for r in (o.get("righe") or []):
            aid = r.get("articolo_id")
            if not aid:
                continue
            qty = int(r.get("quantita") or 0)
            tot = float(r.get("totale") or 0)
            e = agg.setdefault(aid, {
                "articolo_id": aid,
                "codice": r.get("codice", ""),
                "descrizione": r.get("descrizione", ""),
                "unita_misura": r.get("unita_misura", "pz"),
                "quantita_totale": 0,
                "totale_stimato": 0.0,
                "ordinativi_count": 0,
                "ordinativi_nuovo": 0,
                "ordinativi_in_lavorazione": 0,
            })
            e["quantita_totale"] += qty
            e["totale_stimato"] += tot
            e["ordinativi_count"] += 1
            if st == "nuovo":
                e["ordinativi_nuovo"] += 1
            elif st == "in_lavorazione":
                e["ordinativi_in_lavorazione"] += 1
            # prima data ordine per articolo (gestisce dt/str mix)
            if o_date is not None:
                prev = earliest_by_aid.get(aid)
                if prev is None:
                    earliest_by_aid[aid] = o_date
                else:
                    try:
                        if o_date < prev:
                            earliest_by_aid[aid] = o_date
                    except TypeError:
                        # tipi diversi (datetime vs string), normalizziamo a string ISO
                        a_str = o_date.isoformat() if hasattr(o_date, "isoformat") else str(o_date)
                        p_str = prev.isoformat() if hasattr(prev, "isoformat") else str(prev)
                        if a_str < p_str:
                            earliest_by_aid[aid] = o_date

    items: List[Dict[str, Any]] = []
    for aid, e in agg.items():
        e["totale_stimato"] = round(e["totale_stimato"], 2)
        d0 = earliest_by_aid.get(aid)
        if hasattr(d0, "isoformat"):
            e["prima_data_ordine"] = d0.isoformat()
        elif d0:
            e["prima_data_ordine"] = str(d0)
        else:
            e["prima_data_ordine"] = None
        items.append(e)
    items.sort(key=lambda x: x.get("quantita_totale", 0), reverse=True)

    return {
        "items": items,
        "totale_pezzi": sum(i["quantita_totale"] for i in items),
        "totale_articoli": len(items),
        "ordinativi_aperti": len(ords),
        "ordinativi_nuovo": nuovo_cnt,
        "ordinativi_in_lavorazione": in_lav_cnt,
    }


@router.get("/ordinativi/{oid}")
async def get_ord(oid: str, user: Dict = Depends(get_current_user)):
    doc = await db.ordinativi.find_one(merge_scope(user, {"id": oid}), {"_id": 0})
    if not doc: raise HTTPException(404, "Ordinativo non trovato")
    return doc


@router.get("/ordinativi/{oid}/pdf")
async def ord_pdf(oid: str, user: Dict = Depends(get_current_user)):
    from fastapi import Response
    from routers.company import load_company_for_tenant
    from pdf_service import generate_ordinativo_pdf

    doc = await db.ordinativi.find_one(merge_scope(user, {"id": oid}), {"_id": 0})
    if not doc:
        raise HTTPException(404, "Ordinativo non trovato")
    cliente = await db.clienti.find_one(merge_scope(user, {"id": doc["cliente_id"]}), {"_id": 0}) or {}
    company = await load_company_for_tenant(user["tenant_id"])
    pdf_bytes = generate_ordinativo_pdf(doc, cliente, company)
    fname = f"ordinativo-{(doc.get('numero') or oid[:8]).replace('/', '_')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )


@router.post("/ordinativi")
async def create_ord(body: OrdinativoIn, user: Dict = Depends(require_roles("admin", "logistica", "contabilita"))):
    if not body.righe: raise HTTPException(400, "Righe obbligatorie")
    doc = await _create_ordinativo(
        tenant_id_of(user), body.cliente_id, body, "interno",
        body.data_consegna_richiesta, body.note_cliente or "", body.note_interne or "",
        created_by=user["id"], ordine_di_prova=body.ordine_di_prova,
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
    if data.get("stato") == "in_lavorazione" and not cur.get("presa_in_carico_at"):
        patch["presa_in_carico_at"] = now_utc()
    await db.ordinativi.update_one(merge_scope(user, {"id": oid}), {"$set": patch})
    return await db.ordinativi.find_one(merge_scope(user, {"id": oid}), {"_id": 0})


@router.patch("/ordinativi/{oid}/produzione")
async def update_produzione(oid: str, body: ProduzionePatch,
                            user: Dict = Depends(require_roles("admin", "logistica", "contabilita", "produzione"))):
    """Totem produzione: metti in lavorazione, flag righe eseguite, nome operatore."""
    cur = await db.ordinativi.find_one(merge_scope(user, {"id": oid}), {"_id": 0})
    if not cur:
        raise HTTPException(404, "Ordinativo non trovato")
    if cur["stato"] == "convertito_ddt":
        raise HTTPException(409, "Ordinativo già convertito in DDT")
    if cur["stato"] == "annullato":
        raise HTTPException(409, "Ordinativo annullato")
    patch: Dict = {"updated_at": now_utc()}
    if body.operatore is not None:
        patch["operatore_produzione"] = body.operatore.strip()
    if body.stato:
        patch["stato"] = body.stato
        if body.stato == "in_lavorazione" and not cur.get("presa_in_carico_at"):
            patch["presa_in_carico_at"] = now_utc()
    if body.righe_eseguite is not None:
        if len(body.righe_eseguite) != len(cur.get("righe", [])):
            raise HTTPException(422, "righe_eseguite non corrisponde al numero di righe")
        patch["righe_eseguite"] = body.righe_eseguite
    if body.righe_conteggio is not None:
        if len(body.righe_conteggio) != len(cur.get("righe", [])):
            raise HTTPException(422, "righe_conteggio non corrisponde al numero di righe")
        patch["righe_conteggio"] = body.righe_conteggio
    await db.ordinativi.update_one(merge_scope(user, {"id": oid}), {"$set": patch})
    await log_audit(user, "PRODUZIONE_UPDATE", "ordinativo", oid, {k: v for k, v in patch.items() if k != "updated_at"})
    return await db.ordinativi.find_one(merge_scope(user, {"id": oid}), {"_id": 0})


@router.delete("/ordinativi/{oid}")
async def delete_ord(oid: str, user: Dict = Depends(require_roles("admin", "logistica", "contabilita"))):
    cur = await db.ordinativi.find_one(merge_scope(user, {"id": oid}), {"_id": 0})
    if not cur: raise HTTPException(404, "Ordinativo non trovato")
    if cur["stato"] == "convertito_ddt":
        raise HTTPException(409, "Ordinativo già convertito — impossibile eliminare")
    await db.ordinativi.delete_one(merge_scope(user, {"id": oid}))
    return {"ok": True}


@router.post("/ordinativi/{oid}/reinvia-conferma")
async def reinvia_conferma_ordine(oid: str, user: Dict = Depends(require_roles("admin", "logistica", "contabilita"))):
    """Reinvia manualmente l'email di conferma ordine all'indirizzo `email` del cliente."""
    cur = await db.ordinativi.find_one(merge_scope(user, {"id": oid}), {"_id": 0})
    if not cur:
        raise HTTPException(404, "Ordinativo non trovato")
    cli = await db.clienti.find_one(merge_scope(user, {"id": cur["cliente_id"]}), {"_id": 0})
    if not cli:
        raise HTTPException(400, "Cliente non trovato")
    res = await _send_order_confirmation_to_client(user["tenant_id"], cur, cli)
    user_label = user.get("name") or user.get("email") or user.get("id", "")
    entry = {
        "at": now_utc(),
        "by": user_label,
        "to": res.get("to"),
        "status": res.get("status"),
        "error": res.get("error"),
        "recipients_count": res.get("recipients_count", 0),
    }
    await db.ordinativi.update_one(
        merge_scope(user, {"id": oid}),
        {
            "$push": {"client_emails_sent": entry},
            "$set": {
                "client_email_last_status": res.get("status"),
                "client_email_last_at": now_utc(),
                "client_email_last_to": res.get("to"),
                "client_email_last_error": res.get("error"),
                "updated_at": now_utc(),
            },
        },
    )
    if res.get("status") == "skipped":
        raise HTTPException(400, res.get("error") or "Nessuna email cliente disponibile")
    return {"ok": True, **res}


@router.post("/ordinativi/{oid}/converti-ddt")
async def converti_ddt(oid: str, user: Dict = Depends(require_roles("admin", "logistica", "contabilita", "produzione"))):
    cur = await db.ordinativi.find_one(merge_scope(user, {"id": oid}), {"_id": 0})
    if not cur: raise HTTPException(404, "Ordinativo non trovato")
    if cur["stato"] == "convertito_ddt":
        raise HTTPException(409, f"Già convertito in {cur.get('ddt_numero')}")
    if cur["stato"] == "annullato":
        raise HTTPException(400, "Ordinativo annullato")
    cli = await db.clienti.find_one(merge_scope(user, {"id": cur["cliente_id"]}), {"_id": 0})
    if not cli: raise HTTPException(404, "Cliente mancante")
    # Crea DDT — con snapshot peso (§7) usando anagrafica articoli corrente
    ddt_seq = await next_seq("ddt")
    did = new_id()
    from core import format_numero
    numero_ddt = await format_numero("ddt", "DDT", ddt_seq)

    # Snapshot peso per ogni riga + subtotali doc
    tenant_id = tenant_id_of(user)
    articoli_map: Dict[str, Dict] = {}
    for r in (cur.get("righe") or []):
        aid = r.get("articolo_id")
        if aid and aid not in articoli_map:
            a = await db.articoli.find_one({"tenant_id": tenant_id, "id": aid},
                                            {"_id": 0, "peso_medio": 1, "categoria_peso": 1})
            articoli_map[aid] = {
                "peso_medio": float((a or {}).get("peso_medio") or 0),
                "categoria_peso": ((a or {}).get("categoria_peso") or "NON_CLASSIFICATO").upper(),
            }
    peso_totale = 0.0
    peso_by_cat = {"BIANCHERIA_PIANA": 0.0, "SPUGNA": 0.0, "VARIE": 0.0, "NON_CLASSIFICATO": 0.0}
    new_righe = []
    for r in (cur.get("righe") or []):
        aid = r.get("articolo_id")
        art = articoli_map.get(aid or "", {"peso_medio": 0.0, "categoria_peso": "NON_CLASSIFICATO"})
        peso_unit = float(art.get("peso_medio") or 0)
        cat_peso = art.get("categoria_peso", "NON_CLASSIFICATO")
        if cat_peso not in peso_by_cat:
            cat_peso = "NON_CLASSIFICATO"
        qta = float(r.get("quantita") or 0)
        peso_riga = round(peso_unit * qta, 3)
        peso_totale += peso_riga
        peso_by_cat[cat_peso] += peso_riga
        new_r = dict(r)
        new_r["peso_medio_snapshot"] = round(peso_unit, 4)
        new_r["categoria_peso_snapshot"] = cat_peso
        new_r["peso_riga"] = peso_riga
        new_righe.append(new_r)

    ddt_doc = {
        "id": did, "tenant_id": tenant_id, "numero": numero_ddt,
        "cliente_id": cur["cliente_id"], "cliente_nome": cli.get("ragione_sociale", ""),
        "listino_id": cli.get("listino_id"),
        "data": now_utc(),
        "note": f"Generato da {cur['numero']}" + (f" · {cur.get('note_cliente', '')}" if cur.get("note_cliente") else ""),
        "righe": new_righe, "imponibile": cur["totale"],
        # Snapshot peso (§7-9)
        "peso_totale": round(peso_totale, 3),
        "peso_biancheria_piana": round(peso_by_cat["BIANCHERIA_PIANA"], 3),
        "peso_spugna": round(peso_by_cat["SPUGNA"], 3),
        "peso_varie": round(peso_by_cat["VARIE"], 3),
        "peso_non_classificato": round(peso_by_cat["NON_CLASSIFICATO"], 3),
        "calcolo_peso_tipo": "CALCOLO_ORIGINALE",
        "peso_calcolato_at": now_utc(),
        "stato_fatturazione": "non_fatturato",
        "fattura_id": None, "fattura_numero": None,
        "created_at": now_utc(), "updated_at": now_utc(),
        "origine_ordinativo_id": cur["id"], "origine_ordinativo_numero": cur["numero"],
        "operatore_produzione": cur.get("operatore_produzione") or "",
    }
    await db.ddt.insert_one(ddt_doc)
    await db.ordinativi.update_one(merge_scope(user, {"id": oid}), {"$set": {
        "stato": "convertito_ddt", "ddt_id": did, "ddt_numero": numero_ddt, "updated_at": now_utc(),
        "chiusura_at": now_utc(),
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
            "multiplo_quantita": int(a.get("multiplo_quantita") or 1),
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
        "ordine_minimo": round(float(cli.get("ordine_minimo", 50) or 0), 2) if cli.get("ordine_minimo_attivo", True) else 0,
        "articoli": articoli,
    }


@public_router.post("/portale/{token}/ordinativo")
async def portale_crea_ordinativo(token: str, body: PortaleOrdIn):
    cli = await _resolve_portale_token(token)
    if not cli: raise HTTPException(404, "Link non valido")
    if not cli.get("attivo", True): raise HTTPException(403, "Account disattivato")
    if not body.righe: raise HTTPException(400, "Almeno una riga")
    if cli.get("ordine_minimo_attivo", True):
        minimo = round(float(cli.get("ordine_minimo", 50) or 0), 2)
        if minimo > 0:
            rows = await _resolve_righe(cli["tenant_id"], cli["id"], body.righe)
            tot = round(sum(r["totale"] for r in rows), 2)
            if tot < minimo:
                raise HTTPException(400, f"Ordine minimo € {minimo:.2f}: il totale attuale è € {tot:.2f}. Aggiungi articoli per raggiungere la soglia.")
    doc = await _create_ordinativo(
        cli["tenant_id"], cli["id"], body, "portale",
        body.data_consegna_richiesta, body.note_cliente or "",
        ritiro_lavanderia=bool(body.ritiro_lavanderia),
    )
    return {
        "numero": doc["numero"],
        "totale": doc["totale"],
        "righe": doc["righe"],
        "data_consegna_richiesta": doc["data_consegna_richiesta"],
        "stato": doc["stato"],
        "ritiro_lavanderia": doc.get("ritiro_lavanderia", False),
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
    """Cliente self-service: inserisce P.IVA o CF.

    - Se UN solo cliente attivo matcha → ritorna direttamente il `session_token` (TTL 1h).
    - Se PIÙ clienti attivi matchano (stessa P.IVA con strutture multiple) → ritorna
      `multiple_matches=True` con la lista delle strutture; l'utente seleziona quella
      desiderata e chiama `/portale/lookup/select`.

    Anti-enumeration: stesso 404 per non-trovato e disattivato.
    Rate-limit: max 10 lookup falliti per identificativo nei 60s precedenti.
    """
    ident = (body.identificativo or "").strip().upper()
    if not ident:
        raise HTTPException(400, "Identificativo richiesto")

    # Rate-limit
    cutoff = now_utc() - timedelta(seconds=60)
    fails_recent = await db.portale_lookup_failed.count_documents({
        "identificativo": ident,
        "at": {"$gte": cutoff.replace(tzinfo=None)},
    })
    if fails_recent >= 10:
        raise HTTPException(429, "Troppi tentativi. Riprova tra qualche minuto.")

    # Trovo TUTTI i clienti attivi con P.IVA o CF matching
    clienti_match = await db.clienti.find({
        "$or": [
            {"partita_iva": ident},
            {"codice_fiscale": ident},
        ],
        "attivo": {"$ne": False},
    }, {"_id": 0}).to_list(50)

    if not clienti_match:
        await db.portale_lookup_failed.insert_one({
            "identificativo": ident,
            "at": now_utc().replace(tzinfo=None),
        })
        raise HTTPException(404, "Nessun cliente trovato con questo identificativo")

    # CASO 1: una sola struttura → emetto il token direttamente
    if len(clienti_match) == 1:
        cli = clienti_match[0]
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

    # CASO 2: più strutture stesso gruppo → l'utente deve scegliere
    # Genero un "selection token" effimero (5 min) che contiene gli ID dei clienti
    selection_token = secrets.token_urlsafe(24)
    expires_sel = now_utc() + timedelta(minutes=5)
    await db.portale_lookup_selections.insert_one({
        "selection_token": selection_token,
        "identificativo": ident,
        "cliente_ids": [c["id"] for c in clienti_match],
        "tenant_ids": [c["tenant_id"] for c in clienti_match],
        "created_at": now_utc(),
        "expires_at": expires_sel,
    })
    return {
        "multiple_matches": True,
        "selection_token": selection_token,
        "ragione_sociale": clienti_match[0].get("ragione_sociale"),
        "strutture": [
            {
                "cliente_id": c["id"],
                "denominazione_struttura": c.get("denominazione_struttura") or c.get("ragione_sociale"),
                "ragione_sociale": c.get("ragione_sociale"),
                "indirizzo": c.get("indirizzo"),
                "indirizzo_scarico": c.get("indirizzo_scarico"),
                "comune": c.get("comune"),
                "provincia": c.get("provincia"),
            }
            for c in clienti_match
        ],
        "expires_at": expires_sel.isoformat(),
    }


class PortaleSelectIn(BaseModel):
    selection_token: str
    cliente_id: str


@public_router.post("/portale/lookup/select")
async def portale_lookup_select(body: PortaleSelectIn):
    """Step 2: l'utente seleziona una specifica struttura dopo lookup multiplo.
    Convalida il selection_token, emette il session_token vero e proprio."""
    sel = await db.portale_lookup_selections.find_one({
        "selection_token": body.selection_token,
    }, {"_id": 0})
    if not sel:
        raise HTTPException(404, "Selezione scaduta o non valida")
    # Verifica scadenza
    exp = sel.get("expires_at")
    if exp:
        exp_dt = exp if isinstance(exp, datetime) else datetime.fromisoformat(str(exp))
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        if now_utc() > exp_dt:
            await db.portale_lookup_selections.delete_one({"selection_token": body.selection_token})
            raise HTTPException(410, "Selezione scaduta. Riprova dal portale.")
    # Verifica che il cliente_id selezionato sia tra quelli proposti (anti-tampering)
    if body.cliente_id not in (sel.get("cliente_ids") or []):
        raise HTTPException(400, "Struttura non valida per questa selezione")

    cli = await db.clienti.find_one({"id": body.cliente_id, "attivo": {"$ne": False}}, {"_id": 0})
    if not cli:
        raise HTTPException(404, "Struttura non trovata o non attiva")

    # Una volta consumato il selection_token, lo eliminiamo
    await db.portale_lookup_selections.delete_one({"selection_token": body.selection_token})

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
