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

# Demo tenant id — used to migrate legacy data
DEMO_TENANT_ID = "demo-tenant-0000-0000-0000-000000000001"


# --- Constants ------------------------------------------------------------
STATI_LOTTO = [
    "ritirato", "ricevuto", "smistato", "lavato",
    "asciugato", "stirato", "confezionato", "pronto", "consegnato",
]

# Plan definitions (authoritative, server-side) — prices are MONTHLY EUR, cents-aware
PLANS = {
    "starter": {
        "id": "starter",
        "nome": "Starter",
        "price_monthly": 59.00,
        "price_annual": 49.00,  # per month billed annually (2 mesi gratis)
        "currency": "eur",
        "limits": {"users": 5, "ddt_monthly": 500, "sms_monthly": 0},
        "features": ["clienti", "articoli", "listini", "ddt", "fatture", "sospesi", "dashboard"],
        "cta": "Parti subito",
    },
    "pro": {
        "id": "pro",
        "nome": "Pro",
        "price_monthly": 179.00,
        "price_annual": 149.00,
        "currency": "eur",
        "limits": {"users": 20, "ddt_monthly": 5000, "sms_monthly": 100},
        "features": ["starter", "listini_multipli", "audit_log", "export_excel"],
        "cta": "Il più popolare",
        "highlight": True,
    },
    "enterprise": {
        "id": "enterprise",
        "nome": "Enterprise",
        "price_monthly": 449.00,
        "price_annual": 379.00,
        "currency": "eur",
        "limits": {"users": -1, "ddt_monthly": -1, "sms_monthly": 500},  # -1 = unlimited
        "features": ["pro", "multi_sede", "sla_24_7", "priority_support"],
        "cta": "Contattaci",
    },
}
TRIAL_DAYS = 14


