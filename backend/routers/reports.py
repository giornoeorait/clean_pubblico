"""Reports & Statistiche BI — FASE 5.

Endpoint aggregati read-only per dashboard business:
- Fatturato (globale + per cliente + per mese)
- Volume prodotto in kg (pezzi × peso_medio articolo)
- Costi per categoria/mese (già esposti in /api/costi/summary — qui aggiungiamo breakdown)
- Costo produzione per kg (totale costi / kg prodotti)
- Aging sospesi (fasce 0-30, 31-60, 61-90, >90 gg)
- Km automezzi per mese/targa
- Marginalità per cliente (fatturato - quota costi allocata)
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from core import db, get_current_user, tenant_scope, tenant_id_of
from pdf_service import generate_report_pdf

router = APIRouter(tags=["reports"])


def _year_regex(anno: Optional[int]) -> Optional[Dict]:
    if anno is None:
        return None
    return {"$regex": f"^{anno}-"}


# ======================== FATTURATO ========================

@router.get("/reports/fatturato")
async def report_fatturato(anno: Optional[int] = None, user: Dict = Depends(get_current_user)):
    """Fatturato aggregato per mese + top clienti. Usa le fatture emesse."""
    tenant_id = tenant_id_of(user)
    # Filtra per anno via data (BSON datetime) se specificato
    match: Dict = {"tenant_id": tenant_id}
    if anno:
        start = datetime(anno, 1, 1, tzinfo=timezone.utc)
        end = datetime(anno + 1, 1, 1, tzinfo=timezone.utc)
        match["data"] = {"$gte": start, "$lt": end}

    # Per mese
    pipeline_mese = [
        {"$match": match},
        {"$addFields": {
            "mese": {"$dateToString": {"format": "%Y-%m", "date": "$data"}},
        }},
        {"$group": {
            "_id": "$mese",
            "totale": {"$sum": "$totale"},
            "incassato": {"$sum": {"$cond": [{"$eq": ["$stato_incasso", "incassata"]}, "$totale", 0]}},
            "sospeso": {"$sum": {"$cond": [{"$eq": ["$stato_incasso", "da_incassare"]}, "$totale", 0]}},
            "n": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ]
    per_mese: List[Dict] = []
    async for r in db.fatture.aggregate(pipeline_mese):
        per_mese.append({
            "mese": r["_id"],
            "totale": round(r["totale"], 2),
            "incassato": round(r["incassato"], 2),
            "sospeso": round(r["sospeso"], 2),
            "n": r["n"],
        })

    # Per cliente (top 20)
    pipeline_cli = [
        {"$match": match},
        {"$group": {
            "_id": "$cliente_id",
            "cliente_nome": {"$first": "$cliente_nome"},
            "totale": {"$sum": "$totale"},
            "n": {"$sum": 1},
        }},
        {"$sort": {"totale": -1}},
        {"$limit": 20},
    ]
    per_cliente: List[Dict] = []
    async for r in db.fatture.aggregate(pipeline_cli):
        per_cliente.append({
            "cliente_id": r["_id"],
            "cliente_nome": r.get("cliente_nome") or "—",
            "totale": round(r["totale"], 2),
            "n": r["n"],
        })

    totale = round(sum(m["totale"] for m in per_mese), 2)
    incassato = round(sum(m["incassato"] for m in per_mese), 2)
    sospeso = round(sum(m["sospeso"] for m in per_mese), 2)
    return {
        "anno": anno,
        "totale": totale,
        "incassato": incassato,
        "sospeso": sospeso,
        "per_mese": per_mese,
        "per_cliente": per_cliente,
    }


# ======================== PRODUZIONE (kg) ========================

def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # accetta YYYY-MM-DD
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    except Exception:
        try:
            return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            return None


@router.get("/reports/produzione")
async def report_produzione(
    anno: Optional[int] = None,
    data_inizio: Optional[str] = None,  # YYYY-MM-DD
    data_fine: Optional[str] = None,    # YYYY-MM-DD
    cliente_id: Optional[str] = None,
    categoria: Optional[str] = None,    # categoria articolo
    user: Dict = Depends(get_current_user),
):
    """Volume prodotto in kg = Σ (quantita riga DDT × peso_medio articolo).

    Filtri opzionali: anno, intervallo date, cliente, categoria articolo.
    Restituisce anche breakdown per mese, cliente, articolo, categoria, anno e DDT.
    """
    tenant_id = tenant_id_of(user)
    # Mappa articoli: id → {peso_medio, categoria, categoria_peso, codice, descrizione}
    articoli_map: Dict[str, Dict] = {}
    async for a in db.articoli.find(
        {"tenant_id": tenant_id},
        {"_id": 0, "id": 1, "peso_medio": 1, "codice": 1, "descrizione": 1, "categoria": 1, "categoria_peso": 1},
    ):
        articoli_map[a["id"]] = {
            "peso_medio": float(a.get("peso_medio") or 0),
            "categoria": (a.get("categoria") or "—") or "—",
            "categoria_peso": (a.get("categoria_peso") or "NON_CLASSIFICATO"),
            "codice": a.get("codice", ""),
            "descrizione": a.get("descrizione", ""),
        }

    # Match DDT
    match: Dict = {"tenant_id": tenant_id}
    dt_start = _parse_date(data_inizio)
    dt_end = _parse_date(data_fine)
    if dt_start or dt_end:
        date_q: Dict = {}
        if dt_start:
            date_q["$gte"] = dt_start
        if dt_end:
            # include tutto il giorno finale
            date_q["$lte"] = dt_end.replace(hour=23, minute=59, second=59)
        match["data"] = date_q
    elif anno:
        start = datetime(anno, 1, 1, tzinfo=timezone.utc)
        end = datetime(anno + 1, 1, 1, tzinfo=timezone.utc)
        match["data"] = {"$gte": start, "$lt": end}
    if cliente_id:
        match["cliente_id"] = cliente_id

    per_mese: Dict[str, Dict] = {}
    per_anno: Dict[str, Dict] = {}
    per_cliente: Dict[str, Dict] = {}
    per_articolo: Dict[str, Dict] = {}
    per_categoria: Dict[str, Dict] = {}
    per_categoria_peso: Dict[str, Dict] = {
        "BIANCHERIA_PIANA": {"categoria_peso": "BIANCHERIA_PIANA", "label": "Biancheria piana", "kg": 0.0, "pezzi": 0.0},
        "SPUGNA": {"categoria_peso": "SPUGNA", "label": "Spugna", "kg": 0.0, "pezzi": 0.0},
        "VARIE": {"categoria_peso": "VARIE", "label": "Varie", "kg": 0.0, "pezzi": 0.0},
        "NON_CLASSIFICATO": {"categoria_peso": "NON_CLASSIFICATO", "label": "Non classificato", "kg": 0.0, "pezzi": 0.0},
    }
    per_ddt: List[Dict] = []
    tot_kg = 0.0
    tot_pz = 0.0

    async for d in db.ddt.find(match, {"_id": 0}):
        data_val = d.get("data")
        if isinstance(data_val, datetime):
            mese = data_val.strftime("%Y-%m")
            year_str = data_val.strftime("%Y")
            data_iso = data_val.isoformat()
        elif isinstance(data_val, str):
            mese = data_val[:7]
            year_str = data_val[:4]
            data_iso = data_val
        else:
            continue
        cli_id = d.get("cliente_id") or ""
        cli_nome = d.get("cliente_nome") or "—"

        ddt_kg = 0.0
        ddt_pz = 0.0
        ddt_by_catpeso = {"BIANCHERIA_PIANA": 0.0, "SPUGNA": 0.0, "VARIE": 0.0, "NON_CLASSIFICATO": 0.0}

        for r in d.get("righe", []):
            aid = r.get("articolo_id")
            art = articoli_map.get(aid or "", {})
            cat = art.get("categoria", "—")
            cat_peso = art.get("categoria_peso", "NON_CLASSIFICATO") or "NON_CLASSIFICATO"
            # Filtro per categoria (se richiesto)
            if categoria and cat != categoria:
                continue
            qta = float(r.get("quantita") or 0)
            peso = float(art.get("peso_medio", 0) or 0)
            kg = qta * peso
            tot_kg += kg
            tot_pz += qta
            ddt_kg += kg
            ddt_pz += qta
            ddt_by_catpeso[cat_peso if cat_peso in ddt_by_catpeso else "NON_CLASSIFICATO"] += kg
            # mese
            slot = per_mese.setdefault(mese, {"mese": mese, "kg": 0.0, "pezzi": 0.0})
            slot["kg"] += kg; slot["pezzi"] += qta
            # anno
            slot_y = per_anno.setdefault(year_str, {"anno": year_str, "kg": 0.0, "pezzi": 0.0})
            slot_y["kg"] += kg; slot_y["pezzi"] += qta
            # cliente
            slot_c = per_cliente.setdefault(cli_id, {"cliente_id": cli_id, "cliente_nome": cli_nome, "kg": 0.0, "pezzi": 0.0})
            slot_c["kg"] += kg; slot_c["pezzi"] += qta
            # articolo
            slot_a = per_articolo.setdefault(aid or "nd", {
                "articolo_id": aid, "codice": r.get("codice", "") or art.get("codice", ""),
                "descrizione": r.get("descrizione", "") or art.get("descrizione", ""),
                "categoria": cat,
                "categoria_peso": cat_peso,
                "kg": 0.0, "pezzi": 0.0,
            })
            slot_a["kg"] += kg; slot_a["pezzi"] += qta
            # categoria (free-text)
            slot_cat = per_categoria.setdefault(cat, {"categoria": cat, "kg": 0.0, "pezzi": 0.0, "articoli": 0})
            slot_cat["kg"] += kg; slot_cat["pezzi"] += qta
            # categoria_peso (strutturato)
            key = cat_peso if cat_peso in per_categoria_peso else "NON_CLASSIFICATO"
            per_categoria_peso[key]["kg"] += kg
            per_categoria_peso[key]["pezzi"] += qta

        # per DDT (solo se c'è produzione)
        if ddt_kg > 0 or ddt_pz > 0:
            per_ddt.append({
                "ddt_id": d.get("id"),
                "numero": d.get("numero"),
                "data": data_iso,
                "cliente_id": cli_id,
                "cliente_nome": cli_nome,
                "kg": round(ddt_kg, 2),
                "pezzi": round(ddt_pz, 2),
                "kg_biancheria_piana": round(ddt_by_catpeso["BIANCHERIA_PIANA"], 2),
                "kg_spugna": round(ddt_by_catpeso["SPUGNA"], 2),
                "kg_varie": round(ddt_by_catpeso["VARIE"], 2),
                "kg_non_classificato": round(ddt_by_catpeso["NON_CLASSIFICATO"], 2),
            })

    # Numero di articoli distinti per categoria
    art_per_cat: Dict[str, set] = {}
    for a in per_articolo.values():
        art_per_cat.setdefault(a.get("categoria") or "—", set()).add(a.get("articolo_id"))
    for cat, s in art_per_cat.items():
        if cat in per_categoria:
            per_categoria[cat]["articoli"] = len(s)

    def _round(items, keys=("kg", "pezzi")):
        return [{**it, **{k: round(it[k], 2) for k in keys if k in it}} for it in items]

    per_mese_list = _round(sorted(per_mese.values(), key=lambda x: x["mese"]))
    per_anno_list = _round(sorted(per_anno.values(), key=lambda x: x["anno"]))
    per_cliente_list = _round(sorted(per_cliente.values(), key=lambda x: x["kg"], reverse=True))
    per_articolo_list = _round(sorted(per_articolo.values(), key=lambda x: x["kg"], reverse=True))
    per_categoria_list = _round(sorted(per_categoria.values(), key=lambda x: x["kg"], reverse=True))
    # Elenco ordinato biancheria/spugna/varie/non_classificato (ordine fisso)
    per_catpeso_list = _round([per_categoria_peso[k] for k in ("BIANCHERIA_PIANA", "SPUGNA", "VARIE", "NON_CLASSIFICATO")])
    per_ddt.sort(key=lambda x: x["data"], reverse=True)

    return {
        "anno": anno,
        "data_inizio": data_inizio,
        "data_fine": data_fine,
        "cliente_id": cliente_id,
        "categoria": categoria,
        "totale_kg": round(tot_kg, 2),
        "totale_pezzi": round(tot_pz, 2),
        "per_mese": per_mese_list,
        "per_anno": per_anno_list,
        "per_cliente": per_cliente_list[:50],
        "per_articolo": per_articolo_list[:50],
        "per_categoria": per_categoria_list,
        "per_categoria_peso": per_catpeso_list,
        "per_ddt": per_ddt[:500],  # limita per performance UI
        "ddt_count": len(per_ddt),
    }


@router.get("/reports/produzione/articoli-check")
async def articoli_peso_check(user: Dict = Depends(get_current_user)):
    """Controllo dati Articoli per l'analisi kg.

    - senza_peso: articoli con peso_medio mancante/zero
    - sospetti_grammi: articoli con peso >= 50 (probabile errore unità)
    - non_classificati: articoli con categoria_peso = NON_CLASSIFICATO (o mancante)
    """
    tenant_id = tenant_id_of(user)
    tot_articoli = 0
    senza_peso: List[Dict] = []
    sospetti_grammi: List[Dict] = []
    non_classificati: List[Dict] = []
    async for a in db.articoli.find(
        {"tenant_id": tenant_id},
        {"_id": 0, "id": 1, "codice": 1, "descrizione": 1, "categoria": 1, "categoria_peso": 1, "peso_medio": 1},
    ):
        tot_articoli += 1
        pm = a.get("peso_medio")
        try:
            pmv = float(pm) if pm is not None else 0
        except Exception:
            pmv = 0
        cat_peso = (a.get("categoria_peso") or "NON_CLASSIFICATO").upper()
        if pmv <= 0:
            senza_peso.append({
                "id": a["id"], "codice": a.get("codice", ""),
                "descrizione": a.get("descrizione", ""),
                "categoria": a.get("categoria", ""),
                "categoria_peso": cat_peso,
                "peso_medio": pmv,
            })
        elif pmv >= 50:
            sospetti_grammi.append({
                "id": a["id"], "codice": a.get("codice", ""),
                "descrizione": a.get("descrizione", ""),
                "peso_medio": pmv,
            })
        if cat_peso == "NON_CLASSIFICATO":
            non_classificati.append({
                "id": a["id"], "codice": a.get("codice", ""),
                "descrizione": a.get("descrizione", ""),
                "categoria": a.get("categoria", ""),
            })
    return {
        "totale_articoli": tot_articoli,
        "senza_peso_count": len(senza_peso),
        "senza_peso": senza_peso[:200],
        "sospetti_grammi": sospetti_grammi[:50],
        "non_classificati_count": len(non_classificati),
        "non_classificati": non_classificati[:200],
        "unita": "kg",
        "categorie_peso": list(("BIANCHERIA_PIANA", "SPUGNA", "VARIE", "NON_CLASSIFICATO")),
        "note": "Peso medio in chilogrammi. Valori >= 50 possono indicare un errore (dato in grammi). Classifica ogni articolo in una categoria peso (biancheria piana/spugna/varie).",
    }


@router.get("/reports/produzione/xlsx")
async def report_produzione_xlsx(
    anno: Optional[int] = None,
    data_inizio: Optional[str] = None,
    data_fine: Optional[str] = None,
    cliente_id: Optional[str] = None,
    categoria: Optional[str] = None,
    user: Dict = Depends(get_current_user),
):
    """Export Excel dell'analisi produzione kg con tutti gli aggregati."""
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    d = await report_produzione(
        anno=anno, data_inizio=data_inizio, data_fine=data_fine,
        cliente_id=cliente_id, categoria=categoria, user=user,
    )
    wb = Workbook()
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="4F46E5")

    def _write(ws, headers, rows):
        for i, h in enumerate(headers, 1):
            c = ws.cell(row=1, column=i, value=h)
            c.font = header_font; c.fill = header_fill
            c.alignment = Alignment(horizontal="center")
        for ri, row in enumerate(rows, 2):
            for ci, val in enumerate(row, 1):
                ws.cell(row=ri, column=ci, value=val)
        for i in range(1, len(headers) + 1):
            ws.column_dimensions[chr(64 + i)].width = 22

    # Sommario
    ws0 = wb.active; ws0.title = "Sommario"
    filtro_desc = []
    if data_inizio or data_fine:
        filtro_desc.append(f"Periodo: {data_inizio or '…'} → {data_fine or '…'}")
    elif anno:
        filtro_desc.append(f"Anno: {anno}")
    if cliente_id:
        filtro_desc.append(f"Cliente ID: {cliente_id}")
    if categoria:
        filtro_desc.append(f"Categoria: {categoria}")
    _write(ws0,
        ["Metrica", "Valore"],
        [
            ("Totale kg prodotti", d["totale_kg"]),
            ("Totale pezzi", d["totale_pezzi"]),
            ("Peso medio kg/pz", round(d["totale_kg"] / d["totale_pezzi"], 3) if d["totale_pezzi"] else 0),
            ("N° DDT nel periodo", d["ddt_count"]),
            ("Filtri", "; ".join(filtro_desc) or "Nessuno"),
        ],
    )

    # Per mese
    ws1 = wb.create_sheet("Per mese")
    _write(ws1, ["Mese", "Kg", "Pezzi"], [(r["mese"], r["kg"], r["pezzi"]) for r in d["per_mese"]])

    # Per anno
    ws1b = wb.create_sheet("Per anno")
    _write(ws1b, ["Anno", "Kg", "Pezzi"], [(r["anno"], r["kg"], r["pezzi"]) for r in d["per_anno"]])

    # Per cliente
    ws2 = wb.create_sheet("Per cliente")
    _write(ws2, ["Cliente", "Kg", "Pezzi"], [(r["cliente_nome"], r["kg"], r["pezzi"]) for r in d["per_cliente"]])

    # Per categoria (free-text)
    ws3 = wb.create_sheet("Per categoria")
    _write(ws3, ["Categoria", "Kg", "Pezzi", "N° articoli"],
        [(r["categoria"], r["kg"], r["pezzi"], r["articoli"]) for r in d["per_categoria"]])

    # Per categoria peso (strutturata)
    ws3b = wb.create_sheet("Per categoria peso")
    _write(ws3b, ["Categoria peso", "Kg", "Pezzi"],
        [(r["label"], r["kg"], r["pezzi"]) for r in d["per_categoria_peso"]])

    # Per articolo
    ws4 = wb.create_sheet("Per articolo")
    _write(ws4, ["Codice", "Descrizione", "Categoria", "Kg", "Pezzi"],
        [(r["codice"], r["descrizione"], r["categoria"], r["kg"], r["pezzi"]) for r in d["per_articolo"]])

    # Per DDT (con subtotali per categoria_peso)
    ws5 = wb.create_sheet("Per DDT")
    _write(ws5,
        ["Numero", "Data", "Cliente", "Kg biancheria", "Kg spugna", "Kg varie", "Kg non class.", "Kg totale", "Pezzi"],
        [(
            r["numero"], (r["data"] or "")[:10], r["cliente_nome"],
            r.get("kg_biancheria_piana", 0), r.get("kg_spugna", 0), r.get("kg_varie", 0),
            r.get("kg_non_classificato", 0), r["kg"], r["pezzi"],
        ) for r in d["per_ddt"]])

    buf = io.BytesIO()
    wb.save(buf); buf.seek(0)
    period = data_inizio and data_fine and f"{data_inizio}_{data_fine}" or (anno and str(anno)) or "tutto"
    filename = f"Analisi_kg_{period}.xlsx"
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ======================== COSTO PER KG ========================

