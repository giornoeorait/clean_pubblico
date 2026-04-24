"""Seed demo data (commercial flow) + MongoDB indexes + counters."""
import logging
from datetime import datetime, timedelta
from core import (
    db, new_id, now_utc, hash_password, verify_password,
    ADMIN_EMAIL, ADMIN_PASSWORD, DEMO_TENANT_ID,
)

logger = logging.getLogger("cleantec.seed")


TENANT_SCOPED_COLLECTIONS = [
    "users", "clienti", "articoli",
    "listini", "listini_prezzi", "ddt", "fatture",
    "audit_log", "files",
]


async def ensure_demo_tenant():
    existing = await db.tenants.find_one({"id": DEMO_TENANT_ID})
    if not existing:
        now = now_utc()
        await db.tenants.insert_one({
            "id": DEMO_TENANT_ID,
            "slug": "demo",
            "nome": "CleanTec Demo",
            "partita_iva": "",
            "email_admin": ADMIN_EMAIL.lower(),
            "piano": "enterprise",
            "stato": "active",
            "trial_ends_at": None,
            "current_period_end": now + timedelta(days=3650),
            "stripe_customer_id": None,
            "stripe_subscription_id": None,
            "limits": {"users": -1, "ddt_monthly": -1, "sms_monthly": 500},
            "usage": {"users": 0, "ddt_this_month": 0, "sms_this_month": 0, "last_reset": now},
            "is_demo": True,
            "created_at": now,
            "updated_at": now,
        })
        logger.info(f"[SEED] DEMO tenant creato: {DEMO_TENANT_ID}")

    # One-shot migration: rename legacy lotti_* keys -> ddt_* on ALL existing tenants
    migration = await db.tenants.update_many(
        {"$or": [
            {"limits.lotti_monthly": {"$exists": True}},
            {"usage.lotti_this_month": {"$exists": True}},
        ]},
        {"$rename": {
            "limits.lotti_monthly": "limits.ddt_monthly",
            "usage.lotti_this_month": "usage.ddt_this_month",
        }},
    )
    if migration.modified_count:
        logger.info(f"[SEED] migrated lotti_*→ddt_* keys on {migration.modified_count} tenants")

    super_email = "super@cleantec.it"
    if not await db.users.find_one({"email": super_email}):
        await db.users.insert_one({
            "id": new_id(),
            "email": super_email,
            "password_hash": hash_password("Superadmin123!"),
            "name": "Super Admin",
            "role": "superadmin",
            "tenant_id": DEMO_TENANT_ID,
            "attivo": True,
            "email_verified": True,
            "created_at": now_utc(),
        })
        logger.info(f"[SEED] superadmin creato: {super_email}")


async def backfill_tenant_id():
    total = 0
    for coll_name in TENANT_SCOPED_COLLECTIONS:
        res = await db[coll_name].update_many(
            {"tenant_id": {"$exists": False}},
            {"$set": {"tenant_id": DEMO_TENANT_ID}},
        )
        if res.modified_count:
            total += res.modified_count
    if total:
        logger.info(f"[SEED] backfill tenant_id: {total} documenti")


async def ensure_indexes():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.clienti.create_index("id", unique=True)
    await db.clienti.create_index("created_at")
    await db.articoli.create_index("id", unique=True)
    await db.articoli.create_index("barcode")
    await db.listini.create_index("id", unique=True)
    await db.listini_prezzi.create_index([("tenant_id", 1), ("listino_id", 1), ("articolo_id", 1)], unique=True)
    await db.ddt.create_index("id", unique=True)
    await db.ddt.create_index("cliente_id")
    await db.ddt.create_index("data")
    await db.ddt.create_index("stato_fatturazione")
    await db.fatture.create_index("id", unique=True)
    await db.fatture.create_index("cliente_id")
    await db.fatture.create_index("data")
    await db.fatture.create_index("stato_incasso")
    await db.audit_log.create_index("timestamp")
    await db.tenants.create_index("id", unique=True)
    await db.tenants.create_index("slug", unique=True)
    await db.tenants.create_index("email_admin")
    await db.payment_transactions.create_index("session_id", unique=True)
    await db.payment_transactions.create_index("tenant_id")
    await db.payment_transactions.create_index("created_at")
    for coll_name in ["clienti", "articoli", "listini", "ddt", "fatture", "audit_log", "users"]:
        try:
            await db[coll_name].create_index([("tenant_id", 1), ("created_at", -1)])
        except Exception:
            pass


