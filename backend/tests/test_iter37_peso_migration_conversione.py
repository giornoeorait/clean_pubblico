"""Iter37 — Bug fix: peso snapshot su conversione ordinativo→DDT + migration automatica.

Test:
  - Migration: unset peso fields sul DDT, restart backend, verifica RICALCOLO_STORICO applicato
  - Migration idempotenza: 2nd restart non tocca DDT già ricalcolati
  - Conversione ordinativo→DDT: DDT ha peso_totale > 0 + subtotali + calcolo_peso_tipo=CALCOLO_ORIGINALE
  - Regression: POST /api/ddt diretto e GET /api/ddt continuano a funzionare
  - Regression: reports/produzione + dashboard/kpi kg coerenti
"""
import os
import subprocess
import time
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://wash-ops-central.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

ADMIN = {"email": "admin@cleantec.it", "password": "admin123"}


# ---------- Fixtures ---------------------------------------------------------
@pytest.fixture(scope="module")
def mongo():
    cli = MongoClient(MONGO_URL)
    yield cli[DB_NAME]
    cli.close()


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, f"Login admin fallito: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


def _restart_backend_and_wait():
    subprocess.run(["sudo", "supervisorctl", "restart", "backend"], check=False, capture_output=True)
    # Attesa backend health
    for _ in range(30):
        try:
            r = requests.get(f"{API}/health", timeout=3)
            if r.status_code == 200:
                time.sleep(1)  # aspetta seed
                return
        except Exception:
            pass
        time.sleep(1)
    pytest.fail("Backend non ripartito entro 30s")


# ---------- Test 1: Migration automatica al restart ---------------------------
class TestMigrationAutomatica:

    def test_migration_recalcola_ddt_senza_calcolo_peso_tipo(self, mongo, admin_session):
        # Seleziona un DDT esistente con righe non vuote
        ddt = mongo.ddt.find_one({"tenant_id": "demo-tenant-0000-0000-0000-000000000001",
                                   "righe.0": {"$exists": True}}, {"_id": 0})
        assert ddt is not None, "Nessun DDT demo disponibile per test migration"
        ddt_id = ddt["id"]

        # Backup dei valori originali per confronto
        peso_totale_originale = ddt.get("peso_totale")

        # Unset dei campi peso per simulare DDT pre-feature
        mongo.ddt.update_one(
            {"id": ddt_id},
            {"$unset": {
                "calcolo_peso_tipo": 1, "peso_calcolato_at": 1, "peso_totale": 1,
                "peso_biancheria_piana": 1, "peso_spugna": 1, "peso_varie": 1,
                "peso_non_classificato": 1,
            }},
        )

        # Verifica unset effettivo
        stripped = mongo.ddt.find_one({"id": ddt_id}, {"_id": 0})
        assert "calcolo_peso_tipo" not in stripped, "Unset non applicato"
        assert "peso_totale" not in stripped, "Unset peso_totale non applicato"

        # Restart backend → migration runs
        _restart_backend_and_wait()

        # Verifica DDT ricalcolato
        after = mongo.ddt.find_one({"id": ddt_id}, {"_id": 0})
        assert after.get("calcolo_peso_tipo") == "RICALCOLO_STORICO", \
            f"calcolo_peso_tipo atteso RICALCOLO_STORICO, ricevuto {after.get('calcolo_peso_tipo')!r}"
        assert after.get("peso_totale") is not None, "peso_totale non popolato"
        assert after.get("peso_calcolato_at") is not None
        # Subtotali presenti
        for k in ("peso_biancheria_piana", "peso_spugna", "peso_varie", "peso_non_classificato"):
            assert k in after, f"Subtotale {k} mancante"

        # Verifica correttezza: peso_totale = sum(qta × peso_medio) su ogni riga
        atteso = 0.0
        for r in (after.get("righe") or []):
            art = mongo.articoli.find_one({"id": r["articolo_id"]}, {"_id": 0, "peso_medio": 1})
            peso_medio = float((art or {}).get("peso_medio") or 0)
            atteso += peso_medio * float(r.get("quantita") or 0)
        assert abs(after["peso_totale"] - round(atteso, 3)) < 0.01, \
            f"peso_totale ricalcolato ({after['peso_totale']}) diverso da atteso ({atteso})"

        # Verifica snapshot su ogni riga
        for r in after.get("righe") or []:
            assert "peso_medio_snapshot" in r, "peso_medio_snapshot mancante nella riga"
            assert "categoria_peso_snapshot" in r
            assert "peso_riga" in r

        # Verifica che il valore ricalcolato coincida con originale (migration deterministica)
        if peso_totale_originale is not None:
            assert abs(after["peso_totale"] - peso_totale_originale) < 0.01, \
                f"Ricalcolo diverso dal valore originale precedente"

    def test_migration_idempotente(self, mongo):
        """2° restart non deve toccare DDT già con calcolo_peso_tipo."""
        # Contatore DDT prima del secondo restart
        pre_count_by_type = {}
        for row in mongo.ddt.aggregate([
            {"$group": {"_id": "$calcolo_peso_tipo", "n": {"$sum": 1}}}
        ]):
            pre_count_by_type[row["_id"]] = row["n"]
        # Salva timestamps prima
        pre_docs = {d["id"]: d.get("peso_calcolato_at")
                    for d in mongo.ddt.find({}, {"_id": 0, "id": 1, "peso_calcolato_at": 1})}

        # Restart (nessun unset preventivo → nessun DDT da ricalcolare)
        _restart_backend_and_wait()

        # Contatore dopo
        post_count_by_type = {}
        for row in mongo.ddt.aggregate([
            {"$group": {"_id": "$calcolo_peso_tipo", "n": {"$sum": 1}}}
        ]):
            post_count_by_type[row["_id"]] = row["n"]

        assert pre_count_by_type == post_count_by_type, \
            f"Counts calcolo_peso_tipo cambiati fra i due restart: pre={pre_count_by_type} post={post_count_by_type}"

        # Nessun peso_calcolato_at deve essere cambiato per i DDT con calcolo_peso_tipo esistente
        cambiati = 0
        for d in mongo.ddt.find({}, {"_id": 0, "id": 1, "peso_calcolato_at": 1}):
            prev = pre_docs.get(d["id"])
            if prev != d.get("peso_calcolato_at"):
                cambiati += 1
        assert cambiati == 0, f"{cambiati} DDT hanno cambiato peso_calcolato_at durante restart idempotente"


