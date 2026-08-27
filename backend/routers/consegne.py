"""Consegne: elenco consegne per giorno + ottimizzazione giro (Nominatim + OSRM + TSP)."""
import asyncio
import math
from typing import Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException

from core import db, get_current_user, require_roles, tenant_id_of, now_utc

router = APIRouter(prefix="/consegne", tags=["consegne"])

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org"
UA = {"User-Agent": "CleanTec-Lavanderia/1.0 (gestionale consegne)"}


def _addr_cliente(c: Dict) -> str:
    return (c.get("indirizzo_scarico") or "").strip() or (c.get("indirizzo") or "").strip()


async def _geocode(addr: str) -> Optional[Dict]:
    try:
        async with httpx.AsyncClient(timeout=12, headers=UA) as cx:
            r = await cx.get(NOMINATIM_URL, params={"format": "json", "q": addr, "limit": 1, "countrycodes": "it"})
            r.raise_for_status()
            rows = r.json()
            if rows:
                return {"lat": float(rows[0]["lat"]), "lon": float(rows[0]["lon"]), "addr": addr}
    except Exception:
        pass
    return None


async def _geocode_cached(coll, doc: Dict, addr: str, scope: Dict) -> Optional[Dict]:
    geo = doc.get("geo")
    if geo and geo.get("addr") == addr and geo.get("lat"):
        return geo
    geo = await _geocode(addr)
    if geo:
        await coll.update_one(scope, {"$set": {"geo": geo}})
        await asyncio.sleep(1.0)  # rate limit Nominatim
    return geo


