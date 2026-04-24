"""Seed demo data + MongoDB indexes + counter sync + legacy-string to datetime migration."""
import random
import logging
from datetime import datetime, timedelta
from core import (
    db, new_id, now_utc, hash_password, verify_password, to_dt,
    STATI_LOTTO, ADMIN_EMAIL, ADMIN_PASSWORD, DEMO_TENANT_ID,
)

logger = logging.getLogger("cleantec.seed")


# =====================================================================
# Multi-tenant migration: create DEMO tenant and backfill tenant_id
# =====================================================================
# Collections that MUST carry tenant_id for data isolation
TENANT_SCOPED_COLLECTIONS = [
    "users", "clienti", "articoli", "macchine",
    "ritiri", "lotti", "lavorazioni", "consegne",
    "non_conformita", "fatture", "magazzino", "magazzino_movimenti",
    "tickets", "interventi", "audit_log", "files",
    "notifications", "hardware_events",
]


async def ensure_demo_tenant():
    """Create the DEMO tenant + superadmin user if missing. Idempotent."""
    existing = await db.tenants.find_one({"id": DEMO_TENANT_ID})
    if not existing:
        now = now_utc()
        await db.tenants.insert_one({
            "id": DEMO_TENANT_ID,
            "slug": "demo",
            "nome": "CleanTec Demo",
            "partita_iva": "",
            "email_admin": ADMIN_EMAIL.lower(),
            "piano": "enterprise",  # demo has full features unlocked
            "stato": "active",
            "trial_ends_at": None,
            "current_period_end": now + timedelta(days=3650),
            "stripe_customer_id": None,
            "stripe_subscription_id": None,
            "limits": {"users": -1, "lotti_monthly": -1, "sms_monthly": 500},
            "usage": {"users": 0, "lotti_this_month": 0, "sms_this_month": 0, "last_reset": now},
            "is_demo": True,
            "created_at": now,
            "updated_at": now,
        })
        logger.info(f"[SEED] DEMO tenant creato: {DEMO_TENANT_ID}")

    # Seed superadmin user — global SaaS operator
    super_email = "super@cleantec.it"
    if not await db.users.find_one({"email": super_email}):
        await db.users.insert_one({
            "id": new_id(),
            "email": super_email,
            "password_hash": hash_password("Superadmin123!"),
            "name": "Super Admin",
            "role": "superadmin",
            "tenant_id": DEMO_TENANT_ID,  # belongs to DEMO for cross-references
            "attivo": True,
            "email_verified": True,
            "created_at": now_utc(),
        })
        logger.info(f"[SEED] superadmin creato: {super_email}")


async def backfill_tenant_id():
    """Assign tenant_id=DEMO to every legacy document missing it. Idempotent."""
    total = 0
    for coll_name in TENANT_SCOPED_COLLECTIONS:
        coll = db[coll_name]
        res = await coll.update_many(
            {"tenant_id": {"$exists": False}},
            {"$set": {"tenant_id": DEMO_TENANT_ID}},
        )
        if res.modified_count:
            total += res.modified_count
            logger.info(f"[SEED] backfilled tenant_id → {coll_name}: {res.modified_count}")
    if total:
        logger.info(f"[SEED] backfill totale tenant_id: {total} documenti")