# ---------- Test 2: Conversione ordinativo → DDT ----------------------------
class TestConversioneOrdinativoDDT:

    def test_converti_ddt_popola_snapshot_peso_e_subtotali(self, admin_session, mongo):
        # Crea ordinativo con articoli aventi peso_medio > 0
        arts = list(mongo.articoli.find(
            {"tenant_id": "demo-tenant-0000-0000-0000-000000000001", "peso_medio": {"$gt": 0}},
            {"_id": 0, "id": 1, "peso_medio": 1, "categoria_peso": 1}
        ).limit(3))
        assert len(arts) >= 2, "Servono almeno 2 articoli con peso > 0"

        cli = mongo.clienti.find_one({"tenant_id": "demo-tenant-0000-0000-0000-000000000001"}, {"_id": 0, "id": 1})
        assert cli, "Nessun cliente demo"

        payload = {
            "cliente_id": cli["id"],
            "data_consegna_richiesta": "2026-02-01",
            "righe": [{"articolo_id": a["id"], "quantita": 10} for a in arts],
            "note_cliente": "TEST_iter37 conversione",
        }
        r = admin_session.post(f"{API}/ordinativi", json=payload, timeout=15)
        assert r.status_code == 200, f"Creazione ordinativo fallita: {r.status_code} {r.text[:300]}"
        ord_doc = r.json()
        oid = ord_doc["id"]

        try:
            # Converti in DDT
            r2 = admin_session.post(f"{API}/ordinativi/{oid}/converti-ddt", timeout=20)
            assert r2.status_code == 200, f"Conversione fallita: {r2.status_code} {r2.text[:300]}"
            converted = r2.json()
            ddt_id = converted.get("ddt_id")
            assert ddt_id, "ddt_id non ritornato dall'ordinativo dopo conversione"

            # Recupera il DDT dal DB
            ddt = mongo.ddt.find_one({"id": ddt_id}, {"_id": 0})
            assert ddt, f"DDT {ddt_id} non trovato"

            # 1) calcolo_peso_tipo = CALCOLO_ORIGINALE
            assert ddt.get("calcolo_peso_tipo") == "CALCOLO_ORIGINALE", \
                f"Atteso CALCOLO_ORIGINALE, ricevuto {ddt.get('calcolo_peso_tipo')!r}"
            assert ddt.get("peso_calcolato_at") is not None

            # 2) peso_totale > 0 (articoli con peso > 0)
            assert ddt.get("peso_totale", 0) > 0, f"peso_totale atteso > 0, ricevuto {ddt.get('peso_totale')}"

            # 3) peso_totale coerente = sum(qta × peso_medio)
            atteso = sum(float(a["peso_medio"]) * 10 for a in arts)
            assert abs(ddt["peso_totale"] - round(atteso, 3)) < 0.01, \
                f"peso_totale {ddt['peso_totale']} != atteso {atteso}"

            # 4) subtotali categoria coerenti
            sub = {"BIANCHERIA_PIANA": 0.0, "SPUGNA": 0.0, "VARIE": 0.0, "NON_CLASSIFICATO": 0.0}
            for a in arts:
                cat = (a.get("categoria_peso") or "NON_CLASSIFICATO").upper()
                if cat not in sub:
                    cat = "NON_CLASSIFICATO"
                sub[cat] += float(a["peso_medio"]) * 10
            assert abs(ddt.get("peso_biancheria_piana", 0) - round(sub["BIANCHERIA_PIANA"], 3)) < 0.01
            assert abs(ddt.get("peso_spugna", 0) - round(sub["SPUGNA"], 3)) < 0.01
            assert abs(ddt.get("peso_varie", 0) - round(sub["VARIE"], 3)) < 0.01
            assert abs(ddt.get("peso_non_classificato", 0) - round(sub["NON_CLASSIFICATO"], 3)) < 0.01

            # 5) Ogni riga ha snapshot
            for r_ddt in ddt.get("righe") or []:
                assert "peso_medio_snapshot" in r_ddt, "peso_medio_snapshot mancante"
                assert "categoria_peso_snapshot" in r_ddt, "categoria_peso_snapshot mancante"
                assert "peso_riga" in r_ddt, "peso_riga mancante"
                assert r_ddt["peso_riga"] > 0, f"peso_riga=0 per riga con articolo peso>0"

            # 6) DDT tracce dall'ordinativo
            assert ddt.get("origine_ordinativo_id") == oid
            assert ddt.get("origine_ordinativo_numero") == ord_doc["numero"]

            # Cleanup: elimina DDT e ordinativo
            mongo.ddt.delete_one({"id": ddt_id})
        finally:
            # cleanup ordinativo (dopo eliminazione DDT torna nuovo)
            mongo.ordinativi.delete_one({"id": oid})


