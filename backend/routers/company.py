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
    telefono: Optional[str] = ""
    sito_web: Optional[str] = ""


REQUIRED_FIELDS = ["nome", "ragione_sociale", "partita_iva", "indirizzo", "email", "telefono"]


def _public_view(doc: Optional[dict]) -> dict:
    if not doc:
        return {**{k: "" for k in CompanyIn.model_fields.keys()}, "logo_url": None, "setup_complete": False}
    setup_complete = all((doc.get(k) or "").strip() for k in REQUIRED_FIELDS)
    out = {
        **{k: doc.get(k, "") for k in CompanyIn.model_fields.keys()},
        "logo_url": "/api/company/logo" if doc.get("logo_path") else None,
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
    """Return the tenant company logo (tenant-scoped, auth required)."""
    doc = await db.company.find_one(tenant_scope(user), {"_id": 0})
    path = (doc or {}).get("logo_path")
    if not path:
        raise HTTPException(404, "Logo non configurato")
    data, ctype = get_object(path)
    return Response(content=data, media_type=ctype or "image/webp", headers={"Cache-Control": "private, max-age=300"})


async def load_company_for_tenant(tenant_id: str) -> dict:
    """Helper for PDF generation."""
    doc = await db.company.find_one({"tenant_id": tenant_id}, {"_id": 0})
    return doc or {}
