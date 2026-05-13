"""Company profile (anagrafica azienda madre) — per-tenant singleton.

Admin (tenant) gestisce i dati che compaiono come intestazione su DDT, fatture, offerte, contratti.
"""
from typing import Dict, Optional
import io
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response
from pydantic import BaseModel, Field, EmailStr
from PIL import Image

from core import db, now_utc, require_roles, tenant_scope, tenant_id_of, log_audit
from storage import put_object, get_object, APP_NAME

router = APIRouter(tags=["company"])

MAX_LOGO = 4 * 1024 * 1024  # 4 MB


class CompanyIn(BaseModel):
    nome: Optional[str] = ""
    ragione_sociale: Optional[str] = ""
    partita_iva: Optional[str] = ""
    codice_fiscale: Optional[str] = ""
    indirizzo: Optional[str] = ""
    iban: Optional[str] = ""
    email: Optional[str] = ""
    pec: Optional[str] = ""
    codice_sdi: Optional[str] = ""
    telefono: Optional[str] = ""
    sito_web: Optional[str] = ""


REQUIRED_FIELDS = ["nome", "ragione_sociale", "partita_iva", "indirizzo", "email", "telefono"]


def _public_view(doc: Optional[dict]) -> dict:
    if not doc:
        return {**{k: "" for k in CompanyIn.model_fields.keys()}, "logo_url": None, "setup_complete": False}
    setup_complete = all((doc.get(k) or "").strip() for k in REQUIRED_FIELDS)
    tid = doc.get("tenant_id") or ""
    out = {
        **{k: doc.get(k, "") for k in CompanyIn.model_fields.keys()},
        "logo_url": f"/api/company/logo/{tid}" if doc.get("logo_path") and tid else None,
        "setup_complete": setup_complete,
        "updated_at": doc.get("updated_at"),
    }
    return out


@router.get("/company")
async def get_company(user: Dict = Depends(require_roles("admin"))):
    doc = await db.company.find_one(tenant_scope(user), {"_id": 0})
    return _public_view(doc)


@router.put("/company")
async def upsert_company(body: CompanyIn, user: Dict = Depends(require_roles("admin"))):
    payload = {k: (v or "").strip() for k, v in body.model_dump(exclude_unset=False).items()}
    payload["tenant_id"] = tenant_id_of(user)
    payload["updated_at"] = now_utc()
    await db.company.update_one(
        tenant_scope(user),
        {"$set": payload, "$setOnInsert": {"created_at": now_utc()}},
        upsert=True,
    )
    doc = await db.company.find_one(tenant_scope(user), {"_id": 0})
    await log_audit(user, "UPDATE", "company", tenant_id_of(user), {"fields": list(payload.keys())})
    return _public_view(doc)


@router.post("/company/logo")
async def upload_company_logo(file: UploadFile = File(...), user: Dict = Depends(require_roles("admin"))):
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "File vuoto")
    if len(raw) > MAX_LOGO:
        raise HTTPException(400, f"File troppo grande (max {MAX_LOGO // 1024 // 1024} MB)")
    try:
        img = Image.open(io.BytesIO(raw))
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        img.thumbnail((512, 512), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=88, method=6)
        data = buf.getvalue()
    except Exception as e:
        raise HTTPException(400, f"Immagine non valida: {e}")
    path = f"{APP_NAME}/company/{tenant_id_of(user)}-logo-{int(now_utc().timestamp())}.webp"
    put_object(path, data, "image/webp")
    await db.company.update_one(
        tenant_scope(user),
        {"$set": {"logo_path": path, "tenant_id": tenant_id_of(user), "updated_at": now_utc()},
         "$setOnInsert": {"created_at": now_utc()}},
        upsert=True,
    )
    await log_audit(user, "UPLOAD", "company_logo", tenant_id_of(user), {"size": len(data)})
    return {"url": "/api/company/logo", "size": len(data), "width": img.width, "height": img.height}


@router.delete("/company/logo")
async def delete_company_logo(user: Dict = Depends(require_roles("admin"))):
    await db.company.update_one(tenant_scope(user), {"$unset": {"logo_path": ""}, "$set": {"updated_at": now_utc()}})
    return {"ok": True}


@router.get("/company/logo")
async def get_company_logo(user: Dict = Depends(require_roles("admin"))):
    """Return the tenant company logo (tenant-scoped, auth required). Legacy."""
    doc = await db.company.find_one(tenant_scope(user), {"_id": 0})
    path = (doc or {}).get("logo_path")
    if not path:
        raise HTTPException(404, "Logo non configurato")
    data, ctype = get_object(path)
    return Response(content=data, media_type=ctype or "image/webp", headers={"Cache-Control": "private, max-age=300"})


@router.get("/company/logo/{tenant_id}")
async def get_company_logo_public(tenant_id: str):
    """Public endpoint to load the company logo — used by <img> tags which can't send auth headers.

    Only returns the binary if a logo is configured for that tenant. The tenant_id is unguessable
    (UUID) and the logo is intended as public branding (visible on portale pubblico, fatture, ecc.).
    """
    doc = await db.company.find_one({"tenant_id": tenant_id}, {"_id": 0})
    path = (doc or {}).get("logo_path")
    if not path:
        raise HTTPException(404, "Logo non configurato")
    data, ctype = get_object(path)
    return Response(
        content=data,
        media_type=ctype or "image/webp",
        headers={"Cache-Control": "public, max-age=300"},
    )