async def ensure_counters():
    mapping = {
        "fattura": db.fatture,
        "ddt": db.ddt,
    }
    for name, coll in mapping.items():
        existing = await db.counters.find_one({"_id": name})
        if existing is None:
            count = await coll.count_documents({})
            await db.counters.insert_one({"_id": name, "seq": count})


async def seed_admin_and_users():
    admin = await db.users.find_one({"email": ADMIN_EMAIL.lower()})
    if admin is None:
        await db.users.insert_one({
            "id": new_id(),
            "email": ADMIN_EMAIL.lower(),
            "password_hash": hash_password(ADMIN_PASSWORD),
            "name": "Amministratore",
            "role": "admin",
            "tenant_id": DEMO_TENANT_ID,
            "attivo": True,
            "email_verified": True,
            "created_at": now_utc(),
        })
        logger.info(f"[SEED] Admin creato: {ADMIN_EMAIL}")
    elif not verify_password(ADMIN_PASSWORD, admin["password_hash"]):
        await db.users.update_one(
            {"email": ADMIN_EMAIL.lower()},
            {"$set": {"password_hash": hash_password(ADMIN_PASSWORD)}},
        )

    # Ruoli funzionali per il flusso commerciale: contabilità + logistica (per DDT)
    test_users = [
        ("logistica@cleantec.it", "logistica123", "Luca Bianchi (Logistica)", "logistica"),
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
                "tenant_id": DEMO_TENANT_ID,
                "attivo": True,
                "email_verified": True,
                "created_at": now_utc(),
            })