# --- Helpers --------------------------------------------------------------
def new_id() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def to_dt(value) -> Optional[datetime]:
    """Convert an incoming value (None, str YYYY-MM-DD, ISO datetime, datetime) to a tz-aware UTC datetime.

    Returns None if value is None/empty/unparseable — caller decides whether to keep it.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    # Normalize trailing Z
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            # YYYY-MM-DD → midnight UTC
            return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user_id: str, email: str, role: str, tenant_id: str) -> str:
    # Ruolo "produzione" (totem touch-screen): sessione lunga 90 giorni
    expiry = timedelta(days=90) if role == "produzione" else timedelta(hours=12)
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "tenant_id": tenant_id,
        "exp": now_utc() + expiry,
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


async def get_numero_config() -> Dict[str, Any]:
    """Read the per-document-kind suffix config (singleton in app_settings)."""
    doc = await db.app_settings.find_one({"_id": "numerazione"}) or {}
    doc.pop("_id", None)
    return doc


async def format_numero(kind: str, prefix: str, seq: int) -> str:
    """Build the progressive doc number string with optional suffix from settings.

    Reads the suffix from db.app_settings._id='numerazione'.{kind}.suffix.
    Returns a string like "FT-2026-00046" or "FT-2026-00046/L".
    Caller must obtain `seq` via `await next_seq(kind)`.
    """
    cfg = await get_numero_config()
    suffix = ((cfg.get(kind) or {}).get("suffix") or "").strip()
    year = now_utc().year
    return f"{prefix}-{year}-{seq:05d}{suffix}"


async def log_audit(user: Dict[str, Any], azione: str, entita: str,
                    entita_id: str, dettagli: Optional[Dict[str, Any]] = None):
    await db.audit_log.insert_one({
        "id": new_id(),
        "tenant_id": user.get("tenant_id"),
        "user_id": user.get("id"),
        "user_email": user.get("email"),
        "azione": azione,
        "entita": entita,
        "entita_id": entita_id,
        "dettagli": dettagli or {},
        "timestamp": now_utc(),
    })


# --- Permessi granulari (matrice sezione × view/edit) ---------------------
# Elenco chiavi valide delle sezioni: ogni chiave ha 2 flag (view, edit).
# Se un utente non ha `permissions` impostati, si applica il default per ruolo.
PERMISSION_SECTIONS = [
    "clienti", "articoli", "listini", "offerte", "ordinativi", "ddt",
    "fatture", "sospesi", "fornitori", "fatture_fornitore", "ddt_ricevuti",
    "costi", "dipendenti", "report",
]

_ROLE_DEFAULT_PERMISSIONS: Dict[str, Dict[str, Dict[str, bool]]] = {
    "admin": {s: {"view": True, "edit": True} for s in PERMISSION_SECTIONS},
    "contabilita": {s: {"view": True, "edit": True} for s in PERMISSION_SECTIONS},
    "logistica": {
        # Vede + modifica il flusso operativo (clienti/articoli/DDT/ordinativi/DDT ricevuti)
        "clienti":            {"view": True,  "edit": True},
        "articoli":           {"view": True,  "edit": True},
        "listini":            {"view": True,  "edit": False},
        "offerte":            {"view": True,  "edit": False},
        "ordinativi":         {"view": True,  "edit": True},
        "ddt":                {"view": True,  "edit": True},
        "ddt_ricevuti":       {"view": True,  "edit": True},
        # No accesso a fatture / sospesi / fornitori / costi / dipendenti / report
        "fatture":            {"view": False, "edit": False},
        "sospesi":            {"view": False, "edit": False},
        "fornitori":          {"view": False, "edit": False},
        "fatture_fornitore":  {"view": False, "edit": False},
        "costi":              {"view": False, "edit": False},
        "dipendenti":         {"view": False, "edit": False},
        "report":             {"view": False, "edit": False},
    },
    "produzione": {
        # Totem produzione: solo ordinativi (lavorazione + conversione DDT)
        **{s: {"view": False, "edit": False} for s in PERMISSION_SECTIONS},
        "ordinativi": {"view": True, "edit": True},
        "ddt":        {"view": True, "edit": False},
    },
}


def default_permissions_for_role(role: str) -> Dict[str, Dict[str, bool]]:
    """Restituisce il set di permessi di default per un ruolo (deep copy)."""
    base = _ROLE_DEFAULT_PERMISSIONS.get(role)
    if base:
        return {k: dict(v) for k, v in base.items()}
    # ruolo sconosciuto → tutto disabilitato di default
    return {s: {"view": False, "edit": False} for s in PERMISSION_SECTIONS}


def resolve_permissions(user: Dict[str, Any]) -> Dict[str, Dict[str, bool]]:
    """Combina i default del ruolo con l'eventuale override salvato sull'utente.
    Admin e superadmin ottengono sempre `view=edit=true` su tutto (bypass)."""
    role = (user or {}).get("role") or ""
    if role in ("admin", "superadmin"):
        return {s: {"view": True, "edit": True} for s in PERMISSION_SECTIONS}
    perms = default_permissions_for_role(role)
    override = (user or {}).get("permissions") or {}
    if isinstance(override, dict):
        for section, flags in override.items():
            if section not in perms or not isinstance(flags, dict):
                continue
            for k in ("view", "edit"):
                if k in flags:
                    perms[section][k] = bool(flags[k])
    return perms


def has_permission(user: Dict[str, Any], section: str, action: str = "view") -> bool:
    """Ritorna True se l'utente ha il permesso `action` (view|edit) sulla `section`."""
    if action not in ("view", "edit"):
        return False
    perms = resolve_permissions(user)
    entry = perms.get(section, {})
    return bool(entry.get(action, False))


def require_permission(section: str, action: str = "view"):
    """Dependency FastAPI: rifiuta 403 se l'utente non ha il permesso richiesto."""
    async def checker(user: Dict[str, Any] = Depends(get_current_user)):
        if not has_permission(user, section, action):
            raise HTTPException(
                status_code=403,
                detail=f"Permessi insufficienti per {action} · sezione '{section}'",
            )
        return user
    return checker


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
        # Special-case: superadmin-only endpoints must reject regular admins
        if allowed == ("superadmin",):
            if user["role"] != "superadmin":
                raise HTTPException(status_code=403, detail="Permessi insufficienti")
            return user
        # Admin (tenant admin) e superadmin (cross-tenant) bypassano qualsiasi RBAC
        if user["role"] in ("admin", "superadmin"):
            return user
        if user["role"] not in allowed:
            raise HTTPException(status_code=403, detail="Permessi insufficienti")
        return user
    return checker