def _haversine_min(a: Dict, b: Dict) -> float:
    """Tempo stimato in secondi a ~40 km/h su distanza in linea d'aria * 1.3."""
    R = 6371.0
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp = p2 - p1
    dl = math.radians(b["lon"] - a["lon"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    km = 2 * R * math.asin(math.sqrt(h)) * 1.3
    return km / 40.0 * 3600.0


async def _matrix(points: List[Dict]):
    """Matrice durate (sec) e distanze (m). OSRM con fallback haversine."""
    coords = ";".join(f"{p['lon']},{p['lat']}" for p in points)
    try:
        async with httpx.AsyncClient(timeout=20, headers=UA) as cx:
            r = await cx.get(f"{OSRM_URL}/table/v1/driving/{coords}", params={"annotations": "duration,distance"})
            r.raise_for_status()
            d = r.json()
            if d.get("code") == "Ok" and d.get("durations"):
                return d["durations"], d.get("distances"), "osrm"
    except Exception:
        pass
    n = len(points)
    dur = [[_haversine_min(points[i], points[j]) if i != j else 0.0 for j in range(n)] for i in range(n)]
    dist = [[dur[i][j] / 3600.0 * 40000.0 for j in range(n)] for i in range(n)]
    return dur, dist, "stima"


async def _route_geometry(points_ordered: List[Dict]) -> Optional[List[List[float]]]:
    """Geometria reale su strada (lista [lat, lon]) via OSRM route."""
    coords = ";".join(f"{p['lon']},{p['lat']}" for p in points_ordered)
    try:
        async with httpx.AsyncClient(timeout=20, headers=UA) as cx:
            r = await cx.get(f"{OSRM_URL}/route/v1/driving/{coords}",
                             params={"overview": "full", "geometries": "geojson"})
            r.raise_for_status()
            d = r.json()
            if d.get("code") == "Ok" and d.get("routes"):
                return [[lat, lon] for lon, lat in d["routes"][0]["geometry"]["coordinates"]]
    except Exception:
        pass
    return None


def _tsp_round_trip(dur: List[List[float]]) -> List[int]:
    """Giro A/R dal nodo 0: nearest neighbour + 2-opt. Ritorna ordine dei nodi 1..n-1."""
    n = len(dur)
    if n <= 2:
        return list(range(1, n))
    unvisited = set(range(1, n))
    order, cur = [], 0
    while unvisited:
        nxt = min(unvisited, key=lambda j: dur[cur][j])
        order.append(nxt)
        unvisited.discard(nxt)
        cur = nxt

    def tour_cost(o):
        c = dur[0][o[0]] + dur[o[-1]][0]
        for i in range(len(o) - 1):
            c += dur[o[i]][o[i + 1]]
        return c

    improved = True
    while improved:
        improved = False
        for i in range(len(order) - 1):
            for j in range(i + 1, len(order)):
                cand = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                if tour_cost(cand) < tour_cost(order) - 1:
                    order = cand
                    improved = True
    return order


async def _consegne_del_giorno(tenant_id: str, data: str) -> List[Dict]:
    """Ordini convertiti in DDT con consegna richiesta nel giorno, raggruppati per cliente."""
    per_cliente: Dict[str, Dict] = {}
    async for o in db.ordinativi.find(
        {"tenant_id": tenant_id, "stato": "convertito_ddt", "data_consegna_richiesta": data},
        {"_id": 0, "id": 1, "numero": 1, "cliente_id": 1, "cliente_snapshot": 1,
         "ddt_numero": 1, "righe": 1, "data_consegna_richiesta": 1, "operatore_produzione": 1},
    ).sort("numero", 1):
        cid = o["cliente_id"]
        e = per_cliente.get(cid)
        if not e:
            cli = await db.clienti.find_one({"tenant_id": tenant_id, "id": cid}, {"_id": 0}) or {}
            snap = o.get("cliente_snapshot") or {}
            e = per_cliente[cid] = {
                "cliente_id": cid,
                "cliente": snap.get("denominazione_struttura") or snap.get("ragione_sociale") or cli.get("ragione_sociale") or "",
                "indirizzo": _addr_cliente(cli),
                "telefono": cli.get("telefono") or "",
                "ordini": [],
                "pezzi": 0.0,
            }
        e["ordini"].append({"numero": o["numero"], "ddt_numero": o.get("ddt_numero")})
        e["pezzi"] = round(e["pezzi"] + sum(float(r.get("quantita") or 0) for r in (o.get("righe") or [])), 1)
    return list(per_cliente.values())


@router.get("")
async def lista_consegne(data: str, user: Dict = Depends(require_roles("admin", "logistica", "contabilita"))):
    tenant_id = tenant_id_of(user)
    consegne = await _consegne_del_giorno(tenant_id, data)
    return {"data": data, "consegne": consegne, "n_consegne": len(consegne)}


@router.post("/giro")
async def calcola_giro(body: Dict, user: Dict = Depends(require_roles("admin", "logistica", "contabilita"))):
    data = (body or {}).get("data")
    if not data:
        raise HTTPException(422, "Campo 'data' richiesto (YYYY-MM-DD)")
    return await _calcola_giro(tenant_id_of(user), data,
                               cliente_ids=(body or {}).get("cliente_ids"),
                               autista=str((body or {}).get("autista") or "").strip())


@router.get("/giro/pdf")
async def giro_pdf(data: str, clienti: Optional[str] = None, autista: Optional[str] = None,
                   user: Dict = Depends(require_roles("admin", "logistica", "contabilita"))):
    from fastapi import Response
    from pdf_service import generate_giro_pdf
    tenant_id = tenant_id_of(user)
    cliente_ids = [c for c in (clienti or "").split(",") if c] or None
    giro = await _calcola_giro(tenant_id, data, cliente_ids=cliente_ids, autista=(autista or "").strip())
    if not giro.get("tappe"):
        raise HTTPException(404, "Nessuna consegna con indirizzo per questo giorno")
    company = await db.company.find_one({"tenant_id": tenant_id}, {"_id": 0}) or {}
    pdf = generate_giro_pdf(giro, company)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="Giro_consegne_{data}.pdf"'})


async def _calcola_giro(tenant_id: str, data: str, cliente_ids: Optional[List[str]] = None, autista: str = "") -> Dict:
    company = await db.company.find_one({"tenant_id": tenant_id}, {"_id": 0}) or {}
    sede_addr = ", ".join(x for x in [company.get("indirizzo"), company.get("cap"), company.get("comune"), company.get("provincia")] if x)
    if not sede_addr:
        raise HTTPException(422, "Indirizzo lavanderia mancante: compila i dati aziendali in Impostazioni")

    consegne = await _consegne_del_giorno(tenant_id, data)
    if cliente_ids:
        ids = set(cliente_ids)
        consegne = [c for c in consegne if c["cliente_id"] in ids]
    if not consegne:
        return {"data": data, "autista": autista, "tappe": [], "senza_indirizzo": [], "totale_min": 0, "totale_km": 0}

    sede_geo = await _geocode_cached(db.company, company, sede_addr, {"tenant_id": tenant_id})
    if not sede_geo:
        raise HTTPException(422, f"Impossibile geolocalizzare la sede: '{sede_addr}'")

    stops, senza_indirizzo = [], []
    for c in consegne:
        if not c["indirizzo"]:
            senza_indirizzo.append({**c, "motivo": "indirizzo mancante"})
            continue
        cli_doc = await db.clienti.find_one({"tenant_id": tenant_id, "id": c["cliente_id"]}, {"_id": 0, "geo": 1}) or {}
        geo = await _geocode_cached(db.clienti, cli_doc, c["indirizzo"], {"tenant_id": tenant_id, "id": c["cliente_id"]})
        if not geo:
            senza_indirizzo.append({**c, "motivo": "indirizzo non trovato sulla mappa"})
            continue
        stops.append({**c, "lat": geo["lat"], "lon": geo["lon"]})

    if not stops:
        return {"data": data, "autista": autista, "tappe": [], "senza_indirizzo": senza_indirizzo, "totale_min": 0, "totale_km": 0}

    points = [{"lat": sede_geo["lat"], "lon": sede_geo["lon"]}] + [{"lat": s["lat"], "lon": s["lon"]} for s in stops]
    dur, dist, fonte = await _matrix(points)
    order = _tsp_round_trip(dur)

    tappe, tot_sec, tot_m, prev = [], 0.0, 0.0, 0
    for pos, idx in enumerate(order, start=1):
        leg_s = dur[prev][idx] or 0
        leg_m = (dist[prev][idx] or 0) if dist else 0
        tot_sec += leg_s
        tot_m += leg_m
        s = stops[idx - 1]
        tappe.append({
            "posizione": pos, "cliente": s["cliente"], "cliente_id": s["cliente_id"],
            "indirizzo": s["indirizzo"], "telefono": s["telefono"],
            "ordini": s["ordini"], "pezzi": s["pezzi"],
            "lat": s["lat"], "lon": s["lon"],
            "tempo_tappa_min": round(leg_s / 60, 1), "km_tappa": round(leg_m / 1000, 1),
        })
        prev = idx
    rientro_s = dur[prev][0] or 0
    rientro_m = (dist[prev][0] or 0) if dist else 0
    tot_sec += rientro_s
    tot_m += rientro_m

    waypoints = "|".join(f"{t['lat']},{t['lon']}" for t in tappe)
    gmaps = (f"https://www.google.com/maps/dir/?api=1&origin={sede_geo['lat']},{sede_geo['lon']}"
             f"&destination={sede_geo['lat']},{sede_geo['lon']}&travelmode=driving&waypoints={waypoints}")

    sede_pt = {"lat": sede_geo["lat"], "lon": sede_geo["lon"]}
    geometria = await _route_geometry([sede_pt] + [{"lat": t["lat"], "lon": t["lon"]} for t in tappe] + [sede_pt])

    return {
        "data": data,
        "autista": autista,
        "partenza": {"indirizzo": sede_addr, "lat": sede_geo["lat"], "lon": sede_geo["lon"]},
        "tappe": tappe,
        "rientro_min": round(rientro_s / 60, 1), "rientro_km": round(rientro_m / 1000, 1),
        "totale_min": round(tot_sec / 60, 1), "totale_km": round(tot_m / 1000, 1),
        "fonte_tempi": fonte,
        "gmaps_url": gmaps,
        "geometria": geometria,
        "senza_indirizzo": senza_indirizzo,
        "calcolato_at": now_utc().isoformat(),
    }
