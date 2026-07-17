"""DDT (Documenti di Trasporto) — nucleo ERP di consegna."""
from datetime import datetime
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import (
    db, new_id, now_utc, to_dt,
    get_current_user, require_roles, log_audit, next_seq,
    tenant_scope, merge_scope, inject_tenant,
)
from routers.listini import get_prezzo

router = APIRouter(prefix="/ddt", tags=["ddt"])
_WRITE = ("admin", "logistica", "contabilita")


class DDTRigaIn(BaseModel):
    articolo_id: str
    quantita: int = Field(..., gt=0)
    prezzo_unitario: Optional[float] = None  # se None: auto da listino


class DDTIn(BaseModel):
    cliente_id: str
    data: Optional[str] = None
    note: Optional[str] = ""
    righe: List[DDTRigaIn]


class DDTPatch(BaseModel):
    data: Optional[str] = None
    note: Optional[str] = None
    righe: Optional[List[DDTRigaIn]] = None


class DDTOperativiPatch(BaseModel):
    """Toggle flag operativi autista. NON tocca dati fiscali/contabili."""
    consegnato: Optional[bool] = None
    ritirato_sporco: Optional[bool] = None


async def _compute_righe(tenant_id: str, listino_id: Optional[str], righe: List[DDTRigaIn]) -> (List[Dict[str, Any]], float, Dict[str, float]):
    """Ritorna righe arricchite con auto-pricing + snapshot peso + subtotali kg per categoria peso.

    Ogni riga contiene ora:
        peso_medio_snapshot: peso medio unitario congelato al momento del salvataggio (kg)
        categoria_peso_snapshot: categoria peso congelata (BIANCHERIA_PIANA/SPUGNA/VARIE/NON_CLASSIFICATO)
        peso_riga: peso totale riga = quantita × peso_medio_snapshot (kg, 3 decimali)

    Ritorna (righe_arricchite, imponibile_totale, peso_subtotals)
    """
    out = []
    total = 0.0
    peso_totale = 0.0
    peso_by_cat = {"BIANCHERIA_PIANA": 0.0, "SPUGNA": 0.0, "VARIE": 0.0, "NON_CLASSIFICATO": 0.0}
    for r in righe:
        prezzo = r.prezzo_unitario if r.prezzo_unitario is not None else await get_prezzo(tenant_id, listino_id, r.articolo_id)
        articolo = await db.articoli.find_one({"tenant_id": tenant_id, "id": r.articolo_id}, {"_id": 0})
        if not articolo:
            raise HTTPException(400, f"Articolo {r.articolo_id} non trovato")
        riga_tot = round(prezzo * r.quantita, 2)
        # Snapshot peso: congela peso medio e categoria dell'articolo al momento del save
        peso_unit = float(articolo.get("peso_medio") or 0)
        cat_peso = (articolo.get("categoria_peso") or "NON_CLASSIFICATO").upper()
        if cat_peso not in peso_by_cat:
            cat_peso = "NON_CLASSIFICATO"
        peso_riga = round(peso_unit * r.quantita, 3)
        out.append({
            "articolo_id": r.articolo_id,
            "codice": articolo.get("codice", ""),
            "descrizione": articolo.get("descrizione", ""),
            "unita_misura": articolo.get("unita_misura", "pz"),
            "quantita": r.quantita,
            "prezzo_unitario": round(prezzo, 4),
            "totale": riga_tot,
            # snapshot peso — CONGELATI
            "peso_medio_snapshot": round(peso_unit, 4),
            "categoria_peso_snapshot": cat_peso,
            "peso_riga": peso_riga,
        })
        total += riga_tot
        peso_totale += peso_riga
        peso_by_cat[cat_peso] += peso_riga
    peso_subtotals = {
        "peso_totale": round(peso_totale, 3),
        "peso_biancheria_piana": round(peso_by_cat["BIANCHERIA_PIANA"], 3),
        "peso_spugna": round(peso_by_cat["SPUGNA"], 3),
        "peso_varie": round(peso_by_cat["VARIE"], 3),
        "peso_non_classificato": round(peso_by_cat["NON_CLASSIFICATO"], 3),
    }
    return out, round(total, 2), peso_subtotals