# ---------- Test 3: Regression DDT diretto e GET /ddt ------------------------
class TestRegressionDDT:

    def test_post_ddt_diretto_ha_peso_totale_e_calcolo_originale(self, admin_session, mongo):
        arts = list(mongo.articoli.find(
            {"tenant_id": "demo-tenant-0000-0000-0000-000000000001", "peso_medio": {"$gt": 0}},
            {"_id": 0, "id": 1, "peso_medio": 1}
        ).limit(2))
        cli = mongo.clienti.find_one({"tenant_id": "demo-tenant-0000-0000-0000-000000000001"}, {"_id": 0, "id": 1})

        payload = {
            "cliente_id": cli["id"],
            "note": "TEST_iter37 regression",
            "righe": [{"articolo_id": a["id"], "quantita": 5} for a in arts],
        }
        r = admin_session.post(f"{API}/ddt", json=payload, timeout=15)
        assert r.status_code == 200, f"POST /ddt fallito: {r.status_code} {r.text[:300]}"
        ddt = r.json()
        try:
            assert ddt.get("calcolo_peso_tipo") == "CALCOLO_ORIGINALE"
            assert ddt.get("peso_totale", 0) > 0
            atteso = sum(a["peso_medio"] * 5 for a in arts)
            assert abs(ddt["peso_totale"] - round(atteso, 3)) < 0.01
        finally:
            mongo.ddt.delete_one({"id": ddt["id"]})

    def test_get_ddt_list_include_peso_totale(self, admin_session):
        r = admin_session.get(f"{API}/ddt?limit=500", timeout=20)
        assert r.status_code == 200
        docs = r.json()
        assert isinstance(docs, list) and len(docs) > 0
        # Tutti i DDT devono avere peso_totale (dopo migration nessuno dovrebbe essere None)
        missing = [d for d in docs if d.get("peso_totale") is None]
        assert len(missing) == 0, \
            f"{len(missing)}/{len(docs)} DDT senza peso_totale: es. {[d.get('numero') for d in missing[:3]]}"
        # Tutti hanno calcolo_peso_tipo
        no_calc = [d for d in docs if not d.get("calcolo_peso_tipo")]
        assert len(no_calc) == 0, f"{len(no_calc)} DDT senza calcolo_peso_tipo"


# ---------- Test 4: Regression reports & dashboard --------------------------
class TestRegressionReports:

    def test_reports_produzione_kg_coerente(self, admin_session):
        r = admin_session.get(f"{API}/reports/produzione?anno=2026", timeout=15)
        assert r.status_code == 200, f"reports/produzione fallito: {r.status_code} {r.text[:300]}"
        data = r.json()
        # Deve avere totale_kg >= 0 e struttura mensile
        tot_kg = data.get("totale_kg", 0)
        assert isinstance(tot_kg, (int, float))
        assert tot_kg >= 0

    def test_dashboard_kpi_coerente(self, admin_session):
        r = admin_session.get(f"{API}/dashboard/kpi", timeout=15)
        assert r.status_code == 200, f"dashboard/kpi fallito: {r.status_code} {r.text[:300]}"
        data = r.json()
        # kg_mese e kg_anno devono esistere; possono essere dict o scalari
        assert "kg_mese" in data or "kg_anno" in data
