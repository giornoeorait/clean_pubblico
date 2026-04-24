"""Global SaaS branding (superadmin-only write, public read).

Singleton document in db.branding with id='global'.
Serves public endpoints for login page + authenticated write endpoints for superadmin.
"""
import io
import logging
from typing import Dict, Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response
from pydantic import BaseModel, Field
from PIL import Image

from core import db, now_utc, require_roles, log_audit
from storage import put_object, get_object, APP_NAME

logger = logging.getLogger("cleantec.branding")
router = APIRouter(tags=["branding"])

SINGLETON_ID = "global"
MAX_UPLOAD = 8 * 1024 * 1024  # 8 MB raw

# kind -> (max_w, max_h, output_fmt, content_type)
KIND_SPECS = {
    "logo":    (512, 512, "WEBP", "image/webp"),
    "hero":    (1920, 1200, "WEBP", "image/webp"),
    "favicon": (96, 96, "PNG", "image/png"),  # PNG kept for browser compat
}

DEFAULTS = {
    "id": SINGLETON_ID,
    "app_name": "CleanTec",
    "tagline": "Industrial Laundry OS",
    "login_eyebrow": "Control Room",
    "login_title": "Il sistema nervoso della tua lavanderia industriale.",
    "login_subtitle": "ERP commerciale completo: clienti, listini multipli, D.D.T. automatici e fatturazione aggregata in un unico ambiente.",
    "login_features": [
        {"icon": "truck", "label": "D.D.T. automatici"},
        {"icon": "factory", "label": "Listini multipli"},
        {"icon": "shield", "label": "Gestione sospesi"},
        {"icon": "chart", "label": "KPI Real-time"},
    ],
    "login_footer": "© 2026 CleanTec Systems — v1.0",
    "logo_path": None,
    "hero_path": None,
    "favicon_path": None,
    "primary_color": "#4F46E5",   # indaco
    "accent_color":  "#38BDF8",   # celeste
    "dark_color":    "#0EA5E9",   # azzurro
    "logo_scale":    1.0,          # dimensioni logo box (sidebar + login)
    "text_scale":    1.0,          # dimensioni nome app + tagline
}


class FeatureIn(BaseModel):
    icon: str = "sparkle"
    label: str


class BrandingPatch(BaseModel):
    app_name: Optional[str] = None
    tagline: Optional[str] = None
    login_eyebrow: Optional[str] = None
    login_title: Optional[str] = None
    login_subtitle: Optional[str] = None
    login_footer: Optional[str] = None
    login_features: Optional[List[FeatureIn]] = None
    primary_color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    accent_color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    dark_color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    logo_scale: Optional[float] = Field(default=None, ge=0.8, le=3.0)
    text_scale: Optional[float] = Field(default=None, ge=0.8, le=2.5)


async def _get_or_init() -> dict:
    doc = await db.branding.find_one({"id": SINGLETON_ID}, {"_id": 0})
    if not doc:
        doc = {**DEFAULTS, "created_at": now_utc(), "updated_at": now_utc()}
        await db.branding.insert_one(dict(doc))
        doc.pop("_id", None)
        return doc
    # One-shot migration: split legacy brand_scale -> logo_scale + text_scale
    if "brand_scale" in doc and ("logo_scale" not in doc or "text_scale" not in doc):
        legacy = float(doc.get("brand_scale") or 1.0)
        await db.branding.update_one(
            {"id": SINGLETON_ID},
            {"$set": {"logo_scale": legacy, "text_scale": legacy, "updated_at": now_utc()},
             "$unset": {"brand_scale": ""}},
        )
        doc = await db.branding.find_one({"id": SINGLETON_ID}, {"_id": 0})
    return doc


def _public_view(doc: dict) -> dict:
    out = {**DEFAULTS, **{k: v for k, v in doc.items() if v is not None}}
    # Expose public image URLs (no auth) via /api/branding/image/<kind>
    out["logo_url"] = "/api/branding/image/logo" if doc.get("logo_path") else None
    out["hero_url"] = "/api/branding/image/hero" if doc.get("hero_path") else None
    out["favicon_url"] = "/api/branding/image/favicon" if doc.get("favicon_path") else None
    # Drop internal storage paths
    for k in ("logo_path", "hero_path", "favicon_path", "_id"):
        out.pop(k, None)
    return out


