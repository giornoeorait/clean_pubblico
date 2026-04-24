"""Dashboard KPIs (ERP/DDT flow)."""
from datetime import datetime, timezone, timedelta
from typing import Dict
from fastapi import APIRouter, Depends
from core import db, get_current_user, require_roles, tenant_scope

router = APIRouter(tags=["dashboard"])


def _today_utc_start() -> datetime:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)


@router.get("/dashboard/kpi")
async def dashboard_kpi(user: Dict = Depends(get_current_user)):
    today_start = _today_utc_start()
    tomorrow_start = today_start + timedelta(days=1)
    first_day_month = today_start.replace(day=1)
    scope = tenant_scope(user)

    clienti_tot = await db.clienti.count_documents(scope)
    articoli_tot = await db.articoli.count_documents(scope)
    listini_tot = await db.listini.count_documents({**scope, "attivo": True})

    # DDT
    ddt_mese = await db.ddt.count_documents({**scope, "data": {"$gte": first_day_month}})
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

    # Magazzino allarmi (kept for warehouse module)
    magazzino_items = await db.magazzino.find(
        scope, {"_id": 0, "scorta_attuale": 1, "scorta_minima": 1, "scadenza": 1}
    ).to_list(2000)
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

    tickets_aperti = await db.tickets.count_documents({**scope, "stato": {"$in": ["aperto", "in_lavorazione"]}})

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
        "magazzino_allarmi": magazzino_allarmi,
        "tickets_aperti": tickets_aperti,
        "trend_ddt_7gg": trend,
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