@router.get("/reports/costo-kg")
async def report_costo_kg(anno: Optional[int] = None, user: Dict = Depends(get_current_user)):
    """Costo produzione per kg = totale costi / totale kg prodotti.

    Fornisce anche la breakdown per categoria costi e per mese (costo_kg mese-su-mese).
    """
    # Costi aggregati (riusa la stessa logica del modulo costi)
    match: Dict = dict(tenant_scope(user))
    rx = _year_regex(anno)
    if rx:
        match["mese_riferimento"] = rx

    # Per mese costi
    costi_mese: Dict[str, float] = {}
    async for r in db.costi.aggregate([
        {"$match": match},
        {"$group": {"_id": "$mese_riferimento", "totale": {"$sum": "$importo"}}},
    ]):
        costi_mese[r["_id"]] = float(r["totale"])

    costi_cat: Dict[str, float] = {}
    async for r in db.costi.aggregate([
        {"$match": match},
        {"$group": {"_id": "$categoria", "totale": {"$sum": "$importo"}}},
    ]):
        costi_cat[r["_id"]] = round(float(r["totale"]), 2)

    tot_costi = round(sum(costi_cat.values()), 2)

    # Kg (riusa logica produzione ma solo totali per mese)
    tenant_id = tenant_id_of(user)
    pesi: Dict[str, float] = {}
    async for a in db.articoli.find({"tenant_id": tenant_id}, {"_id": 0, "id": 1, "peso_medio": 1}):
        pesi[a["id"]] = float(a.get("peso_medio") or 0)

    ddt_match: Dict = {"tenant_id": tenant_id}
    if anno:
        start = datetime(anno, 1, 1, tzinfo=timezone.utc)
        end = datetime(anno + 1, 1, 1, tzinfo=timezone.utc)
        ddt_match["data"] = {"$gte": start, "$lt": end}

    kg_mese: Dict[str, float] = {}
    tot_kg = 0.0
    async for d in db.ddt.find(ddt_match, {"_id": 0}):
        dv = d.get("data")
        mese = dv.strftime("%Y-%m") if isinstance(dv, datetime) else (dv[:7] if isinstance(dv, str) else None)
        if not mese:
            continue
        for r in d.get("righe", []):
            kg = float(r.get("quantita") or 0) * pesi.get(r.get("articolo_id"), 0)
            kg_mese[mese] = kg_mese.get(mese, 0.0) + kg
            tot_kg += kg

    # Per mese combinato
    mesi = sorted(set(list(costi_mese.keys()) + list(kg_mese.keys())))
    per_mese = []
    for m in mesi:
        costi = round(costi_mese.get(m, 0.0), 2)
        kg = round(kg_mese.get(m, 0.0), 2)
        costo_kg = round(costi / kg, 4) if kg > 0 else None
        per_mese.append({"mese": m, "costi": costi, "kg": kg, "costo_kg": costo_kg})

    return {
        "anno": anno,
        "totale_costi": tot_costi,
        "totale_kg": round(tot_kg, 2),
        "costo_kg_medio": round(tot_costi / tot_kg, 4) if tot_kg > 0 else None,
        "per_categoria": costi_cat,
        "per_mese": per_mese,
    }


