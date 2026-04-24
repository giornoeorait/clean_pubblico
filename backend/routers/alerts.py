"""Alerts aggregator: soglie costi categoria + scadenze fatture fornitore.

Endpoint unico GET /api/alerts che ritorna una lista aggregata di alert attivi.
Pensato per essere polled dal frontend (banner/badge in UI).
"""
from datetime import datetime, timezone
from typing import Dict, List
from fastapi import APIRouter, Depends

from core import db, get_current_user, tenant_id_of

router = APIRouter(tags=["alerts"])


@router.get("/alerts")
async def list_alerts(user: Dict = Depends(get_current_user)):
    """Ritorna alert attivi per il tenant.

    Tipi di alert:
      - 'costo_soglia': spesa mese corrente categoria > 120% media ultimi 3 mesi completati
      - 'fattura_scadenza': fattura fornitore con data_scadenza <= oggi+3 e stato_pagamento=da_pagare
      - 'fattura_scaduta': data_scadenza < oggi e da_pagare
      - 'aging_sospeso': fattura cliente con anzianità > 60 giorni
    """
    tenant_id = tenant_id_of(user)
    today = datetime.now(timezone.utc).date()
    alerts: List[Dict] = []

    # ========= COSTI: soglia 120% media 3 mesi =========
    mese_corr = today.strftime("%Y-%m")
    # Calcola mesi precedenti
    y, m = today.year, today.month
    prev3: List[str] = []
    for _ in range(3):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
        prev3.append(f"{y:04d}-{m:02d}")

    costi_cat_mese: Dict[str, float] = {}
    async for r in db.costi.aggregate([
        {"$match": {"tenant_id": tenant_id, "mese_riferimento": mese_corr}},
        {"$group": {"_id": "$categoria", "totale": {"$sum": "$importo"}}},
    ]):
        costi_cat_mese[r["_id"]] = float(r["totale"])

    medie: Dict[str, float] = {}
    async for r in db.costi.aggregate([
        {"$match": {"tenant_id": tenant_id, "mese_riferimento": {"$in": prev3}}},
        {"$group": {"_id": {"cat": "$categoria", "mese": "$mese_riferimento"}, "totale": {"$sum": "$importo"}}},
    ]):
        cat = r["_id"]["cat"]
        medie.setdefault(cat, []).append(float(r["totale"]))
    for cat, lst in medie.items():
        media = sum(lst) / len(lst)
        corr = costi_cat_mese.get(cat, 0)
        if media > 0 and corr > media * 1.2:
            alerts.append({
                "tipo": "costo_soglia",
                "severity": "warning",
                "categoria": cat,
                "mese": mese_corr,
                "importo_corrente": round(corr, 2),
                "media_3m": round(media, 2),
                "scostamento_perc": round(((corr - media) / media) * 100, 1),
                "messaggio": f"Costi {cat} di {mese_corr}: € {corr:.2f} (+{round(((corr-media)/media)*100, 1)}% vs media 3 mesi)",
            })

    # ========= FATTURE FORNITORE: scadenza imminente o scaduta =========
    async for f in db.fatture_fornitore.find(
        {"tenant_id": tenant_id, "stato_pagamento": "da_pagare", "data_scadenza": {"$ne": None}},
        {"_id": 0},
    ):
        scad = f.get("data_scadenza")
        if not scad:
            continue
        try:
            d_scad = datetime.strptime(scad[:10], "%Y-%m-%d").date()
        except Exception:
            continue
        giorni = (d_scad - today).days
        if giorni < 0:
            alerts.append({
                "tipo": "fattura_scaduta",
                "severity": "error",
                "fattura_id": f["id"],
                "numero": f.get("numero"),
                "fornitore": (f.get("fornitore_snapshot") or {}).get("ragione_sociale", "—"),
                "importo": round(float(f.get("totale", 0)), 2),
                "data_scadenza": scad,
                "giorni_ritardo": -giorni,
                "messaggio": f"Fattura fornitore {f.get('numero')} SCADUTA da {-giorni} giorni — € {f.get('totale', 0):.2f}",
            })
        elif giorni <= 3:
            alerts.append({
                "tipo": "fattura_scadenza",
                "severity": "warning",
                "fattura_id": f["id"],
                "numero": f.get("numero"),
                "fornitore": (f.get("fornitore_snapshot") or {}).get("ragione_sociale", "—"),
                "importo": round(float(f.get("totale", 0)), 2),
                "data_scadenza": scad,
                "giorni_alla_scadenza": giorni,
                "messaggio": f"Fattura fornitore {f.get('numero')} scade tra {giorni} giorni — € {f.get('totale', 0):.2f}",
            })

    # ========= AGING: fatture cliente > 60gg =========
    async for f in db.fatture.find(
        {"tenant_id": tenant_id, "stato_incasso": "da_incassare"},
        {"_id": 0},
    ):
        data_val = f.get("data")
        if isinstance(data_val, datetime):
            d = data_val.date()
        elif isinstance(data_val, str):
            try:
                d = datetime.strptime(data_val[:10], "%Y-%m-%d").date()
            except Exception:
                continue
        else:
            continue
        giorni = (today - d).days
        if giorni > 60:
            alerts.append({
                "tipo": "aging_sospeso",
                "severity": "error" if giorni > 90 else "warning",
                "fattura_id": f["id"],
                "numero": f.get("numero"),
                "cliente": f.get("cliente_nome"),
                "importo": round(float(f.get("totale", 0)), 2),
                "giorni": giorni,
                "messaggio": f"Fattura {f.get('numero')} cliente {f.get('cliente_nome')}: sospeso da {giorni} giorni — € {f.get('totale', 0):.2f}",
            })

    # Ordina per severità + tipo
    severity_order = {"error": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: (severity_order.get(a.get("severity"), 9), a.get("tipo", "")))

    by_sev = {"error": 0, "warning": 0, "info": 0}
    for a in alerts:
        by_sev[a.get("severity", "info")] = by_sev.get(a.get("severity", "info"), 0) + 1

    return {
        "totale": len(alerts),
        "per_severity": by_sev,
        "alerts": alerts,
    }
