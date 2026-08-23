"""Fatturazione riepilogativa da DDT + gestione incasso + sospesi.

Flusso:
1. GET /fatture/fatturabili?cliente_id=XXX -> elenco DDT non_fatturati del cliente
2. POST /fatture -> crea fattura da ddt_ids, marca DDT come fatturato
3. POST /fatture/{fid}/incassa -> imposta incasso
4. GET /sospesi -> fatture da_incassare
"""
import re
from datetime import datetime
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core import (
    db, new_id, now_utc, to_dt,
    get_current_user, require_roles, require_permission, log_audit, next_seq,
    tenant_scope, merge_scope, inject_tenant,
)

router = APIRouter(prefix="/fatture", tags=["billing"])
_WRITE = ("admin", "contabilita")


# ---- Numerazione con riempimento automatico dei buchi ----
_FATT_PREFIX = "FT"


def _iva_suffix(iva_pct: float) -> str:
    """Suffisso di serie in base all'IVA: F per IVA>0, C per IVA=0. Vuoto = legacy."""
    try:
        v = float(iva_pct)
    except Exception:
        v = 0.0
    return "C" if v == 0 else "F"


async def _global_max_fattura_seq(tenant_id: str, year: int) -> int:
    """Max seq storico considerando tutte le fatture (legacy + F + C) di un tenant/anno."""
    docs = await db.fatture.find(
        {"tenant_id": tenant_id, "numero": {"$regex": rf"^{_FATT_PREFIX}-{year}-"}},
        {"numero": 1, "_id": 0},
    ).to_list(200000)
    max_seq = 0
    for d in docs:
        m = re.match(rf"^{_FATT_PREFIX}-{year}-(\d+)[FC]?", d.get("numero", "") or "")
        if m:
            s = int(m.group(1))
            if s > max_seq:
                max_seq = s
    return max_seq


async def _next_fattura_seq(tenant_id: str, year: int, suffix: str = "", kind: str = "fattura") -> int:
    """Restituisce il prossimo progressivo di fattura.

    - Se `suffix` è vuoto: comportamento legacy con riempimento buchi su tutte le fatture.
    - Se `suffix` è "F" o "C": due serie indipendenti. Il primo numero di ciascuna serie parte
      dal max globale (legacy incluso) + 1; i buchi vengono riempiti solo all'interno della
      propria serie.
    """
    if suffix in ("F", "C"):
        pattern = rf"^{_FATT_PREFIX}-{year}-(\d+){suffix}$"
        docs = await db.fatture.find(
            {"tenant_id": tenant_id, "numero": {"$regex": pattern}},
            {"numero": 1, "_id": 0},
        ).to_list(100000)
        used = set()
        max_series = 0
        for d in docs:
            m = re.match(pattern, d.get("numero", "") or "")
            if m:
                s = int(m.group(1))
                used.add(s)
                if s > max_series:
                    max_series = s
        # Riempi buchi interni alla serie
        for i in range(1, max_series + 1):
            if i not in used:
                return i
        # Nessun buco: prossimo nella serie MA non minore del max globale (legacy incluso) + 1
        global_max = await _global_max_fattura_seq(tenant_id, year)
        return max(max_series + 1, global_max + 1)

    # Legacy: nessun suffisso, riempimento buchi tra le fatture senza suffisso
    docs = await db.fatture.find(
        {"tenant_id": tenant_id, "numero": {"$regex": rf"^{_FATT_PREFIX}-{year}-\d+$"}},
        {"numero": 1, "_id": 0},
    ).to_list(100000)
    used = set()
    max_seq = 0
    for d in docs:
        m = re.match(rf"^{_FATT_PREFIX}-{year}-(\d+)$", d.get("numero", "") or "")
        if m:
            s = int(m.group(1))
            used.add(s)
            if s > max_seq:
                max_seq = s
    for i in range(1, max_seq + 1):
        if i not in used:
            return i
    seq = await next_seq(kind)
    if seq <= max_seq:
        await db.counters.update_one(
            {"_id": kind}, {"$set": {"seq": max_seq + 1}}, upsert=True
        )
        return max_seq + 1
    return seq


class FatturaFromDDT(BaseModel):
    cliente_id: str
    ddt_ids: List[str] = Field(..., min_length=1)
    data: Optional[str] = None
    scadenza: Optional[str] = None
    iva_pct: Optional[float] = None  # None → usa company.iva_default_pct (fallback 22)
    note: Optional[str] = ""
    # Se true, i ddt_ids sono relativi a più clienti della stessa Ragione Sociale.
    # Il `cliente_id` diventa l'intestatario "principale"; gli altri clienti (fratelli
    # della stessa RS) vengono comunque marcati come fatturati e i loro DDT allegati.
    ragione_sociale_mode: Optional[bool] = False


class IncassoIn(BaseModel):
    data_incasso: Optional[str] = None
    metodo: Optional[str] = "bonifico"  # bonifico | contanti | carta | altro
    note: Optional[str] = ""


def _normalize_piva(v: str) -> str:
    """Rimuove spazi, punti, trattini e zeri iniziali per confronto laschi."""
    if not v:
        return ""
    s = re.sub(r"[\s\.\-]+", "", str(v))
    return s.lstrip("0")


