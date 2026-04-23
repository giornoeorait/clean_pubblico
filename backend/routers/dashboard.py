"""Dashboard KPIs, audit log, health.

Uses native BSON datetime fields for efficient range queries.
"""
from datetime import datetime, timezone, timedelta
from typing import Dict
from fastapi import APIRouter, Depends
from core import db, get_current_user, require_roles, STATI_LOTTO

router = APIRouter(tags=["dashboard"])


def _today_utc_start() -> datetime:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)


@router.get("/dashboard/kpi")
async def dashboard_kpi(user: Dict = Depends(get_current_user)):
    today_start = _today_utc_start()
    tomorrow_start = today_start + timedelta(days=1)
    first_day_month = today_start.replace(day=1)

    lotti_totali = await db.lotti.count_documents({})
    lotti_attivi = await db.lotti.count_documents({"stato_corrente": {"$nin": ["consegnato"]}})
    lotti_oggi = await db.lotti.find(
        {"created_at": {"$gte": today_start, "$lt": tomorrow_start}},
        {"peso": 1, "_id": 0},
    ).to_list(5000)
    kg_oggi = sum(l.get("peso", 0) for l in lotti_oggi)

    macchine = await db.macchine.find({}, {"_id": 0}).to_list(500)
    macchine_in_uso = sum(1 for m in macchine if m.get("stato") == "in_uso")
    macchine_disp = sum(1 for m in macchine if m.get("stato") == "disponibile")

    nc_aperte = await db.non_conformita.count_documents({"stato": "aperta"})
    tickets_aperti = await db.tickets.count_documents({"stato": {"$in": ["aperto", "in_lavorazione"]}})

    # Magazzino: conta gli articoli in allarme (scorta <= minima oppure scadenza imminente/scaduta)
    magazzino_items = await db.magazzino.find({}, {"_id": 0, "scorta_attuale": 1, "scorta_minima": 1, "scadenza": 1}).to_list(2000)
    magazzino_allarmi = 0
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    for it in magazzino_items:
        scorta = float(it.get("scorta_attuale", 0) or 0)
        minima = float(it.get("scorta_minima", 0) or 0)
        alarm = scorta <= minima
        sc = it.get("scadenza")
        if sc and isinstance(sc, datetime):
            sc_naive = sc.replace(tzinfo=None) if sc.tzinfo else sc
            if (sc_naive - now_naive).days <= 30:
                alarm = True
        if alarm:
            magazzino_allarmi += 1
    consegne_oggi = await db.consegne.count_documents(
        {"data_prevista": {"$gte": today_start, "$lt": tomorrow_start}}
    )

    # Real punctuality KPI: % of delivered consegne where data_consegna_effettiva <= data_prevista
    consegne_consegnate = await db.consegne.find(
        {"stato": "consegnata"},
        {"data_prevista": 1, "data_consegna_effettiva": 1, "_id": 0},
    ).to_list(5000)
    total_delivered = len(consegne_consegnate)
    puntuali = sum(
        1 for c in consegne_consegnate
        if c.get("data_consegna_effettiva") and c.get("data_prevista")
        and c["data_consegna_effettiva"] <= c["data_prevista"]
    )
    puntualita_pct = round((puntuali / total_delivered * 100) if total_delivered else 100.0, 1)

    fatture_mese = await db.fatture.find(
        {"data": {"$gte": first_day_month}}, {"totale": 1, "_id": 0}
    ).to_list(2000)
    fatturato_mese = sum(f.get("totale", 0) for f in fatture_mese)

    # Trend last 7 days (range query per day, Mongo-indexed)
    trend = []
    for i in range(6, -1, -1):
        day_start = today_start - timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        lotti_d = await db.lotti.find(
            {"created_at": {"$gte": day_start, "$lt": day_end}},
            {"peso": 1, "_id": 0},
        ).to_list(5000)
        trend.append({
            "giorno": day_start.strftime("%m-%d"),
            "kg": round(sum(l.get("peso", 0) for l in lotti_d), 1),
        })

    stati_dist = []
    for s in STATI_LOTTO:
        c = await db.lotti.count_documents({"stato_corrente": s})
        stati_dist.append({"stato": s, "count": c})

    return {
        "kg_oggi": round(kg_oggi, 1),
        "lotti_totali": lotti_totali,
        "lotti_attivi": lotti_attivi,
        "macchine_in_uso": macchine_in_uso,
        "macchine_disponibili": macchine_disp,
        "macchine_totali": len(macchine),
        "nc_aperte": nc_aperte,
        "tickets_aperti": tickets_aperti,
        "magazzino_allarmi": magazzino_allarmi,
        "consegne_oggi": consegne_oggi,
        "consegne_consegnate": total_delivered,
        "consegne_puntuali": puntuali,
        "puntualita_pct": puntualita_pct,
        "fatturato_mese": round(fatturato_mese, 2),
        "trend_kg_7gg": trend,
        "stati_distribution": stati_dist,
    }


@router.get("/audit-log")
async def get_audit(user: Dict = Depends(require_roles("admin")), limit: int = 500):
    return await db.audit_log.find({}, {"_id": 0}).sort("timestamp", -1).to_list(limit)


@router.get("/")
async def root():
    return {"app": "CleanTec", "status": "ok", "version": "1.2.0"}


@router.get("/health")
async def health():
    try:
        await db.command("ping")
        return {"status": "ok", "db": "ok"}
    except Exception as e:
        return {"status": "degraded", "db": str(e)}
