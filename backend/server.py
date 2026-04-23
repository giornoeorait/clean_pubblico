"""CleanTec FastAPI entry point."""
import logging
import os
from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware

from core import client
from routers import auth, users, catalog, operations, billing, dashboard, magazzino, manutenzione
from seed import run_all as run_seed

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("cleantec")

app = FastAPI(title="CleanTec API", version="1.1.0")

api = APIRouter(prefix="/api")
api.include_router(auth.router)
api.include_router(users.router)
api.include_router(catalog.router)
api.include_router(operations.router)
api.include_router(billing.router)
api.include_router(dashboard.router)
api.include_router(magazzino.router)
api.include_router(manutenzione.router)
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
    await run_seed()


@app.on_event("shutdown")
async def on_shutdown():
    client.close()
