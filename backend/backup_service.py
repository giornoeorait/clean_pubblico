"""Cloud backup service: snapshot creation, restore, retention, and daily scheduler.

A snapshot is a JSON serialization of all operational + catalog collections for a tenant,
uploaded to Emergent Object Storage under `cleantec/backups/{tenant_id}/{snapshot_id}.json`.
Metadata is tracked in MongoDB collection `cloud_backups` so we can list/restore/delete.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from core import db, new_id, now_utc
from storage import put_object, get_object, APP_NAME

logger = logging.getLogger("cleantec.backup")

# Keep operational + catalog/config collections in the backup
OPERATIONAL_COLLECTIONS = [
    "clienti", "ddt", "fatture", "offerte", "ordinativi",
    "fornitori", "ddt_fornitore", "fatture_fornitore",
    "costi", "dipendenti", "automezzi",
    "portale_sessions", "portale_lookup_failed",
    "audit_log", "email_events",
]
CATALOG_COLLECTIONS = ["articoli", "listini", "listini_prezzi", "termini_templates", "branding"]
ALL_RESTORABLE = OPERATIONAL_COLLECTIONS + CATALOG_COLLECTIONS

# Retention policy: keep the last N snapshots per tenant
RETENTION_KEEP = 7

# Daily snapshot window (UTC hour). Scheduler triggers when the hour rolls over to this value.
DAILY_HOUR_UTC = 3


def _serialize_doc(d: dict) -> dict:
    """Convert datetime to ISO strings for JSON dump."""
    out = {}
    for k, v in d.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, list):
            out[k] = [_serialize_doc(x) if isinstance(x, dict) else x for x in v]
        elif isinstance(v, dict):
            out[k] = _serialize_doc(v)
        else:
            out[k] = v
    return out


async def build_tenant_dump(tenant_id: str) -> dict:
    """Build a serializable dict containing all operative/catalog data of a tenant."""
    company_doc = await db.company.find_one({"tenant_id": tenant_id}, {"_id": 0})
    dump = {
        "exported_at": now_utc().isoformat(),
        "tenant_id": tenant_id,
        "version": "1.0",
        "collections": {},
    }
    for c in OPERATIONAL_COLLECTIONS + CATALOG_COLLECTIONS:
        docs = await db[c].find({"tenant_id": tenant_id}, {"_id": 0}).to_list(100000)
        dump["collections"][c] = [_serialize_doc(d) for d in docs]
    dump["company"] = _serialize_doc(company_doc) if company_doc else None
    return dump


async def apply_restore(tenant_id: str, data: dict, mode: str = "merge") -> dict:
    """Restore a backup dump into a tenant. Returns summary."""
    if mode not in ("merge", "replace"):
        raise ValueError("mode must be 'merge' or 'replace'")

    collections = data.get("collections") or {}
    if not isinstance(collections, dict):
        raise ValueError("Invalid backup format — 'collections' missing")

    summary: Dict[str, Dict[str, int]] = {}
    for cname, docs in collections.items():
        if cname not in ALL_RESTORABLE or not isinstance(docs, list):
            continue
        if mode == "replace":
            res = await db[cname].delete_many({"tenant_id": tenant_id})
            wiped = int(res.deleted_count)
        else:
            wiped = 0
        inserted = updated = 0
        for doc in docs:
            if not isinstance(doc, dict) or "id" not in doc:
                continue
            doc["tenant_id"] = tenant_id
            doc.pop("_id", None)
            res = await db[cname].update_one(
                {"id": doc["id"], "tenant_id": tenant_id},
                {"$set": doc},
                upsert=True,
            )
            if res.upserted_id:
                inserted += 1
            elif res.modified_count:
                updated += 1
        summary[cname] = {"inserted": inserted, "updated": updated, "wiped": wiped}

    if isinstance(data.get("company"), dict):
        c = dict(data["company"])
        c["tenant_id"] = tenant_id
        c.pop("_id", None)
        await db.company.update_one({"tenant_id": tenant_id}, {"$set": c}, upsert=True)
        summary["company"] = {"inserted": 0, "updated": 1, "wiped": 0}

    total_in = sum(v["inserted"] for v in summary.values())
    total_up = sum(v["updated"] for v in summary.values())
    total_wiped = sum(v["wiped"] for v in summary.values())
    return {
        "mode": mode,
        "tenant_id": tenant_id,
        "total_inserted": total_in,
        "total_updated": total_up,
        "total_wiped": total_wiped,
        "per_collection": summary,
    }


async def create_snapshot(tenant_id: str, source: str = "manual",
                          created_by_email: Optional[str] = None) -> dict:
    """Create a snapshot in Object Storage and track it in MongoDB.

    Returns the snapshot metadata document (minus _id).
    """
    dump = await build_tenant_dump(tenant_id)
    payload = json.dumps(dump, indent=2, ensure_ascii=False).encode("utf-8")
    total_records = sum(len(v) for v in dump["collections"].values())

    snapshot_id = new_id()
    path = f"{APP_NAME}/backups/{tenant_id}/{snapshot_id}.json"
    put_object(path, payload, "application/json")

    company_doc = await db.company.find_one({"tenant_id": tenant_id}, {"_id": 0})
    azienda_nome = (company_doc or {}).get("nome") or (company_doc or {}).get("ragione_sociale") or ""

    meta = {
        "id": snapshot_id,
        "tenant_id": tenant_id,
        "storage_path": path,
        "size_bytes": len(payload),
        "total_records": total_records,
        "source": source,             # 'auto' | 'manual'
        "created_by": created_by_email or source,
        "azienda_nome": azienda_nome,
        "created_at": now_utc(),
    }
    await db.cloud_backups.insert_one(dict(meta))
    # Mongo mutates inserted dict adding _id — strip before returning
    meta.pop("_id", None)
    meta["created_at"] = meta["created_at"].isoformat()
    return meta


async def list_snapshots(tenant_id: str) -> List[dict]:
    docs = await db.cloud_backups.find(
        {"tenant_id": tenant_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    for d in docs:
        ca = d.get("created_at")
        if isinstance(ca, datetime):
            d["created_at"] = ca.isoformat()
    return docs


async def restore_snapshot(tenant_id: str, snapshot_id: str, mode: str = "merge") -> dict:
    meta = await db.cloud_backups.find_one(
        {"id": snapshot_id, "tenant_id": tenant_id}, {"_id": 0}
    )
    if not meta:
        raise FileNotFoundError("Snapshot non trovato")
    raw, _ctype = get_object(meta["storage_path"])
    data = json.loads(raw.decode("utf-8"))
    # Force tenant_id to current tenant (defense in depth)
    summary = await apply_restore(tenant_id, data, mode=mode)
    summary["snapshot_id"] = snapshot_id
    return summary


async def delete_snapshot(tenant_id: str, snapshot_id: str) -> bool:
    """Delete a snapshot metadata record. The storage object is left as orphan
    (storage API has no delete primitive exposed here); retention will eventually
    overwrite the space via tenant churn.
    """
    res = await db.cloud_backups.delete_one({"id": snapshot_id, "tenant_id": tenant_id})
    return bool(res.deleted_count)


async def apply_retention(tenant_id: str, keep: int = RETENTION_KEEP) -> int:
    """Keep only the most recent `keep` snapshots; delete the rest. Returns count deleted."""
    docs = await db.cloud_backups.find(
        {"tenant_id": tenant_id}, {"_id": 0, "id": 1, "created_at": 1}
    ).sort("created_at", -1).to_list(1000)
    if len(docs) <= keep:
        return 0
    to_delete_ids = [d["id"] for d in docs[keep:]]
    res = await db.cloud_backups.delete_many(
        {"tenant_id": tenant_id, "id": {"$in": to_delete_ids}}
    )
    return int(res.deleted_count)


# ---------------- Scheduler ----------------

_scheduler_task: Optional[asyncio.Task] = None
_last_run_date: Optional[str] = None  # 'YYYY-MM-DD' (UTC) of the last successful run


async def resolve_alert_recipients(tenant_id: str) -> list:
    """Return the deduped list of email recipients for alert notifications of a tenant.

    Sources:
      - company.notifications.recipients (always)
      - if company.notifications.include_admin (default True): all active admin users of the tenant
    """
    company = await db.company.find_one({"tenant_id": tenant_id}, {"_id": 0}) or {}
    n = company.get("notifications") or {}
    recipients = [r for r in (n.get("recipients") or []) if r]
    include_admin = bool(n.get("include_admin", True))
    seen = set(r.strip().lower() for r in recipients if r)
    out = list(recipients)
    if include_admin:
        cursor = db.users.find(
            {"tenant_id": tenant_id, "role": "admin", "attivo": True},
            {"_id": 0, "email": 1},
        )
        async for u in cursor:
            e = (u.get("email") or "").strip().lower()
            if e and e not in seen:
                seen.add(e)
                out.append(e)
    return out


async def _send_failure_alert(tenant_id: str, error: str) -> None:
    """Notify configured recipients that a scheduled backup failed for this tenant."""
    try:
        from smtp_service import send_email  # local import avoids circular
        recipients = await resolve_alert_recipients(tenant_id)
        if not recipients:
            logger.info(f"No alert recipients for tenant {tenant_id} — skipping email")
            return
        company = await db.company.find_one({"tenant_id": tenant_id}, {"_id": 0}) or {}
        azienda = company.get("nome") or company.get("ragione_sociale") or tenant_id
        subject = f"[CleanTec] ⚠️ Backup automatico fallito · {azienda}"
        when = now_utc().strftime("%d/%m/%Y %H:%M UTC")
        text = (
            f"Attenzione,\n\nil backup automatico programmato di CleanTec per il tenant \"{azienda}\" "
            f"è fallito il {when}.\n\nDettagli errore:\n{error}\n\n"
            f"Cosa fare:\n"
            f"1. Accedi alla pagina Azienda → sezione 'Snapshot Cloud' e prova a creare uno snapshot manuale.\n"
            f"2. Se l'errore persiste, contatta il supporto.\n\n"
            f"— CleanTec (notifica automatica)"
        )
        for r in recipients:
            try:
                await send_email(
                    to=r, subject=subject, body_text=text,
                    tenant_id=tenant_id, context={"type": "backup_failure", "error": error[:200]},
                )
            except Exception as e:
                logger.error(f"Failed to send alert to {r} for tenant {tenant_id}: {e}")
    except Exception as e:
        logger.error(f"Failed to dispatch failure alert for tenant {tenant_id}: {e}")


async def run_daily_snapshots() -> dict:
    """Iterate every tenant and create one snapshot. Apply retention. Returns summary."""
    tenants = await db.tenants.find({}, {"_id": 0, "id": 1, "stato": 1}).to_list(10000)
    created = 0
    pruned = 0
    failed = []
    for t in tenants:
        tid = t.get("id")
        if not tid:
            continue
        # Skip suspended/cancelled tenants
        if t.get("stato") in ("suspended", "canceled"):
            continue
        try:
            await create_snapshot(tid, source="auto", created_by_email="scheduler")
            created += 1
            pruned += await apply_retention(tid, RETENTION_KEEP)
        except Exception as e:
            logger.error(f"Snapshot failed for tenant {tid}: {e}")
            failed.append({"tenant_id": tid, "error": str(e)})
            await _send_failure_alert(tid, str(e))
    logger.info(f"Daily snapshots: {created} created, {pruned} pruned, {len(failed)} failed")
    return {"created": created, "pruned": pruned, "failed": failed, "at": now_utc().isoformat()}


async def _scheduler_loop():
    """Background loop: every 60s checks if it's time for the daily snapshot."""
    global _last_run_date
    logger.info(f"Backup scheduler started (target hour: {DAILY_HOUR_UTC:02d}:00 UTC)")
    # On startup, set _last_run_date so we don't fire immediately on restart
    today_utc = now_utc().strftime("%Y-%m-%d")
    if now_utc().hour < DAILY_HOUR_UTC:
        # The 03:00 hour today hasn't happened yet, leave _last_run_date unset
        _last_run_date = None
    else:
        # Hour has passed today; consider today already done
        _last_run_date = today_utc

    while True:
        try:
            now = now_utc()
            today = now.strftime("%Y-%m-%d")
            if now.hour == DAILY_HOUR_UTC and _last_run_date != today:
                logger.info("Triggering daily snapshot run")
                try:
                    await run_daily_snapshots()
                    _last_run_date = today
                except Exception as e:
                    logger.error(f"Daily snapshot run failed: {e}")
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            logger.info("Backup scheduler cancelled")
            break
        except Exception as e:
            logger.error(f"Scheduler loop error: {e}")
            await asyncio.sleep(60)


def start_scheduler():
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        return
    _scheduler_task = asyncio.create_task(_scheduler_loop())


def stop_scheduler():
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