async def seed_clienti_articoli():
    if await db.clienti.count_documents({}) == 0:
        clienti_demo = [
            {"ragione_sociale": "Hotel Excelsior Roma Srl", "partita_iva": "IT01234567890", "codice_fiscale": "01234567890",
             "indirizzo": "Via Veneto 125, 00187 Roma (RM)", "email": "info@excelsior-roma.it", "telefono": "+39 06 47081",
             "pec": "excelsior.roma@pec.legalmail.it", "codice_sdi": "ABCDE12",
             "denominazione_struttura": "Hotel Excelsior Roma", "indirizzo_scarico": "Via Veneto 125, 00187 Roma (RM) — ingresso carico/scarico",
             "tipologia": "hotel"},
            {"ragione_sociale": "Ospedale San Raffaele Spa", "partita_iva": "IT09876543210", "codice_fiscale": "09876543210",
             "indirizzo": "Via Olgettina 60, 20132 Milano (MI)", "email": "logistica@sanraffaele.it", "telefono": "+39 02 26431",
             "pec": "sanraffaele.logistica@pec.it", "codice_sdi": "M5UXCR1",
             "denominazione_struttura": "Ospedale San Raffaele - Servizi Sanitari",
             "indirizzo_scarico": "Via Olgettina 60, 20132 Milano — reparto lavanderia",
             "tipologia": "ospedale"},
            {"ragione_sociale": "Ristorante Villa Reale Srl", "partita_iva": "IT11223344556", "codice_fiscale": "11223344556",
             "indirizzo": "Corso Buenos Aires 12, 20124 Milano (MI)", "email": "info@villarealemi.it", "telefono": "+39 02 2940111",
             "pec": "villareale@pec.it", "codice_sdi": "", "denominazione_struttura": "Ristorante Villa Reale",
             "indirizzo_scarico": "", "tipologia": "ristorante"},
            {"ragione_sociale": "Grand Hotel Rimini Spa", "partita_iva": "IT55667788990", "codice_fiscale": "55667788990",
             "indirizzo": "P.le Indipendenza 2, 47921 Rimini (RN)", "email": "reception@grandhotelrimini.com", "telefono": "+39 0541 56000",
             "pec": "grandhotelrimini@pec.legalmail.it", "codice_sdi": "T04ZHR3",
             "denominazione_struttura": "Grand Hotel Rimini", "indirizzo_scarico": "", "tipologia": "hotel"},
            {"ragione_sociale": "Clinica Mater Dei Srl", "partita_iva": "IT99887766554", "codice_fiscale": "99887766554",
             "indirizzo": "Via Bertoloni 34, 00197 Roma (RM)", "email": "reception@materdei.it", "telefono": "+39 06 809051",
             "pec": "materdei@pec.it", "codice_sdi": "",
             "denominazione_struttura": "Clinica Mater Dei - Servizi Generali", "indirizzo_scarico": "",
             "tipologia": "ospedale"},
        ]
        for c in clienti_demo:
            c.update({
                "id": new_id(), "tenant_id": DEMO_TENANT_ID,
                "condizioni_pagamento": "30gg", "attivo": True,
                "giorni_ritiro": [],
                "created_at": now_utc(), "note": "",
            })
        await db.clienti.insert_many(clienti_demo)
        logger.info(f"[SEED] Clienti: {len(clienti_demo)}")

    if await db.articoli.count_documents({}) == 0:
        articoli_demo = [
            # prezzo = valore convenzionale singolo IVA esclusa
            # prezzo_noleggio / prezzo_lavaggio = driver listini
            {"codice": "LEN-MAT", "descrizione": "Lenzuolo Matrimoniale", "categoria": "biancheria", "unita_misura": "pz",
             "prezzo": 12.0, "prezzo_noleggio": 1.20, "prezzo_lavaggio": 0.85, "giacenza": 480},
            {"codice": "LEN-SIN", "descrizione": "Lenzuolo Singolo", "categoria": "biancheria", "unita_misura": "pz",
             "prezzo": 9.0, "prezzo_noleggio": 0.90, "prezzo_lavaggio": 0.65, "giacenza": 620},
            {"codice": "ASC-VIS", "descrizione": "Asciugamano Viso", "categoria": "biancheria", "unita_misura": "pz",
             "prezzo": 5.0, "prezzo_noleggio": 0.50, "prezzo_lavaggio": 0.35, "giacenza": 1200},
            {"codice": "TOV-RIS", "descrizione": "Tovagliato Ristorante", "categoria": "tovagliato", "unita_misura": "kg",
             "prezzo": 25.0, "prezzo_noleggio": 2.50, "prezzo_lavaggio": 1.80, "giacenza": 300},
            {"codice": "DIV-OSP", "descrizione": "Divisa Ospedaliera", "categoria": "divise", "unita_misura": "pz",
             "prezzo": 18.0, "prezzo_noleggio": 1.80, "prezzo_lavaggio": 1.20, "giacenza": 380},
            {"codice": "KIT-CAM", "descrizione": "Kit Camera Completo", "categoria": "kit", "unita_misura": "pz",
             "prezzo": 45.0, "prezzo_noleggio": 4.50, "prezzo_lavaggio": 3.20, "giacenza": 150},
        ]
        for a in articoli_demo:
            a.update({"id": new_id(), "tenant_id": DEMO_TENANT_ID, "attivo": True, "created_at": now_utc()})
        await db.articoli.insert_many(articoli_demo)
        logger.info(f"[SEED] Articoli: {len(articoli_demo)}")


