"""Dashboard KPIs — flusso commerciale (Listini → DDT → Fatture → Sospesi)."""
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from fastapi import APIRouter, Depends
from core import db, get_current_user, require_roles, tenant_scope

router = APIRouter(tags=["dashboard"])

# Mesi storici "pre-app" che vengono integrati automaticamente nelle statistiche
# annuali della dashboard. Sono i mesi caricati via Excel prima dell'attivazione
# completa dell'app (gennaio→marzo 2026).
STORICO_PREAPP_MONTHS = [(2026, 1), (2026, 2), (2026, 3), (2026, 4), (2026, 5)]


def _today_utc_start() -> datetime:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)


def _ddt_sum_imponibile(docs: List[Dict[str, Any]]) -> float:
    return sum(d.get("imponibile", 0) for d in docs)


@router.get("/dashboard/kpi")
async def dashboard_kpi(user: Dict = Depends(get_current_user)):
    today_start = _today_utc_start()
    today_end = today_start + timedelta(days=1)
    tomorrow_start = today_end
    first_day_month = today_start.replace(day=1)
    first_day_year = today_start.replace(month=1, day=1)
    scope = tenant_scope(user)

    clienti_tot = await db.clienti.count_documents(scope)
    articoli_tot = await db.articoli.count_documents(scope)
    listini_tot = await db.listini.count_documents({**scope, "attivo": True})

    # DDT
    # Nota: il campo `data` può essere salvato come datetime O come ISO string.
    # Per il filtro mensile usiamo datetime nativo (cassa di solito sempre datetime).
    ddt_mese_docs = await db.ddt.find(
        {**scope, "data": {"$gte": first_day_month}},
        {"data": 1, "imponibile": 1, "stato_fatturazione": 1, "_id": 0},
    ).to_list(20000)
    ddt_mese = len(ddt_mese_docs)
    ddt_mese_non_fatt = [d for d in ddt_mese_docs if d.get("stato_fatturazione") != "fatturato"]
    fatturare_mese_importo = round(_ddt_sum_imponibile(ddt_mese_non_fatt), 2)

    ddt_non_fatturati = await db.ddt.count_documents({**scope, "stato_fatturazione": "non_fatturato"})
    ddt_oggi = await db.ddt.count_documents({**scope, "created_at": {"$gte": today_start, "$lt": tomorrow_start}})

    # Fatture
    fatture_mese_docs = await db.fatture.find(
        {**scope, "data": {"$gte": first_day_month}}, {"totale": 1, "stato_incasso": 1, "_id": 0}
    ).to_list(5000)
    fatturato_mese = sum(f.get("totale", 0) for f in fatture_mese_docs)

    # Sospesi (da_incassare)
    sospesi_docs = await db.fatture.find(
        {**scope, "stato_incasso": "da_incassare"}, {"totale": 1, "_id": 0}
    ).to_list(5000)
    sospesi_totale = sum(f.get("totale", 0) for f in sospesi_docs)
    sospesi_count = len(sospesi_docs)

    # Incassato questo mese
    incassate_docs = await db.fatture.find(
        {**scope, "stato_incasso": "incassata", "data_incasso": {"$gte": first_day_month}},
        {"totale": 1, "_id": 0},
    ).to_list(5000)
    incassato_mese = sum(f.get("totale", 0) for f in incassate_docs)

    # Trend DDT 7gg (count per day)
    trend = []
    for i in range(6, -1, -1):
        day_start = today_start - timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        c = await db.ddt.count_documents({**scope, "data": {"$gte": day_start, "$lt": day_end}})
        trend.append({"giorno": day_start.strftime("%m-%d"), "ddt": c})

    # Serie cumulativa "Da fatturare nel mese": valore prodotto giorno per giorno
    # (DDT non ancora inclusi in fattura), cumulato dall'inizio del mese a oggi.
    cumul_serie: List[Dict[str, Any]] = []
    running = 0.0
    cur = first_day_month
    def _as_aware(dt):
        if isinstance(dt, datetime) and dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    while cur <= today_start:
        nxt = cur + timedelta(days=1)
        day_val = sum(
            d.get("imponibile", 0) for d in ddt_mese_non_fatt
            if d.get("data") and isinstance(d.get("data"), datetime)
            and cur <= _as_aware(d["data"]) < nxt
        )
        running += day_val
        cumul_serie.append({
            "giorno": cur.strftime("%d/%m"),
            "valore_giorno": round(day_val, 2),
            "cumulato": round(running, 2),
        })
        cur = nxt

    # ---- Storico pre-app integrato in statistiche annuali ----
    tenant_id = user["tenant_id"]
    anno_corrente = today_start.year
    storico_q = {
        "tenant_id": tenant_id,
        "anno": anno_corrente,
    }
    storico_docs = await db.fatturato_storico.find(storico_q, {"_id": 0}).to_list(5000)
    # Includi solo mesi pre-app autorizzati (es. gen/feb/mar 2026)
    months_allowed = {m for (y, m) in STORICO_PREAPP_MONTHS if y == anno_corrente}
    storico_filtered = [s for s in storico_docs if s.get("mese") in months_allowed]
    storico_totale_anno = round(sum(s.get("totale_netto", 0) for s in storico_filtered), 2)
    # mesi inclusi (per badge UI)
    storico_mesi_inclusi = sorted({s["mese"] for s in storico_filtered})

    # Fatturato anno = somma fatture emesse anno corrente + storico pre-app del medesimo anno
    fatture_anno_docs = await db.fatture.find(
        {**scope, "data": {"$gte": first_day_year}}, {"totale": 1, "_id": 0}
    ).to_list(20000)
    fatturato_anno_fatture = sum(f.get("totale", 0) for f in fatture_anno_docs)
    # de-duplicazione: se per un mese pre-app esistono GIÀ fatture vere, non sommiamo
    # lo storico per quel mese (evita doppi conteggi).
    fatture_anno_mesi = set()
    for f in fatture_anno_docs:
        fd = f.get("data")
        if isinstance(fd, datetime):
            fd_aware = fd if fd.tzinfo else fd.replace(tzinfo=timezone.utc)
            if fd_aware.year == anno_corrente:
                fatture_anno_mesi.add(fd_aware.month)
    storico_da_sommare = [s for s in storico_filtered if s["mese"] not in fatture_anno_mesi]
    storico_aggiunto = round(sum(s.get("totale_netto", 0) for s in storico_da_sommare), 2)
    fatturato_anno = round(fatturato_anno_fatture + storico_aggiunto, 2)

    # ---- Produzione kg (con snapshot su DDT, fallback anagrafica) ----
    # Query DDT del mese e dell'anno con solo i campi necessari
    def _sum_pesi(docs, key):
        return round(sum(float(d.get(key) or 0) for d in docs), 3)

    def _fallback_kg(doc, cat_key: str, articoli_map: Dict[str, Dict]) -> float:
        """Se DDT senza snapshot, ricalcola on-the-fly dall'anagrafica corrente."""
        tot = 0.0
        for r in (doc.get("righe") or []):
            aid = r.get("articolo_id")
            art = articoli_map.get(aid or "", {})
            cat = (art.get("categoria_peso") or "NON_CLASSIFICATO").upper()
            peso_unit = float(art.get("peso_medio") or 0)
            qta = float(r.get("quantita") or 0)
            if cat_key == "totale":
                tot += qta * peso_unit
            elif cat == cat_key:
                tot += qta * peso_unit
        return round(tot, 3)

    async def _cache_articoli():
        m: Dict[str, Dict] = {}
        async for a in db.articoli.find(
            {"tenant_id": user["tenant_id"]},
            {"_id": 0, "id": 1, "peso_medio": 1, "categoria_peso": 1},
        ):
            m[a["id"]] = a
        return m

    articoli_cache = None

    async def _aggregate_kg(match: Dict[str, Any]):
        nonlocal articoli_cache
        docs = await db.ddt.find(
            match,
            {"_id": 0, "id": 1, "righe": 1, "peso_totale": 1, "peso_biancheria_piana": 1,
             "peso_spugna": 1, "peso_varie": 1, "peso_non_classificato": 1, "calcolo_peso_tipo": 1},
        ).to_list(20000)
        # Split: docs con snapshot vs docs senza
        docs_snap = [d for d in docs if d.get("calcolo_peso_tipo")]
        docs_no_snap = [d for d in docs if not d.get("calcolo_peso_tipo")]
        tot = _sum_pesi(docs_snap, "peso_totale")
        bp = _sum_pesi(docs_snap, "peso_biancheria_piana")
        sp = _sum_pesi(docs_snap, "peso_spugna")
        va = _sum_pesi(docs_snap, "peso_varie")
        nc = _sum_pesi(docs_snap, "peso_non_classificato")
        if docs_no_snap:
            if articoli_cache is None:
                articoli_cache = await _cache_articoli()
            for d in docs_no_snap:
                tot += _fallback_kg(d, "totale", articoli_cache)
                bp += _fallback_kg(d, "BIANCHERIA_PIANA", articoli_cache)
                sp += _fallback_kg(d, "SPUGNA", articoli_cache)
                va += _fallback_kg(d, "VARIE", articoli_cache)
                nc += _fallback_kg(d, "NON_CLASSIFICATO", articoli_cache)
        return {
            "totale": round(tot, 3),
            "biancheria_piana": round(bp, 3),
            "spugna": round(sp, 3),
            "varie": round(va, 3),
            "non_classificato": round(nc, 3),
        }

    kg_mese = await _aggregate_kg({**scope, "data": {"$gte": first_day_month}})
    kg_anno = await _aggregate_kg({**scope, "data": {"$gte": first_day_year}})

    # Serie mensile per grafico confronto categorie (ultimi 12 mesi)
    serie_kg = []
    for i in range(11, -1, -1):
        # calcolo primo giorno del mese N-i
        y = today_start.year
        m = today_start.month - i
        while m <= 0:
            m += 12
            y -= 1
        month_start = datetime(y, m, 1, tzinfo=timezone.utc)
        if m == 12:
            month_end = datetime(y + 1, 1, 1, tzinfo=timezone.utc)
        else:
            month_end = datetime(y, m + 1, 1, tzinfo=timezone.utc)
        kg_m = await _aggregate_kg({**scope, "data": {"$gte": month_start, "$lt": month_end}})
        serie_kg.append({
            "mese": f"{y}-{m:02d}",
            "biancheria_piana": kg_m["biancheria_piana"],
            "spugna": kg_m["spugna"],
            "varie": kg_m["varie"],
            "non_classificato": kg_m["non_classificato"],
            "totale": kg_m["totale"],
        })

    return {
        "clienti_totali": clienti_tot,
        "articoli_totali": articoli_tot,
        "listini_attivi": listini_tot,
        "ddt_mese": ddt_mese,
        "ddt_oggi": ddt_oggi,
        "ddt_non_fatturati": ddt_non_fatturati,
        "fatturato_mese": round(fatturato_mese, 2),
        "incassato_mese": round(incassato_mese, 2),
        "sospesi_totale": round(sospesi_totale, 2),
        "sospesi_count": sospesi_count,
        "trend_ddt_7gg": trend,
        # Nuovo KPI: DDT del mese ancora da fatturare (importo)
        "fatturare_mese_importo": fatturare_mese_importo,
        "fatturare_mese_count": len(ddt_mese_non_fatt),
        "fatturare_mese_serie_cumul": cumul_serie,
        # Statistiche annuali integrate con storico pre-app
        "fatturato_anno": fatturato_anno,
        "fatturato_anno_fatture": round(fatturato_anno_fatture, 2),
        "fatturato_anno_storico": storico_aggiunto,
        "storico_totale_anno": storico_totale_anno,
        "storico_mesi_inclusi": storico_mesi_inclusi,
        "anno_corrente": anno_corrente,
        # ---- Produzione kg (mese e anno correnti, con serie 12 mesi) ----
        "kg_mese": kg_mese,
        "kg_anno": kg_anno,
        "kg_serie_mensile": serie_kg,
    }


@router.get("/audit-log")
async def get_audit(user: Dict = Depends(require_roles("admin")), limit: int = 500):
    return await db.audit_log.find(tenant_scope(user), {"_id": 0}).sort("timestamp", -1).to_list(limit)


@router.get("/")
async def root():
    return {"app": "CleanTec", "status": "ok", "version": "2.0.0"}


@router.get("/health")
async def health():
    try:
        await db.command("ping")
        return {"status": "ok", "db": "ok"}
    except Exception as e:
        return {"status": "degraded", "db": str(e)}