async def _build_fatture_query(
    user: Dict,
    cliente_id: Optional[str],
    stato_incasso: Optional[str],
    data_inizio: Optional[str],
    data_fine: Optional[str],
    piva: Optional[str],
) -> Dict[str, Any]:
    query: Dict[str, Any] = dict(tenant_scope(user))
    if cliente_id:
        query["cliente_id"] = cliente_id
    if stato_incasso:
        query["stato_incasso"] = stato_incasso
    # Utente cliente vede solo le proprie
    if user["role"] == "cliente" and user.get("cliente_id"):
        query["cliente_id"] = user["cliente_id"]
    # Range date (accetta ISO YYYY-MM-DD o datetime completo)
    date_q: Dict[str, Any] = {}
    if data_inizio:
        d1 = to_dt(data_inizio)
        if d1:
            date_q["$gte"] = d1
    if data_fine:
        d2 = to_dt(data_fine)
        if d2:
            # includi tutto il giorno finale
            d2 = d2.replace(hour=23, minute=59, second=59)
            date_q["$lte"] = d2
    if date_q:
        query["data"] = date_q
    # Filtro P.IVA: normalizza (ignorando spazi, punti, trattini e zeri iniziali)
    # Cerca prima i clienti che matchano e usa i loro id per filtrare le fatture
    if piva and piva.strip():
        piva_norm = _normalize_piva(piva)
        if piva_norm:
            # regex "contiene" sulla PIVA normalizzata; per farlo semplice
            # cerchiamo direttamente nella collezione clienti e confrontiamo in Python
            cli_ids: List[str] = []
            async for c in db.clienti.find(
                merge_scope(user, {}),
                {"_id": 0, "id": 1, "partita_iva": 1, "codice_fiscale": 1},
            ):
                p1 = _normalize_piva(c.get("partita_iva") or "")
                p2 = _normalize_piva(c.get("codice_fiscale") or "")
                if piva_norm in p1 or (p2 and piva_norm in p2):
                    cli_ids.append(c["id"])
            if not cli_ids:
                # nessun cliente → nessuna fattura
                query["_no_match"] = True
            else:
                # combina con eventuale cliente_id già impostato
                existing = query.get("cliente_id")
                if isinstance(existing, str):
                    query["cliente_id"] = existing if existing in cli_ids else "__none__"
                else:
                    query["cliente_id"] = {"$in": cli_ids}
    return query


@router.get("")
async def list_fatture(
    user: Dict = Depends(require_permission("fatture", "view")),
    cliente_id: Optional[str] = None,
    stato_incasso: Optional[str] = None,  # da_incassare | incassata
    data_inizio: Optional[str] = None,    # YYYY-MM-DD
    data_fine: Optional[str] = None,      # YYYY-MM-DD
    piva: Optional[str] = None,           # filtra per P.IVA/CF cliente
    limit: int = 500,
):
    query = await _build_fatture_query(user, cliente_id, stato_incasso, data_inizio, data_fine, piva)
    if query.pop("_no_match", False):
        return []
    docs = await db.fatture.find(query, {"_id": 0}).sort("data", -1).to_list(limit)
    from routers.ddt import _enrich_cliente_denominazione
    return await _enrich_cliente_denominazione(docs, user)


@router.get("/summary")
async def summary_fatture(
    user: Dict = Depends(require_permission("fatture", "view")),
    cliente_id: Optional[str] = None,
    stato_incasso: Optional[str] = None,
    data_inizio: Optional[str] = None,
    data_fine: Optional[str] = None,
    piva: Optional[str] = None,
):
    """Totali aggregati sul dataset filtrato (intero, non paginato).

    Restituisce: {count, totale_imponibile, totale_iva, totale_documento}.
    """
    query = await _build_fatture_query(user, cliente_id, stato_incasso, data_inizio, data_fine, piva)
    if query.pop("_no_match", False):
        return {"count": 0, "totale_imponibile": 0.0, "totale_iva": 0.0, "totale_documento": 0.0}
    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": None,
            "count": {"$sum": 1},
            "totale_imponibile": {"$sum": {"$ifNull": ["$imponibile", 0]}},
            "totale_iva": {"$sum": {"$ifNull": ["$iva", 0]}},
            "totale_documento": {"$sum": {"$ifNull": ["$totale", 0]}},
        }},
    ]
    res = await db.fatture.aggregate(pipeline).to_list(1)
    if not res:
        return {"count": 0, "totale_imponibile": 0.0, "totale_iva": 0.0, "totale_documento": 0.0}
    r = res[0]
    return {
        "count": int(r.get("count") or 0),
        "totale_imponibile": round(float(r.get("totale_imponibile") or 0), 2),
        "totale_iva": round(float(r.get("totale_iva") or 0), 2),
        "totale_documento": round(float(r.get("totale_documento") or 0), 2),
    }


@router.get("/fatturabili")
async def list_fatturabili(cliente_id: str, user: Dict = Depends(require_roles(*_WRITE))):
    """Elenco DDT non fatturati per il cliente specificato."""
    ddts = await db.ddt.find(
        merge_scope(user, {"cliente_id": cliente_id, "stato_fatturazione": "non_fatturato"}),
        {"_id": 0},
    ).sort("data", 1).to_list(1000)
    totale = round(sum(d.get("imponibile", 0) for d in ddts), 2)
    return {"ddts": ddts, "count": len(ddts), "totale_imponibile": totale}


@router.get("/ragioni-sociali")
async def list_ragioni_sociali(user: Dict = Depends(require_roles(*_WRITE))):
    """Elenco delle Ragioni Sociali distinte dei clienti attivi, con contatore struttura.
    Serve alla nuova modalità 'Fattura per Ragione Sociale'.
    """
    clienti = await db.clienti.find(
        merge_scope(user, {}),
        {"_id": 0, "id": 1, "ragione_sociale": 1, "denominazione_struttura": 1, "attivo": 1, "partita_iva": 1},
    ).to_list(20000)
    rs_map: Dict[str, Dict[str, Any]] = {}
    for c in clienti:
        rs = (c.get("ragione_sociale") or "").strip()
        if not rs:
            continue
        key = rs.lower()
        e = rs_map.setdefault(key, {
            "ragione_sociale": rs,
            "clienti_ids": [],
            "clienti_count": 0,
            "strutture": [],
            "partita_iva": c.get("partita_iva") or "",
        })
        e["clienti_ids"].append(c["id"])
        e["clienti_count"] += 1
        if c.get("denominazione_struttura"):
            e["strutture"].append(c["denominazione_struttura"])
    result = list(rs_map.values())
    # solo RS che raggruppano 2+ clienti (le altre coincidono con "per cliente")
    result = [r for r in result if r["clienti_count"] >= 2]
    result.sort(key=lambda x: x["ragione_sociale"].lower())
    return result


