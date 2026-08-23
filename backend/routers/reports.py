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

from core import db, get_current_user, tenant_scope, tenant_id_of, require_roles, require_permission, now_utc
from pdf_service import generate_report_pdf

router = APIRouter(tags=["reports"])


def _year_regex(anno: Optional[int]) -> Optional[Dict]:
    if anno is None:
        return None
    return {"$regex": f"^{anno}-"}


# ======================== FATTURATO ========================

@router.get("/reports/fatturato")
async def report_fatturato(anno: Optional[int] = None, user: Dict = Depends(require_permission("report", "view"))):
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
    mese: Optional[int] = None,        # 1-12 (in combinazione con anno)
    data_inizio: Optional[str] = None,  # YYYY-MM-DD
    data_fine: Optional[str] = None,    # YYYY-MM-DD
    cliente_id: Optional[str] = None,
    categoria: Optional[str] = None,    # categoria articolo (free-text)
    categoria_peso: Optional[str] = None,  # BIANCHERIA_PIANA|SPUGNA|VARIE|NON_CLASSIFICATO
    articolo_id: Optional[str] = None,
    stato_fatturazione: Optional[str] = None,  # non_fatturato | fatturato
    solo_consegnati: bool = False,
    user: Dict = Depends(require_permission("report", "view")),
):
    """Volume prodotto in kg = Σ (quantita riga DDT × peso_medio articolo).

    Filtri opzionali: anno, mese, intervallo date, cliente, categoria articolo, categoria_peso,
    articolo, stato_fatturazione, solo_consegnati.
    Restituisce breakdown per mese, cliente, articolo, categoria, anno, DDT + KPI aggregati
    (peso_medio_per_ddt, peso_medio_giornaliero, peso_medio_mensile).

    Regole di inclusione (§13):
    - Solo DDT emessi (nel sistema tutti i DDT sono confermati, non esistono bozze/annullati).
    - Righe con quantita <= 0 vengono ignorate.
    - Articoli senza peso valido contribuiscono a 0 kg (non escludiamo il record).
    - Data di riferimento = `data` del DDT (non `created_at`).
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
        try:
            a_int = int(anno)
            m_int = int(mese) if mese is not None else None
        except (TypeError, ValueError):
            a_int = None
            m_int = None
        if a_int:
            if m_int and 1 <= m_int <= 12:
                start = datetime(a_int, m_int, 1, tzinfo=timezone.utc)
                if m_int == 12:
                    end = datetime(a_int + 1, 1, 1, tzinfo=timezone.utc)
                else:
                    end = datetime(a_int, m_int + 1, 1, tzinfo=timezone.utc)
            else:
                start = datetime(a_int, 1, 1, tzinfo=timezone.utc)
                end = datetime(a_int + 1, 1, 1, tzinfo=timezone.utc)
            match["data"] = {"$gte": start, "$lt": end}
    if cliente_id:
        match["cliente_id"] = cliente_id
    if stato_fatturazione:
        match["stato_fatturazione"] = stato_fatturazione
    if solo_consegnati:
        match["consegnato"] = True

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
            mese_key = data_val.strftime("%Y-%m")
            year_str = data_val.strftime("%Y")
            data_iso = data_val.isoformat()
        elif isinstance(data_val, str):
            mese_key = data_val[:7]
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
            # Filtro articolo (se richiesto)
            if articolo_id and aid != articolo_id:
                continue
            # Filtro qta > 0 (§13: escludi righe con quantita nulle/negative)
            qta_check = float(r.get("quantita") or 0)
            if qta_check <= 0:
                continue
            art = articoli_map.get(aid or "", {})
            cat = art.get("categoria", "—")
            # PREFERISCI snapshot se presente (peso storico congelato al save del DDT)
            has_snapshot = "peso_riga" in r or "peso_medio_snapshot" in r
            if has_snapshot:
                cat_peso = (r.get("categoria_peso_snapshot") or "NON_CLASSIFICATO").upper()
                peso_unit_used = float(r.get("peso_medio_snapshot") or 0)
                kg = float(r.get("peso_riga") or 0)
                # Se peso_riga è mancante ma abbiamo peso_medio_snapshot, ricalcola
                if not kg and peso_unit_used:
                    kg = float(r.get("quantita") or 0) * peso_unit_used
            else:
                cat_peso = art.get("categoria_peso", "NON_CLASSIFICATO") or "NON_CLASSIFICATO"
                peso_unit_used = float(art.get("peso_medio", 0) or 0)
                kg = float(r.get("quantita") or 0) * peso_unit_used
            # Filtro per categoria (se richiesto) — usa la categoria commerciale dell'articolo
            if categoria and cat != categoria:
                continue
            # Filtro per categoria_peso (se richiesto)
            if categoria_peso and cat_peso != categoria_peso.upper():
                continue
            qta = float(r.get("quantita") or 0)
            tot_kg += kg
            tot_pz += qta
            ddt_kg += kg
            ddt_pz += qta
            ddt_by_catpeso[cat_peso if cat_peso in ddt_by_catpeso else "NON_CLASSIFICATO"] += kg
            # mese
            slot = per_mese.setdefault(mese_key, {"mese": mese_key, "kg": 0.0, "pezzi": 0.0})
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
    per_catpeso_list = _round([per_categoria_peso[k] for k in ("BIANCHERIA_PIANA", "SPUGNA", "VARIE", "NON_CLASSIFICATO")])
    per_ddt.sort(key=lambda x: x["data"], reverse=True)

    # ---- KPI derivati ---------------------------------------------------
    ddt_count = len(per_ddt)
    peso_medio_ddt = round(tot_kg / ddt_count, 3) if ddt_count else 0.0
    # Peso medio giornaliero: distinct date days con almeno un DDT
    giorni_distinti = len({(r["data"] or "")[:10] for r in per_ddt if r.get("data")})
    peso_medio_giornaliero = round(tot_kg / giorni_distinti, 3) if giorni_distinti else 0.0
    # Peso medio mensile
    mesi_distinti = len(per_mese_list) or 1
    peso_medio_mensile = round(tot_kg / mesi_distinti, 3)

    # Mese label esplicito (se filtro mese) — cast difensivo
    mese_label = None
    try:
        m_int = int(mese) if mese is not None else None
        a_int = int(anno) if anno is not None else None
        if m_int and a_int and 1 <= m_int <= 12:
            mese_label = f"{a_int}-{m_int:02d}"
    except (TypeError, ValueError):
        mese_label = None

    return {
        "anno": anno,
        "mese": mese,
        "mese_label": mese_label,
        "data_inizio": data_inizio,
        "data_fine": data_fine,
        "cliente_id": cliente_id,
        "categoria": categoria,
        "categoria_peso": categoria_peso,
        "articolo_id": articolo_id,
        "stato_fatturazione": stato_fatturazione,
        "solo_consegnati": solo_consegnati,
        "totale_kg": round(tot_kg, 3),
        "totale_pezzi": round(tot_pz, 3),
        "peso_medio_per_ddt": peso_medio_ddt,
        "peso_medio_giornaliero": peso_medio_giornaliero,
        "peso_medio_mensile": peso_medio_mensile,
        "giorni_distinti": giorni_distinti,
        "mesi_distinti": mesi_distinti,
        "per_mese": per_mese_list,
        "per_anno": per_anno_list,
        "per_cliente": per_cliente_list[:50],
        "per_articolo": per_articolo_list[:50],
        "per_categoria": per_categoria_list,
        "per_categoria_peso": per_catpeso_list,
        "per_ddt": per_ddt[:500],
        "ddt_count": ddt_count,
    }


@router.get("/reports/produzione/articoli-check")
async def articoli_peso_check(user: Dict = Depends(require_permission("report", "view"))):
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
    mese: Optional[int] = None,
    data_inizio: Optional[str] = None,
    data_fine: Optional[str] = None,
    cliente_id: Optional[str] = None,
    categoria: Optional[str] = None,
    categoria_peso: Optional[str] = None,
    articolo_id: Optional[str] = None,
    stato_fatturazione: Optional[str] = None,
    solo_consegnati: bool = False,
    user: Dict = Depends(require_permission("report", "view")),
):
    """Export Excel dell'analisi produzione kg con tutti gli aggregati."""
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    d = await report_produzione(
        anno=anno, mese=mese, data_inizio=data_inizio, data_fine=data_fine,
        cliente_id=cliente_id, categoria=categoria, categoria_peso=categoria_peso,
        articolo_id=articolo_id, stato_fatturazione=stato_fatturazione,
        solo_consegnati=solo_consegnati, user=user,
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
            ("Peso medio per DDT", d.get("peso_medio_per_ddt", 0)),
            ("Peso medio giornaliero", d.get("peso_medio_giornaliero", 0)),
            ("Peso medio mensile", d.get("peso_medio_mensile", 0)),
            ("Giorni distinti", d.get("giorni_distinti", 0)),
            ("Mesi distinti", d.get("mesi_distinti", 0)),
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


# ==================== PDF EXPORT PRODUZIONE (Analisi kg) ====================

@router.get("/reports/produzione/pdf")
async def report_produzione_pdf(
    anno: Optional[int] = None,
    mese: Optional[int] = None,
    data_inizio: Optional[str] = None,
    data_fine: Optional[str] = None,
    cliente_id: Optional[str] = None,
    categoria: Optional[str] = None,
    categoria_peso: Optional[str] = None,
    articolo_id: Optional[str] = None,
    stato_fatturazione: Optional[str] = None,
    solo_consegnati: bool = False,
    user: Dict = Depends(require_permission("report", "view")),
):
    """Export PDF dell'analisi produzione kg. Rispetta i filtri applicati."""
    import io
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    d = await report_produzione(
        anno=anno, mese=mese, data_inizio=data_inizio, data_fine=data_fine,
        cliente_id=cliente_id, categoria=categoria, categoria_peso=categoria_peso,
        articolo_id=articolo_id, stato_fatturazione=stato_fatturazione,
        solo_consegnati=solo_consegnati, user=user,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        rightMargin=12 * mm, leftMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=16, textColor=colors.HexColor("#1e293b"))
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=11, textColor=colors.HexColor("#334155"), spaceBefore=8)
    small = ParagraphStyle("s", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#64748b"))

    parts = []
    parts.append(Paragraph("Analisi produzione in kg", h1))
    filtri = []
    if data_inizio or data_fine:
        filtri.append(f"Periodo: {data_inizio or '…'} → {data_fine or '…'}")
    elif anno:
        filtri.append(f"Anno: {anno}" + (f" - Mese: {mese:02d}" if mese else ""))
    if cliente_id:
        filtri.append(f"Cliente ID: {cliente_id}")
    if categoria:
        filtri.append(f"Categoria: {categoria}")
    if categoria_peso:
        filtri.append(f"Cat. peso: {categoria_peso}")
    if articolo_id:
        filtri.append(f"Articolo ID: {articolo_id}")
    if stato_fatturazione:
        filtri.append(f"Stato: {stato_fatturazione}")
    if solo_consegnati:
        filtri.append("Solo consegnati")
    parts.append(Paragraph("Filtri: " + (" · ".join(filtri) or "Nessuno"), small))
    parts.append(Spacer(1, 4 * mm))

    # KPI table
    parts.append(Paragraph("Indicatori", h2))
    kpi_data = [
        ["Totale kg", f"{d['totale_kg']:.3f} kg"],
        ["Totale pezzi", str(int(d['totale_pezzi']))],
        ["N° DDT", str(d["ddt_count"])],
        ["Peso medio per DDT", f"{d.get('peso_medio_per_ddt', 0):.3f} kg"],
        ["Peso medio giornaliero", f"{d.get('peso_medio_giornaliero', 0):.3f} kg"],
        ["Peso medio mensile", f"{d.get('peso_medio_mensile', 0):.3f} kg"],
        ["Giorni distinti", str(d.get("giorni_distinti", 0))],
    ]
    tkpi = Table(kpi_data, colWidths=[60 * mm, 40 * mm])
    tkpi.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
        ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#0f172a")),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    parts.append(tkpi)

    # Per categoria peso
    parts.append(Paragraph("Per categoria peso", h2))
    cat_rows = [["Categoria", "Kg", "Pezzi"]]
    for c in d.get("per_categoria_peso", []):
        cat_rows.append([c["label"], f"{c['kg']:.3f}", f"{int(c['pezzi'])}"])
    tcat = Table(cat_rows, colWidths=[60 * mm, 40 * mm, 40 * mm])
    tcat.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    parts.append(tcat)

    # Per mese con subtotali per categoria peso
    parts.append(Paragraph("Analisi mensile", h2))
    mese_rows = [["Mese", "Bianch.", "Spugna", "Varie", "Non class.", "Totale kg"]]
    monthly_split: Dict[str, Dict[str, float]] = {}
    for r in d.get("per_ddt", []):
        m_key = (r.get("data") or "")[:7]
        if not m_key:
            continue
        slot = monthly_split.setdefault(m_key, {"BIANCHERIA_PIANA": 0.0, "SPUGNA": 0.0, "VARIE": 0.0, "NON_CLASSIFICATO": 0.0})
        slot["BIANCHERIA_PIANA"] += r.get("kg_biancheria_piana", 0)
        slot["SPUGNA"] += r.get("kg_spugna", 0)
        slot["VARIE"] += r.get("kg_varie", 0)
        slot["NON_CLASSIFICATO"] += r.get("kg_non_classificato", 0)
    for m_key in sorted(monthly_split.keys()):
        s = monthly_split[m_key]
        tot = sum(s.values())
        mese_rows.append([m_key, f"{s['BIANCHERIA_PIANA']:.3f}", f"{s['SPUGNA']:.3f}",
                          f"{s['VARIE']:.3f}", f"{s['NON_CLASSIFICATO']:.3f}", f"{tot:.3f}"])
    if len(mese_rows) == 1:
        mese_rows.append(["—", "0", "0", "0", "0", "0"])
    tmese = Table(mese_rows, colWidths=[28 * mm, 30 * mm, 30 * mm, 30 * mm, 30 * mm, 35 * mm])
    tmese.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("PADDING", (0, 0), (-1, -1), 3),
    ]))
    parts.append(tmese)

    # Top clienti
    parts.append(Paragraph("Top clienti per kg", h2))
    cli_rows = [["Cliente", "Kg", "Pezzi"]]
    for c in d.get("per_cliente", [])[:15]:
        cli_rows.append([c["cliente_nome"], f"{c['kg']:.3f}", f"{int(c['pezzi'])}"])
    tcli = Table(cli_rows, colWidths=[120 * mm, 40 * mm, 40 * mm])
    tcli.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("PADDING", (0, 0), (-1, -1), 3),
    ]))
    parts.append(tcli)

    doc.build(parts)
    buf.seek(0)
    period = data_inizio and data_fine and f"{data_inizio}_{data_fine}" or (anno and str(anno)) or "tutto"
    filename = f"Analisi_kg_{period}.pdf"
    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ==================== STATISTICHE PESO SINGOLO CLIENTE ====================