# --- CRUD DDT ---------------------------------------------------------------
@router.get("")
async def list_ddt(
    user: Dict = Depends(get_current_user),
    cliente_id: Optional[str] = None,
    stato_fatturazione: Optional[str] = None,  # non_fatturato | fatturato
    from_date: Optional[str] = None,   # ISO date YYYY-MM-DD inclusive
    to_date: Optional[str] = None,     # ISO date YYYY-MM-DD inclusive
    limit: int = 500,
):
    q: Dict[str, Any] = dict(tenant_scope(user))
    if cliente_id:
        q["cliente_id"] = cliente_id
    if stato_fatturazione:
        q["stato_fatturazione"] = stato_fatturazione
    if user["role"] == "cliente" and user.get("cliente_id"):
        q["cliente_id"] = user["cliente_id"]
    # Filtro intervallo date.
    # IMPORTANTE: in DB `data` può essere salvato sia come ISO string ("YYYY-MM-DDT...")
    # che come BSON datetime. MongoDB NON confronta cross-type, quindi usiamo $or
    # con entrambe le rappresentazioni.
    if from_date or to_date:
        from datetime import datetime as _dt
        date_or = []
        # Versione stringa (ISO sortable: T è dopo qualsiasi cifra valida)
        str_q: Dict[str, Any] = {}
        if from_date:
            str_q["$gte"] = from_date
        if to_date:
            str_q["$lte"] = f"{to_date}T23:59:59.999"
        date_or.append({"data": str_q})
        # Versione datetime
        dt_q: Dict[str, Any] = {}
        try:
            if from_date:
                dt_q["$gte"] = _dt.fromisoformat(from_date)
            if to_date:
                dt_q["$lte"] = _dt.fromisoformat(f"{to_date}T23:59:59.999")
            date_or.append({"data": dt_q})
        except ValueError:
            pass
        q["$or"] = date_or
    docs = await db.ddt.find(q, {"_id": 0}).sort("data", -1).to_list(limit)
    return await _enrich_cliente_denominazione(docs, user)


async def _enrich_cliente_denominazione(docs: list, user: Dict) -> list:
    """Add `cliente_denominazione` on each doc by joining with db.clienti (legacy data fix)."""
    missing_ids = list({d.get("cliente_id") for d in docs
                       if d.get("cliente_id") and not d.get("cliente_denominazione")})
    if not missing_ids:
        return docs
    cur = db.clienti.find(
        {"tenant_id": user["tenant_id"], "id": {"$in": missing_ids}},
        {"_id": 0, "id": 1, "denominazione_struttura": 1},
    )
    by_id: Dict[str, str] = {}
    async for c in cur:
        by_id[c["id"]] = c.get("denominazione_struttura") or ""
    for d in docs:
        if not d.get("cliente_denominazione"):
            d["cliente_denominazione"] = by_id.get(d.get("cliente_id"), "")
    return docs


@router.post("")
async def create_ddt(body: DDTIn, user: Dict = Depends(require_roles(*_WRITE))):
    cliente = await db.clienti.find_one(merge_scope(user, {"id": body.cliente_id}), {"_id": 0})
    if not cliente:
        raise HTTPException(400, "Cliente non trovato")
    if not body.righe:
        raise HTTPException(400, "Almeno una riga richiesta")

    listino_id = cliente.get("listino_id") or None
    righe, imponibile, peso_sub = await _compute_righe(user["tenant_id"], listino_id, body.righe)

    seq = await next_seq("ddt")
    from core import format_numero
    doc = {
        "id": new_id(),
        "numero": await format_numero("ddt", "DDT", seq),
        "cliente_id": body.cliente_id,
        "cliente_nome": cliente.get("ragione_sociale", ""),
        "cliente_denominazione": cliente.get("denominazione_struttura", ""),
        "listino_id": listino_id,
        "data": to_dt(body.data) or now_utc(),
        "note": body.note or "",
        "righe": righe,
        "imponibile": imponibile,
        # ---- Peso: snapshot al momento del salvataggio (kg, 3 decimali) ----
        **peso_sub,
        "calcolo_peso_tipo": "CALCOLO_ORIGINALE",
        "peso_calcolato_at": now_utc(),
        # -------------------------------------------------------------------
        "stato_fatturazione": "non_fatturato",
        "fattura_id": None,
        "fattura_numero": None,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    inject_tenant(doc, user)
    await db.ddt.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "ddt", doc["id"], {"cliente": cliente.get("ragione_sociale")})
    return doc


@router.get("/{did}")
async def get_ddt(did: str, user: Dict = Depends(get_current_user)):
    doc = await db.ddt.find_one(merge_scope(user, {"id": did}), {"_id": 0})
    if not doc:
        raise HTTPException(404, "DDT non trovato")
    return doc


