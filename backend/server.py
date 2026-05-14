"""CleanTec FastAPI entry point."""
import logging
import os
from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware

from core import client
from routers import auth, users, catalog, billing, dashboard, files, tenants, subscriptions, superadmin, listini, ddt, branding, company, offerte, ordinativi, fornitori, costi, reports, hr, alerts, imports
from seed import run_all as run_seed
from storage import init_storage
from backup_service import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("cleantec")

app = FastAPI(title="CleanTec API", version="1.1.0")

api = APIRouter(prefix="/api")
api.include_router(auth.router)
api.include_router(users.router)
api.include_router(catalog.router)
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