@router.get("/clienti/{cliente_id}/statistiche-peso")
async def cliente_statistiche_peso(
    cliente_id: str,
    anno: Optional[int] = None,
    mese: Optional[int] = None,
    data_inizio: Optional[str] = None,
    data_fine: Optional[str] = None,
    categoria: Optional[str] = None,
    articolo_id: Optional[str] = None,
    user: Dict = Depends(require_permission("report", "view")),
):
    """Statistiche peso per un singolo cliente con filtri (§12)."""
    cli = await db.clienti.find_one({"tenant_id": tenant_id_of(user), "id": cliente_id}, {"_id": 0})
    if not cli:
        raise HTTPException(404, "Cliente non trovato")
    if user["role"] == "cliente" and user.get("cliente_id") != cliente_id:
        raise HTTPException(403, "Accesso negato")

    periodo = await report_produzione(
        anno=anno, mese=mese, data_inizio=data_inizio, data_fine=data_fine,
        cliente_id=cliente_id, categoria=categoria, articolo_id=articolo_id,
        user=user,
    )
    complessivo = await report_produzione(cliente_id=cliente_id, user=user)
    now = now_utc()
    mese_corr = await report_produzione(anno=now.year, mese=now.month, cliente_id=cliente_id, user=user)
    anno_corr = await report_produzione(anno=now.year, cliente_id=cliente_id, user=user)

    return {
        "cliente": {
            "id": cli["id"],
            "ragione_sociale": cli.get("ragione_sociale", ""),
            "denominazione_struttura": cli.get("denominazione_struttura", ""),
        },
        "periodo": {
            "totale_kg": periodo["totale_kg"],
            "totale_pezzi": periodo["totale_pezzi"],
            "ddt_count": periodo["ddt_count"],
            "peso_medio_per_ddt": periodo.get("peso_medio_per_ddt", 0),
            "peso_medio_giornaliero": periodo.get("peso_medio_giornaliero", 0),
            "peso_medio_mensile": periodo.get("peso_medio_mensile", 0),
            "per_categoria_peso": periodo["per_categoria_peso"],
            "per_mese": periodo["per_mese"],
            "per_articolo": periodo["per_articolo"][:20],
            "per_ddt": periodo["per_ddt"][:100],
            "filtri": {
                "anno": anno, "mese": mese, "data_inizio": data_inizio, "data_fine": data_fine,
                "categoria": categoria, "articolo_id": articolo_id,
            },
        },
        "complessivo": {
            "totale_kg": complessivo["totale_kg"],
            "ddt_count": complessivo["ddt_count"],
            "per_categoria_peso": complessivo["per_categoria_peso"],
        },
        "mese_corrente": {
            "totale_kg": mese_corr["totale_kg"],
            "per_categoria_peso": mese_corr["per_categoria_peso"],
            "ddt_count": mese_corr["ddt_count"],
        },
        "anno_corrente": {
            "totale_kg": anno_corr["totale_kg"],
            "per_categoria_peso": anno_corr["per_categoria_peso"],
            "ddt_count": anno_corr["ddt_count"],
        },
    }