# =====================================================================
# Indexes
# =====================================================================
async def ensure_indexes():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.users.create_index("created_at")
    await db.clienti.create_index("id", unique=True)
    await db.clienti.create_index("created_at")
    await db.articoli.create_index("id", unique=True)
    await db.articoli.create_index("barcode")
    await db.macchine.create_index("id", unique=True)
    await db.lotti.create_index("id", unique=True)
    await db.lotti.create_index("stato_corrente")
    await db.lotti.create_index("cliente_id")
    await db.lotti.create_index("created_at")
    await db.ritiri.create_index("id", unique=True)
    await db.ritiri.create_index("data_ritiro")
    await db.consegne.create_index("id", unique=True)
    await db.consegne.create_index("data_prevista")
    await db.consegne.create_index("data_consegna_effettiva")
    await db.consegne.create_index("stato")
    await db.fatture.create_index("id", unique=True)
    await db.fatture.create_index("cliente_id")
    await db.fatture.create_index("data")
    await db.lavorazioni.create_index("id", unique=True)
    await db.lavorazioni.create_index("created_at")
    await db.non_conformita.create_index("id", unique=True)
    await db.non_conformita.create_index("created_at")
    await db.audit_log.create_index("timestamp")
    await db.magazzino.create_index("id", unique=True)
    await db.magazzino.create_index("categoria")
    await db.magazzino.create_index("codice")
    await db.magazzino_movimenti.create_index("articolo_id")
    await db.magazzino_movimenti.create_index("timestamp")
    await db.tickets.create_index("id", unique=True)
    await db.tickets.create_index("macchina_id")
    await db.tickets.create_index("stato")
    await db.tickets.create_index("created_at")
    await db.interventi.create_index("ticket_id")
    await db.interventi.create_index("data_intervento")
    # Multi-tenant indexes
    await db.tenants.create_index("id", unique=True)
    await db.tenants.create_index("slug", unique=True)
    await db.tenants.create_index("email_admin")
    await db.payment_transactions.create_index("session_id", unique=True)
    await db.payment_transactions.create_index("tenant_id")
    await db.payment_transactions.create_index("created_at")
    # Compound indexes for hot query paths (tenant + existing key)
    for coll_name in ["lotti", "ritiri", "consegne", "fatture", "tickets", "clienti", "articoli", "macchine", "magazzino", "non_conformita", "lavorazioni", "notifications", "hardware_events", "audit_log", "users"]:
        try:
            await db[coll_name].create_index([("tenant_id", 1), ("created_at", -1)])
        except Exception:
            pass


# =====================================================================
# Counters
# =====================================================================
async def ensure_counters():
    """Align counters with existing collection counts so new inserts never reuse a numero."""
    mapping = {
        "ritiro": db.ritiri,
        "lotto": db.lotti,
        "consegna": db.consegne,
        "fattura": db.fatture,
        "ticket": db.tickets,
        "ddt": db.ddt,
    }
    for name, coll in mapping.items():
        existing = await db.counters.find_one({"_id": name})
        if existing is None:
            count = await coll.count_documents({})
            await db.counters.insert_one({"_id": name, "seq": count})


# =====================================================================
# Legacy date-string → BSON datetime migration
# =====================================================================
_DATETIME_FIELDS = {
    "users": ["created_at"],
    "clienti": ["created_at", "updated_at"],
    "articoli": ["created_at", "updated_at"],
    "macchine": ["created_at", "updated_at", "manutenzione_prossima"],
    "ritiri": ["created_at", "data_ritiro"],
    "lotti": ["created_at"],
    "consegne": ["created_at", "updated_at", "data_prevista", "data_consegna_effettiva"],
    "fatture": ["created_at", "updated_at", "data", "scadenza"],
    "lavorazioni": ["created_at", "updated_at", "inizio", "fine"],
    "non_conformita": ["created_at", "updated_at"],
    "audit_log": ["timestamp"],
}


async def migrate_dates():
    """One-shot: convert string date/datetime fields into native BSON datetime."""
    total = 0
    for coll_name, fields in _DATETIME_FIELDS.items():
        coll = db[coll_name]
        for field in fields:
            cursor = coll.find({field: {"$type": "string"}}, {"_id": 1, field: 1})
            async for doc in cursor:
                dt = to_dt(doc.get(field))
                if dt is not None:
                    await coll.update_one({"_id": doc["_id"]}, {"$set": {field: dt}})
                    total += 1
                else:
                    # Unparseable → drop it to avoid $type mismatch in range queries
                    await coll.update_one({"_id": doc["_id"]}, {"$unset": {field: ""}})

    # Nested: lotti.storico_stati[].timestamp
    async for lotto in db.lotti.find({"storico_stati.timestamp": {"$type": "string"}}):
        storico = lotto.get("storico_stati", [])
        changed = False
        for entry in storico:
            ts = entry.get("timestamp")
            if isinstance(ts, str):
                dt = to_dt(ts)
                if dt is not None:
                    entry["timestamp"] = dt
                    changed = True
        if changed:
            await db.lotti.update_one({"_id": lotto["_id"]}, {"$set": {"storico_stati": storico}})
            total += 1
    if total:
        logger.info(f"[MIGRATE] Convertiti {total} campi stringa → BSON datetime")