# ======================== AGING SOSPESI ========================

@router.get("/reports/aging-sospesi")
async def report_aging_sospesi(user: Dict = Depends(get_current_user)):
    """Fasce di scadenza per fatture da_incassare. Basato sulla data fattura (+30gg default).

    Buckets: 0-30, 31-60, 61-90, >90 giorni dalla data fattura.
    """
    tenant_id = tenant_id_of(user)
    today = datetime.now(timezone.utc).date()
    buckets = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, ">90": 0.0}
    counts = {"0-30": 0, "31-60": 0, "61-90": 0, ">90": 0}
    dettagli: List[Dict] = []

    async for f in db.fatture.find(
        {"tenant_id": tenant_id, "stato_incasso": "da_incassare"}, {"_id": 0}
    ):
        data_str = f.get("data")
        try:
            if isinstance(data_str, str):
                d = datetime.fromisoformat(data_str.replace("Z", "+00:00")).date() if "T" in data_str else datetime.strptime(data_str, "%Y-%m-%d").date()
            elif isinstance(data_str, datetime):
                d = data_str.date()
            else:
                continue
        except Exception:
            continue

        giorni = (today - d).days
        tot = float(f.get("totale") or 0)
        if giorni <= 30:
            bucket = "0-30"
        elif giorni <= 60:
            bucket = "31-60"
        elif giorni <= 90:
            bucket = "61-90"
        else:
            bucket = ">90"
        buckets[bucket] += tot
        counts[bucket] += 1
        dettagli.append({
            "numero": f.get("numero"),
            "cliente_nome": f.get("cliente_nome"),
            "data": data_str if isinstance(data_str, str) else d.isoformat(),
            "totale": round(tot, 2),
            "giorni": giorni,
            "bucket": bucket,
        })

    totale = round(sum(buckets.values()), 2)
    dettagli.sort(key=lambda x: x["giorni"], reverse=True)
    return {
        "oggi": today.isoformat(),
        "totale_sospeso": totale,
        "numero_fatture": sum(counts.values()),
        "buckets": [{"bucket": k, "totale": round(v, 2), "n": counts[k]} for k, v in buckets.items()],
        "dettagli": dettagli[:50],
    }


