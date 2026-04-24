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

from core import db, get_current_user, tenant_scope, tenant_id_of

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

@router.get("/reports/produzione")
async def report_produzione(anno: Optional[int] = None, user: Dict = Depends(get_current_user)):
    """Volume prodotto in kg = Σ (quantita riga DDT × peso_medio articolo).

    Usa i DDT emessi (vendite) come proxy del volume trattato.
    """
    tenant_id = tenant_id_of(user)
    # Mappa articoli → peso_medio
    pesi: Dict[str, float] = {}
    async for a in db.articoli.find({"tenant_id": tenant_id}, {"_id": 0, "id": 1, "peso_medio": 1, "codice": 1, "descrizione": 1}):
        pesi[a["id"]] = float(a.get("peso_medio") or 0)

    # Carica DDT dell'anno (data è BSON datetime nei DDT)
    match: Dict = {"tenant_id": tenant_id}
    if anno:
        start = datetime(anno, 1, 1, tzinfo=timezone.utc)
        end = datetime(anno + 1, 1, 1, tzinfo=timezone.utc)
        match["data"] = {"$gte": start, "$lt": end}

    per_mese: Dict[str, Dict] = {}          # mese -> {kg, pezzi}
    per_cliente: Dict[str, Dict] = {}       # cliente_id -> {nome, kg, pezzi}
    per_articolo: Dict[str, Dict] = {}      # articolo_id -> {codice, descr, kg, pezzi}
    tot_kg = 0.0
    tot_pz = 0.0

    async for d in db.ddt.find(match, {"_id": 0}):
        data_val = d.get("data")
        if isinstance(data_val, datetime):
            mese = data_val.strftime("%Y-%m")
        elif isinstance(data_val, str):
            mese = data_val[:7]
        else:
            continue
        cli_id = d.get("cliente_id") or ""
        cli_nome = d.get("cliente_nome") or "—"

        for r in d.get("righe", []):
            aid = r.get("articolo_id")
            qta = float(r.get("quantita") or 0)
            peso = pesi.get(aid, 0)
            kg = qta * peso
            tot_kg += kg
            tot_pz += qta
            # mese
            slot = per_mese.setdefault(mese, {"mese": mese, "kg": 0.0, "pezzi": 0.0})
            slot["kg"] += kg
            slot["pezzi"] += qta
            # cliente
            slot_c = per_cliente.setdefault(cli_id, {"cliente_id": cli_id, "cliente_nome": cli_nome, "kg": 0.0, "pezzi": 0.0})
            slot_c["kg"] += kg
            slot_c["pezzi"] += qta
            # articolo
            slot_a = per_articolo.setdefault(aid or "nd", {
                "articolo_id": aid, "codice": r.get("codice", ""),
                "descrizione": r.get("descrizione", ""),
                "kg": 0.0, "pezzi": 0.0,
            })
            slot_a["kg"] += kg
            slot_a["pezzi"] += qta

    def _round(items, keys=("kg", "pezzi")):
        return [{**it, **{k: round(it[k], 2) for k in keys if k in it}} for it in items]

    per_mese_list = _round(sorted(per_mese.values(), key=lambda x: x["mese"]))
    per_cliente_list = _round(sorted(per_cliente.values(), key=lambda x: x["kg"], reverse=True)[:20])
    per_articolo_list = _round(sorted(per_articolo.values(), key=lambda x: x["kg"], reverse=True)[:20])

    return {
        "anno": anno,
        "totale_kg": round(tot_kg, 2),
        "totale_pezzi": round(tot_pz, 2),
        "per_mese": per_mese_list,
        "per_cliente": per_cliente_list,
        "per_articolo": per_articolo_list,
    }


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