# =====================================================================
# Demo seed
# =====================================================================
async def seed_admin_and_users():
    admin = await db.users.find_one({"email": ADMIN_EMAIL.lower()})
    if admin is None:
        await db.users.insert_one({
            "id": new_id(),
            "email": ADMIN_EMAIL.lower(),
            "password_hash": hash_password(ADMIN_PASSWORD),
            "name": "Amministratore",
            "role": "admin",
            "attivo": True,
            "created_at": now_utc(),
        })
        logger.info(f"[SEED] Admin creato: {ADMIN_EMAIL}")
    elif not verify_password(ADMIN_PASSWORD, admin["password_hash"]):
        await db.users.update_one(
            {"email": ADMIN_EMAIL.lower()},
            {"$set": {"password_hash": hash_password(ADMIN_PASSWORD)}},
        )

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
                "created_at": now_utc(),
            })


async def seed_portale_cliente_user():
    """Seed a demo portale-cliente account linked to the first seeded cliente."""
    email = "cliente@cleantec.it"
    existing = await db.users.find_one({"email": email})
    primary = await db.clienti.find_one({"ragione_sociale": "Hotel Excelsior Roma"}, {"_id": 0})
    if not primary:
        # Fallback to first cliente
        primary = await db.clienti.find_one({}, {"_id": 0})
    if not primary:
        return
    if existing is None:
        await db.users.insert_one({
            "id": new_id(),
            "email": email,
            "password_hash": hash_password("cliente123"),
            "name": f"Portale {primary['ragione_sociale']}",
            "role": "cliente",
            "cliente_id": primary["id"],
            "attivo": True,
            "created_at": now_utc(),
        })
        logger.info(f"[SEED] Portale cliente creato: {email} → {primary['ragione_sociale']}")
    elif not existing.get("cliente_id"):
        # Backfill: ensure link
        await db.users.update_one(
            {"email": email},
            {"$set": {"cliente_id": primary["id"], "role": "cliente"}},
        )


async def seed_catalog_and_lotti():
    if await db.clienti.count_documents({}) == 0:
        clienti_demo = [
            {"ragione_sociale": "Hotel Excelsior Roma", "partita_iva": "IT01234567890", "indirizzo": "Via Veneto 125, Roma", "email": "info@excelsior-roma.it", "telefono": "+39 06 47081", "tipologia": "hotel", "giorni_ritiro": [1, 3, 5], "sla_ore": 48},
            {"ragione_sociale": "Ospedale San Raffaele", "partita_iva": "IT09876543210", "indirizzo": "Via Olgettina 60, Milano", "email": "logistica@sanraffaele.it", "telefono": "+39 02 26431", "tipologia": "ospedale", "giorni_ritiro": [0, 1, 2, 3, 4, 5], "sla_ore": 24},
            {"ragione_sociale": "Ristorante Villa Reale", "partita_iva": "IT11223344556", "indirizzo": "Corso Buenos Aires 12, Milano", "email": "info@villarealemi.it", "telefono": "+39 02 2940111", "tipologia": "ristorante", "giorni_ritiro": [1, 4], "sla_ore": 72},
            {"ragione_sociale": "Grand Hotel Rimini", "partita_iva": "IT55667788990", "indirizzo": "P.le Indipendenza 2, Rimini", "email": "reception@grandhotelrimini.com", "telefono": "+39 0541 56000", "tipologia": "hotel", "giorni_ritiro": [1, 3, 5], "sla_ore": 48},
            {"ragione_sociale": "Clinica Mater Dei", "partita_iva": "IT99887766554", "indirizzo": "Via Bertoloni 34, Roma", "email": "reception@materdei.it", "telefono": "+39 06 809051", "tipologia": "ospedale", "giorni_ritiro": [0, 2, 4], "sla_ore": 24},
        ]
        for c in clienti_demo:
            c.update({"id": new_id(), "listino": "standard", "condizioni_pagamento": "30gg",
                      "attivo": True, "created_at": now_utc(), "note": ""})
        await db.clienti.insert_many(clienti_demo)

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
            a.update({"id": new_id(), "created_at": now_utc()})
        await db.articoli.insert_many(articoli_demo)

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
            m.update({"id": new_id(), "created_at": now_utc(),
                      "manutenzione_prossima": now_utc() + timedelta(days=30)})
        await db.macchine.insert_many(macchine_demo)

    if await db.lotti.count_documents({}) == 0:
        pass  # Lotti sono stati rimossi dal modulo. Non creare più demo lotti.


