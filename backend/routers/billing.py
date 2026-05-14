"""Fatturazione riepilogativa da DDT + gestione incasso + sospesi.

Flusso:
1. GET /fatture/fatturabili?cliente_id=XXX -> elenco DDT non_fatturati del cliente
2. POST /fatture -> crea fattura da ddt_ids, marca DDT come fatturato
3. POST /fatture/{fid}/incassa -> imposta incasso
4. GET /sospesi -> fatture da_incassare
"""
from datetime import datetime
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core import (
    db, new_id, now_utc, to_dt,
    get_current_user, require_roles, log_audit, next_seq,
    tenant_scope, merge_scope, inject_tenant,
)

router = APIRouter(prefix="/fatture", tags=["billing"])
_WRITE = ("admin", "contabilita")


class FatturaFromDDT(BaseModel):
    cliente_id: str
    ddt_ids: List[str] = Field(..., min_length=1)
    data: Optional[str] = None
    scadenza: Optional[str] = None
    iva_pct: Optional[float] = None  # None → usa company.iva_default_pct (fallback 22)
    note: Optional[str] = ""


class IncassoIn(BaseModel):
    data_incasso: Optional[str] = None
    metodo: Optional[str] = "bonifico"  # bonifico | contanti | carta | altro
    note: Optional[str] = ""


@router.get("")
async def list_fatture(
    user: Dict = Depends(get_current_user),
    cliente_id: Optional[str] = None,
    stato_incasso: Optional[str] = None,  # da_incassare | incassata
    limit: int = 200,
):
    query: Dict[str, Any] = dict(tenant_scope(user))
    if cliente_id:
        query["cliente_id"] = cliente_id
    if stato_incasso:
        query["stato_incasso"] = stato_incasso
    if user["role"] == "cliente" and user.get("cliente_id"):
        query["cliente_id"] = user["cliente_id"]
    return await db.fatture.find(query, {"_id": 0}).sort("data", -1).to_list(limit)


@router.get("/fatturabili")
async def list_fatturabili(cliente_id: str, user: Dict = Depends(require_roles(*_WRITE))):
    """Elenco DDT non fatturati per il cliente specificato."""
    ddts = await db.ddt.find(
        merge_scope(user, {"cliente_id": cliente_id, "stato_fatturazione": "non_fatturato"}),
        {"_id": 0},
    ).sort("data", 1).to_list(1000)
    totale = round(sum(d.get("imponibile", 0) for d in ddts), 2)
    return {"ddts": ddts, "count": len(ddts), "totale_imponibile": totale}


