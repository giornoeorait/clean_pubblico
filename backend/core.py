"""Shared core utilities: DB, security, helpers, constants."""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import uuid
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from typing import Optional, Any, Dict

from fastapi import HTTPException, Request, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument


# --- DB -------------------------------------------------------------------
mongo_url = os.environ["MONGO_URL"]
db_name = os.environ["DB_NAME"]
client = AsyncIOMotorClient(mongo_url, maxPoolSize=200, minPoolSize=10)
db = client[db_name]


# --- Config ---------------------------------------------------------------
JWT_ALGORITHM = "HS256"
JWT_SECRET = os.environ.get("JWT_SECRET", "cleantec-default-secret-change-me")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@cleantec.it")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


# --- Constants ------------------------------------------------------------
STATI_LOTTO = [
    "ritirato", "ricevuto", "smistato", "lavato",
    "asciugato", "stirato", "confezionato", "pronto", "consegnato",
]


# --- Helpers --------------------------------------------------------------
def new_id() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": now_utc() + timedelta(hours=12),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def clean_doc(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if doc is None:
        return None
    doc.pop("_id", None)
    doc.pop("password_hash", None)
    return doc


async def next_seq(name: str) -> int:
    """Atomic counter for progressive numbering (findOneAndUpdate + $inc, upsert)."""
    doc = await db.counters.find_one_and_update(
        {"_id": name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc["seq"])


async def log_audit(user: Dict[str, Any], azione: str, entita: str,
                    entita_id: str, dettagli: Optional[Dict[str, Any]] = None):
    await db.audit_log.insert_one({
        "id": new_id(),
        "user_id": user.get("id"),
        "user_email": user.get("email"),
        "azione": azione,
        "entita": entita,
        "entita_id": entita_id,
        "dettagli": dettagli or {},
        "timestamp": now_utc().isoformat(),
    })


# --- Auth dependencies ----------------------------------------------------
async def get_current_user(request: Request) -> Dict[str, Any]:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Non autenticato")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Token non valido")
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
        if not user or not user.get("attivo", True):
            raise HTTPException(status_code=401, detail="Utente non trovato o disattivato")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token scaduto")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token non valido")


def require_roles(*allowed: str):
    async def checker(user: Dict[str, Any] = Depends(get_current_user)):
        if user["role"] not in allowed and user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Permessi insufficienti")
        return user
    return checker