async def seed_listini_and_ddt():
    """Seed demo listini + prezzi + DDT non fatturati per dimostrare il flusso."""
    if await db.listini.count_documents({"tenant_id": {"$exists": True}}) > 0:
        return
    from core import DEMO_TENANT_ID
    clienti = await db.clienti.find({"tenant_id": DEMO_TENANT_ID}, {"_id": 0}).to_list(100)
    articoli = await db.articoli.find({"tenant_id": DEMO_TENANT_ID}, {"_id": 0}).to_list(100)
    if not clienti or not articoli:
        return

    # 2 listini: Standard e VIP (prezzi +20%)
    listino_std = {
        "id": new_id(), "tenant_id": DEMO_TENANT_ID,
        "nome": "Standard", "descrizione": "Listino standard", "attivo": True,
        "created_at": now_utc(), "updated_at": now_utc(),
    }
    listino_vip = {
        "id": new_id(), "tenant_id": DEMO_TENANT_ID,
        "nome": "VIP Hotel 5 stelle", "descrizione": "Listino agevolato clienti top", "attivo": True,
        "created_at": now_utc(), "updated_at": now_utc(),
    }
    await db.listini.insert_many([listino_std, listino_vip])

    prezzi_std = []
    prezzi_vip = []
    for a in articoli:
        base = float(a.get("prezzo", 1) or 1)
        prezzi_std.append({
            "tenant_id": DEMO_TENANT_ID, "listino_id": listino_std["id"],
            "articolo_id": a["id"], "prezzo": round(base, 2), "updated_at": now_utc(),
        })
        prezzi_vip.append({
            "tenant_id": DEMO_TENANT_ID, "listino_id": listino_vip["id"],
            "articolo_id": a["id"], "prezzo": round(base * 0.9, 2), "updated_at": now_utc(),
        })
    if prezzi_std:
        await db.listini_prezzi.insert_many(prezzi_std + prezzi_vip)

    # Assign listino ai clienti: prime 2 → VIP, altri → Standard
    for idx, cli in enumerate(clienti):
        lid = listino_vip["id"] if idx < 2 else listino_std["id"]
        await db.clienti.update_one({"id": cli["id"]}, {"$set": {"listino_id": lid}})

    # Seed 6 DDT demo (non_fatturati) sui primi 2 clienti
    import random as _r
    _r.seed(11)
    for i, cli in enumerate(clienti[:3]):
        fresh_cli = await db.clienti.find_one({"id": cli["id"]}, {"_id": 0})
        listino_id = fresh_cli.get("listino_id")
        for k in range(2):
            rows = []
            imp = 0.0
            for a in _r.sample(articoli, min(3, len(articoli))):
                q = _r.randint(5, 80)
                p_doc = await db.listini_prezzi.find_one({
                    "tenant_id": DEMO_TENANT_ID, "listino_id": listino_id, "articolo_id": a["id"],
                })
                prezzo = float((p_doc or {}).get("prezzo", a.get("prezzo", 1)))
                tot = round(prezzo * q, 2)
                rows.append({
                    "articolo_id": a["id"], "codice": a.get("codice", ""),
                    "descrizione": a.get("descrizione", ""), "unita_misura": a.get("unita_misura", "pz"),
                    "quantita": q, "prezzo_unitario": prezzo, "totale": tot,
                })
                imp += tot
            seq = await __import__("core", fromlist=["next_seq"]).next_seq("ddt")
            await db.ddt.insert_one({
                "id": new_id(), "tenant_id": DEMO_TENANT_ID,
                "numero": f"DDT-{datetime.now().year}-{seq:05d}",
                "cliente_id": cli["id"], "cliente_nome": cli.get("ragione_sociale", ""),
                "listino_id": listino_id,
                "data": now_utc() - timedelta(days=_r.randint(1, 20)),
                "note": "",
                "righe": rows, "imponibile": round(imp, 2),
                "stato_fatturazione": "non_fatturato",
                "fattura_id": None, "fattura_numero": None,
                "created_at": now_utc(), "updated_at": now_utc(),
            })
    logger.info("[SEED] Listini + DDT demo creati")