@router.post("")
async def create_fattura_from_ddt(body: FatturaFromDDT, user: Dict = Depends(require_roles(*_WRITE))):
    cliente = await db.clienti.find_one(merge_scope(user, {"id": body.cliente_id}), {"_id": 0})
    if not cliente:
        raise HTTPException(400, "Cliente non trovato")

    # Load DDTs belonging to this cliente AND not already invoiced
    ddts = await db.ddt.find(
        merge_scope(user, {
            "id": {"$in": body.ddt_ids},
            "cliente_id": body.cliente_id,
            "stato_fatturazione": "non_fatturato",
        }),
        {"_id": 0},
    ).to_list(len(body.ddt_ids))
    if len(ddts) != len(body.ddt_ids):
        raise HTTPException(400, "Uno o più DDT non validi o già fatturati")

    imponibile = round(sum(d.get("imponibile", 0) for d in ddts), 2)
    # Resolve IVA: explicit body value > company default > 22
    iva_pct = body.iva_pct
    if iva_pct is None:
        comp = await db.company.find_one(tenant_scope(user), {"_id": 0}) or {}
        iva_pct = float(comp.get("iva_default_pct") or 22)
    iva = round(imponibile * iva_pct / 100, 2)
    totale = round(imponibile + iva, 2)

    seq = await next_seq("fattura")
    fid = new_id()
    from core import format_numero
    numero = await format_numero("fattura", "FT", seq)

    doc = {
        "id": fid,
        "numero": numero,
        "cliente_id": body.cliente_id,
        "cliente_nome": cliente.get("ragione_sociale", ""),
        "cliente_denominazione": cliente.get("denominazione_struttura", ""),
        "data": to_dt(body.data) or now_utc(),
        "scadenza": to_dt(body.scadenza) if body.scadenza else None,
        "iva_pct": iva_pct,
        "imponibile": imponibile,
        "iva": iva,
        "totale": totale,
        "ddt_ids": [d["id"] for d in ddts],
        "ddt_numeri": [d["numero"] for d in ddts],
        "note": body.note or "",
        "stato_incasso": "da_incassare",
        "data_incasso": None,
        "metodo_incasso": None,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    inject_tenant(doc, user)
    await db.fatture.insert_one(doc)

    # Mark DDTs as fatturato
    await db.ddt.update_many(
        merge_scope(user, {"id": {"$in": [d["id"] for d in ddts]}}),
        {"$set": {
            "stato_fatturazione": "fatturato",
            "fattura_id": fid,
            "fattura_numero": numero,
            "updated_at": now_utc(),
        }},
    )

    doc.pop("_id", None)
    await log_audit(user, "CREATE", "fattura", fid, {"ddt_count": len(ddts), "totale": totale})
    return doc


@router.get("/xml-bulk")
async def fatture_xml_bulk(
    user: Dict = Depends(get_current_user),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    month: Optional[str] = Query(None),  # "YYYY-MM"
):
    """Esporta in un singolo ZIP tutti gli XML Fattura Elettronica del periodo.

    Specifica:
      - `month=YYYY-MM` per esportare un singolo mese, oppure
      - `from=YYYY-MM-DD&to=YYYY-MM-DD` per un intervallo arbitrario.
    """
    import io
    import zipfile
    from datetime import date
    from calendar import monthrange
    from fastapi import Response
    from routers.company import load_company_for_tenant
    from services.fattura_elettronica import build_fattura_elettronica_xml

    # ----- Risolvi from/to -----
    if month:
        try:
            y, m = month.split("-")
            y, m = int(y), int(m)
            d_from = date(y, m, 1).isoformat()
            d_to = date(y, m, monthrange(y, m)[1]).isoformat()
            zip_name = f"Fatture_Elettroniche_{y:04d}-{m:02d}.zip"
        except Exception:
            raise HTTPException(400, "Parametro 'month' non valido (atteso YYYY-MM)")
    else:
        if not from_ or not to:
            raise HTTPException(400, "Specifica 'month' oppure 'from' e 'to'")
        try:
            date.fromisoformat(from_); date.fromisoformat(to)
        except Exception:
            raise HTTPException(400, "Date non valide (atteso YYYY-MM-DD)")
        if from_ > to:
            raise HTTPException(400, "'from' deve essere ≤ 'to'")
        d_from, d_to = from_, to
        zip_name = f"Fatture_Elettroniche_{d_from}_{d_to}.zip"

    # ----- Query fatture del periodo -----
    fatture = await db.fatture.find(
        merge_scope(user, {"data": {"$gte": d_from, "$lte": d_to}}),
        {"_id": 0},
    ).sort("data", 1).to_list(5000)

    if not fatture:
        raise HTTPException(404, f"Nessuna fattura trovata nel periodo {d_from} → {d_to}")

    company = await load_company_for_tenant(user["tenant_id"])

    # ----- Costruisci ZIP in memoria -----
    skipped: List[Dict[str, str]] = []
    included = 0
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fatt in fatture:
            cliente = await db.clienti.find_one(
                merge_scope(user, {"id": fatt["cliente_id"]}), {"_id": 0}
            ) or {}
            ddt_list = await db.ddt.find(
                merge_scope(user, {"id": {"$in": fatt.get("ddt_ids", [])}}),
                {"_id": 0},
            ).to_list(500)
            try:
                xml_bytes, filename = build_fattura_elettronica_xml(fatt, company, cliente, ddt_list)
                # Evita collisioni di nome (raro ma possibile su progressivi cross-anno)
                base_name = filename
                seq = 2
                while base_name in zf.namelist():
                    base_name = filename.replace(".xml", f"_{seq}.xml")
                    seq += 1
                zf.writestr(base_name, xml_bytes)
                included += 1
            except ValueError as e:
                skipped.append({"numero": fatt.get("numero", "?"), "reason": str(e)})

        # Manifest sommario (utile in caso di skip)
        manifest = (
            f"Export Fatture Elettroniche\n"
            f"Periodo: {d_from} → {d_to}\n"
            f"Generato: {now_utc().isoformat()}\n"
            f"Totale fatture nel periodo: {len(fatture)}\n"
            f"XML generati: {included}\n"
            f"Saltate per errore: {len(skipped)}\n"
        )
        if skipped:
            manifest += "\nFatture saltate:\n"
            for s in skipped:
                manifest += f"  · {s['numero']}: {s['reason']}\n"
        zf.writestr("_MANIFEST.txt", manifest.encode("utf-8"))

    if included == 0:
        raise HTTPException(
            400,
            f"Nessuna fattura del periodo è esportabile. {len(skipped)} fatture saltate per dati mancanti."
        )

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_name}"',
            "X-Export-Total": str(len(fatture)),
            "X-Export-Included": str(included),
            "X-Export-Skipped": str(len(skipped)),
        },
    )