async def seed_listini_and_ddt():
    if await db.listini.count_documents({"tenant_id": DEMO_TENANT_ID}) > 0:
        return
    clienti = await db.clienti.find({"tenant_id": DEMO_TENANT_ID}, {"_id": 0}).to_list(100)
    articoli = await db.articoli.find({"tenant_id": DEMO_TENANT_ID}, {"_id": 0}).to_list(100)
    if not clienti or not articoli:
        return

    listino_std = {
        "id": new_id(), "tenant_id": DEMO_TENANT_ID,
        "nome": "Noleggio Standard", "tipo": "noleggio",
        "descrizione": "Listino noleggio standard", "attivo": True,
        "created_at": now_utc(), "updated_at": now_utc(),
    }
    listino_vip = {
        "id": new_id(), "tenant_id": DEMO_TENANT_ID,
        "nome": "Lavaggio VIP Hotel 5 stelle", "tipo": "lavaggio",
        "descrizione": "Listino lavaggio clienti top", "attivo": True,
        "created_at": now_utc(), "updated_at": now_utc(),
    }
    await db.listini.insert_many([listino_std, listino_vip])

    prezzi = []
    for a in articoli:
        p_nol = float(a.get("prezzo_noleggio") or a.get("prezzo", 1) or 1)
        p_lav = float(a.get("prezzo_lavaggio") or a.get("prezzo", 1) or 1)
        prezzi.append({
            "tenant_id": DEMO_TENANT_ID, "listino_id": listino_std["id"],
            "articolo_id": a["id"], "prezzo": round(p_nol, 2), "updated_at": now_utc(),
        })
        prezzi.append({
            "tenant_id": DEMO_TENANT_ID, "listino_id": listino_vip["id"],
            "articolo_id": a["id"], "prezzo": round(p_lav * 0.9, 2), "updated_at": now_utc(),
        })
    await db.listini_prezzi.insert_many(prezzi)

    # Assegnazione listino ai clienti
    for idx, cli in enumerate(clienti):
        lid = listino_vip["id"] if idx < 2 else listino_std["id"]
        await db.clienti.update_one({"id": cli["id"]}, {"$set": {"listino_id": lid}})

    # DDT demo
    import random as _r
    _r.seed(11)
    next_seq = (await __import__("core", fromlist=["next_seq"])).next_seq
    for cli in clienti[:3]:
        fresh_cli = await db.clienti.find_one({"id": cli["id"]}, {"_id": 0})
        listino_id = fresh_cli.get("listino_id")
        for _k in range(2):
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
            seq = await next_seq("ddt")
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
    logger.info("[SEED] Listini (Std + VIP) + 6 DDT demo creati")


async def migrate_phase2():
    """Backfill new fields introduced in FASE 2 (listini.tipo, articoli.prezzo_noleggio/lavaggio/giacenza)."""
    # Listini: default tipo=lavaggio for existing rows without one
    res = await db.listini.update_many(
        {"tipo": {"$exists": False}},
        {"$set": {"tipo": "lavaggio"}},
    )
    if res.modified_count:
        logger.info(f"[SEED] migrate phase2: listini.tipo backfilled on {res.modified_count} docs")
    # Articoli: default prezzo_noleggio=prezzo, prezzo_lavaggio=prezzo, giacenza=0
    async for a in db.articoli.find(
        {"$or": [
            {"prezzo_noleggio": {"$exists": False}},
            {"prezzo_lavaggio": {"$exists": False}},
            {"giacenza": {"$exists": False}},
        ]},
        {"_id": 1, "prezzo": 1, "prezzo_noleggio": 1, "prezzo_lavaggio": 1, "giacenza": 1},
    ):
        base = float(a.get("prezzo") or 0)
        upd = {}
        if "prezzo_noleggio" not in a or a.get("prezzo_noleggio") is None:
            upd["prezzo_noleggio"] = round(base * 0.1, 2) if base else 0.0
        if "prezzo_lavaggio" not in a or a.get("prezzo_lavaggio") is None:
            upd["prezzo_lavaggio"] = round(base * 0.07, 2) if base else 0.0
        if "giacenza" not in a or a.get("giacenza") is None:
            upd["giacenza"] = 0
        if upd:
            await db.articoli.update_one({"_id": a["_id"]}, {"$set": upd})
    # Rimuovi sla_ore legacy
    await db.clienti.update_many({"sla_ore": {"$exists": True}}, {"$unset": {"sla_ore": ""}})


async def run_all():
    await ensure_demo_tenant()
    await seed_admin_and_users()
    await seed_clienti_articoli()
    await seed_listini_and_ddt()
    await migrate_phase2()
    await backfill_tenant_id()
    await ensure_indexes()
    await ensure_counters()
    logger.info("[SEED] Completato.")