async def seed_magazzino():
    if await db.magazzino.count_documents({}) > 0:
        return
    now = now_utc()
    items = [
        {"codice": "DET-UNI-25", "descrizione": "Detergente Universale 25L", "categoria": "detergente", "unita_misura": "L", "scorta_attuale": 140.0, "scorta_minima": 50.0, "prezzo_unitario": 4.2, "fornitore": "Ecolab", "scadenza": now + timedelta(days=320)},
        {"codice": "DET-SAN-10", "descrizione": "Detergente Sanitario 10L", "categoria": "detergente", "unita_misura": "L", "scorta_attuale": 18.0, "scorta_minima": 20.0, "prezzo_unitario": 8.5, "fornitore": "Diversey", "scadenza": now + timedelta(days=180)},
        {"codice": "SBI-CLO-5", "descrizione": "Sbiancante al cloro 5L", "categoria": "chimico", "unita_misura": "L", "scorta_attuale": 62.0, "scorta_minima": 25.0, "prezzo_unitario": 3.1, "fornitore": "Ecolab", "scadenza": now + timedelta(days=25)},
        {"codice": "AMM-SOF-20", "descrizione": "Ammorbidente Soft 20L", "categoria": "detergente", "unita_misura": "L", "scorta_attuale": 0.0, "scorta_minima": 10.0, "prezzo_unitario": 5.8, "fornitore": "Ecolab", "scadenza": now + timedelta(days=210)},
        {"codice": "DPI-GUA-M", "descrizione": "Guanti protettivi Taglia M", "categoria": "dpi", "unita_misura": "conf", "scorta_attuale": 24.0, "scorta_minima": 10.0, "prezzo_unitario": 12.0, "fornitore": "3M", "scadenza": None},
        {"codice": "DPI-MSK-FFP2", "descrizione": "Mascherine FFP2 (conf. 20 pz)", "categoria": "dpi", "unita_misura": "conf", "scorta_attuale": 8.0, "scorta_minima": 15.0, "prezzo_unitario": 18.5, "fornitore": "3M", "scadenza": now + timedelta(days=500)},
        {"codice": "DPI-GRE-L", "descrizione": "Grembiule impermeabile L", "categoria": "dpi", "unita_misura": "pz", "scorta_attuale": 35.0, "scorta_minima": 15.0, "prezzo_unitario": 8.0, "fornitore": "Safety Srl", "scadenza": None},
        {"codice": "CON-SAC-80L", "descrizione": "Sacchi biancheria 80L (500 pz)", "categoria": "consumabile", "unita_misura": "conf", "scorta_attuale": 6.0, "scorta_minima": 3.0, "prezzo_unitario": 22.0, "fornitore": "Packaging Plus", "scadenza": None},
    ]
    for it in items:
        it.update({"id": new_id(), "attivo": True, "note": "", "created_at": now, "updated_at": now})
    await db.magazzino.insert_many(items)
    logger.info(f"[SEED] Magazzino: {len(items)} articoli")


