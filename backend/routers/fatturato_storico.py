"""Fatturato storico pre-app: dati di produzione importati da Excel.

Collezione: `fatturato_storico` con upsert su (tenant_id, cliente_id, anno, mese)
così re-importi successivi aggiornano senza duplicare.

Endpoints (admin/contabilita):
  POST /api/imports/fatturato-storico/preview  — parse Excel, ritorna preview con fuzzy match cliente
  POST /api/imports/fatturato-storico/commit   — conferma e salva
  GET  /api/fatturato-storico                  — lista (filtri: anno, cliente_id)
  GET  /api/fatturato-storico/summary          — aggregati per cliente / mese / anno

Formato Excel atteso (foglio "contabilità"):
  Riga header per struttura: [A]=nome_struttura, [B]='Fatture Mese'|'Proforma Mese', [D]='Totale'
  Righe dati:                [B]='Proforma <Mese> <YY>', [C]='Proforma <nome> (copy)', [D]=importo
"""
from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Query
from pydantic import BaseModel

from core import db, log_audit, new_id, now_utc, require_roles, tenant_id_of

router = APIRouter(tags=["fatturato_storico"])

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

MESI = {
    "gennaio": 1, "gennnaio": 1, "genaio": 1, "genniao": 1, "gennaaio": 1, "genario": 1,
    "febbraio": 2, "febraio": 2, "febbaio": 2, "febraaio": 2,
    "marzo": 3, "marozo": 3,
    "aprile": 4, "apprile": 4,
    "maggio": 5, "magio": 5,
    "giugno": 6, "giungo": 6,
    "luglio": 7, "lugio": 7,
    "agosto": 8, "agost": 8,
    "settembre": 9, "setembre": 9, "settenbre": 9,
    "ottobre": 10, "otobre": 10,
    "novembre": 11, "novenbre": 11,
    "dicembre": 12, "dicenbre": 12, "dicembr": 12,
}
MESI_LABEL = {1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile", 5: "Maggio", 6: "Giugno",
              7: "Luglio", 8: "Agosto", 9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre"}


def _norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s or "").lower())


def _parse_mese(text: str) -> Tuple[Optional[int], Optional[int]]:
    """Parsifica una stringa tipo 'Proforma Gennaio 26' → (mese=1, anno=2026)."""
    if not text:
        return None, None
    t = str(text).lower()
    mese = None
    for k, v in MESI.items():
        if k in t:
            mese = v
            break
    # cerca 2-4 digits
    m = re.search(r"(20\d{2}|\b\d{2}\b)", t)
    anno = None
    if m:
        v = int(m.group(1))
        anno = v if v >= 1000 else 2000 + v
    return mese, anno