# ------------------- PUBLIC -------------------
@router.get("/branding")
async def get_branding_public():
    doc = await _get_or_init()
    return _public_view(doc)


@router.get("/branding/image/{kind}")
async def get_branding_image(kind: str):
    if kind not in KIND_SPECS:
        raise HTTPException(404, "Asset non trovato")
    doc = await db.branding.find_one({"id": SINGLETON_ID}, {"_id": 0})
    path = (doc or {}).get(f"{kind}_path") if doc else None
    if not path:
        raise HTTPException(404, "Asset non configurato")
    try:
        data, content_type = get_object(path)
    except Exception as e:
        logger.error(f"Branding image fetch failed: {e}")
        raise HTTPException(500, "Errore lettura asset")
    # Cache 5 min to reduce load while still reflecting updates
    return Response(
        content=data,
        media_type=content_type or KIND_SPECS[kind][2].lower(),
        headers={"Cache-Control": "public, max-age=300"},
    )


# ------------------- SUPERADMIN -------------------
@router.get("/admin/branding")
async def get_branding_admin(user: Dict = Depends(require_roles("superadmin"))):
    doc = await _get_or_init()
    return _public_view(doc)


@router.put("/admin/branding")
async def update_branding(body: BrandingPatch, user: Dict = Depends(require_roles("superadmin"))):
    await _get_or_init()
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if "login_features" in updates:
        updates["login_features"] = [f for f in updates["login_features"] if f.get("label")]
    updates["updated_at"] = now_utc()
    updates["updated_by"] = user.get("id")
    await db.branding.update_one({"id": SINGLETON_ID}, {"$set": updates})
    await log_audit(user, "UPDATE", "branding", SINGLETON_ID, {"fields": list(updates.keys())})
    doc = await db.branding.find_one({"id": SINGLETON_ID}, {"_id": 0})
    return _public_view(doc)


@router.post("/admin/branding/upload/{kind}")
async def upload_branding_image(
    kind: str,
    file: UploadFile = File(...),
    user: Dict = Depends(require_roles("superadmin")),
):
    if kind not in KIND_SPECS:
        raise HTTPException(400, f"Tipo non valido: {kind}")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "File vuoto")
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(400, f"File troppo grande (max {MAX_UPLOAD // 1024 // 1024} MB)")

    max_w, max_h, fmt, ctype = KIND_SPECS[kind]
    try:
        img = Image.open(io.BytesIO(raw))
        # Flatten transparency for WEBP without alpha issues if needed
        if fmt == "WEBP" and img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        elif fmt == "PNG" and img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        # Resize preserving aspect ratio
        img.thumbnail((max_w, max_h), Image.LANCZOS)
        buf = io.BytesIO()
        if fmt == "WEBP":
            img.save(buf, format="WEBP", quality=85, method=6)
        else:
            img.save(buf, format="PNG", optimize=True)
        data = buf.getvalue()
    except Exception as e:
        logger.error(f"Image processing failed: {e}")
        raise HTTPException(400, f"Immagine non valida: {e}")

    ext = "webp" if fmt == "WEBP" else "png"
    path = f"{APP_NAME}/branding/{kind}-{int(now_utc().timestamp())}.{ext}"
    try:
        put_object(path, data, ctype)
    except Exception as e:
        logger.error(f"Branding upload failed: {e}")
        raise HTTPException(500, "Upload fallito")

    await _get_or_init()
    await db.branding.update_one(
        {"id": SINGLETON_ID},
        {"$set": {f"{kind}_path": path, "updated_at": now_utc(), "updated_by": user.get("id")}},
    )
    await log_audit(user, "UPLOAD", "branding", kind, {"path": path, "size": len(data)})
    return {
        "kind": kind,
        "url": f"/api/branding/image/{kind}",
        "size": len(data),
        "width": img.width,
        "height": img.height,
        "format": fmt,
    }


@router.delete("/admin/branding/image/{kind}")
async def delete_branding_image(kind: str, user: Dict = Depends(require_roles("superadmin"))):
    if kind not in KIND_SPECS:
        raise HTTPException(400, "Tipo non valido")
    await db.branding.update_one(
        {"id": SINGLETON_ID},
        {"$unset": {f"{kind}_path": ""}, "$set": {"updated_at": now_utc()}},
    )
    await log_audit(user, "DELETE", "branding", kind)
    return {"ok": True}
