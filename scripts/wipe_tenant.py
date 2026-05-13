#!/usr/bin/env python3
"""CleanTec — Script di wipe operativo per un singolo tenant.

USAGE
=====
  export MONGO_URL='mongodb+srv://...'   # connection string di PRODUZIONE
  export DB_NAME='cleantec_prod'         # nome del database
  python wipe_tenant.py

Lo script:
  1. Chiede l'email dell'admin del tenant da pulire (oppure passa --tenant-id direttamente)
  2. Mostra il riepilogo (tenant trovato + conteggio record per collezione)
  3. Chiede conferma manuale (deve digitare "WIPE")
  4. Esegue dump JSON di backup in ./backups/{tenant}-{timestamp}.json
  5. Cancella i record (filtrati per tenant_id) dalle collezioni operative
  6. Resetta i contatori di numerazione (PROMPT separato — globali, attenzione multi-tenant)
  7. Stampa report finale

COSA NON TOCCA:
  - users, tenants, app_settings, branding, company, subscriptions, payments_transactions
  - articoli, listini, listini_prezzi, termini_templates  (catalog + template)
"""
from __future__ import annotations
import json
import os
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

try:
    from pymongo import MongoClient
except ImportError:
    sys.exit("Manca pymongo: pip install pymongo")


# Collezioni operative da svuotare (filtrate per tenant_id)
OPERATIONAL_COLLECTIONS = [
    "clienti",
    "ddt",
    "fatture",
    "offerte",
    "ordinativi",
    "fornitori",
    "ddt_fornitore",
    "fatture_fornitore",
    "costi",
    "dipendenti",
    "automezzi",
    "portale_sessions",
    "portale_lookup_failed",
    "audit_log",
    "email_events",
]

# Collezioni mantenute (per riferimento)
PRESERVED_COLLECTIONS = [
    "users", "tenants", "app_settings", "branding", "company",
    "articoli", "listini", "listini_prezzi", "termini_templates",
    "payment_transactions", "files",
]

# Contatori da resettare se richiesto
COUNTER_KEYS = ["ddt", "fattura", "ordinativi", "offerta", "ddt_fornitore", "fattura_fornitore"]


def confirm(prompt: str, expected: str = "WIPE") -> bool:
    print(prompt)
    ans = input(f"Per confermare digita esattamente '{expected}': ").strip()
    return ans == expected


def yes_no(q: str, default: bool = False) -> bool:
    d = "Y/n" if default else "y/N"
    ans = input(f"{q} [{d}]: ").strip().lower()
    if not ans:
        return default
    return ans in ("y", "yes", "s", "si", "sì")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", help="Tenant ID diretto (skip lookup email)")
    parser.add_argument("--email", help="Email admin del tenant da pulire (usata per trovare tenant_id)")
    parser.add_argument("--no-backup", action="store_true", help="Salta il dump JSON pre-wipe")
    parser.add_argument("--reset-counters", action="store_true", help="Resetta anche i contatori numerazione (GLOBALI, attenzione)")
    args = parser.parse_args()

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        sys.exit("ERR: imposta MONGO_URL e DB_NAME nelle variabili d'ambiente prima di eseguire.")

    print("=" * 70)
    print(f"  CleanTec wipe-tenant")
    print(f"  DB: {db_name}  ·  cluster: {mongo_url.split('@')[-1].split('/')[0]}")
    print("=" * 70)

    client = MongoClient(mongo_url)
    db = client[db_name]

    # 1) Trova tenant
    tenant_id = args.tenant_id
    if not tenant_id:
        email = args.email or input("Email admin del tenant da pulire: ").strip()
        if not email:
            sys.exit("Email richiesta.")
        user = db.users.find_one({"email": email})
        if not user:
            sys.exit(f"Utente '{email}' non trovato.")
        tenant_id = user.get("tenant_id")
        if not tenant_id:
            sys.exit(f"Utente '{email}' non ha tenant_id (forse superadmin).")
        print(f"\n→ Tenant ID trovato per {email}: {tenant_id}")

    tenant = db.tenants.find_one({"id": tenant_id}) or {}
    print(f"→ Tenant: {tenant.get('nome') or tenant.get('ragione_sociale') or '(?)'}")
    print(f"   slug: {tenant.get('slug')}")
    print(f"   piano: {tenant.get('piano')}")

    # 2) Riepilogo conteggio
    print(f"\nCollezioni operative da svuotare (filter: tenant_id={tenant_id}):")
    counts = {}
    total = 0
    for c in OPERATIONAL_COLLECTIONS:
        n = db[c].count_documents({"tenant_id": tenant_id})
        counts[c] = n
        total += n
        print(f"   • {c:<28} {n:>6} record")
    print(f"   {'TOTALE':<28} {total:>6} record")
    print(f"\nNON saranno toccate: {', '.join(PRESERVED_COLLECTIONS)}")

    if total == 0:
        print("\n✅ Niente da fare — nessun record operativo per questo tenant.")
        return

    # 3) Conferma
    print()
    if not confirm("⚠️  ATTENZIONE: questa operazione è IRREVERSIBILE."):
        print("Annullato.")
        return

    # 4) Backup JSON
    if not args.no_backup:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_dir = Path("./backups")
        backup_dir.mkdir(exist_ok=True)
        backup_file = backup_dir / f"tenant-{tenant_id}-{ts}.json"
        dump = {"tenant_id": tenant_id, "exported_at": ts, "collections": {}}
        for c in OPERATIONAL_COLLECTIONS:
            docs = list(db[c].find({"tenant_id": tenant_id}, {"_id": 0}))
            # Stringify datetimes
            for d in docs:
                for k, v in list(d.items()):
                    if isinstance(v, datetime):
                        d[k] = v.isoformat()
            dump["collections"][c] = docs
        with backup_file.open("w") as f:
            json.dump(dump, f, indent=2, default=str)
        print(f"\n💾 Backup salvato: {backup_file.resolve()}  ({backup_file.stat().st_size // 1024} KB)")
    else:
        print("\n⚠️  Backup saltato (--no-backup)")

    # 5) Wipe
    print("\n🧹 Cancellazione in corso...")
    for c in OPERATIONAL_COLLECTIONS:
        res = db[c].delete_many({"tenant_id": tenant_id})
        if res.deleted_count or counts[c]:
            print(f"   • {c:<28} cancellati: {res.deleted_count}")

    # 6) Counters (globali — attenzione multi-tenant)
    if args.reset_counters or yes_no(
        "\n⚙️  Vuoi RESETTARE anche i contatori di numerazione (DDT, FT, ORD)?\n"
        "   ATTENZIONE: i counters sono GLOBALI — se hai altri tenant attivi le loro numerazioni\n"
        "   sequenziali andranno potenzialmente in conflitto. Procedi solo se sei l'unico tenant\n"
        "   attivo o se accetti il rischio.",
        default=False,
    ):
        for key in COUNTER_KEYS:
            res = db.counters.delete_one({"_id": key})
            print(f"   • counter '{key}' reset → {res.deleted_count > 0}")

    print("\n✅ Operazione completata.")
    print(f"   Backup: {backup_file.resolve() if not args.no_backup else 'N/A'}")
    print(f"   Tenant: {tenant_id}")
    print(f"   Record cancellati: {total}\n")


if __name__ == "__main__":
    main()
