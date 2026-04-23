"""Seed demo data + MongoDB indexes + counter sync + legacy-string to datetime migration."""
import random
import logging
from datetime import datetime, timedelta
from core import (
    db, new_id, now_utc, hash_password, verify_password, to_dt,
    STATI_LOTTO, ADMIN_EMAIL, ADMIN_PASSWORD,
)

logger = logging.getLogger("cleantec.seed")


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
        clienti = await db.clienti.find({}, {"_id": 0}).to_list(100)
        articoli = await db.articoli.find({}, {"_id": 0}).to_list(100)
        if clienti and articoli:
            random.seed(42)
            stati_sample = list(STATI_LOTTO)
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
                        "timestamp": base_time + timedelta(hours=j * 2),
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
                    "created_at": base_time,
                })


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


async def run_all():
    await migrate_dates()
    await seed_admin_and_users()
    await seed_catalog_and_lotti()
    await seed_portale_cliente_user()
    await seed_magazzino()
    await ensure_indexes()
    await ensure_counters()
    logger.info("[SEED] Completato.")