@router.get("/{did}/pdf")
async def ddt_pdf(did: str, user: Dict = Depends(get_current_user)):
    from fastapi import Response
    from pdf_service import generate_ddt_pdf
    from routers.company import load_company_for_tenant
    ddt_doc = await db.ddt.find_one(merge_scope(user, {"id": did}), {"_id": 0})
    if not ddt_doc:
        raise HTTPException(404, "DDT non trovato")
    cliente = await db.clienti.find_one(merge_scope(user, {"id": ddt_doc["cliente_id"]}), {"_id": 0}) or {}
    company = await load_company_for_tenant(user["tenant_id"])
    pdf = generate_ddt_pdf(ddt_doc, cliente, company)
    filename = f"{ddt_doc.get('numero', 'DDT')}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.patch("/{did}")
async def update_ddt(did: str, body: DDTPatch, user: Dict = Depends(require_roles(*_WRITE))):
    existing = await db.ddt.find_one(merge_scope(user, {"id": did}), {"_id": 0})
    if not existing:
        raise HTTPException(404, "DDT non trovato")
    if existing.get("stato_fatturazione") == "fatturato":
        raise HTTPException(409, "DDT già fatturato: non modificabile")

    data = body.model_dump(exclude_unset=True)
    if "data" in data and data["data"]:
        if user.get("role") != "admin" and not user.get("can_edit_dates"):
            raise HTTPException(403, "Non hai i permessi per modificare la data del DDT")
        data["data"] = to_dt(data["data"]) or now_utc()
    if body.righe is not None:
        righe, imp, peso_sub = await _compute_righe(user["tenant_id"], existing.get("listino_id"), body.righe)
        data["righe"] = righe
        data["imponibile"] = imp
        # Ricalcola snapshot peso (nuovo save = nuovo snapshot originale)
        data.update(peso_sub)
        data["calcolo_peso_tipo"] = "CALCOLO_ORIGINALE"
        data["peso_calcolato_at"] = now_utc()
    data["updated_at"] = now_utc()
    await db.ddt.update_one(merge_scope(user, {"id": did}), {"$set": data})
    await log_audit(user, "UPDATE", "ddt", did)
    return {"ok": True}


@router.patch("/{did}/operativi")
async def update_ddt_operativi(did: str, body: DDTOperativiPatch, user: Dict = Depends(require_roles(*_WRITE))):
    """Toggle flag operativi (consegnato / ritirato_sporco) con timestamp + utente.
    Non altera dati fiscali/contabili; funziona anche se il DDT è fatturato."""
    existing = await db.ddt.find_one(merge_scope(user, {"id": did}), {"_id": 0})
    if not existing:
        raise HTTPException(404, "DDT non trovato")
    patch: Dict[str, Any] = {"updated_at": now_utc()}
    user_label = user.get("name") or user.get("email") or user.get("id", "")
    if body.consegnato is not None:
        patch["consegnato"] = bool(body.consegnato)
        if body.consegnato:
            patch["consegnato_at"] = now_utc()
            patch["consegnato_by"] = user_label
        else:
            patch["consegnato_at"] = None
            patch["consegnato_by"] = None
    if body.ritirato_sporco is not None:
        patch["ritirato_sporco"] = bool(body.ritirato_sporco)
        if body.ritirato_sporco:
            patch["ritirato_sporco_at"] = now_utc()
            patch["ritirato_sporco_by"] = user_label
        else:
            patch["ritirato_sporco_at"] = None
            patch["ritirato_sporco_by"] = None
    if len(patch) == 1:
        raise HTTPException(400, "Nessun flag operativo fornito")
    await db.ddt.update_one(merge_scope(user, {"id": did}), {"$set": patch})
    await log_audit(user, "UPDATE_OPERATIVI", "ddt", did, {
        "consegnato": patch.get("consegnato"),
        "ritirato_sporco": patch.get("ritirato_sporco"),
    })
    doc = await db.ddt.find_one(merge_scope(user, {"id": did}), {"_id": 0})
    return doc