@router.get("/fatturabili-rs")
async def list_fatturabili_by_rs(ragione_sociale: str, user: Dict = Depends(require_roles(*_WRITE))):
    """DDT non fatturati di TUTTI i clienti con la stessa Ragione Sociale.
    Include l'elenco dei clienti-fratelli e il totale imponibile aggregato.
    """
    rs = ragione_sociale.strip()
    if not rs:
        raise HTTPException(400, "ragione_sociale mancante")
    siblings = await db.clienti.find(
        merge_scope(user, {"ragione_sociale": {"$regex": f"^{re.escape(rs)}$", "$options": "i"}}),
        {"_id": 0},
    ).to_list(500)
    if not siblings:
        raise HTTPException(404, f"Nessun cliente con ragione sociale '{rs}'")
    sib_ids = [s["id"] for s in siblings]
    ddts = await db.ddt.find(
        merge_scope(user, {"cliente_id": {"$in": sib_ids}, "stato_fatturazione": "non_fatturato"}),
        {"_id": 0},
    ).sort("data", 1).to_list(5000)
    totale = round(sum(d.get("imponibile", 0) for d in ddts), 2)
    return {
        "ragione_sociale": rs,
        "clienti": siblings,
        "clienti_count": len(siblings),
        "ddts": ddts,
        "count": len(ddts),
        "totale_imponibile": totale,
    }