@router.get("/{fid}/pdf")
async def fattura_pdf(fid: str, user: Dict = Depends(get_current_user)):
    from fastapi import Response
    from pdf_service import generate_fattura_pdf
    from routers.company import load_company_for_tenant
    fatt = await db.fatture.find_one(merge_scope(user, {"id": fid}), {"_id": 0})
    if not fatt:
        raise HTTPException(404, "Fattura non trovata")
    cliente = await db.clienti.find_one(merge_scope(user, {"id": fatt["cliente_id"]}), {"_id": 0}) or {}
    ddt_list = await db.ddt.find(
        merge_scope(user, {"id": {"$in": fatt.get("ddt_ids", [])}}),
        {"_id": 0},
    ).to_list(500)
    company = await load_company_for_tenant(user["tenant_id"])
    pdf = generate_fattura_pdf(fatt, cliente, company, ddt_list)
    filename = f"{fatt.get('numero', 'Fattura')}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/{fid}/xml")
async def fattura_xml_elettronica(fid: str, user: Dict = Depends(get_current_user)):
    """Export XML Fattura Elettronica (v1.2.2 FPR12 — privati B2B/B2C) per upload allo SdI."""
    from fastapi import Response
    from routers.company import load_company_for_tenant
    from services.fattura_elettronica import build_fattura_elettronica_xml

    fatt = await db.fatture.find_one(merge_scope(user, {"id": fid}), {"_id": 0})
    if not fatt:
        raise HTTPException(404, "Fattura non trovata")
    cliente = await db.clienti.find_one(merge_scope(user, {"id": fatt["cliente_id"]}), {"_id": 0}) or {}
    ddt_list = await db.ddt.find(
        merge_scope(user, {"id": {"$in": fatt.get("ddt_ids", [])}}),
        {"_id": 0},
    ).to_list(500)
    company = await load_company_for_tenant(user["tenant_id"])
    try:
        xml_bytes, filename = build_fattura_elettronica_xml(fatt, company, cliente, ddt_list)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return Response(
        content=xml_bytes,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{fid}")
async def get_fattura(fid: str, user: Dict = Depends(get_current_user)):
    doc = await db.fatture.find_one(merge_scope(user, {"id": fid}), {"_id": 0})
    if not doc:
        raise HTTPException(404, "Fattura non trovata")
    # Enrich with DDTs details
    if doc.get("ddt_ids"):
        doc["ddts"] = await db.ddt.find(
            merge_scope(user, {"id": {"$in": doc["ddt_ids"]}}), {"_id": 0}
        ).to_list(100)
    return doc


@router.post("/{fid}/incassa")
async def incassa_fattura(fid: str, body: IncassoIn, user: Dict = Depends(require_roles(*_WRITE))):
    fattura = await db.fatture.find_one(merge_scope(user, {"id": fid}), {"_id": 0})
    if not fattura:
        raise HTTPException(404, "Fattura non trovata")
    if fattura.get("stato_incasso") == "incassata":
        raise HTTPException(400, "Fattura già incassata")
    await db.fatture.update_one(
        merge_scope(user, {"id": fid}),
        {"$set": {
            "stato_incasso": "incassata",
            "data_incasso": to_dt(body.data_incasso) or now_utc(),
            "metodo_incasso": body.metodo,
            "note_incasso": body.note or "",
            "updated_at": now_utc(),
        }},
    )
    await log_audit(user, "INCASSA", "fattura", fid, {"metodo": body.metodo})
    return {"ok": True}


@router.post("/{fid}/annulla-incasso")
async def annulla_incasso(fid: str, user: Dict = Depends(require_roles("admin"))):
    await db.fatture.update_one(
        merge_scope(user, {"id": fid}),
        {"$set": {"stato_incasso": "da_incassare", "updated_at": now_utc()},
         "$unset": {"data_incasso": "", "metodo_incasso": "", "note_incasso": ""}},
    )
    await log_audit(user, "UNDO_INCASSO", "fattura", fid)
    return {"ok": True}


@router.delete("/{fid}")
async def delete_fattura(fid: str, user: Dict = Depends(require_roles("admin"))):
    """Elimina fattura: riabilita DDT collegati."""
    fattura = await db.fatture.find_one(merge_scope(user, {"id": fid}), {"_id": 0})
    if not fattura:
        raise HTTPException(404, "Fattura non trovata")
    if fattura.get("stato_incasso") == "incassata":
        raise HTTPException(409, "Fattura incassata: non eliminabile")
    # Unlink DDTs
    if fattura.get("ddt_ids"):
        await db.ddt.update_many(
            merge_scope(user, {"id": {"$in": fattura["ddt_ids"]}}),
            {"$set": {"stato_fatturazione": "non_fatturato"},
             "$unset": {"fattura_id": "", "fattura_numero": ""}},
        )
    await db.fatture.delete_one(merge_scope(user, {"id": fid}))
    await log_audit(user, "DELETE", "fattura", fid)
    return {"ok": True}


# --- Sospesi ---------------------------------------------------------------
sospesi_router = APIRouter(prefix="/sospesi", tags=["sospesi"])


@sospesi_router.get("")
async def list_sospesi(
    user: Dict = Depends(get_current_user),
    cliente_id: Optional[str] = None,
    dal: Optional[str] = None,
    al: Optional[str] = None,
    numero: Optional[str] = None,
    limit: int = 500,
):
    q: Dict[str, Any] = {**tenant_scope(user), "stato_incasso": "da_incassare"}
    if cliente_id: q["cliente_id"] = cliente_id
    if numero: q["numero"] = {"$regex": numero, "$options": "i"}
    if dal or al:
        date_q: Dict[str, Any] = {}
        if dal:
            d1 = to_dt(dal)
            if d1: date_q["$gte"] = d1
        if al:
            d2 = to_dt(al)
            if d2: date_q["$lte"] = d2
        if date_q: q["data"] = date_q
    if user["role"] == "cliente" and user.get("cliente_id"):
        q["cliente_id"] = user["cliente_id"]
    fatture = await db.fatture.find(q, {"_id": 0}).sort("data", 1).to_list(limit)
    totale = round(sum(f.get("totale", 0) for f in fatture), 2)
    return {
        "fatture": fatture,
        "count": len(fatture),
        "totale_sospesi": totale,
    }