@router.delete("/{did}")
async def delete_ddt(did: str, user: Dict = Depends(require_roles(*_WRITE))):
    existing = await db.ddt.find_one(merge_scope(user, {"id": did}), {"_id": 0})
    if not existing:
        raise HTTPException(404, "DDT non trovato")
    if existing.get("stato_fatturazione") == "fatturato":
        raise HTTPException(409, "DDT fatturato non può essere eliminato")
    await db.ddt.delete_one(merge_scope(user, {"id": did}))

    # Se questo DDT è stato generato da un ordinativo, riportiamo l'ordinativo a "nuovo"
    # in modo che torni editabile dall'utente.
    linked_ord = await db.ordinativi.find_one(
        merge_scope(user, {"ddt_id": did}), {"_id": 0, "id": 1, "numero": 1}
    )
    if linked_ord:
        await db.ordinativi.update_one(
            {"id": linked_ord["id"], "tenant_id": existing.get("tenant_id")},
            {"$set": {"stato": "nuovo", "ddt_id": None, "ddt_numero": None, "updated_at": now_utc()}},
        )

    await log_audit(user, "DELETE", "ddt", did, {"reverted_ordinativo": (linked_ord or {}).get("numero")})
    return {"ok": True, "reverted_ordinativo": (linked_ord or {}).get("numero")}



# ============ RICALCOLO STORICO PESO DDT =====================================

@router.get("/peso/ricalcolo/preview")
async def preview_ricalcolo_peso(user: Dict = Depends(require_roles("admin"))):
    """Anteprima del ricalcolo massivo peso su DDT storici (Admin only).

    Non modifica nulla. Ritorna:
    - ddt_totali: numero DDT del tenant
    - ddt_da_ricalcolare: quelli SENZA snapshot peso (peso_totale mancante o calcolo_peso_tipo assente)
    - ddt_con_calcolo_originale: quelli già con CALCOLO_ORIGINALE (verranno saltati, non sovrascritti)
    - ddt_con_ricalcolo_storico: già ricalcolati in precedenza
    - articoli_senza_peso: n° articoli con peso_medio=0 (righe verranno calcolate 0)
    - articoli_non_classificati: n° articoli con categoria_peso=NON_CLASSIFICATO
    - anomalie: elenco righe la cui articolo_id non esiste più (verranno saltate)
    """
    tenant_id = user["tenant_id"]
    tot_ddt = await db.ddt.count_documents({"tenant_id": tenant_id})
    con_originale = await db.ddt.count_documents({
        "tenant_id": tenant_id, "calcolo_peso_tipo": "CALCOLO_ORIGINALE",
    })
    con_ricalcolo = await db.ddt.count_documents({
        "tenant_id": tenant_id, "calcolo_peso_tipo": "RICALCOLO_STORICO",
    })
    # DDT da ricalcolare = quelli senza campo calcolo_peso_tipo
    da_ricalcolare = await db.ddt.count_documents({
        "tenant_id": tenant_id,
        "$or": [
            {"calcolo_peso_tipo": {"$exists": False}},
            {"calcolo_peso_tipo": None},
        ],
    })
    # Anagrafica articoli — controlli
    art_senza_peso = 0
    art_non_class = 0
    articoli_map: Dict[str, Dict] = {}
    async for a in db.articoli.find(
        {"tenant_id": tenant_id},
        {"_id": 0, "id": 1, "peso_medio": 1, "categoria_peso": 1, "codice": 1},
    ):
        articoli_map[a["id"]] = a
        pm = float(a.get("peso_medio") or 0)
        if pm <= 0:
            art_senza_peso += 1
        if (a.get("categoria_peso") or "NON_CLASSIFICATO").upper() == "NON_CLASSIFICATO":
            art_non_class += 1
    # Anomalie: righe con articolo_id mancante nell'anagrafica
    anomalie: List[Dict] = []
    async for d in db.ddt.find(
        {"tenant_id": tenant_id, "$or": [{"calcolo_peso_tipo": {"$exists": False}}, {"calcolo_peso_tipo": None}]},
        {"_id": 0, "id": 1, "numero": 1, "righe.articolo_id": 1, "righe.codice": 1},
    ):
        for r in (d.get("righe") or []):
            aid = r.get("articolo_id")
            if aid and aid not in articoli_map:
                anomalie.append({
                    "ddt_id": d.get("id"),
                    "ddt_numero": d.get("numero"),
                    "articolo_id": aid,
                    "codice": r.get("codice", ""),
                })
    return {
        "ddt_totali": tot_ddt,
        "ddt_da_ricalcolare": da_ricalcolare,
        "ddt_con_calcolo_originale": con_originale,
        "ddt_con_ricalcolo_storico": con_ricalcolo,
        "articoli_senza_peso": art_senza_peso,
        "articoli_non_classificati": art_non_class,
        "anomalie_count": len(anomalie),
        "anomalie": anomalie[:50],
        "note": "Il ricalcolo NON sovrascrive DDT con calcolo_peso_tipo già valorizzato. Marca i DDT trattati come RICALCOLO_STORICO con timestamp.",
    }