# ======================== KM AUTOMEZZI ========================

@router.get("/reports/km-automezzi")
async def report_km(anno: Optional[int] = None, user: Dict = Depends(get_current_user)):
    """Km percorsi + spesa per automezzo (targa) — da costi.categoria=automezzi."""
    match: Dict = dict(tenant_scope(user))
    match["categoria"] = "automezzi"
    rx = _year_regex(anno)
    if rx:
        match["mese_riferimento"] = rx

    per_targa: Dict[str, Dict] = {}
    per_mese: Dict[str, Dict] = {}

    async for c in db.costi.find(match, {"_id": 0}):
        targa = c.get("automezzo_targa") or "—"
        mese = c.get("mese_riferimento") or ""
        km = float(c.get("automezzo_km") or 0)
        importo = float(c.get("importo") or 0)
        tipo = c.get("tipo_automezzo_costo") or "altro"

        t = per_targa.setdefault(targa, {"targa": targa, "km_totali": 0.0, "spesa_totale": 0.0, "per_tipo": {}})
        t["km_totali"] += km
        t["spesa_totale"] += importo
        t["per_tipo"][tipo] = round(t["per_tipo"].get(tipo, 0) + importo, 2)

        m = per_mese.setdefault(mese, {"mese": mese, "km": 0.0, "spesa": 0.0})
        m["km"] += km
        m["spesa"] += importo

    per_targa_list = sorted(
        [{**v, "km_totali": round(v["km_totali"], 2), "spesa_totale": round(v["spesa_totale"], 2),
          "costo_km": round(v["spesa_totale"] / v["km_totali"], 4) if v["km_totali"] > 0 else None}
         for v in per_targa.values()],
        key=lambda x: x["spesa_totale"], reverse=True,
    )
    per_mese_list = sorted(
        [{**v, "km": round(v["km"], 2), "spesa": round(v["spesa"], 2)} for v in per_mese.values()],
        key=lambda x: x["mese"],
    )

    return {
        "anno": anno,
        "totale_km": round(sum(t["km_totali"] for t in per_targa_list), 2),
        "totale_spesa": round(sum(t["spesa_totale"] for t in per_targa_list), 2),
        "per_targa": per_targa_list,
        "per_mese": per_mese_list,
    }


