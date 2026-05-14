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
from smtp_service import send_email
from backup_service import (
    create_snapshot as _create_snapshot,
    list_snapshots as _list_snapshots,
    restore_snapshot as _restore_snapshot,
    delete_snapshot as _delete_snapshot,
    apply_retention as _apply_retention,
    run_daily_snapshots as _run_daily_snapshots,
    RETENTION_KEEP,
)

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
    regime_fiscale: Optional[str] = "RF01"   # FatturaPA RegimeFiscale (RF01..RF19)
    iva_default_pct: Optional[float] = 22.0  # Aliquota IVA di default per nuove fatture


REQUIRED_FIELDS = ["nome", "ragione_sociale", "partita_iva", "indirizzo", "email", "telefono"]


def _field_default(name: str):
    """Return the Pydantic-declared default for a CompanyIn field (or empty string)."""
    f = CompanyIn.model_fields.get(name)
    if f is None:
        return ""
    d = f.default
    return "" if d is None else d


def _public_view(doc: Optional[dict]) -> dict:
    if not doc:
        return {**{k: _field_default(k) for k in CompanyIn.model_fields.keys()},
                "logo_url": None, "setup_complete": False}
    setup_complete = all((str(doc.get(k) or "")).strip() for k in REQUIRED_FIELDS)
    tid = doc.get("tenant_id") or ""
    out = {
        **{k: (doc[k] if doc.get(k) not in (None, "") else _field_default(k))
           for k in CompanyIn.model_fields.keys()},
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
    payload = {
        k: (v.strip() if isinstance(v, str) else v)
        for k, v in body.model_dump(exclude_unset=False).items()
    }
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


class RestoreOperativoIn(BaseModel):
    confirm: str                # deve essere "RESTORE"
    mode: str = "merge"         # "merge" (upsert per id) | "replace" (wipe + import)
    data: dict                  # contenuto del file JSON di backup


@router.post("/company/restore-operativo")
async def restore_operativo(body: RestoreOperativoIn, user: Dict = Depends(require_roles("admin"))):
    """Ripristina un backup JSON precedentemente esportato.

    mode:
      - "merge"  → upsert per id (mantiene i record esistenti non in backup)
      - "replace"→ cancella tutto poi reinserisce SOLO i record del backup

    Safety: confirm='RESTORE' obbligatorio; tutti i record vengono forzati al tenant_id corrente.
    """
    if body.confirm != "RESTORE":
        raise HTTPException(400, "Confirm string non valida — atteso 'RESTORE'")
    if body.mode not in ("merge", "replace"):
        raise HTTPException(400, "mode deve essere 'merge' o 'replace'")

    tid = tenant_id_of(user)
    collections = body.data.get("collections") or {}
    if not isinstance(collections, dict):
        raise HTTPException(400, "Formato backup non valido — 'collections' mancante o invalido")

    # Validazione: il backup deve essere dello stesso tenant (oppure superadmin can override)
    backup_tid = body.data.get("tenant_id")
    if backup_tid and backup_tid != tid:
        raise HTTPException(400, f"Backup tenant_id mismatch (backup: {backup_tid}, attuale: {tid})")

    summary: Dict[str, Dict[str, int]] = {}

    # Determine which collections to import (operative + catalog se presenti)
    ALL_RESTORABLE = OPERATIONAL_COLLECTIONS + ["articoli", "listini", "listini_prezzi", "termini_templates", "branding"]

    for cname, docs in collections.items():
        if cname not in ALL_RESTORABLE:
            continue
        if not isinstance(docs, list):
            continue

        if body.mode == "replace":
            del_res = await db[cname].delete_many({"tenant_id": tid})
            wiped = int(del_res.deleted_count)
        else:
            wiped = 0

        inserted = 0
        updated = 0
        for doc in docs:
            if not isinstance(doc, dict) or "id" not in doc:
                continue
            # Forza il tenant_id corrente (mai fidarsi del backup)
            doc["tenant_id"] = tid
            doc.pop("_id", None)
            res = await db[cname].update_one(
                {"id": doc["id"], "tenant_id": tid},
                {"$set": doc},
                upsert=True,
            )
            if res.upserted_id:
                inserted += 1
            elif res.modified_count:
                updated += 1
        summary[cname] = {"inserted": inserted, "updated": updated, "wiped": wiped}

    # Ripristina anche company se presente nel backup
    if isinstance(body.data.get("company"), dict):
        c = dict(body.data["company"])
        c["tenant_id"] = tid
        c.pop("_id", None)
        await db.company.update_one({"tenant_id": tid}, {"$set": c}, upsert=True)
        summary["company"] = {"inserted": 0, "updated": 1, "wiped": 0}

    total_in = sum(v["inserted"] for v in summary.values())
    total_up = sum(v["updated"] for v in summary.values())
    total_wiped = sum(v["wiped"] for v in summary.values())

    await log_audit(user, "RESTORE", "tenant_data", tid,
                    {"mode": body.mode, "total_inserted": total_in, "total_updated": total_up, "total_wiped": total_wiped})

    return {
        "ok": True,
        "mode": body.mode,
        "tenant_id": tid,
        "total_inserted": total_in,
        "total_updated": total_up,
        "total_wiped": total_wiped,
        "per_collection": summary,
        "message": f"Ripristinati {total_in + total_up} record ({total_in} nuovi, {total_up} aggiornati). Wipe pre-restore: {total_wiped} record.",
    }


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


# ============== CLOUD BACKUPS (Emergent Object Storage) ==============


class CloudRestoreIn(BaseModel):
    confirm: str             # must be "RESTORE"
    mode: str = "merge"      # "merge" | "replace"


@router.post("/company/backup/cloud")
async def create_cloud_backup(user: Dict = Depends(require_roles("admin"))):
    """Crea ora uno snapshot del tenant e lo carica su Emergent Object Storage."""
    tid = tenant_id_of(user)
    try:
        meta = await _create_snapshot(tid, source="manual", created_by_email=user.get("email"))
        pruned = await _apply_retention(tid, RETENTION_KEEP)
    except Exception as e:
        raise HTTPException(500, f"Errore creazione snapshot: {e}")
    await log_audit(user, "CREATE", "cloud_backup", meta["id"],
                    {"size_bytes": meta["size_bytes"], "total_records": meta["total_records"], "pruned": pruned})
    return {"ok": True, "snapshot": meta, "pruned": pruned, "retention": RETENTION_KEEP}


@router.get("/company/backup/cloud/list")
async def list_cloud_backups(user: Dict = Depends(require_roles("admin"))):
    """Elenca gli snapshot cloud disponibili per il proprio tenant (più recenti prima)."""
    tid = tenant_id_of(user)
    snapshots = await _list_snapshots(tid)
    return {"snapshots": snapshots, "retention_days": RETENTION_KEEP}


@router.post("/company/backup/cloud/{snapshot_id}/restore")
async def restore_cloud_backup(snapshot_id: str, body: CloudRestoreIn,
                               user: Dict = Depends(require_roles("admin"))):
    """Ripristina i dati del tenant da uno snapshot cloud."""
    if body.confirm != "RESTORE":
        raise HTTPException(400, "Confirm string non valida — atteso 'RESTORE'")
    if body.mode not in ("merge", "replace"):
        raise HTTPException(400, "mode deve essere 'merge' o 'replace'")
    tid = tenant_id_of(user)
    try:
        summary = await _restore_snapshot(tid, snapshot_id, mode=body.mode)
    except FileNotFoundError:
        raise HTTPException(404, "Snapshot non trovato")
    except Exception as e:
        raise HTTPException(500, f"Errore ripristino snapshot: {e}")
    await log_audit(user, "RESTORE", "cloud_backup", snapshot_id,
                    {"mode": body.mode, "total_inserted": summary["total_inserted"],
                     "total_updated": summary["total_updated"], "total_wiped": summary["total_wiped"]})
    return {
        "ok": True,
        **summary,
        "message": (f"Ripristinati {summary['total_inserted'] + summary['total_updated']} record "
                    f"({summary['total_inserted']} nuovi, {summary['total_updated']} aggiornati). "
                    f"Wipe pre-restore: {summary['total_wiped']} record."),
    }


@router.delete("/company/backup/cloud/{snapshot_id}")
async def delete_cloud_backup(snapshot_id: str, user: Dict = Depends(require_roles("admin"))):
    """Elimina uno snapshot cloud (solo metadata; l'oggetto fisico viene scartato per retention)."""
    tid = tenant_id_of(user)
    ok = await _delete_snapshot(tid, snapshot_id)
    if not ok:
        raise HTTPException(404, "Snapshot non trovato")
    await log_audit(user, "DELETE", "cloud_backup", snapshot_id, {})
    return {"ok": True}


@router.post("/company/backup/cloud/run-now")
async def run_scheduler_now(user: Dict = Depends(require_roles("superadmin"))):
    """Trigger manuale del run quotidiano per TUTTI i tenant (riservato a superadmin)."""
    result = await _run_daily_snapshots()
    return result


# ============== NOTIFICATION SETTINGS (backup alerts via email) ==============


class NotificationSettingsIn(BaseModel):
    recipients: list[str] = []   # additional emails to alert on failures
    include_admin: bool = True   # also include current tenant admin emails


def _validate_email(e: str) -> str:
    e = (e or "").strip().lower()
    if not e or "@" not in e or "." not in e.split("@", 1)[1]:
        raise HTTPException(400, f"Email non valida: {e!r}")
    return e


@router.get("/company/notifications")
async def get_notification_settings(user: Dict = Depends(require_roles("admin"))):
    """Restituisce la configurazione notifiche email del tenant (lista destinatari + flag admin)."""
    doc = await db.company.find_one(tenant_scope(user), {"_id": 0}) or {}
    n = doc.get("notifications") or {}
    return {
        "recipients": list(n.get("recipients") or []),
        "include_admin": bool(n.get("include_admin", True)),
    }


@router.put("/company/notifications")
async def update_notification_settings(body: NotificationSettingsIn,
                                       user: Dict = Depends(require_roles("admin"))):
    """Aggiorna la lista dei destinatari email per le notifiche di sistema (backup falliti, ecc.)."""
    seen = set()
    cleaned: list[str] = []
    for raw in (body.recipients or []):
        e = _validate_email(raw)
        if e in seen:
            continue
        seen.add(e)
        cleaned.append(e)
    if len(cleaned) > 20:
        raise HTTPException(400, "Massimo 20 destinatari")
    n = {"recipients": cleaned, "include_admin": bool(body.include_admin)}
    await db.company.update_one(
        tenant_scope(user),
        {"$set": {"notifications": n, "tenant_id": tenant_id_of(user), "updated_at": now_utc()},
         "$setOnInsert": {"created_at": now_utc()}},
        upsert=True,
    )
    await log_audit(user, "UPDATE", "company_notifications", tenant_id_of(user),
                    {"count": len(cleaned), "include_admin": n["include_admin"]})
    return n


@router.post("/company/notifications/test")
async def test_notification(user: Dict = Depends(require_roles("admin"))):
    """Invia un'email di test ai destinatari configurati (e admin se attivo)."""
    from backup_service import resolve_alert_recipients
    tid = tenant_id_of(user)
    recipients = await resolve_alert_recipients(tid)
    if not recipients:
        raise HTTPException(400, "Nessun destinatario configurato")
    company = await db.company.find_one({"tenant_id": tid}, {"_id": 0}) or {}
    azienda = company.get("nome") or company.get("ragione_sociale") or "Il tuo tenant"
    sent = []
    for r in recipients:
        ev = await send_email(
            to=r,
            subject=f"[CleanTec] Test notifica · {azienda}",
            body_text=(f"Ciao,\n\nquesto è un test del sistema di notifiche di CleanTec per il tenant "
                       f"\"{azienda}\".\n\nSe ricevi questa email, le notifiche di sistema (es. backup "
                       f"falliti) ti raggiungeranno correttamente.\n\n— CleanTec"),
            tenant_id=tid,
            context={"type": "notification_test"},
        )
        sent.append({"to": r, "status": ev.get("status")})
    await log_audit(user, "TEST", "company_notifications", tid, {"count": len(sent)})
    return {"ok": True, "sent": sent}


# ============== NUMERAZIONE DOCUMENTI ==============

NUMERAZIONE_KINDS = [
    {"key": "fattura",            "prefix": "FT",        "label": "Fatture clienti"},
    {"key": "ddt",                "prefix": "DDT",       "label": "DDT clienti"},
    {"key": "offerta",            "prefix": "OF",        "label": "Offerte / Preventivi"},
    {"key": "contratto",          "prefix": "CT",        "label": "Contratti"},
    {"key": "ordinativo",         "prefix": "ORD",       "label": "Ordinativi"},
    {"key": "ddt_fornitore",      "prefix": "FORN-DDT",  "label": "DDT fornitori"},
    {"key": "fattura_fornitore",  "prefix": "FORN-FT",   "label": "Fatture fornitori"},
]


class NumerazioneEntry(BaseModel):
    key: str
    seq: int = Field(ge=0)
    suffix: Optional[str] = ""


class NumerazioneIn(BaseModel):
    entries: list[NumerazioneEntry]


@router.get("/company/numerazione")
async def get_numerazione(user: Dict = Depends(require_roles("admin"))):
    """Restituisce per ogni kind: seq attuale, suffix configurato, prefisso e label umano."""
    cfg_doc = await db.app_settings.find_one({"_id": "numerazione"}) or {}
    out = []
    for k in NUMERAZIONE_KINDS:
        counter = await db.counters.find_one({"_id": k["key"]}) or {}
        cfg = (cfg_doc.get(k["key"]) or {}) if isinstance(cfg_doc.get(k["key"]), dict) else {}
        out.append({
            "key": k["key"],
            "prefix": k["prefix"],
            "label": k["label"],
            "current_seq": int(counter.get("seq", 0)),
            "suffix": (cfg.get("suffix") or ""),
        })
    return {"entries": out}


@router.put("/company/numerazione")
async def update_numerazione(body: NumerazioneIn, user: Dict = Depends(require_roles("admin"))):
    """Aggiorna seq + suffix per i kind specificati.

    Regola di sicurezza: il nuovo seq deve essere >= seq corrente (no riduzioni → eviterebbe duplicati).
    Per `seq=N`, la prossima emissione sarà numero N+1.
    """
    valid_keys = {k["key"] for k in NUMERAZIONE_KINDS}
    errors: list[str] = []
    updates: dict[str, dict] = {}
    for e in body.entries:
        if e.key not in valid_keys:
            errors.append(f"Kind '{e.key}' non riconosciuto")
            continue
        current = await db.counters.find_one({"_id": e.key}) or {}
        current_seq = int(current.get("seq", 0))
        if e.seq < current_seq:
            errors.append(f"{e.key}: nuovo seq ({e.seq}) inferiore al corrente ({current_seq}). "
                          f"Per evitare duplicati il numero di partenza non può essere abbassato.")
            continue
        updates[e.key] = {"seq": e.seq, "suffix": (e.suffix or "").strip()}

    if errors:
        raise HTTPException(400, "; ".join(errors))

    # Apply updates atomically
    for kind, vals in updates.items():
        await db.counters.update_one(
            {"_id": kind}, {"$set": {"seq": vals["seq"]}}, upsert=True,
        )

    # Persist suffix in app_settings._id=numerazione
    suffix_set = {f"{kind}.suffix": vals["suffix"] for kind, vals in updates.items()}
    if suffix_set:
        await db.app_settings.update_one(
            {"_id": "numerazione"},
            {"$set": suffix_set},
            upsert=True,
        )

    await log_audit(user, "UPDATE", "numerazione", tenant_id_of(user),
                    {"updated": list(updates.keys())})
    # Return refreshed state
    return await get_numerazione(user)  # type: ignore[arg-type]
