"""BI Insights: forecast lotti + consumi detergenti vs produzione."""
from datetime import timedelta, datetime, timezone
from typing import Dict, Any, List
from fastapi import APIRouter, Depends
from core import db, now_utc, get_current_user, tenant_scope

router = APIRouter(prefix="/insights", tags=["insights"])


def _simple_forecast(series: List[float], periods: int = 7) -> List[float]:
    """Linear regression on last N days → predict next `periods` days."""
    n = len(series)
    if n < 2:
        return [series[-1] if series else 0.0] * periods
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(series) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, series))
    den = sum((x - mean_x) ** 2 for x in xs) or 1
    slope = num / den
    intercept = mean_y - slope * mean_x
    return [max(0.0, round(intercept + slope * (n + i), 2)) for i in range(periods)]


@router.get("/forecast")
async def forecast(user: Dict = Depends(get_current_user), history_days: int = 30, forecast_days: int = 7):
    """Return historical kg/day + linear forecast for next N days."""
    today = now_utc().replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - timedelta(days=history_days - 1)
    scope = tenant_scope(user)

    # Aggregate kg per day
    history = []
    for i in range(history_days):
        day = start + timedelta(days=i)
        day_end = day + timedelta(days=1)
        lotti = await db.lotti.find(
            {**scope, "created_at": {"$gte": day, "$lt": day_end}},
            {"peso": 1, "_id": 0},
        ).to_list(10000)
        kg = sum(l.get("peso", 0) for l in lotti)
        history.append({"giorno": day.strftime("%m-%d"), "kg": round(kg, 1)})

    series = [h["kg"] for h in history]
    forecast_values = _simple_forecast(series, forecast_days)
    future = []
    for i, v in enumerate(forecast_values):
        day = today + timedelta(days=i + 1)
        future.append({"giorno": day.strftime("%m-%d"), "kg": v})

    total_hist = sum(series)
    avg_hist = total_hist / history_days if history_days else 0
    trend = "crescita" if forecast_values[-1] > avg_hist * 1.05 else ("calo" if forecast_values[-1] < avg_hist * 0.95 else "stabile")

    return {
        "history": history,
        "forecast": future,
        "avg_kg_day": round(avg_hist, 1),
        "total_kg_last_period": round(total_hist, 1),
        "trend": trend,
        "expected_next_week_kg": round(sum(forecast_values), 1),
    }


@router.get("/consumi-detergenti")
async def consumi_detergenti(user: Dict = Depends(get_current_user), days: int = 30):
    """Correlation between kg lavati e consumo detergenti (scarichi magazzino con categoria detergenti)."""
    today = now_utc().replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - timedelta(days=days - 1)
    scope = tenant_scope(user)

    # Kg lavati totali nel periodo
    lotti = await db.lotti.find(
        {**scope, "created_at": {"$gte": start}},
        {"peso": 1, "_id": 0},
    ).to_list(50000)
    total_kg = sum(l.get("peso", 0) for l in lotti)

    # Consumo detergenti (scarichi) nel periodo
    movs = await db.magazzino_movimenti.find(
        {**scope, "tipo": "scarico", "timestamp": {"$gte": start}},
        {"articolo_codice": 1, "quantita": 1, "_id": 0},
    ).to_list(50000)

    # Raggruppa per articolo
    by_item: Dict[str, float] = {}
    total_qty = 0.0
    for m in movs:
        code = m.get("articolo_codice", "?")
        q = float(m.get("quantita", 0) or 0)
        by_item[code] = by_item.get(code, 0) + q
        total_qty += q

    ratio_l_per_kg = round((total_qty / total_kg), 4) if total_kg else 0

    # Also projected cost (rough): sum cost per item
    articoli = await db.magazzino.find(scope, {"_id": 0, "codice": 1, "costo_unitario": 1}).to_list(1000)
    cost_map = {a["codice"]: float(a.get("costo_unitario", 0) or 0) for a in articoli}
    projected_cost = sum(qty * cost_map.get(code, 0) for code, qty in by_item.items())

    return {
        "periodo_giorni": days,
        "total_kg_lavati": round(total_kg, 1),
        "total_qta_detergenti": round(total_qty, 2),
        "ratio_detergenti_per_kg": ratio_l_per_kg,
        "costo_stimato": round(projected_cost, 2),
        "costo_per_kg": round(projected_cost / total_kg, 3) if total_kg else 0,
        "top_consumi": sorted(
            [{"codice": k, "quantita": round(v, 2), "costo": round(v * cost_map.get(k, 0), 2)} for k, v in by_item.items()],
            key=lambda x: x["quantita"], reverse=True
        )[:10],
    }
