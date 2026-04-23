from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import uuid
import logging
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Any, Dict

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, Query
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr


# =====================================================================
# CONFIG
# =====================================================================
mongo_url = os.environ['MONGO_URL']
db_name = os.environ['DB_NAME']
client = AsyncIOMotorClient(mongo_url, maxPoolSize=200, minPoolSize=10)
db = client[db_name]

JWT_ALGORITHM = "HS256"
JWT_SECRET = os.environ.get("JWT_SECRET", "cleantec-default-secret-change-me")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@cleantec.it")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

app = FastAPI(title="CleanTec API", version="1.0.0")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("cleantec")


# =====================================================================
# UTILITIES
# =====================================================================
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


async def log_audit(user: Dict[str, Any], azione: str, entita: str, entita_id: str, dettagli: Optional[Dict[str, Any]] = None):
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


# =====================================================================
# AUTH / RBAC
# =====================================================================
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


# =====================================================================
# MODELS (Pydantic for validation)
# =====================================================================
class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str = "produzione"
    cliente_id: Optional[str] = None


class ClienteIn(BaseModel):
    ragione_sociale: str
    partita_iva: Optional[str] = ""
    codice_fiscale: Optional[str] = ""
    indirizzo: Optional[str] = ""
    email: Optional[str] = ""
    telefono: Optional[str] = ""
    tipologia: str = "hotel"  # hotel, ristorante, ospedale, industria, altro
    listino: str = "standard"
    condizioni_pagamento: str = "30gg"
    giorni_ritiro: List[int] = Field(default_factory=list)  # 0=Lun..6=Dom
    sla_ore: int = 48
    note: Optional[str] = ""
    attivo: bool = True


class ArticoloIn(BaseModel):
    codice: str
    descrizione: str
    categoria: str = "biancheria"
    tipo: str = "capo"  # capo, lotto_peso, kit
    materiale: Optional[str] = ""
    lavaggio: str = "standard"
    temperatura: int = 60
    barcode: Optional[str] = ""
    peso_medio: float = 0.5
    prezzo: float = 0.0
    prezzo_tipo: str = "capo"  # capo, kg, canone


class MacchinaIn(BaseModel):
    codice: str
    tipo: str  # lavatrice, asciugatrice, stiratrice
    capacita_kg: float
    stato: str = "disponibile"
    reparto: str = "lavaggio"
    ore_lavoro: float = 0
    manutenzione_prossima: Optional[str] = None


class RitiroIn(BaseModel):
    cliente_id: str
    data_ritiro: str
    operatore: str
    peso_totale: float = 0
    quantita_totale: int = 0
    anomalie: Optional[str] = ""
    firma_url: Optional[str] = ""
    foto_urls: List[str] = Field(default_factory=list)
    note: Optional[str] = ""


class LottoIn(BaseModel):
    ritiro_id: str
    cliente_id: str
    articolo_id: str
    quantita: int = 1
    peso: float = 0
    priorita: str = "normale"  # normale, alta, urgente


class CambiaStatoIn(BaseModel):
    nuovo_stato: str
    macchina_id: Optional[str] = None
    note: Optional[str] = ""
    esito: str = "ok"


class LavorazioneIn(BaseModel):
    lotto_id: str
    tipo: str  # lavaggio, asciugatura, stiratura
    macchina_id: Optional[str] = None
    programma: Optional[str] = ""
    temperatura: Optional[int] = 40
    detergenti: Optional[str] = ""
    tempo_min: Optional[int] = 60


class ConsegnaIn(BaseModel):
    cliente_id: str
    lotti_ids: List[str] = Field(default_factory=list)
    data_prevista: str
    autista: Optional[str] = ""
    note: Optional[str] = ""


class NonConformitaIn(BaseModel):
    lotto_id: Optional[str] = None
    tipo_difetto: str
    gravita: str = "media"  # bassa, media, alta, critica
    foto_urls: List[str] = Field(default_factory=list)
    responsabile: Optional[str] = ""
    azione_correttiva: Optional[str] = ""


