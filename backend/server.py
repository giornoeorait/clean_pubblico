"""CleanTec FastAPI entry point."""
import logging
import os
import subprocess
from datetime import datetime, timezone
from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware

from core import client
from routers import auth, users, catalog, billing, dashboard, files, tenants, subscriptions, superadmin, listini, ddt, branding, company, offerte, ordinativi, fornitori, costi, reports, hr, alerts, imports, fatturato_storico, clienti_export
from seed import run_all as run_seed
from storage import init_storage
from backup_service import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("cleantec")

app = FastAPI(title="CleanTec API", version="1.1.0")


def _compute_app_version() -> str:
    """Compute a build/deploy version string. Priority:
    1) Env var APP_VERSION (set at deploy time)
    2) Short git commit hash
    3) Startup timestamp (changes on every restart)
    """
    env_v = os.environ.get("APP_VERSION")
    if env_v:
        return env_v
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd="/app", stderr=subprocess.DEVNULL
        ).decode().strip()
        if out:
            return out
    except Exception:
        pass
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


APP_VERSION = _compute_app_version()
STARTED_AT = datetime.now(timezone.utc).isoformat()

api = APIRouter(prefix="/api")


@api.get("/version")
async def get_version():
    """Public endpoint used by the frontend to detect new deployments."""
    return {"version": APP_VERSION, "started_at": STARTED_AT}


api.include_router(auth.router)
api.include_router(users.router)
api.include_router(catalog.router)
api.include_router(clienti_export.router)
api.include_router(billing.router)
api.include_router(billing.sospesi_router)
api.include_router(listini.router)
api.include_router(ddt.router)
api.include_router(dashboard.router)
api.include_router(files.router)
api.include_router(tenants.router)
api.include_router(subscriptions.router)
api.include_router(superadmin.router)
api.include_router(branding.router)
api.include_router(company.router)
api.include_router(offerte.router)
api.include_router(ordinativi.router)
api.include_router(ordinativi.public_router)
api.include_router(fornitori.router)
api.include_router(costi.router)
api.include_router(reports.router)
api.include_router(hr.router)
api.include_router(alerts.router)
api.include_router(imports.router)
api.include_router(fatturato_storico.router)
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    init_storage()
    await run_seed()
    # TTL indexes: cleanup automatico dei record scaduti
    try:
        from core import db as _db
        await _db.portale_sessions.create_index("expires_at", expireAfterSeconds=0)
        await _db.portale_lookup_failed.create_index("at", expireAfterSeconds=300)  # 5 min cleanup
        await _db.cloud_backups.create_index([("tenant_id", 1), ("created_at", -1)])
    except Exception:
        pass
    # Avvia scheduler backup giornalieri (03:00 UTC)
    start_scheduler()


@app.on_event("shutdown")
async def on_shutdown():
    stop_scheduler()
    client.close()