# --- Multi-tenant helpers -------------------------------------------------
def tenant_id_of(user: Dict[str, Any]) -> str:
    tid = user.get("tenant_id")
    if not tid:
        # Defense in depth — should never happen after migration
        raise HTTPException(status_code=403, detail="Utente non associato a un tenant")
    return tid


def tenant_scope(user: Dict[str, Any]) -> Dict[str, str]:
    """Return the base filter to enforce tenant isolation on every query."""
    return {"tenant_id": tenant_id_of(user)}


def merge_scope(user: Dict[str, Any], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Merge tenant_id filter with an additional query."""
    q = tenant_scope(user)
    if extra:
        q = {**extra, **q}
    return q


def inject_tenant(doc: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    """Stamp tenant_id on a document being inserted."""
    doc["tenant_id"] = tenant_id_of(user)
    return doc


async def get_tenant(user: Dict[str, Any]) -> Dict[str, Any]:
    """Load the tenant document of the current user (raises if missing)."""
    tenant = await db.tenants.find_one({"id": tenant_id_of(user)}, {"_id": 0})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant non trovato")
    return tenant


async def is_tenant_active(user: Dict[str, Any]) -> bool:
    """Trial attivo o subscription active → True; past_due/canceled/suspended → False."""
    t = await db.tenants.find_one({"id": tenant_id_of(user)}, {"_id": 0})
    if not t:
        return False
    stato = t.get("stato", "trial")
    if stato == "active":
        # Also check current_period_end not elapsed
        pe = t.get("current_period_end")
        if isinstance(pe, datetime):
            pe_aware = pe if pe.tzinfo else pe.replace(tzinfo=timezone.utc)
            if pe_aware > now_utc():
                return True
            return False
        return True
    if stato == "trial":
        ends = t.get("trial_ends_at")
        if isinstance(ends, datetime):
            ends_aware = ends if ends.tzinfo else ends.replace(tzinfo=timezone.utc)
            if ends_aware > now_utc():
                return True
        return False
    return False


async def enforce_quota(user: Dict[str, Any], resource: str) -> None:
    """Raise 402 if tenant exceeds the resource quota for its plan.

    Resources supported:
      - 'users'        → max concurrent active users
      - 'ddt_monthly'  → max DDT created this calendar month
    """
    if user["role"] == "superadmin":
        return
    tenant = await db.tenants.find_one({"id": tenant_id_of(user)}, {"_id": 0})
    if not tenant:
        return  # defensive
    if tenant.get("is_demo"):
        return  # demo tenant always unlimited
    limit = int(tenant.get("limits", {}).get(resource, 0) or 0)
    if limit == -1:
        return  # unlimited
    tid = tenant["id"]
    if resource == "users":
        current = await db.users.count_documents({"tenant_id": tid, "attivo": True})
    elif resource == "ddt_monthly":
        today = now_utc()
        month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        current = await db.ddt.count_documents({"tenant_id": tid, "created_at": {"$gte": month_start}})
    else:
        return
    if current >= limit:
        raise HTTPException(
            status_code=402,
            detail=f"Limite '{resource}' raggiunto ({current}/{limit}) per il piano '{tenant.get('piano')}'. Aggiorna il piano.",
        )


def require_active_tenant():
    """Dependency that enforces the tenant has an active subscription or trial."""
    async def checker(user: Dict[str, Any] = Depends(get_current_user)):
        if user["role"] == "superadmin":
            return user
        ok = await is_tenant_active(user)
        if not ok:
            raise HTTPException(status_code=402, detail="Abbonamento non attivo. Aggiorna il piano.")
        return user
    return checker