@router.post("")
async def create_fattura_from_ddt(body: FatturaFromDDT, user: Dict = Depends(require_roles(*_WRITE))):
    cliente = await db.clienti.find_one(merge_scope(user, {"id": body.cliente_id}), {"_id": 0})
    if not cliente:
        raise HTTPException(400, "Cliente non trovato")

    # Se modalità "Ragione Sociale", i DDT possono appartenere a clienti diversi
    # ma con la stessa ragione_sociale del cliente intestatario. In tal caso
    # rimuoviamo il vincolo `cliente_id` sulla query DDT.
    ddt_query: Dict[str, Any] = {
        "id": {"$in": body.ddt_ids},
        "stato_fatturazione": "non_fatturato",
    }
    if body.ragione_sociale_mode:
        rs = (cliente.get("ragione_sociale") or "").strip()
        if not rs:
            raise HTTPException(400, "Cliente principale senza ragione sociale")
        # elenco clienti-fratelli con stessa RS (case-insensitive)
        siblings = await db.clienti.find(
            merge_scope(user, {"ragione_sociale": {"$regex": f"^{re.escape(rs)}$", "$options": "i"}}),
            {"_id": 0, "id": 1},
        ).to_list(500)
        sib_ids = [s["id"] for s in siblings] or [body.cliente_id]
        ddt_query["cliente_id"] = {"$in": sib_ids}
    else:
        ddt_query["cliente_id"] = body.cliente_id

    ddts = await db.ddt.find(merge_scope(user, ddt_query), {"_id": 0}).to_list(len(body.ddt_ids))
    if len(ddts) != len(body.ddt_ids):
        raise HTTPException(400, "Uno o più DDT non validi o già fatturati")

    # Ordinamento cronologico crescente per data + numero (Modifica 3)
    def _sort_key(d):
        dt = d.get("data")
        # tratta datetime/date/string uniformemente
        try:
            key_dt = dt.isoformat() if hasattr(dt, "isoformat") else str(dt or "")
        except Exception:
            key_dt = ""
        return (key_dt, d.get("numero", ""))
    ddts.sort(key=_sort_key)

    imponibile = round(sum(d.get("imponibile", 0) for d in ddts), 2)

    # ---- Aggregazione articoli + dettagli DDT per il riepilogo cumulativo ----
    # ddt_dettagli: lista di {id, numero, data, imponibile}
    # riepilogo_articoli: aggregato per articolo_id con qty totale e prezzo medio ponderato
    ddt_dettagli: List[Dict[str, Any]] = []
    art_agg: Dict[str, Dict[str, Any]] = {}
    for d in ddts:
        d_data = d.get("data")
        if hasattr(d_data, "isoformat"):
            d_data_iso = d_data.isoformat()
        else:
            d_data_iso = str(d_data) if d_data else None
        ddt_dettagli.append({
            "id": d["id"],
            "numero": d.get("numero"),
            "data": d_data_iso,
            "imponibile": round(d.get("imponibile", 0), 2),
            "righe_count": len(d.get("righe") or []),
        })
        for r in (d.get("righe") or []):
            aid = r.get("articolo_id")
            if not aid:
                continue
            qty = int(r.get("quantita") or 0)
            tot = float(r.get("totale") or 0)
            entry = art_agg.setdefault(aid, {
                "articolo_id": aid,
                "codice": r.get("codice", ""),
                "descrizione": r.get("descrizione", ""),
                "unita_misura": r.get("unita_misura", "pz"),
                "quantita_totale": 0,
                "totale": 0.0,
            })
            entry["quantita_totale"] += qty
            entry["totale"] += tot
    # prezzo unitario medio ponderato
    riepilogo_articoli: List[Dict[str, Any]] = []
    for e in art_agg.values():
        qty = e["quantita_totale"]
        e["totale"] = round(e["totale"], 2)
        e["prezzo_unitario_medio"] = round(e["totale"] / qty, 4) if qty else 0
        riepilogo_articoli.append(e)
    riepilogo_articoli.sort(key=lambda x: (x.get("codice") or "", x.get("descrizione") or ""))

    # Resolve IVA: explicit body value > company default > 22
    iva_pct = body.iva_pct
    if iva_pct is None:
        comp = await db.company.find_one(tenant_scope(user), {"_id": 0}) or {}
        iva_pct = float(comp.get("iva_default_pct") or 22)
    iva = round(imponibile * iva_pct / 100, 2)
    totale = round(imponibile + iva, 2)

    fid = new_id()
    fatt_data = to_dt(body.data) or now_utc()
    year = fatt_data.year if hasattr(fatt_data, "year") else now_utc().year
    # Doppia numerazione: suffisso F (IVA>0) / C (IVA=0)
    suffix = _iva_suffix(iva_pct)
    seq = await _next_fattura_seq(user["tenant_id"], year, suffix=suffix)
    from core import format_numero
    base_numero = await format_numero("fattura", _FATT_PREFIX, seq)
    numero = f"{base_numero}{suffix}"

    doc = {
        "id": fid,
        "numero": numero,
        "cliente_id": body.cliente_id,
        "cliente_nome": cliente.get("ragione_sociale", ""),
        "cliente_denominazione": cliente.get("denominazione_struttura", ""),
        "data": fatt_data,
        "scadenza": to_dt(body.scadenza) if body.scadenza else None,
        "iva_pct": iva_pct,
        "imponibile": imponibile,
        "iva": iva,
        "totale": totale,
        "ddt_ids": [d["id"] for d in ddts],
        "ddt_numeri": [d["numero"] for d in ddts],
        "ddt_dettagli": ddt_dettagli,
        "riepilogo_articoli": riepilogo_articoli,
        "note": body.note or "",
        "stato_incasso": "da_incassare",
        "data_incasso": None,
        "metodo_incasso": None,
        "xml_transmitted": False,
        "xml_transmitted_at": None,
        "xml_transmitted_by": None,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    inject_tenant(doc, user)
    await db.fatture.insert_one(doc)

    # Mark DDTs as fatturato
    await db.ddt.update_many(
        merge_scope(user, {"id": {"$in": [d["id"] for d in ddts]}}),
        {"$set": {
            "stato_fatturazione": "fatturato",
            "fattura_id": fid,
            "fattura_numero": numero,
            "updated_at": now_utc(),
        }},
    )

    doc.pop("_id", None)
    await log_audit(user, "CREATE", "fattura", fid, {"ddt_count": len(ddts), "totale": totale})
    return doc


@router.get("/xml-bulk")
async def fatture_xml_bulk(
    user: Dict = Depends(require_permission("fatture", "view")),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    month: Optional[str] = Query(None),  # "YYYY-MM"
):
    """Esporta in un singolo ZIP tutti gli XML Fattura Elettronica del periodo.

    Specifica:
      - `month=YYYY-MM` per esportare un singolo mese, oppure
      - `from=YYYY-MM-DD&to=YYYY-MM-DD` per un intervallo arbitrario.
    """
    import io
    import zipfile
    from datetime import date
    from calendar import monthrange
    from fastapi import Response
    from routers.company import load_company_for_tenant
    from services.fattura_elettronica import build_fattura_elettronica_xml
    from services.invoice_validation import InvoiceValidationError

    # ----- Risolvi from/to -----
    if month:
        try:
            y, m = month.split("-")
            y, m = int(y), int(m)
            d_from = date(y, m, 1).isoformat()
            d_to = date(y, m, monthrange(y, m)[1]).isoformat()
            zip_name = f"Fatture_Elettroniche_{y:04d}-{m:02d}.zip"
        except Exception:
            raise HTTPException(400, "Parametro 'month' non valido (atteso YYYY-MM)")
    else:
        if not from_ or not to:
            raise HTTPException(400, "Specifica 'month' oppure 'from' e 'to'")
        try:
            date.fromisoformat(from_); date.fromisoformat(to)
        except Exception:
            raise HTTPException(400, "Date non valide (atteso YYYY-MM-DD)")
        if from_ > to:
            raise HTTPException(400, "'from' deve essere ≤ 'to'")
        d_from, d_to = from_, to
        zip_name = f"Fatture_Elettroniche_{d_from}_{d_to}.zip"

    # ----- Query fatture del periodo -----
    fatture = await db.fatture.find(
        merge_scope(user, {"data": {"$gte": d_from, "$lte": d_to}}),
        {"_id": 0},
    ).sort("data", 1).to_list(5000)

    if not fatture:
        raise HTTPException(404, f"Nessuna fattura trovata nel periodo {d_from} → {d_to}")

    company = await load_company_for_tenant(user["tenant_id"])

    # ----- Costruisci ZIP in memoria -----
    skipped: List[Dict[str, str]] = []
    included = 0
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fatt in fatture:
            cliente = await db.clienti.find_one(
                merge_scope(user, {"id": fatt["cliente_id"]}), {"_id": 0}
            ) or {}
            ddt_list = await db.ddt.find(
                merge_scope(user, {"id": {"$in": fatt.get("ddt_ids", [])}}),
                {"_id": 0},
            ).to_list(500)
            try:
                xml_bytes, filename = build_fattura_elettronica_xml(fatt, company, cliente, ddt_list)
                # Evita collisioni di nome (raro ma possibile su progressivi cross-anno)
                base_name = filename
                seq = 2
                while base_name in zf.namelist():
                    base_name = filename.replace(".xml", f"_{seq}.xml")
                    seq += 1
                zf.writestr(base_name, xml_bytes)
                included += 1
            except InvoiceValidationError as e:
                # Errore di validazione: salta la fattura con messaggio dettagliato
                msgs = "; ".join(err["message"] for err in e.errors[:3])
                skipped.append({"numero": fatt.get("numero", "?"), "reason": msgs})
            except ValueError as e:
                skipped.append({"numero": fatt.get("numero", "?"), "reason": str(e)})

        # Manifest sommario (utile in caso di skip)
        manifest = (
            f"Export Fatture Elettroniche\n"
            f"Periodo: {d_from} → {d_to}\n"
            f"Generato: {now_utc().isoformat()}\n"
            f"Totale fatture nel periodo: {len(fatture)}\n"
            f"XML generati: {included}\n"
            f"Saltate per errore: {len(skipped)}\n"
        )
        if skipped:
            manifest += "\nFatture saltate:\n"
            for s in skipped:
                manifest += f"  · {s['numero']}: {s['reason']}\n"
        zf.writestr("_MANIFEST.txt", manifest.encode("utf-8"))

    if included == 0:
        raise HTTPException(
            400,
            f"Nessuna fattura del periodo è esportabile. {len(skipped)} fatture saltate per dati mancanti."
        )

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_name}"',
            "X-Export-Total": str(len(fatture)),
            "X-Export-Included": str(included),
            "X-Export-Skipped": str(len(skipped)),
        },
    )