class FatturaIn(BaseModel):
    cliente_id: str
    data: str
    righe: List[Dict[str, Any]] = Field(default_factory=list)
    iva_pct: float = 22
    scadenza: Optional[str] = None


# =====================================================================
# STATI LOTTO (traceability)
# =====================================================================
STATI_LOTTO = [
    "ritirato", "ricevuto", "smistato", "lavato",
    "asciugato", "stirato", "confezionato", "pronto", "consegnato"
]


# =====================================================================
# AUTH ROUTES
# =====================================================================
@api.post("/auth/login")
async def login(body: LoginIn, response: Response):
    email = body.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    if not user.get("attivo", True):
        raise HTTPException(status_code=403, detail="Utente disattivato")
    token = create_access_token(user["id"], user["email"], user["role"])
    response.set_cookie(
        key="access_token", value=token, httponly=True, secure=False,
        samesite="lax", max_age=43200, path="/"
    )
    clean_doc(user)
    return {"user": user, "token": token}


@api.post("/auth/logout")
async def logout(response: Response, user: Dict = Depends(get_current_user)):
    response.delete_cookie(key="access_token", path="/")
    return {"ok": True}


@api.get("/auth/me")
async def auth_me(user: Dict = Depends(get_current_user)):
    return user


# =====================================================================
# USERS (admin)
# =====================================================================
@api.get("/users")
async def list_users(user: Dict = Depends(require_roles("admin"))):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(5000)
    return users