# ==================== ANOMALIE PESI ====================

@router.get("/reports/anomalie-pesi")
async def anomalie_pesi(user: Dict = Depends(require_roles("admin"))):
    """Pannello 'Anomalie pesi' (§14) — Admin only.

    Rileva articoli con peso mancante/zero/negativo, categoria non assegnata,
    righe con qta<=0, DDT con differenze tra subtotali e totale, articoli mancanti.
    """
    tenant_id = tenant_id_of(user)
    articoli_anomali: List[Dict] = []
    ddt_by_articolo: Dict[str, set] = {}
    async for d in db.ddt.find({"tenant_id": tenant_id}, {"_id": 0, "id": 1, "righe.articolo_id": 1}):
        for r in (d.get("righe") or []):
            aid = r.get("articolo_id")
            if aid:
                ddt_by_articolo.setdefault(aid, set()).add(d["id"])

    articoli_ids_esistenti = set()
    async for a in db.articoli.find(
        {"tenant_id": tenant_id},
        {"_id": 0, "id": 1, "codice": 1, "descrizione": 1, "categoria": 1, "categoria_peso": 1, "peso_medio": 1},
    ):
        articoli_ids_esistenti.add(a["id"])
        pm = a.get("peso_medio")
        try:
            pmv = float(pm) if pm is not None else 0
        except Exception:
            pmv = 0
        cat_peso = (a.get("categoria_peso") or "").upper()
        problemi: List[str] = []
        if pm is None:
            problemi.append("peso medio mancante")
        elif pmv == 0:
            problemi.append("peso medio uguale a zero")
        elif pmv < 0:
            problemi.append("peso medio negativo")
        if not cat_peso or cat_peso == "NON_CLASSIFICATO":
            problemi.append("categoria peso non assegnata")
        if not a.get("categoria"):
            problemi.append("categoria commerciale mancante")
        if problemi:
            n_ddt = len(ddt_by_articolo.get(a["id"], set()))
            articoli_anomali.append({
                "articolo_id": a["id"],
                "codice": a.get("codice", ""),
                "descrizione": a.get("descrizione", ""),
                "categoria": a.get("categoria", ""),
                "categoria_peso": a.get("categoria_peso", ""),
                "peso_medio": pmv,
                "problemi": problemi,
                "ddt_coinvolti": n_ddt,
                "azione_consigliata": (
                    "Aggiorna anagrafica articolo e rilancia il ricalcolo storico"
                    if any("peso" in p for p in problemi)
                    else "Classifica l'articolo nella categoria peso corretta"
                ),
            })

    ddt_anomali: List[Dict] = []
    righe_qta_zero = 0
    righe_articolo_mancante = 0
    async for d in db.ddt.find(
        {"tenant_id": tenant_id},
        {"_id": 0, "id": 1, "numero": 1, "data": 1, "peso_totale": 1,
         "peso_biancheria_piana": 1, "peso_spugna": 1, "peso_varie": 1, "peso_non_classificato": 1,
         "calcolo_peso_tipo": 1, "righe": 1},
    ):
        problemi_ddt: List[str] = []
        subs = float(d.get("peso_biancheria_piana", 0) or 0) + float(d.get("peso_spugna", 0) or 0) \
             + float(d.get("peso_varie", 0) or 0) + float(d.get("peso_non_classificato", 0) or 0)
        tot = float(d.get("peso_totale") or 0)
        if d.get("calcolo_peso_tipo") and abs(subs - tot) > 0.005:
            problemi_ddt.append(f"somma subtotali ({subs:.3f}) ≠ peso_totale ({tot:.3f})")
        if not d.get("calcolo_peso_tipo"):
            problemi_ddt.append("DDT non ancora calcolato (esegui ricalcolo storico)")
        for r in (d.get("righe") or []):
            q = float(r.get("quantita") or 0)
            if q <= 0:
                righe_qta_zero += 1
            aid = r.get("articolo_id")
            if aid and aid not in articoli_ids_esistenti:
                righe_articolo_mancante += 1
        if problemi_ddt:
            dd_val = d.get("data")
            ddt_anomali.append({
                "ddt_id": d["id"],
                "numero": d.get("numero"),
                "data": dd_val.isoformat() if hasattr(dd_val, "isoformat") else dd_val,
                "problemi": problemi_ddt,
                "peso_totale": tot,
                "somma_subtotali": round(subs, 3),
            })

    return {
        "articoli_anomali_count": len(articoli_anomali),
        "articoli_anomali": articoli_anomali[:200],
        "ddt_anomali_count": len(ddt_anomali),
        "ddt_anomali": ddt_anomali[:200],
        "righe_qta_zero": righe_qta_zero,
        "righe_articolo_mancante": righe_articolo_mancante,
        "generato_at": now_utc().isoformat(),
    }




# ======================== COSTO PER KG ========================

@router.get("/reports/costo-kg")
async def report_costo_kg(anno: Optional[int] = None, user: Dict = Depends(require_permission("report", "view"))):
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
async def report_aging_sospesi(user: Dict = Depends(require_permission("report", "view"))):
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
async def report_km(anno: Optional[int] = None, user: Dict = Depends(require_permission("report", "view"))):
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
async def report_marginalita(anno: Optional[int] = None, user: Dict = Depends(require_permission("report", "view"))):
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
async def report_pdf(tipo: str, anno: Optional[int] = None, user: Dict = Depends(require_permission("report", "view"))):
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