class RicalcoloIn(BaseModel):
    conferma: bool = False


@router.post("/peso/ricalcolo/esegui")
async def esegui_ricalcolo_peso(body: RicalcoloIn, user: Dict = Depends(require_roles("admin"))):
    """Esegue il ricalcolo massivo peso sui DDT storici (Admin only).

    Regole:
    - NON sovrascrive DDT con calcolo_peso_tipo già presente (CALCOLO_ORIGINALE o RICALCOLO_STORICO)
    - Usa peso_medio e categoria_peso dell'anagrafica articoli AL MOMENTO del ricalcolo
    - Popola snapshot su ogni riga (peso_medio_snapshot, categoria_peso_snapshot, peso_riga)
    - Popola subtotali doc (peso_totale, peso_biancheria_piana, peso_spugna, peso_varie, peso_non_classificato)
    - Marca ogni DDT con calcolo_peso_tipo=RICALCOLO_STORICO + peso_calcolato_at=now
    """
    if not body.conferma:
        raise HTTPException(400, "Aggiungi 'conferma': true per eseguire il ricalcolo")

    tenant_id = user["tenant_id"]
    articoli_map: Dict[str, Dict] = {}
    async for a in db.articoli.find(
        {"tenant_id": tenant_id},
        {"_id": 0, "id": 1, "peso_medio": 1, "categoria_peso": 1},
    ):
        articoli_map[a["id"]] = {
            "peso_medio": float(a.get("peso_medio") or 0),
            "categoria_peso": (a.get("categoria_peso") or "NON_CLASSIFICATO").upper(),
        }

    aggiornati = 0
    saltati_gia_calcolati = 0
    now = now_utc()

    async for d in db.ddt.find(
        {"tenant_id": tenant_id},
        {"_id": 0, "id": 1, "righe": 1, "calcolo_peso_tipo": 1},
    ):
        if d.get("calcolo_peso_tipo"):
            saltati_gia_calcolati += 1
            continue
        peso_totale = 0.0
        peso_by_cat = {"BIANCHERIA_PIANA": 0.0, "SPUGNA": 0.0, "VARIE": 0.0, "NON_CLASSIFICATO": 0.0}
        new_righe: List[Dict] = []
        for r in (d.get("righe") or []):
            aid = r.get("articolo_id")
            art = articoli_map.get(aid or "", {"peso_medio": 0.0, "categoria_peso": "NON_CLASSIFICATO"})
            peso_unit = float(art.get("peso_medio") or 0)
            cat_peso = art.get("categoria_peso", "NON_CLASSIFICATO")
            if cat_peso not in peso_by_cat:
                cat_peso = "NON_CLASSIFICATO"
            qta = float(r.get("quantita") or 0)
            peso_riga = round(peso_unit * qta, 3)
            peso_totale += peso_riga
            peso_by_cat[cat_peso] += peso_riga
            new_r = dict(r)
            new_r["peso_medio_snapshot"] = round(peso_unit, 4)
            new_r["categoria_peso_snapshot"] = cat_peso
            new_r["peso_riga"] = peso_riga
            new_righe.append(new_r)
        await db.ddt.update_one(
            {"tenant_id": tenant_id, "id": d["id"]},
            {"$set": {
                "righe": new_righe,
                "peso_totale": round(peso_totale, 3),
                "peso_biancheria_piana": round(peso_by_cat["BIANCHERIA_PIANA"], 3),
                "peso_spugna": round(peso_by_cat["SPUGNA"], 3),
                "peso_varie": round(peso_by_cat["VARIE"], 3),
                "peso_non_classificato": round(peso_by_cat["NON_CLASSIFICATO"], 3),
                "calcolo_peso_tipo": "RICALCOLO_STORICO",
                "peso_calcolato_at": now,
                "updated_at": now_utc(),
            }},
        )
        aggiornati += 1

    await log_audit(user, "RICALCOLO_PESO_STORICO", "ddt", "*", {
        "aggiornati": aggiornati,
        "saltati_gia_calcolati": saltati_gia_calcolati,
    })
    return {
        "aggiornati": aggiornati,
        "saltati_gia_calcolati": saltati_gia_calcolati,
        "eseguito_at": now.isoformat(),
    }