@api.post("/users")
async def create_user(body: UserCreate, user: Dict = Depends(require_roles("admin"))):
    existing = await db.users.find_one({"email": body.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email già registrata")
    doc = {
        "id": new_id(),
        "email": body.email.lower(),
        "password_hash": hash_password(body.password),
        "name": body.name,
        "role": body.role,
        "cliente_id": body.cliente_id,
        "attivo": True,
        "created_at": now_utc().isoformat(),
    }
    await db.users.insert_one(doc)
    await log_audit(user, "CREATE", "user", doc["id"], {"email": doc["email"]})
    doc.pop("password_hash", None)
    doc.pop("_id", None)
    return doc


@api.patch("/users/{uid}")
async def update_user(uid: str, body: Dict[str, Any], user: Dict = Depends(require_roles("admin"))):
    body.pop("_id", None)
    if "password" in body and body["password"]:
        body["password_hash"] = hash_password(body.pop("password"))
    else:
        body.pop("password", None)
    await db.users.update_one({"id": uid}, {"$set": body})
    await log_audit(user, "UPDATE", "user", uid, body)
    return {"ok": True}


@api.delete("/users/{uid}")
async def delete_user(uid: str, user: Dict = Depends(require_roles("admin"))):
    await db.users.update_one({"id": uid}, {"$set": {"attivo": False}})
    await log_audit(user, "DEACTIVATE", "user", uid)
    return {"ok": True}


# =====================================================================
# GENERIC CRUD FACTORY
# =====================================================================
def crud_endpoints(path: str, collection_name: str, model, entity_label: str, allowed_write_roles=("admin",)):
    coll = db[collection_name]

    @api.get(f"/{path}")
    async def list_all(user: Dict = Depends(get_current_user), q: Optional[str] = None, limit: int = 500):
        query = {}
        if q:
            query = {"$or": [
                {"descrizione": {"$regex": q, "$options": "i"}},
                {"codice": {"$regex": q, "$options": "i"}},
                {"ragione_sociale": {"$regex": q, "$options": "i"}},
            ]}
        items = await coll.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
        return items

    @api.post(f"/{path}")
    async def create_one(body: model, user: Dict = Depends(require_roles(*allowed_write_roles))):
        doc = body.model_dump()
        doc["id"] = new_id()
        doc["created_at"] = now_utc().isoformat()
        doc["updated_at"] = doc["created_at"]
        await coll.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(user, "CREATE", entity_label, doc["id"])
        return doc

    @api.get(f"/{path}/{{item_id}}")
    async def get_one(item_id: str, user: Dict = Depends(get_current_user)):
        doc = await coll.find_one({"id": item_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail=f"{entity_label} non trovato")
        return doc

    @api.patch(f"/{path}/{{item_id}}")
    async def update_one(item_id: str, body: Dict[str, Any], user: Dict = Depends(require_roles(*allowed_write_roles))):
        body.pop("_id", None)
        body.pop("id", None)
        body["updated_at"] = now_utc().isoformat()
        res = await coll.update_one({"id": item_id}, {"$set": body})
        if res.matched_count == 0:
            raise HTTPException(status_code=404, detail=f"{entity_label} non trovato")
        await log_audit(user, "UPDATE", entity_label, item_id, body)
        return {"ok": True}

    @api.delete(f"/{path}/{{item_id}}")
    async def delete_one(item_id: str, user: Dict = Depends(require_roles(*allowed_write_roles))):
        await coll.delete_one({"id": item_id})
        await log_audit(user, "DELETE", entity_label, item_id)
        return {"ok": True}


crud_endpoints("clienti", "clienti", ClienteIn, "cliente", allowed_write_roles=("admin", "contabilita"))
crud_endpoints("articoli", "articoli", ArticoloIn, "articolo", allowed_write_roles=("admin", "contabilita"))
crud_endpoints("macchine", "macchine", MacchinaIn, "macchina", allowed_write_roles=("admin", "produzione"))


# =====================================================================
# RITIRI / ACCETTAZIONE MERCE
# =====================================================================
@api.get("/ritiri")
async def list_ritiri(user: Dict = Depends(get_current_user), limit: int = 200):
    items = await db.ritiri.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return items


@api.post("/ritiri")
async def create_ritiro(body: RitiroIn, user: Dict = Depends(require_roles("admin", "logistica", "produzione"))):
    doc = body.model_dump()
    doc["id"] = new_id()
    num = await db.ritiri.count_documents({})
    doc["numero"] = f"RIT-{datetime.now().year}-{num + 1:05d}"
    doc["stato"] = "creato"
    doc["created_at"] = now_utc().isoformat()
    await db.ritiri.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "ritiro", doc["id"])
    return doc


@api.get("/ritiri/{rid}")
async def get_ritiro(rid: str, user: Dict = Depends(get_current_user)):
    doc = await db.ritiri.find_one({"id": rid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Ritiro non trovato")
    doc["lotti"] = await db.lotti.find({"ritiro_id": rid}, {"_id": 0}).to_list(1000)
    return doc


# =====================================================================
# LOTTI E TRACCIABILITÀ
# =====================================================================
@api.get("/lotti")
async def list_lotti(
    user: Dict = Depends(get_current_user),
    stato: Optional[str] = None,
    cliente_id: Optional[str] = None,
    limit: int = 500,
):
    query: Dict[str, Any] = {}
    if stato:
        query["stato_corrente"] = stato
    if cliente_id:
        query["cliente_id"] = cliente_id
    items = await db.lotti.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return items


@api.post("/lotti")
async def create_lotto(body: LottoIn, user: Dict = Depends(require_roles("admin", "produzione", "logistica"))):
    doc = body.model_dump()
    doc["id"] = new_id()
    num = await db.lotti.count_documents({})
    doc["numero"] = f"LOT-{datetime.now().year}-{num + 1:06d}"
    doc["stato_corrente"] = "ritirato"
    doc["storico_stati"] = [{
        "stato": "ritirato",
        "timestamp": now_utc().isoformat(),
        "operatore": user["name"],
        "note": "Creato all'accettazione",
        "esito": "ok",
    }]
    doc["created_at"] = now_utc().isoformat()
    await db.lotti.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "lotto", doc["id"])
    return doc


@api.post("/lotti/{lid}/cambia-stato")
async def cambia_stato_lotto(lid: str, body: CambiaStatoIn, user: Dict = Depends(require_roles("admin", "produzione", "qualita", "logistica"))):
    if body.nuovo_stato not in STATI_LOTTO:
        raise HTTPException(400, f"Stato non valido. Ammessi: {STATI_LOTTO}")
    lotto = await db.lotti.find_one({"id": lid})
    if not lotto:
        raise HTTPException(404, "Lotto non trovato")
    entry = {
        "stato": body.nuovo_stato,
        "timestamp": now_utc().isoformat(),
        "operatore": user["name"],
        "macchina_id": body.macchina_id,
        "note": body.note,
        "esito": body.esito,
    }
    await db.lotti.update_one(
        {"id": lid},
        {"$set": {"stato_corrente": body.nuovo_stato}, "$push": {"storico_stati": entry}},
    )
    await log_audit(user, "STATE_CHANGE", "lotto", lid, entry)
    return {"ok": True, "nuovo_stato": body.nuovo_stato}


@api.get("/lotti/{lid}")
async def get_lotto(lid: str, user: Dict = Depends(get_current_user)):
    doc = await db.lotti.find_one({"id": lid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Lotto non trovato")
    return doc


# =====================================================================
# LAVORAZIONI (MES)
# =====================================================================
@api.get("/lavorazioni")
async def list_lavorazioni(user: Dict = Depends(get_current_user), stato: Optional[str] = None, limit: int = 500):
    query: Dict[str, Any] = {}
    if stato:
        query["stato"] = stato
    items = await db.lavorazioni.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return items


@api.post("/lavorazioni")
async def create_lavorazione(body: LavorazioneIn, user: Dict = Depends(require_roles("admin", "produzione"))):
    doc = body.model_dump()
    doc["id"] = new_id()
    doc["stato"] = "pending"
    doc["operatore_id"] = user["id"]
    doc["operatore_nome"] = user["name"]
    doc["created_at"] = now_utc().isoformat()
    await db.lavorazioni.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "lavorazione", doc["id"])
    return doc


@api.patch("/lavorazioni/{lid}")
async def update_lavorazione(lid: str, body: Dict[str, Any], user: Dict = Depends(require_roles("admin", "produzione"))):
    body.pop("_id", None)
    body["updated_at"] = now_utc().isoformat()
    if body.get("stato") == "in_corso" and "inizio" not in body:
        body["inizio"] = now_utc().isoformat()
    if body.get("stato") == "completato" and "fine" not in body:
        body["fine"] = now_utc().isoformat()
    await db.lavorazioni.update_one({"id": lid}, {"$set": body})
    await log_audit(user, "UPDATE", "lavorazione", lid, body)
    return {"ok": True}


# =====================================================================
# CONSEGNE / LOGISTICA
# =====================================================================
@api.get("/consegne")
async def list_consegne(user: Dict = Depends(get_current_user), limit: int = 200):
    items = await db.consegne.find({}, {"_id": 0}).sort("data_prevista", -1).to_list(limit)
    return items


@api.post("/consegne")
async def create_consegna(body: ConsegnaIn, user: Dict = Depends(require_roles("admin", "logistica"))):
    doc = body.model_dump()
    doc["id"] = new_id()
    num = await db.consegne.count_documents({})
    doc["numero"] = f"CON-{datetime.now().year}-{num + 1:05d}"
    doc["stato"] = "pianificata"
    doc["created_at"] = now_utc().isoformat()
    await db.consegne.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "consegna", doc["id"])
    return doc


@api.patch("/consegne/{cid}")
async def update_consegna(cid: str, body: Dict[str, Any], user: Dict = Depends(require_roles("admin", "logistica"))):
    body.pop("_id", None)
    body["updated_at"] = now_utc().isoformat()
    await db.consegne.update_one({"id": cid}, {"$set": body})
    await log_audit(user, "UPDATE", "consegna", cid, body)
    return {"ok": True}


# =====================================================================
# NON CONFORMITÀ
# =====================================================================
@api.get("/non-conformita")
async def list_nc(user: Dict = Depends(get_current_user), limit: int = 200):
    items = await db.non_conformita.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return items


@api.post("/non-conformita")
async def create_nc(body: NonConformitaIn, user: Dict = Depends(require_roles("admin", "qualita", "produzione"))):
    doc = body.model_dump()
    doc["id"] = new_id()
    doc["stato"] = "aperta"
    doc["segnalato_da"] = user["name"]
    doc["created_at"] = now_utc().isoformat()
    await db.non_conformita.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "non_conformita", doc["id"])
    return doc


@api.patch("/non-conformita/{nid}")
async def update_nc(nid: str, body: Dict[str, Any], user: Dict = Depends(require_roles("admin", "qualita"))):
    body.pop("_id", None)
    body["updated_at"] = now_utc().isoformat()
    await db.non_conformita.update_one({"id": nid}, {"$set": body})
    await log_audit(user, "UPDATE", "non_conformita", nid, body)
    return {"ok": True}


# =====================================================================
# FATTURE
# =====================================================================
@api.get("/fatture")
async def list_fatture(user: Dict = Depends(get_current_user), cliente_id: Optional[str] = None, limit: int = 200):
    query: Dict[str, Any] = {}
    if cliente_id:
        query["cliente_id"] = cliente_id
    if user["role"] == "cliente" and user.get("cliente_id"):
        query["cliente_id"] = user["cliente_id"]
    items = await db.fatture.find(query, {"_id": 0}).sort("data", -1).to_list(limit)
    return items


@api.post("/fatture")
async def create_fattura(body: FatturaIn, user: Dict = Depends(require_roles("admin", "contabilita"))):
    doc = body.model_dump()
    doc["id"] = new_id()
    num = await db.fatture.count_documents({})
    doc["numero"] = f"FT-{datetime.now().year}-{num + 1:05d}"
    imponibile = sum(r.get("totale", r.get("quantita", 0) * r.get("prezzo", 0)) for r in doc["righe"])
    iva = imponibile * doc["iva_pct"] / 100
    doc["imponibile"] = round(imponibile, 2)
    doc["iva"] = round(iva, 2)
    doc["totale"] = round(imponibile + iva, 2)
    doc["stato"] = "bozza"
    doc["created_at"] = now_utc().isoformat()
    await db.fatture.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "CREATE", "fattura", doc["id"])
    return doc


@api.patch("/fatture/{fid}")
async def update_fattura(fid: str, body: Dict[str, Any], user: Dict = Depends(require_roles("admin", "contabilita"))):
    body.pop("_id", None)
    body["updated_at"] = now_utc().isoformat()
    await db.fatture.update_one({"id": fid}, {"$set": body})
    await log_audit(user, "UPDATE", "fattura", fid, body)
    return {"ok": True}


# =====================================================================
# KPI DASHBOARD
# =====================================================================
@api.get("/dashboard/kpi")
async def dashboard_kpi(user: Dict = Depends(get_current_user)):
    today = datetime.now(timezone.utc).date().isoformat()
    first_day_month = datetime.now(timezone.utc).replace(day=1).date().isoformat()

    lotti_totali = await db.lotti.count_documents({})
    lotti_attivi = await db.lotti.count_documents({"stato_corrente": {"$nin": ["consegnato"]}})
    lotti_oggi = await db.lotti.find({"created_at": {"$gte": today}}, {"peso": 1, "_id": 0}).to_list(5000)
    kg_oggi = sum(l.get("peso", 0) for l in lotti_oggi)

    macchine = await db.macchine.find({}, {"_id": 0}).to_list(500)
    macchine_in_uso = sum(1 for m in macchine if m.get("stato") == "in_uso")
    macchine_disp = sum(1 for m in macchine if m.get("stato") == "disponibile")

    nc_aperte = await db.non_conformita.count_documents({"stato": "aperta"})
    consegne_oggi = await db.consegne.count_documents({"data_prevista": today})
    consegne_totali = await db.consegne.count_documents({})
    consegne_puntuali = await db.consegne.count_documents({"stato": "consegnata"})
    puntualita_pct = round((consegne_puntuali / consegne_totali * 100) if consegne_totali else 100, 1)

    fatture_mese = await db.fatture.find({"data": {"$gte": first_day_month}}, {"totale": 1, "_id": 0}).to_list(2000)
    fatturato_mese = sum(f.get("totale", 0) for f in fatture_mese)

    # Trend ultimi 7 giorni (kg per giorno)
    trend = []
    for i in range(6, -1, -1):
        d = (datetime.now(timezone.utc) - timedelta(days=i)).date().isoformat()
        lotti_d = await db.lotti.find({"created_at": {"$regex": f"^{d}"}}, {"peso": 1, "_id": 0}).to_list(5000)
        trend.append({"giorno": d[5:], "kg": round(sum(l.get("peso", 0) for l in lotti_d), 1)})

    # Distribuzione per stato
    stati_dist = []
    for s in STATI_LOTTO:
        c = await db.lotti.count_documents({"stato_corrente": s})
        stati_dist.append({"stato": s, "count": c})

    return {
        "kg_oggi": round(kg_oggi, 1),
        "lotti_totali": lotti_totali,
        "lotti_attivi": lotti_attivi,
        "macchine_in_uso": macchine_in_uso,
        "macchine_disponibili": macchine_disp,
        "macchine_totali": len(macchine),
        "nc_aperte": nc_aperte,
        "consegne_oggi": consegne_oggi,
        "puntualita_pct": puntualita_pct,
        "fatturato_mese": round(fatturato_mese, 2),
        "trend_kg_7gg": trend,
        "stati_distribution": stati_dist,
    }


# =====================================================================
# AUDIT LOG
# =====================================================================
@api.get("/audit-log")
async def get_audit(user: Dict = Depends(require_roles("admin")), limit: int = 500):
    items = await db.audit_log.find({}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    return items


# =====================================================================
# ROOT + HEALTH
# =====================================================================
@api.get("/")
async def root():
    return {"app": "CleanTec", "status": "ok", "version": "1.0.0"}


@api.get("/health")
async def health():
    try:
        await db.command("ping")
        return {"status": "ok", "db": "ok"}
    except Exception as e:
        return {"status": "degraded", "db": str(e)}


# =====================================================================
# SEEDING
# =====================================================================
async def seed_data():
    # Admin
    admin = await db.users.find_one({"email": ADMIN_EMAIL.lower()})
    if admin is None:
        await db.users.insert_one({
            "id": new_id(),
            "email": ADMIN_EMAIL.lower(),
            "password_hash": hash_password(ADMIN_PASSWORD),
            "name": "Amministratore",
            "role": "admin",
            "attivo": True,
            "created_at": now_utc().isoformat(),
        })
        logger.info(f"[SEED] Admin creato: {ADMIN_EMAIL}")
    elif not verify_password(ADMIN_PASSWORD, admin["password_hash"]):
        await db.users.update_one({"email": ADMIN_EMAIL.lower()}, {"$set": {"password_hash": hash_password(ADMIN_PASSWORD)}})
        logger.info("[SEED] Password admin aggiornata")

    # Utenti demo per ruoli
    test_users = [
        ("produzione@cleantec.it", "produzione123", "Mario Rossi (Produzione)", "produzione"),
        ("logistica@cleantec.it", "logistica123", "Luca Bianchi (Logistica)", "logistica"),
        ("qualita@cleantec.it", "qualita123", "Anna Verdi (Qualità)", "qualita"),
        ("contabilita@cleantec.it", "contabilita123", "Paolo Neri (Contabilità)", "contabilita"),
    ]
    for email, pwd, name, role in test_users:
        if not await db.users.find_one({"email": email}):
            await db.users.insert_one({
                "id": new_id(),
                "email": email,
                "password_hash": hash_password(pwd),
                "name": name,
                "role": role,
                "attivo": True,
                "created_at": now_utc().isoformat(),
            })

    # Clienti demo
    if await db.clienti.count_documents({}) == 0:
        clienti_demo = [
            {"ragione_sociale": "Hotel Excelsior Roma", "partita_iva": "IT01234567890", "indirizzo": "Via Veneto 125, Roma", "email": "info@excelsior-roma.it", "telefono": "+39 06 47081", "tipologia": "hotel", "giorni_ritiro": [1, 3, 5], "sla_ore": 48},
            {"ragione_sociale": "Ospedale San Raffaele", "partita_iva": "IT09876543210", "indirizzo": "Via Olgettina 60, Milano", "email": "logistica@sanraffaele.it", "telefono": "+39 02 26431", "tipologia": "ospedale", "giorni_ritiro": [0, 1, 2, 3, 4, 5], "sla_ore": 24},
            {"ragione_sociale": "Ristorante Villa Reale", "partita_iva": "IT11223344556", "indirizzo": "Corso Buenos Aires 12, Milano", "email": "info@villarealemi.it", "telefono": "+39 02 2940111", "tipologia": "ristorante", "giorni_ritiro": [1, 4], "sla_ore": 72},
            {"ragione_sociale": "Grand Hotel Rimini", "partita_iva": "IT55667788990", "indirizzo": "P.le Indipendenza 2, Rimini", "email": "reception@grandhotelrimini.com", "telefono": "+39 0541 56000", "tipologia": "hotel", "giorni_ritiro": [1, 3, 5], "sla_ore": 48},
            {"ragione_sociale": "Clinica Mater Dei", "partita_iva": "IT99887766554", "indirizzo": "Via Bertoloni 34, Roma", "email": "reception@materdei.it", "telefono": "+39 06 809051", "tipologia": "ospedale", "giorni_ritiro": [0, 2, 4], "sla_ore": 24},
        ]
        for c in clienti_demo:
            c["id"] = new_id()
            c["listino"] = "standard"
            c["condizioni_pagamento"] = "30gg"
            c["attivo"] = True
            c["created_at"] = now_utc().isoformat()
            c["note"] = ""
        await db.clienti.insert_many(clienti_demo)

    # Articoli demo
    if await db.articoli.count_documents({}) == 0:
        articoli_demo = [
            {"codice": "LEN-MAT", "descrizione": "Lenzuolo Matrimoniale", "categoria": "biancheria", "tipo": "capo", "materiale": "cotone", "lavaggio": "standard", "temperatura": 60, "barcode": "8001234500001", "peso_medio": 0.9, "prezzo": 1.2, "prezzo_tipo": "capo"},
            {"codice": "LEN-SIN", "descrizione": "Lenzuolo Singolo", "categoria": "biancheria", "tipo": "capo", "materiale": "cotone", "lavaggio": "standard", "temperatura": 60, "barcode": "8001234500002", "peso_medio": 0.6, "prezzo": 0.9, "prezzo_tipo": "capo"},
            {"codice": "ASC-VIS", "descrizione": "Asciugamano Viso", "categoria": "biancheria", "tipo": "capo", "materiale": "spugna", "lavaggio": "spugna", "temperatura": 60, "barcode": "8001234500003", "peso_medio": 0.3, "prezzo": 0.5, "prezzo_tipo": "capo"},
            {"codice": "TOV-RIS", "descrizione": "Tovagliato Ristorante", "categoria": "tovagliato", "tipo": "lotto_peso", "materiale": "lino", "lavaggio": "delicato", "temperatura": 40, "barcode": "", "peso_medio": 0, "prezzo": 2.5, "prezzo_tipo": "kg"},
            {"codice": "DIV-OSP", "descrizione": "Divisa Ospedaliera", "categoria": "divise", "tipo": "capo", "materiale": "poliestere", "lavaggio": "sanitario", "temperatura": 90, "barcode": "8001234500005", "peso_medio": 0.7, "prezzo": 1.8, "prezzo_tipo": "capo"},
            {"codice": "KIT-CAM", "descrizione": "Kit Camera Completo", "categoria": "kit", "tipo": "kit", "materiale": "misto", "lavaggio": "standard", "temperatura": 60, "barcode": "", "peso_medio": 2.5, "prezzo": 4.5, "prezzo_tipo": "capo"},
        ]
        for a in articoli_demo:
            a["id"] = new_id()
            a["created_at"] = now_utc().isoformat()
        await db.articoli.insert_many(articoli_demo)

    # Macchine demo
    if await db.macchine.count_documents({}) == 0:
        macchine_demo = [
            {"codice": "LAV-01", "tipo": "lavatrice", "capacita_kg": 100, "stato": "in_uso", "reparto": "lavaggio", "ore_lavoro": 12450},
            {"codice": "LAV-02", "tipo": "lavatrice", "capacita_kg": 100, "stato": "disponibile", "reparto": "lavaggio", "ore_lavoro": 11200},
            {"codice": "LAV-03", "tipo": "lavatrice", "capacita_kg": 60, "stato": "disponibile", "reparto": "lavaggio", "ore_lavoro": 9800},
            {"codice": "ASC-01", "tipo": "asciugatrice", "capacita_kg": 80, "stato": "in_uso", "reparto": "asciugatura", "ore_lavoro": 10500},
            {"codice": "ASC-02", "tipo": "asciugatrice", "capacita_kg": 80, "stato": "manutenzione", "reparto": "asciugatura", "ore_lavoro": 14200},
            {"codice": "STI-01", "tipo": "stiratrice", "capacita_kg": 0, "stato": "in_uso", "reparto": "stiratura", "ore_lavoro": 8900},
            {"codice": "STI-02", "tipo": "stiratrice", "capacita_kg": 0, "stato": "disponibile", "reparto": "stiratura", "ore_lavoro": 7600},
        ]
        for m in macchine_demo:
            m["id"] = new_id()
            m["created_at"] = now_utc().isoformat()
            m["manutenzione_prossima"] = (now_utc() + timedelta(days=30)).date().isoformat()
        await db.macchine.insert_many(macchine_demo)

    # Lotti demo (con diversi stati per popolare kanban)
    if await db.lotti.count_documents({}) == 0:
        clienti = await db.clienti.find({}, {"_id": 0}).to_list(100)
        articoli = await db.articoli.find({}, {"_id": 0}).to_list(100)
        if clienti and articoli:
            import random
            random.seed(42)
            stati_sample = ["ritirato", "ricevuto", "smistato", "lavato", "asciugato", "stirato", "confezionato", "pronto", "consegnato"]
            for i in range(30):
                cli = random.choice(clienti)
                art = random.choice(articoli)
                stato = random.choice(stati_sample)
                qta = random.randint(10, 200)
                peso = round(qta * (art.get("peso_medio", 0.5) or 0.5), 1)
                lid = new_id()
                storico = []
                idx = STATI_LOTTO.index(stato)
                base_time = now_utc() - timedelta(hours=random.randint(1, 48))
                for j in range(idx + 1):
                    storico.append({
                        "stato": STATI_LOTTO[j],
                        "timestamp": (base_time + timedelta(hours=j * 2)).isoformat(),
                        "operatore": "Sistema Demo",
                        "note": "",
                        "esito": "ok",
                    })
                await db.lotti.insert_one({
                    "id": lid,
                    "numero": f"LOT-{datetime.now().year}-{i + 1:06d}",
                    "ritiro_id": "",
                    "cliente_id": cli["id"],
                    "articolo_id": art["id"],
                    "quantita": qta,
                    "peso": peso,
                    "priorita": random.choice(["normale", "normale", "alta", "urgente"]),
                    "stato_corrente": stato,
                    "storico_stati": storico,
                    "created_at": base_time.isoformat(),
                })

    # Indici MongoDB
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.clienti.create_index("id", unique=True)
    await db.articoli.create_index("id", unique=True)
    await db.articoli.create_index("barcode")
    await db.macchine.create_index("id", unique=True)
    await db.lotti.create_index("id", unique=True)
    await db.lotti.create_index("stato_corrente")
    await db.lotti.create_index("cliente_id")
    await db.ritiri.create_index("id", unique=True)
    await db.consegne.create_index("id", unique=True)
    await db.consegne.create_index("data_prevista")
    await db.fatture.create_index("id", unique=True)
    await db.fatture.create_index("cliente_id")
    await db.lavorazioni.create_index("id", unique=True)
    await db.non_conformita.create_index("id", unique=True)
    await db.audit_log.create_index("timestamp")

    logger.info("[SEED] Seeding completato.")


# =====================================================================
# APP WIRING
# =====================================================================
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
    await seed_data()


@app.on_event("shutdown")
async def on_shutdown():
    client.close()