# ======================== MARGINALITÀ ========================

@router.get("/reports/marginalita")
async def report_marginalita(anno: Optional[int] = None, user: Dict = Depends(get_current_user)):
    """Marginalità per cliente = Fatturato - quota costi allocata per kg prodotto.

    Allocazione: costi totali / kg totali = costo_kg; per ogni cliente: costo = costo_kg × kg_cliente;
    margine = fatturato_cliente - costo_allocato.
    """
    tenant_id = tenant_id_of(user)

    # Fatturato per cliente
    match_ft: Dict = {"tenant_id": tenant_id}
    if anno:
        start = datetime(anno, 1, 1, tzinfo=timezone.utc)
        end = datetime(anno + 1, 1, 1, tzinfo=timezone.utc)
        match_ft["data"] = {"$gte": start, "$lt": end}
    fat_cli: Dict[str, Dict] = {}
    async for r in db.fatture.aggregate([
        {"$match": match_ft},
        {"$group": {"_id": "$cliente_id", "cliente_nome": {"$first": "$cliente_nome"}, "totale": {"$sum": "$totale"}}},
    ]):
        fat_cli[r["_id"]] = {"cliente_id": r["_id"], "cliente_nome": r.get("cliente_nome") or "—", "fatturato": round(float(r["totale"]), 2)}

    # Kg per cliente (da DDT)
    pesi: Dict[str, float] = {}
    async for a in db.articoli.find({"tenant_id": tenant_id}, {"_id": 0, "id": 1, "peso_medio": 1}):
        pesi[a["id"]] = float(a.get("peso_medio") or 0)

    ddt_match: Dict = {"tenant_id": tenant_id}
    if anno:
        start = datetime(anno, 1, 1, tzinfo=timezone.utc)
        end = datetime(anno + 1, 1, 1, tzinfo=timezone.utc)
        ddt_match["data"] = {"$gte": start, "$lt": end}
    kg_cli: Dict[str, float] = {}
    tot_kg = 0.0
    async for d in db.ddt.find(ddt_match, {"_id": 0}):
        cli = d.get("cliente_id") or ""
        k = 0.0
        for r in d.get("righe", []):
            k += float(r.get("quantita") or 0) * pesi.get(r.get("articolo_id"), 0)
        kg_cli[cli] = kg_cli.get(cli, 0.0) + k
        tot_kg += k

    # Costi totali anno
    match_c: Dict = {"tenant_id": tenant_id}
    rx = _year_regex(anno)
    if rx:
        match_c["mese_riferimento"] = rx
    tot_costi = 0.0
    async for r in db.costi.aggregate([
        {"$match": match_c},
        {"$group": {"_id": None, "totale": {"$sum": "$importo"}}},
    ]):
        tot_costi = float(r.get("totale", 0))

    costo_kg = (tot_costi / tot_kg) if tot_kg > 0 else 0.0

    # Componi per cliente
    all_cli = set(fat_cli.keys()) | set(kg_cli.keys())
    rows = []
    for cid in all_cli:
        fat = fat_cli.get(cid, {"cliente_id": cid, "cliente_nome": "—", "fatturato": 0.0})
        kg = round(kg_cli.get(cid, 0.0), 2)
        costo_alloc = round(kg * costo_kg, 2)
        margine = round(fat["fatturato"] - costo_alloc, 2)
        margine_perc = round((margine / fat["fatturato"]) * 100, 2) if fat["fatturato"] > 0 else None
        rows.append({
            "cliente_id": fat["cliente_id"],
            "cliente_nome": fat["cliente_nome"],
            "fatturato": fat["fatturato"],
            "kg": kg,
            "costo_allocato": costo_alloc,
            "margine": margine,
            "margine_perc": margine_perc,
        })
    rows.sort(key=lambda x: x["margine"], reverse=True)

    return {
        "anno": anno,
        "totale_fatturato": round(sum(r["fatturato"] for r in rows), 2),
        "totale_costi": round(tot_costi, 2),
        "totale_kg": round(tot_kg, 2),
        "costo_kg_medio": round(costo_kg, 4),
        "margine_totale": round(sum(r["margine"] for r in rows), 2),
        "per_cliente": rows,
    }


# ======================== PDF EXPORT ========================

_REPORT_FUNCS = {
    "fatturato": report_fatturato,
    "produzione": report_produzione,
    "costo_kg": report_costo_kg,
    "marginalita": report_marginalita,
    "aging": report_aging_sospesi,
    "km": report_km,
}


@router.get("/reports/{tipo}/pdf")
async def report_pdf(tipo: str, anno: Optional[int] = None, user: Dict = Depends(get_current_user)):
    fn = _REPORT_FUNCS.get(tipo)
    if not fn:
        raise HTTPException(404, f"Report '{tipo}' non esistente. Ammessi: {list(_REPORT_FUNCS.keys())}")
    # Chiama la funzione report (accettano anno Optional eccetto aging)
    if tipo == "aging":
        data = await fn(user=user)
    else:
        data = await fn(anno=anno, user=user)
    tenant_id = tenant_id_of(user)
    company = await db.company.find_one({"tenant_id": tenant_id}, {"_id": 0}) or {}
    pdf_bytes = generate_report_pdf(tipo, data, company, anno=anno)
    filename = f"report-{tipo}-{anno or 'all'}.pdf"
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