async def load_company_for_tenant(tenant_id: str) -> dict:
    """Helper for PDF generation."""
    doc = await db.company.find_one({"tenant_id": tenant_id}, {"_id": 0})
    return doc or {}


# ============== EXPORT BACKUP ==============

OPERATIONAL_COLLECTIONS = [
    "clienti", "ddt", "fatture", "offerte", "ordinativi",
    "fornitori", "ddt_fornitore", "fatture_fornitore",
    "costi", "dipendenti", "automezzi",
    "portale_sessions", "portale_lookup_failed",
    "audit_log", "email_events",
]

COUNTER_KEYS = ["ddt", "fattura", "ordinativi", "offerta", "ddt_fornitore", "fattura_fornitore"]


def _serialize_doc(d: dict) -> dict:
    """Convert datetime/ObjectId to ISO strings for JSON dump."""
    import datetime as _dt
    out = {}
    for k, v in d.items():
        if isinstance(v, _dt.datetime):
            out[k] = v.isoformat()
        elif isinstance(v, list):
            out[k] = [_serialize_doc(x) if isinstance(x, dict) else x for x in v]
        elif isinstance(v, dict):
            out[k] = _serialize_doc(v)
        else:
            out[k] = v
    return out


@router.get("/company/export-operativo")
async def export_operativo(user: Dict = Depends(require_roles("admin"))):
    """Esporta un dump JSON completo dei dati operativi del proprio tenant.

    Include anche company, branding, articoli, listini, termini_templates per ripristino totale.
    Il file è un download attachment.
    """
    import json
    from datetime import datetime as _dt, timezone as _tz
    from fastapi.responses import Response as _Response

    tid = tenant_id_of(user)
    company_doc = await db.company.find_one({"tenant_id": tid}, {"_id": 0})

    dump = {
        "exported_at": _dt.now(_tz.utc).isoformat(),
        "tenant_id": tid,
        "version": "1.0",
        "collections": {},
    }

    # Dati operativi
    for c in OPERATIONAL_COLLECTIONS:
        docs = await db[c].find({"tenant_id": tid}, {"_id": 0}).to_list(100000)
        dump["collections"][c] = [_serialize_doc(d) for d in docs]

    # Catalog & config (utili per ripristino totale)
    for c in ["articoli", "listini", "listini_prezzi", "termini_templates", "branding"]:
        docs = await db[c].find({"tenant_id": tid}, {"_id": 0}).to_list(100000)
        dump["collections"][c] = [_serialize_doc(d) for d in docs]

    dump["company"] = _serialize_doc(company_doc) if company_doc else None

    await log_audit(user, "EXPORT", "tenant_backup", tid,
                    {"total": sum(len(v) for v in dump["collections"].values())})

    payload = json.dumps(dump, indent=2, ensure_ascii=False).encode("utf-8")
    azienda = (company_doc or {}).get("nome") or "tenant"
    ts = _dt.now(_tz.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"backup-{azienda.replace(' ', '_')}-{ts}.json"
    return _Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ============== RESET OPERATIVO ==============


class ResetOperativoIn(BaseModel):
    confirm: str  # deve essere "RESET" per procedere
    reset_counters: bool = True


@router.post("/company/reset-operativo")
async def reset_operativo(body: ResetOperativoIn, user: Dict = Depends(require_roles("admin"))):
    """Cancella tutti i dati operativi del proprio tenant (richiede confirm='RESET').

    NON tocca: articoli, listini, listini_prezzi, termini_templates, users, tenants,
    company, branding, app_settings, payment_transactions, files.

    I counters di numerazione sono globali; se reset_counters=True vengono azzerati
    (utile se sei l'unico tenant del DB).
    """
    if body.confirm != "RESET":
        raise HTTPException(400, "Confirm string non valida — atteso 'RESET'")

    tid = tenant_id_of(user)
    deleted: Dict[str, int] = {}
    total = 0
    for c in OPERATIONAL_COLLECTIONS:
        res = await db[c].delete_many({"tenant_id": tid})
        deleted[c] = int(res.deleted_count)
        total += int(res.deleted_count)

    counters_reset = 0
    if body.reset_counters:
        for key in COUNTER_KEYS:
            res = await db.counters.delete_one({"_id": key})
            if res.deleted_count:
                counters_reset += 1

    # Log dopo aver pulito (l'audit_log appena svuotato riceve subito un nuovo record)
    await log_audit(user, "WIPE", "tenant_data", tid,
                    {"deleted": deleted, "counters_reset": counters_reset, "total": total})

    return {
        "ok": True,
        "tenant_id": tid,
        "total_deleted": total,
        "per_collection": deleted,
        "counters_reset": counters_reset,
        "message": f"{total} record cancellati dal tuo tenant. Catalogo, anagrafica azienda e utenti sono stati preservati.",
    }