@router.get("/{fid}/pdf")
async def fattura_pdf(fid: str, user: Dict = Depends(require_permission("fatture", "view"))):
    from fastapi import Response
    from pdf_service import generate_fattura_pdf
    from routers.company import load_company_for_tenant
    fatt = await db.fatture.find_one(merge_scope(user, {"id": fid}), {"_id": 0})
    if not fatt:
        raise HTTPException(404, "Fattura non trovata")
    cliente = await db.clienti.find_one(merge_scope(user, {"id": fatt["cliente_id"]}), {"_id": 0}) or {}
    ddt_list = await db.ddt.find(
        merge_scope(user, {"id": {"$in": fatt.get("ddt_ids", [])}}),
        {"_id": 0},
    ).to_list(500)
    company = await load_company_for_tenant(user["tenant_id"])
    pdf = generate_fattura_pdf(fatt, cliente, company, ddt_list)
    filename = f"{fatt.get('numero', 'Fattura')}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/{fid}/xml")
async def fattura_xml_elettronica(fid: str, user: Dict = Depends(require_permission("fatture", "view"))):
    """Export XML Fattura Elettronica (v1.2.2 FPR12 — privati B2B/B2C) per upload allo SdI."""
    from fastapi import Response
    from routers.company import load_company_for_tenant
    from services.fattura_elettronica import build_fattura_elettronica_xml
    from services.invoice_validation import InvoiceValidationError

    fatt = await db.fatture.find_one(merge_scope(user, {"id": fid}), {"_id": 0})
    if not fatt:
        raise HTTPException(404, "Fattura non trovata")
    cliente = await db.clienti.find_one(merge_scope(user, {"id": fatt["cliente_id"]}), {"_id": 0}) or {}
    ddt_list = await db.ddt.find(
        merge_scope(user, {"id": {"$in": fatt.get("ddt_ids", [])}}),
        {"_id": 0},
    ).to_list(500)
    company = await load_company_for_tenant(user["tenant_id"])
    try:
        xml_bytes, filename = build_fattura_elettronica_xml(fatt, company, cliente, ddt_list)
    except InvoiceValidationError as e:
        # 422: dati anagrafici/totali non conformi a specifiche SdI
        raise HTTPException(status_code=422, detail=e.to_dict())
    except ValueError as e:
        raise HTTPException(400, str(e))
    return Response(
        content=xml_bytes,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{fid}/validate")
async def validate_fattura(fid: str, user: Dict = Depends(require_permission("fatture", "view"))):
    """Esegue tutti i controlli formali SdI sulla fattura SENZA generarne lo XML.

    Ritorna:
      { ok: bool, errors: [{code, field, message}, ...] }
    """
    from routers.company import load_company_for_tenant
    from services.invoice_validation import validate_invoice_data
    from services.xsd_validator import validate_xml_against_xsd
    from services.fattura_elettronica import build_fattura_elettronica_xml
    from services.invoice_validation import InvoiceValidationError

    fatt = await db.fatture.find_one(merge_scope(user, {"id": fid}), {"_id": 0})
    if not fatt:
        raise HTTPException(404, "Fattura non trovata")
    cliente = await db.clienti.find_one(merge_scope(user, {"id": fatt["cliente_id"]}), {"_id": 0}) or {}
    ddt_list = await db.ddt.find(
        merge_scope(user, {"id": {"$in": fatt.get("ddt_ids", [])}}),
        {"_id": 0},
    ).to_list(500)
    company = await load_company_for_tenant(user["tenant_id"])

    pre_errors = validate_invoice_data(fatt, company, cliente, ddt_list)
    if pre_errors:
        return {"ok": False, "stage": "pre", "errors": pre_errors}

    # Se i dati passano, tentiamo la generazione + XSD per individuare errori formali XSD
    try:
        build_fattura_elettronica_xml(fatt, company, cliente, ddt_list, validate_xsd=True)
    except InvoiceValidationError as e:
        return {"ok": False, "stage": "xsd", "errors": e.errors}
    except ValueError as e:
        return {"ok": False, "stage": "generation", "errors": [{"code": "E_GEN", "field": "/", "message": str(e)}]}

    return {"ok": True, "errors": []}


@router.get("/{fid}")
async def get_fattura(fid: str, user: Dict = Depends(require_permission("fatture", "view"))):
    doc = await db.fatture.find_one(merge_scope(user, {"id": fid}), {"_id": 0})
    if not doc:
        raise HTTPException(404, "Fattura non trovata")
    # Enrich with DDTs details
    if doc.get("ddt_ids"):
        doc["ddts"] = await db.ddt.find(
            merge_scope(user, {"id": {"$in": doc["ddt_ids"]}}), {"_id": 0}
        ).to_list(100)
        # Ordinamento cronologico crescente (Mod. 3)
        def _dsort(d):
            dt = d.get("data")
            try:
                return (dt.isoformat() if hasattr(dt, "isoformat") else str(dt or ""), d.get("numero", ""))
            except Exception:
                return ("", d.get("numero", ""))
        doc["ddts"].sort(key=_dsort)
        if doc.get("ddt_dettagli"):
            doc["ddt_dettagli"].sort(key=lambda x: (x.get("data") or "", x.get("numero") or ""))
        # Backfill on-the-fly per fatture vecchie senza ddt_dettagli/riepilogo_articoli
        if not doc.get("ddt_dettagli"):
            dets: List[Dict[str, Any]] = []
            for d in doc["ddts"]:
                d_data = d.get("data")
                d_data_iso = d_data.isoformat() if hasattr(d_data, "isoformat") else (str(d_data) if d_data else None)
                dets.append({
                    "id": d["id"], "numero": d.get("numero"),
                    "data": d_data_iso,
                    "imponibile": round(d.get("imponibile", 0), 2),
                    "righe_count": len(d.get("righe") or []),
                })
            doc["ddt_dettagli"] = dets
        if not doc.get("riepilogo_articoli"):
            agg: Dict[str, Dict[str, Any]] = {}
            for d in doc["ddts"]:
                for r in (d.get("righe") or []):
                    aid = r.get("articolo_id")
                    if not aid: continue
                    qty = int(r.get("quantita") or 0)
                    tot = float(r.get("totale") or 0)
                    e = agg.setdefault(aid, {
                        "articolo_id": aid, "codice": r.get("codice", ""),
                        "descrizione": r.get("descrizione", ""),
                        "unita_misura": r.get("unita_misura", "pz"),
                        "quantita_totale": 0, "totale": 0.0,
                    })
                    e["quantita_totale"] += qty
                    e["totale"] += tot
            riep: List[Dict[str, Any]] = []
            for e in agg.values():
                e["totale"] = round(e["totale"], 2)
                e["prezzo_unitario_medio"] = round(e["totale"] / e["quantita_totale"], 4) if e["quantita_totale"] else 0
                riep.append(e)
            doc["riepilogo_articoli"] = sorted(riep, key=lambda x: (x.get("codice") or "", x.get("descrizione") or ""))
    return doc


class RinumeraIn(BaseModel):
    """Rinumera e/o ridata una fattura non ancora trasmessa a SDI.

    - `seq` o `numero`: nuovo progressivo/numero (opzionali se si vuole solo cambiare la data)
    - `nuova_data`: nuova data documento in formato ISO YYYY-MM-DD (opzionale)
    - `motivazione`: motivazione obbligatoria (min 10 caratteri) — verrà loggata su audit_log
    """
    seq: Optional[int] = None
    numero: Optional[str] = None
    nuova_data: Optional[str] = None
    motivazione: str = Field(..., min_length=10, max_length=500)


@router.patch("/{fid}/rinumera")
async def rinumera_fattura(fid: str, body: RinumeraIn, user: Dict = Depends(require_roles("admin"))):
    """Modifica manuale del numero e/o data fattura (solo per fatture NON trasmesse a SDI).

    Consentito ad Admin/Super User (§16). La modifica viene loggata sull'audit log
    (non alterabile) con motivazione obbligatoria.
    """
    fattura = await db.fatture.find_one(merge_scope(user, {"id": fid}), {"_id": 0})
    if not fattura:
        raise HTTPException(404, "Fattura non trovata")
    if fattura.get("xml_transmitted"):
        raise HTTPException(409, "La fattura risulta già trasmessa a SDI: dati fiscali immutabili per legge. Sblocca la trasmissione se hai fatto un errore.")

    old_numero = fattura.get("numero")
    old_data = fattura.get("data")

    # ----- Nuova data (opzionale) -----
    new_data = None
    if body.nuova_data and body.nuova_data.strip():
        new_data = to_dt(body.nuova_data.strip())
        if not new_data:
            raise HTTPException(400, "Formato nuova_data non valido (atteso YYYY-MM-DD)")

    # Se cambia l'anno della fattura, blocca (implica ricalcolo intera serie)
    old_year = old_data.year if hasattr(old_data, "year") else now_utc().year
    new_year_for_num = (new_data.year if new_data else old_year)

    # ----- Nuovo numero (opzionale) -----
    new_numero = None
    if body.numero and body.numero.strip():
        candidate = body.numero.strip().upper()
        m = re.match(rf"^{_FATT_PREFIX}-(\d{{4}})-(\d+)(.*)$", candidate)
        if not m:
            raise HTTPException(400, f"Formato numero non valido. Atteso: {_FATT_PREFIX}-{new_year_for_num}-00001[suffix]")
        num_year = int(m.group(1))
        if num_year != new_year_for_num:
            raise HTTPException(400, f"L'anno del numero ({num_year}) non corrisponde all'anno della fattura ({new_year_for_num})")
        new_numero = candidate
    elif body.seq is not None:
        if body.seq < 1:
            raise HTTPException(400, "Il progressivo deve essere >= 1")
        # Costruiamo il numero direttamente usando l'anno corretto della fattura
        # (get_numero_config potrebbe aggiungere un suffisso locale, ma la doppia
        # numerazione F/C usa già la logica dedicata in creazione; qui manteniamo
        # il suffisso della fattura originale se presente e non ne è stato indicato uno).
        old_suffix = ""
        m_old = re.match(rf"^{_FATT_PREFIX}-\d{{4}}-\d+(.*)$", old_numero or "")
        if m_old:
            old_suffix = m_old.group(1) or ""
        new_numero = f"{_FATT_PREFIX}-{new_year_for_num}-{int(body.seq):05d}{old_suffix}"

    if new_numero is None and new_data is None:
        raise HTTPException(400, "Specificare almeno un cambio: nuovo numero (seq/numero) o nuova data.")

    # No-op: stessi valori
    same_numero = (new_numero is None) or (new_numero == old_numero)
    same_data = (new_data is None) or (
        hasattr(old_data, "date") and hasattr(new_data, "date") and old_data.date() == new_data.date()
    )
    if same_numero and same_data:
        return fattura

    # ----- Verifica unicità del nuovo numero (se cambia) -----
    if new_numero and new_numero != old_numero:
        dup = await db.fatture.find_one({
            "tenant_id": user["tenant_id"],
            "numero": new_numero,
            "id": {"$ne": fid},
        }, {"_id": 0, "id": 1, "numero": 1})
        if dup:
            raise HTTPException(409, f"Il numero {new_numero} è già usato da un'altra fattura di questo anno.")

    # ----- Update -----
    set_fields: Dict[str, Any] = {"updated_at": now_utc()}
    if new_numero and new_numero != old_numero:
        set_fields["numero"] = new_numero
    if new_data and not same_data:
        set_fields["data"] = new_data

    await db.fatture.update_one(merge_scope(user, {"id": fid}), {"$set": set_fields})

    # Aggiorna DDT collegati (denormalizzazione) se il numero cambia
    if "numero" in set_fields:
        await db.ddt.update_many(
            merge_scope(user, {"fattura_id": fid}),
            {"$set": {"fattura_numero": set_fields["numero"], "updated_at": now_utc()}},
        )

    # ----- Audit log non alterabile -----
    def _iso(v):
        try:
            return v.isoformat() if hasattr(v, "isoformat") else (str(v) if v else None)
        except Exception:
            return None

    await log_audit(
        user,
        "RINUMERA_RIDATA",
        "fattura",
        fid,
        {
            "old_numero": old_numero,
            "new_numero": set_fields.get("numero", old_numero),
            "old_data": _iso(old_data),
            "new_data": _iso(set_fields.get("data", old_data)),
            "motivazione": body.motivazione.strip(),
        },
    )
    return await db.fatture.find_one(merge_scope(user, {"id": fid}), {"_id": 0})


@router.post("/{fid}/segna-trasmessa")
async def segna_fattura_trasmessa(fid: str, user: Dict = Depends(require_roles(*_WRITE))):
    """Marca la fattura come inviata a SDI. Dopo questa azione il numero è immutabile."""
    fattura = await db.fatture.find_one(merge_scope(user, {"id": fid}), {"_id": 0})
    if not fattura:
        raise HTTPException(404, "Fattura non trovata")
    if fattura.get("xml_transmitted"):
        return fattura
    user_label = user.get("name") or user.get("email") or user.get("id", "")
    await db.fatture.update_one(
        merge_scope(user, {"id": fid}),
        {"$set": {
            "xml_transmitted": True,
            "xml_transmitted_at": now_utc(),
            "xml_transmitted_by": user_label,
            "updated_at": now_utc(),
        }},
    )
    await log_audit(user, "SDI_TRANSMITTED", "fattura", fid)
    return await db.fatture.find_one(merge_scope(user, {"id": fid}), {"_id": 0})


@router.post("/{fid}/annulla-trasmissione")
async def annulla_trasmissione(fid: str, user: Dict = Depends(require_roles("admin"))):
    """Rimuove il flag di trasmissione — SOLO ADMIN (per errori). Non ha effetti fiscali."""
    fattura = await db.fatture.find_one(merge_scope(user, {"id": fid}), {"_id": 0})
    if not fattura:
        raise HTTPException(404, "Fattura non trovata")
    await db.fatture.update_one(
        merge_scope(user, {"id": fid}),
        {"$set": {
            "xml_transmitted": False,
            "xml_transmitted_at": None,
            "xml_transmitted_by": None,
            "updated_at": now_utc(),
        }},
    )
    await log_audit(user, "SDI_UNTRANSMITTED", "fattura", fid)
    return await db.fatture.find_one(merge_scope(user, {"id": fid}), {"_id": 0})


# ---- Modifica 4: invio fattura via e-mail ----
class InviaEmailIn(BaseModel):
    to: Optional[str] = None  # se assente, usa l'email del cliente
    subject: Optional[str] = None
    body: Optional[str] = None


def _client_email(cliente: Dict[str, Any]) -> str:
    """Ritorna il primo indirizzo email valorizzato tra i possibili campi anagrafica."""
    for k in ("email_fatturazione", "email", "pec"):
        v = (cliente.get(k) or "").strip()
        if v:
            return v
    return ""


@router.post("/{fid}/send-email")
async def send_fattura_email(fid: str, body: InviaEmailIn, user: Dict = Depends(require_roles(*_WRITE))):
    """Genera il PDF della fattura, lo allega e invia via SMTP configurato.
    Registra data/ora/utente ed esito su fattura.emails_sent e su db.email_events.
    """
    fattura = await db.fatture.find_one(merge_scope(user, {"id": fid}), {"_id": 0})
    if not fattura:
        raise HTTPException(404, "Fattura non trovata")
    cliente = await db.clienti.find_one(merge_scope(user, {"id": fattura["cliente_id"]}), {"_id": 0})
    if not cliente:
        raise HTTPException(400, "Cliente non trovato")

    to_email = (body.to or _client_email(cliente)).strip()
    if not to_email:
        raise HTTPException(400, "Nessun indirizzo e-mail disponibile per il cliente")

    # PDF (genera al volo)
    company = await db.company.find_one(tenant_scope(user), {"_id": 0}) or {}
    ddt_list = await db.ddt.find(
        merge_scope(user, {"id": {"$in": fattura.get("ddt_ids") or []}}), {"_id": 0}
    ).to_list(500)
    from pdf_service import generate_fattura_pdf
    try:
        pdf_bytes = generate_fattura_pdf(fattura, cliente, company, ddt_list)
    except Exception as e:
        raise HTTPException(500, f"Errore generazione PDF: {e}")

    fdate = fattura.get("data")
    fdate_str = fdate.strftime("%d/%m/%Y") if hasattr(fdate, "strftime") else str(fdate or "")
    subject = body.subject or f"Fattura n. {fattura.get('numero','')} del {fdate_str}"
    body_text = body.body or (
        "Gentile Cliente,\n\n"
        "come da riferimenti in oggetto, inviamo in allegato copia cortesia della fattura\n"
        "relativa ai servizi mensili erogati.\n\n"
        "Cordiali saluti."
    )
    filename = f"Fattura_{fattura.get('numero','')}.pdf"
    attachments = [{"filename": filename, "content": pdf_bytes, "mime": "application/pdf"}]

    from smtp_service import send_email
    event = await send_email(
        to=to_email,
        subject=subject,
        body_text=body_text,
        tenant_id=user.get("tenant_id"),
        context={"fattura_id": fid, "fattura_numero": fattura.get("numero")},
        attachments=attachments,
    )

    status = event.get("status", "logged")
    result = "sent" if status == "sent" else ("failed" if status == "failed" else "logged")
    sent_at = now_utc()
    user_label = user.get("name") or user.get("email") or user.get("id", "")
    # append allo storico invii
    entry = {
        "at": sent_at,
        "by": user_label,
        "to": to_email,
        "status": result,
        "error": event.get("error"),
    }
    await db.fatture.update_one(
        merge_scope(user, {"id": fid}),
        {
            "$push": {"emails_sent": entry},
            "$set": {
                "email_last_status": result,
                "email_last_at": sent_at,
                "email_last_to": to_email,
                "updated_at": now_utc(),
            },
        },
    )
    await log_audit(user, "SEND_EMAIL", "fattura", fid, {"to": to_email, "status": result})
    return {"ok": True, "status": result, "to": to_email, "error": event.get("error")}


@router.post("/{fid}/incassa")
async def incassa_fattura(fid: str, body: IncassoIn, user: Dict = Depends(require_roles(*_WRITE))):
    fattura = await db.fatture.find_one(merge_scope(user, {"id": fid}), {"_id": 0})
    if not fattura:
        raise HTTPException(404, "Fattura non trovata")
    if fattura.get("stato_incasso") == "incassata":
        raise HTTPException(400, "Fattura già incassata")
    await db.fatture.update_one(
        merge_scope(user, {"id": fid}),
        {"$set": {
            "stato_incasso": "incassata",
            "data_incasso": to_dt(body.data_incasso) or now_utc(),
            "metodo_incasso": body.metodo,
            "note_incasso": body.note or "",
            "updated_at": now_utc(),
        }},
    )
    await log_audit(user, "INCASSA", "fattura", fid, {"metodo": body.metodo})
    return {"ok": True}


@router.post("/{fid}/annulla-incasso")
async def annulla_incasso(fid: str, user: Dict = Depends(require_roles("admin"))):
    await db.fatture.update_one(
        merge_scope(user, {"id": fid}),
        {"$set": {"stato_incasso": "da_incassare", "updated_at": now_utc()},
         "$unset": {"data_incasso": "", "metodo_incasso": "", "note_incasso": ""}},
    )
    await log_audit(user, "UNDO_INCASSO", "fattura", fid)
    return {"ok": True}


@router.delete("/{fid}")
async def delete_fattura(fid: str, user: Dict = Depends(require_roles("admin"))):
    """Elimina fattura: riabilita DDT collegati."""
    fattura = await db.fatture.find_one(merge_scope(user, {"id": fid}), {"_id": 0})
    if not fattura:
        raise HTTPException(404, "Fattura non trovata")
    if fattura.get("stato_incasso") == "incassata":
        raise HTTPException(409, "Fattura incassata: non eliminabile")
    # Unlink DDTs
    if fattura.get("ddt_ids"):
        await db.ddt.update_many(
            merge_scope(user, {"id": {"$in": fattura["ddt_ids"]}}),
            {"$set": {"stato_fatturazione": "non_fatturato"},
             "$unset": {"fattura_id": "", "fattura_numero": ""}},
        )
    await db.fatture.delete_one(merge_scope(user, {"id": fid}))
    await log_audit(user, "DELETE", "fattura", fid)
    return {"ok": True}


# --- Sospesi ---------------------------------------------------------------
sospesi_router = APIRouter(prefix="/sospesi", tags=["sospesi"])


@sospesi_router.get("")
async def list_sospesi(
    user: Dict = Depends(require_permission("sospesi", "view")),
    cliente_id: Optional[str] = None,
    dal: Optional[str] = None,
    al: Optional[str] = None,
    numero: Optional[str] = None,
    limit: int = 500,
):
    q: Dict[str, Any] = {**tenant_scope(user), "stato_incasso": "da_incassare"}
    if cliente_id: q["cliente_id"] = cliente_id
    if numero: q["numero"] = {"$regex": numero, "$options": "i"}
    if dal or al:
        date_q: Dict[str, Any] = {}
        if dal:
            d1 = to_dt(dal)
            if d1: date_q["$gte"] = d1
        if al:
            d2 = to_dt(al)
            if d2: date_q["$lte"] = d2
        if date_q: q["data"] = date_q
    if user["role"] == "cliente" and user.get("cliente_id"):
        q["cliente_id"] = user["cliente_id"]
    fatture = await db.fatture.find(q, {"_id": 0}).sort("data", 1).to_list(limit)
    from routers.ddt import _enrich_cliente_denominazione
    fatture = await _enrich_cliente_denominazione(fatture, user)
    totale = round(sum(f.get("totale", 0) for f in fatture), 2)
    return {
        "fatture": fatture,
        "count": len(fatture),
        "totale_sospesi": totale,
    }