async def seed_tickets():
    if await db.tickets.count_documents({}) > 0:
        return
    macchine = await db.macchine.find({}, {"_id": 0}).to_list(50)
    if not macchine:
        return
    now = now_utc()
    by_codice = {m["codice"]: m for m in macchine}
    demo = [
        {"mac": "ASC-02", "tipo": "guasto", "priorita": "critica", "stato": "in_lavorazione", "titolo": "Guasto resistenza riscaldamento",
         "descrizione": "La macchina non raggiunge la temperatura di 80°C. Ciclo interrotto a metà.", "fermo": True, "age_h": 12,
         "interventi": [{"operatore": "Franco Tecnici Srl", "descrizione": "Diagnosi iniziale: resistenza bruciata, richiesto ricambio.", "durata_min": 45, "pezzi_usati": [], "costo": 120.0}]},
        {"mac": "LAV-01", "tipo": "preventiva", "priorita": "media", "stato": "chiuso", "titolo": "Sostituzione cuscinetti annuali",
         "descrizione": "Manutenzione programmata annuale come da piano fornitore.", "fermo": False, "age_h": 240,
         "interventi": [
             {"operatore": "Matteo Rossi", "descrizione": "Smontaggio cestello, ispezione.", "durata_min": 90, "pezzi_usati": ["Cuscinetti X2"], "costo": 180.0},
             {"operatore": "Matteo Rossi", "descrizione": "Montaggio nuovi cuscinetti + test 30'.", "durata_min": 120, "pezzi_usati": [], "costo": 0.0},
         ]},
        {"mac": "STI-01", "tipo": "guasto", "priorita": "alta", "stato": "aperto", "titolo": "Rumore anomalo rullo principale",
         "descrizione": "Al terzo ciclo della giornata il rullo emette un rumore metallico intermittente.", "fermo": False, "age_h": 3,
         "interventi": []},
        {"mac": "LAV-02", "tipo": "revisione", "priorita": "bassa", "stato": "risolto", "titolo": "Revisione semestrale pompe",
         "descrizione": "Controllo e pulizia pompe di scarico + sostituzione filtri.", "fermo": False, "age_h": 96,
         "interventi": [{"operatore": "Giorgio Impiantisti", "descrizione": "Pulizia pompe e sostituzione filtri std.", "durata_min": 75, "pezzi_usati": ["Filtro STD-02"], "costo": 45.0}]},
    ]
    for idx, d in enumerate(demo, start=1):
        mac = by_codice.get(d["mac"])
        if not mac:
            continue
        created = now - timedelta(hours=d["age_h"])
        tid = new_id()
        costo_tot = sum(i["costo"] for i in d["interventi"])
        durata_tot = sum(i["durata_min"] for i in d["interventi"])
        t_doc = {
            "id": tid,
            "numero": f"TKT-{datetime.now().year}-{idx:05d}",
            "macchina_id": mac["id"],
            "macchina_codice": mac["codice"],
            "tipo": d["tipo"],
            "priorita": d["priorita"],
            "stato": d["stato"],
            "titolo": d["titolo"],
            "descrizione": d["descrizione"],
            "segnalato_da": "Sistema Demo",
            "assegnato_a": d["interventi"][0]["operatore"] if d["interventi"] else "",
            "fermo_macchina": d["fermo"],
            "interventi_count": len(d["interventi"]),
            "durata_totale_min": durata_tot,
            "costo_totale": round(costo_tot, 2),
            "created_at": created,
            "updated_at": created,
        }
        if d["stato"] in ("risolto", "chiuso"):
            t_doc["chiuso_at"] = created + timedelta(hours=max(2, d["age_h"] // 4))
        await db.tickets.insert_one(t_doc)
        for j, iv in enumerate(d["interventi"]):
            await db.interventi.insert_one({
                "id": new_id(),
                "ticket_id": tid,
                "macchina_id": mac["id"],
                "data_intervento": created + timedelta(hours=j + 1),
                "operatore": iv["operatore"],
                "descrizione": iv["descrizione"],
                "durata_min": iv["durata_min"],
                "pezzi_usati": iv["pezzi_usati"],
                "costo": iv["costo"],
                "note": "",
                "created_at": created + timedelta(hours=j + 1),
            })
        # Seed-time: allinea stato macchina
        if d["fermo"] and d["stato"] not in ("risolto", "chiuso"):
            await db.macchine.update_one({"id": mac["id"]}, {"$set": {"stato": "guasto"}})
    logger.info(f"[SEED] Tickets: {len(demo)}")


async def run_all():
    await migrate_dates()
    await ensure_demo_tenant()
    await seed_admin_and_users()
    await seed_catalog_and_lotti()
    await seed_portale_cliente_user()
    await seed_magazzino()
    await seed_tickets()
    await seed_listini_and_ddt()
    await backfill_tenant_id()
    await ensure_indexes()
    await ensure_counters()
    logger.info("[SEED] Completato.")