def _fuzzy_match(target: str, candidates: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    """Trova il miglior cliente che matcha `target` (denominazione struttura nell'excel).

    Strategia:
      1) match esatto su denominazione_struttura normalizzata
      2) match per "starts_with" / "contains"
      3) match Jaccard sui token (>=0.5 → ok, altrimenti None)
    Ritorna {cliente_id, score, reason} o None.
    """
    tnorm = _norm(target)
    if not tnorm:
        return None

    # 1) esatto
    for c in candidates:
        if c["_norm_den"] == tnorm or c["_norm_rs"] == tnorm:
            return {"cliente_id": c["id"], "score": 1.0, "reason": "esatto"}

    # 2) contains / starts_with
    for c in candidates:
        if c["_norm_den"] and (tnorm in c["_norm_den"] or c["_norm_den"] in tnorm):
            return {"cliente_id": c["id"], "score": 0.85, "reason": "contains"}

    # 3) Jaccard sui token
    target_tokens = set(re.findall(r"[a-z0-9]+", target.lower()))
    best = None
    for c in candidates:
        for src_field in ("denominazione_struttura", "ragione_sociale"):
            txt = (c.get(src_field) or "").lower()
            if not txt:
                continue
            src_tokens = set(re.findall(r"[a-z0-9]+", txt))
            if not src_tokens:
                continue
            inter = target_tokens & src_tokens
            union = target_tokens | src_tokens
            score = len(inter) / len(union) if union else 0
            if score >= 0.5 and (best is None or score > best["score"]):
                best = {"cliente_id": c["id"], "score": round(score, 2), "reason": "jaccard"}
    return best


def _parse_excel(file_bytes: bytes) -> List[Dict[str, Any]]:
    """Estrae le righe dal file Excel. Ritorna lista di dict:
       {struttura: str, mese: int, anno: int, totale: float}
    """
    try:
        from openpyxl import load_workbook
    except ImportError:
        raise HTTPException(500, "openpyxl non installato")

    try:
        wb = load_workbook(io.BytesIO(file_bytes), data_only=True)
    except Exception as e:
        raise HTTPException(400, f"File Excel non valido: {e}")

    ws = wb[wb.sheetnames[0]]
    out: List[Dict[str, Any]] = []
    current_struttura: Optional[str] = None

    for r in range(1, ws.max_row + 1):
        a = ws.cell(r, 1).value
        b = ws.cell(r, 2).value
        d = ws.cell(r, 4).value

        # Riga header (col A piena, D non numerico): nuova struttura
        if a and not isinstance(d, (int, float)):
            # filtra header generici tipo "Contabilità", "Scheda Clienti 2026"
            atxt = str(a).strip()
            if len(atxt) > 2 and "scheda" not in atxt.lower() and "contabil" not in atxt.lower():
                current_struttura = atxt
            continue

        # Riga dati: B contiene "Proforma <mese> <yy>" e D è numero
        if current_struttura and b and isinstance(d, (int, float)):
            mese, anno = _parse_mese(str(b))
            if mese and anno:
                out.append({
                    "struttura": current_struttura,
                    "mese": mese,
                    "anno": anno,
                    "totale": round(float(d), 2),
                })
    return out


# ---------------- Pydantic ----------------

class CommitItem(BaseModel):
    cliente_id: Optional[str] = None
    struttura_excel: str
    mese: int
    anno: int
    totale: float


class CommitIn(BaseModel):
    items: List[CommitItem]


# ---------------- Endpoints ----------------

@router.post("/imports/fatturato-storico/preview")
async def preview_import(
    file: UploadFile = File(...),
    user: Dict = Depends(require_roles("admin", "contabilita")),
):
    """Parsifica il file e ritorna le righe con matching cliente automatico."""
    raw = await file.read()
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(413, "File troppo grande (max 5 MB)")

    rows = _parse_excel(raw)
    if not rows:
        raise HTTPException(400, "Nessuna riga valida nel file Excel")

    tid = tenant_id_of(user)
    # Carico i clienti del tenant per matching
    clienti = await db.clienti.find(
        {"tenant_id": tid, "attivo": {"$ne": False}},
        {"_id": 0, "id": 1, "ragione_sociale": 1, "denominazione_struttura": 1},
    ).to_list(10000)
    for c in clienti:
        c["_norm_den"] = _norm(c.get("denominazione_struttura"))
        c["_norm_rs"] = _norm(c.get("ragione_sociale"))

    # Cache match per struttura (evita ri-calcolo per mese)
    match_cache: Dict[str, Optional[Dict[str, Any]]] = {}
    out_items: List[Dict[str, Any]] = []
    for row in rows:
        s = row["struttura"]
        if s not in match_cache:
            match_cache[s] = _fuzzy_match(s, clienti)
        m = match_cache[s]
        out_items.append({
            "struttura_excel": s,
            "mese": row["mese"],
            "anno": row["anno"],
            "mese_label": MESI_LABEL.get(row["mese"], str(row["mese"])),
            "totale": row["totale"],
            "cliente_id": m["cliente_id"] if m else None,
            "match_score": m["score"] if m else 0,
            "match_reason": m["reason"] if m else "no-match",
        })

    # Sommario uniqe strutture
    strutture_uniche = list({i["struttura_excel"]: i["cliente_id"] for i in out_items}.items())
    matched = sum(1 for s, cid in strutture_uniche if cid)
    return {
        "items": out_items,
        "summary": {
            "total_rows": len(out_items),
            "strutture_uniche": len(strutture_uniche),
            "strutture_matched": matched,
            "strutture_unmatched": len(strutture_uniche) - matched,
        },
        "clienti": [
            {"id": c["id"], "label": c.get("denominazione_struttura") or c.get("ragione_sociale"),
             "ragione_sociale": c.get("ragione_sociale")}
            for c in clienti
        ],
    }


@router.post("/imports/fatturato-storico/commit")
async def commit_import(body: CommitIn, user: Dict = Depends(require_roles("admin", "contabilita"))):
    """Salva le righe nel DB (upsert su cliente_id+anno+mese). Solo righe con cliente_id valido."""
    tid = tenant_id_of(user)
    now = now_utc()

    # cache denominazioni
    valid_clienti_ids = set()
    cli_docs = await db.clienti.find(
        {"tenant_id": tid}, {"_id": 0, "id": 1, "denominazione_struttura": 1, "ragione_sociale": 1}
    ).to_list(10000)
    cli_map = {c["id"]: c for c in cli_docs}
    valid_clienti_ids = set(cli_map.keys())

    upserted = 0
    skipped = 0
    for it in body.items:
        if not it.cliente_id or it.cliente_id not in valid_clienti_ids:
            skipped += 1
            continue
        cli = cli_map[it.cliente_id]
        doc = {
            "tenant_id": tid,
            "cliente_id": it.cliente_id,
            "cliente_denominazione": cli.get("denominazione_struttura") or "",
            "cliente_ragione_sociale": cli.get("ragione_sociale") or "",
            "struttura_excel": it.struttura_excel,
            "anno": int(it.anno),
            "mese": int(it.mese),
            "totale_netto": round(float(it.totale), 2),
            "origine": "import_excel",
            "updated_at": now,
        }
        await db.fatturato_storico.update_one(
            {"tenant_id": tid, "cliente_id": it.cliente_id, "anno": doc["anno"], "mese": doc["mese"]},
            {"$set": doc, "$setOnInsert": {"id": new_id(), "created_at": now}},
            upsert=True,
        )
        upserted += 1

    await log_audit(user, "IMPORT", "fatturato_storico", tid, {"upserted": upserted, "skipped": skipped})
    return {"ok": True, "upserted": upserted, "skipped": skipped}


@router.get("/fatturato-storico")
async def list_storico(
    anno: Optional[int] = Query(None),
    cliente_id: Optional[str] = Query(None),
    user: Dict = Depends(require_roles("admin", "contabilita")),
):
    """Lista dei record storici filtrati."""
    tid = tenant_id_of(user)
    q: Dict[str, Any] = {"tenant_id": tid}
    if anno:
        q["anno"] = anno
    if cliente_id:
        q["cliente_id"] = cliente_id
    docs = await db.fatturato_storico.find(q, {"_id": 0}).sort([("anno", -1), ("mese", 1)]).to_list(50000)
    return docs


@router.get("/fatturato-storico/summary")
async def summary_storico(
    anno: Optional[int] = Query(None),
    user: Dict = Depends(require_roles("admin", "contabilita")),
):
    """Aggregati per cliente, mese, e totale anno."""
    tid = tenant_id_of(user)
    q: Dict[str, Any] = {"tenant_id": tid}
    if anno:
        q["anno"] = anno
    docs = await db.fatturato_storico.find(q, {"_id": 0}).to_list(50000)

    # per cliente
    per_cliente: Dict[str, Dict[str, Any]] = {}
    for d in docs:
        cid = d["cliente_id"]
        if cid not in per_cliente:
            per_cliente[cid] = {
                "cliente_id": cid,
                "cliente_denominazione": d.get("cliente_denominazione"),
                "cliente_ragione_sociale": d.get("cliente_ragione_sociale"),
                "totale": 0.0,
                "per_mese": {},
            }
        per_cliente[cid]["totale"] += d.get("totale_netto", 0)
        key = f"{d['anno']}-{d['mese']:02d}"
        per_cliente[cid]["per_mese"][key] = per_cliente[cid]["per_mese"].get(key, 0) + d.get("totale_netto", 0)

    # per mese (trend globale)
    per_mese: Dict[str, float] = {}
    for d in docs:
        key = f"{d['anno']}-{d['mese']:02d}"
        per_mese[key] = per_mese.get(key, 0) + d.get("totale_netto", 0)

    totale = sum(d.get("totale_netto", 0) for d in docs)
    anni_disponibili = sorted({d["anno"] for d in docs}, reverse=True)

    return {
        "totale": round(totale, 2),
        "anni_disponibili": anni_disponibili,
        "per_cliente": sorted(per_cliente.values(), key=lambda x: -x["totale"]),
        "per_mese": [{"periodo": k, "totale": round(v, 2)} for k, v in sorted(per_mese.items())],
    }


@router.delete("/fatturato-storico/{rec_id}")
async def delete_storico(rec_id: str, user: Dict = Depends(require_roles("admin"))):
    tid = tenant_id_of(user)
    res = await db.fatturato_storico.delete_one({"tenant_id": tid, "id": rec_id})
    if not res.deleted_count:
        raise HTTPException(404, "Record non trovato")
    return {"ok": True}


class StoricoAggregatoIn(BaseModel):
    anno: int
    mese: int
    totale_netto: float
    note: Optional[str] = ""


@router.post("/fatturato-storico/aggregato")
async def upsert_storico_aggregato(body: StoricoAggregatoIn, user: Dict = Depends(require_roles("admin"))):
    """Registra/aggiorna il fatturato aggregato di un mese storico (senza dettaglio per cliente).
    Salvato con `cliente_id=None` e `origine='aggregato_manuale'`.
    Idempotente su (tenant_id, anno, mese, origine='aggregato_manuale').
    """
    if body.mese < 1 or body.mese > 12:
        raise HTTPException(400, "mese deve essere tra 1 e 12")
    tid = tenant_id_of(user)
    doc = {
        "id": new_id(),
        "tenant_id": tid,
        "cliente_id": None,
        "cliente_denominazione": "Aggregato mensile",
        "anno": int(body.anno),
        "mese": int(body.mese),
        "totale_netto": round(float(body.totale_netto), 2),
        "origine": "aggregato_manuale",
        "note": body.note or "",
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    await db.fatturato_storico.update_one(
        {"tenant_id": tid, "anno": doc["anno"], "mese": doc["mese"], "origine": "aggregato_manuale"},
        {"$set": doc},
        upsert=True,
    )
    await log_audit(user, "UPSERT_AGGREGATO", "fatturato_storico", f"{doc['anno']}-{doc['mese']:02d}", {"totale_netto": doc["totale_netto"]})
    return doc
