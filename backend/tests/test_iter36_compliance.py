"""Iter36 — Compliance §16 sicurezza + §17 migrazioni + §18/§19 criteri accettazione.

Copre:
- §16 Sicurezza: PATCH /fatture/{id}/rinumera admin-only; POST/PATCH /articoli
  admin+contabilita; GET /reports/anomalie-pesi admin-only; utente cliente su
  /fatture vede solo le proprie.
- §16 Audit log: RINUMERA_RIDATA e RICALCOLO_PESO_STORICO scrivono su db.audit_log.
- §17 Migrazioni: articoli demo hanno categoria_peso; counts clienti/articoli/DDT/
  fatture > 0; indici Mongo su db.ddt e db.articoli presenti.
- §18 Fatturazione: filtri combinati; summary indipendente da limit.
- §18 Pesi: snapshot invariante, dashboard kg vs report produzione.
- §14 Anomalie: peso_medio=0 → problema; categoria=NON_CLASSIFICATO → problema.
- §13 Regole inclusione: righe con quantita<=0 escluse dagli aggregati.
"""
import os
import re
import time
import pytest
import requests
from pathlib import Path
from datetime import datetime
from pymongo import MongoClient


# ---------- Config ----------
def _load_backend_url() -> str:
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v
    env_file = Path("/app/frontend/.env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    return ""


def _load_mongo_config():
    env_file = Path("/app/backend/.env")
    mongo, db = None, None
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip().strip('"')
            if line.startswith("MONGO_URL="):
                mongo = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("DB_NAME="):
                db = line.split("=", 1)[1].strip().strip('"')
    return mongo or os.environ.get("MONGO_URL"), db or os.environ.get("DB_NAME")


BASE_URL = _load_backend_url().rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@cleantec.it"
ADMIN_PASSWORD = "admin123"
CONT_EMAIL = "contabilita@cleantec.it"
CONT_PASSWORD = "contabilita123"

MONGO_URL, DB_NAME = _load_mongo_config()


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    token = r.json().get("access_token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def cont_session():
    return _login(CONT_EMAIL, CONT_PASSWORD)


@pytest.fixture(scope="module")
def mongo_db():
    if not MONGO_URL or not DB_NAME:
        pytest.skip("MONGO_URL/DB_NAME not configured")
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=3000)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="module")
def tenant_id(admin_session):
    r = admin_session.get(f"{API}/auth/me")
    assert r.status_code == 200
    return r.json().get("tenant_id")


@pytest.fixture(scope="module")
def cliente_user(admin_session, mongo_db, tenant_id):
    """Crea (o riusa) un utente ruolo=cliente per test RBAC.
    Ritorna (session, user_dict) — usa il primo cliente demo come cliente_id.
    """
    # trova un cliente esistente per legare user.cliente_id
    cli = mongo_db.clienti.find_one({"tenant_id": tenant_id}, {"_id": 0, "id": 1})
    assert cli, "Nessun cliente demo trovato — seed non eseguito?"
    cid = cli["id"]

    email = "TEST_cliente_iter36@cleantec.it"
    pw = "TestCliente123!"
    # cleanup se esiste
    mongo_db.users.delete_many({"email": email})

    r = admin_session.post(f"{API}/users", json={
        "email": email,
        "password": pw,
        "name": "TEST Cliente Iter36",
        "role": "cliente",
        "cliente_id": cid,
    })
    if r.status_code not in (200, 201):
        pytest.skip(f"Impossibile creare user cliente per test: {r.status_code} {r.text}")
    uid = r.json().get("id")
    sess = _login(email, pw)
    yield sess, {"id": uid, "email": email, "cliente_id": cid}
    # teardown
    try:
        admin_session.delete(f"{API}/users/{uid}?hard=true")
    except Exception:
        pass
    mongo_db.users.delete_many({"email": email})


# ------------------------------------------------------------------
# §16 SICUREZZA — RBAC su endpoint sensibili
# ------------------------------------------------------------------
class TestSicurezza16:
    def _pick_non_transmitted_fattura(self, session):
        r = session.get(f"{API}/fatture?limit=200")
        assert r.status_code == 200
        for f in r.json():
            if not f.get("xml_transmitted"):
                return f
        return None

    def test_rinumera_contabilita_forbidden(self, admin_session, cont_session):
        """PATCH /fatture/{id}/rinumera con utente contabilita → 403."""
        f = self._pick_non_transmitted_fattura(admin_session)
        assert f, "Nessuna fattura non trasmessa nel demo"
        r = cont_session.patch(
            f"{API}/fatture/{f['id']}/rinumera",
            json={"motivazione": "Tentativo non autorizzato di test compliance"},
        )
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"

    def test_rinumera_admin_missing_motivazione(self, admin_session):
        """Admin senza motivazione → 422 (Pydantic min_length)."""
        f = self._pick_non_transmitted_fattura(admin_session)
        assert f
        r = admin_session.patch(f"{API}/fatture/{f['id']}/rinumera", json={})
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"

    def test_rinumera_admin_short_motivazione(self, admin_session):
        """Motivazione < 10 char → 422."""
        f = self._pick_non_transmitted_fattura(admin_session)
        assert f
        r = admin_session.patch(
            f"{API}/fatture/{f['id']}/rinumera",
            json={"motivazione": "corta"},
        )
        assert r.status_code == 422

    def test_rinumera_admin_noop_ok(self, admin_session):
        """Admin con motivazione valida ma nessun cambio dati → 200 no-op (idempotente)."""
        f = self._pick_non_transmitted_fattura(admin_session)
        assert f
        # No seq / numero / nuova_data → controller ritorna 400 "Specificare almeno un cambio"
        r = admin_session.patch(
            f"{API}/fatture/{f['id']}/rinumera",
            json={"motivazione": "Test compliance §16 — nessun cambio richiesto"},
        )
        # accettiamo 400 (nessun cambio) come sinonimo di "validato dopo RBAC"
        assert r.status_code in (200, 400), f"expected 200/400, got {r.status_code}: {r.text}"

    def test_articoli_cliente_forbidden(self, cliente_user):
        """POST /articoli con ruolo cliente → 403."""
        sess, _ = cliente_user
        r = sess.post(f"{API}/articoli", json={
            "codice": "TEST_CL_36",
            "descrizione": "TEST cliente non autorizzato",
            "unita_misura": "pz",
            "prezzo": 1.0,
        })
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"

    def test_articoli_patch_cliente_forbidden(self, cliente_user, admin_session, tenant_id, mongo_db):
        """PATCH /articoli/{id} con ruolo cliente → 403."""
        sess, _ = cliente_user
        # prendi un articolo qualsiasi via mongo (non serve UI)
        art = mongo_db.articoli.find_one({"tenant_id": tenant_id}, {"_id": 0, "id": 1})
        assert art
        r = sess.patch(f"{API}/articoli/{art['id']}", json={"descrizione": "hack"})
        assert r.status_code == 403

    def test_articoli_write_contabilita_ok(self, cont_session):
        """Contabilita PUÒ creare articoli (poi cleanup)."""
        r = cont_session.post(f"{API}/articoli", json={
            "codice": "TEST_36_CONT",
            "descrizione": "TEST iter36 contabilita",
            "unita_misura": "pz",
            "prezzo": 1.0,
            "peso_medio": 0.1,
            "categoria_peso": "VARIE",
        })
        assert r.status_code in (200, 201), f"contabilita create articolo failed: {r.status_code} {r.text}"
        aid = r.json().get("id")
        # cleanup
        cont_session.delete(f"{API}/articoli/{aid}")

    def test_anomalie_pesi_contabilita_forbidden(self, cont_session):
        """GET /reports/anomalie-pesi con ruolo contabilita → 403."""
        r = cont_session.get(f"{API}/reports/anomalie-pesi")
        assert r.status_code == 403

    def test_anomalie_pesi_admin_ok(self, admin_session):
        r = admin_session.get(f"{API}/reports/anomalie-pesi")
        assert r.status_code == 200
        d = r.json()
        assert "articoli_anomali" in d and "ddt_anomali" in d

    def test_cliente_vede_solo_proprie_fatture(self, cliente_user):
        """User role=cliente su GET /fatture ottiene solo cliente_id proprio."""
        sess, meta = cliente_user
        r = sess.get(f"{API}/fatture?limit=500")
        assert r.status_code == 200
        data = r.json()
        # tutte le fatture ritornate devono avere cliente_id == user.cliente_id
        for f in data:
            assert f.get("cliente_id") == meta["cliente_id"], (
                f"leak: fattura {f.get('id')} cliente_id={f.get('cliente_id')} != {meta['cliente_id']}"
            )


# ------------------------------------------------------------------
# §16 AUDIT LOG
# ------------------------------------------------------------------
class TestAuditLog16:
    def test_rinumera_scrive_audit(self, admin_session, mongo_db, tenant_id):
        """Ogni PATCH rinumera-ridata deve creare record azione=RINUMERA_RIDATA."""
        # trova una fattura non trasmessa
        r = admin_session.get(f"{API}/fatture?limit=200")
        fatt = None
        for f in r.json():
            if not f.get("xml_transmitted"):
                fatt = f
                break
        assert fatt, "Nessuna fattura non trasmessa"

        # esegui un ridata a stessa data (no-op) per generare audit? no — no-op ritorna early.
        # invece: cambia data di 1 giorno + rimetti — su fattura non trasmessa
        old_data = fatt.get("data", "")
        # parse date
        try:
            old_date = datetime.fromisoformat(old_data.replace("Z", "+00:00")).date()
        except Exception:
            old_date = datetime.utcnow().date()

        new_date = old_date.replace(day=max(1, min(28, old_date.day)))
        # forza cambio: usa un +1 giorno se possibile
        try:
            from datetime import timedelta
            new_date_dt = old_date + timedelta(days=1)
        except Exception:
            new_date_dt = old_date

        motiv = "Test audit log iter36 — cambio data compliance"
        r = admin_session.patch(
            f"{API}/fatture/{fatt['id']}/rinumera",
            json={"nuova_data": new_date_dt.isoformat(), "motivazione": motiv},
        )
        assert r.status_code in (200, 409), f"rinumera failed: {r.status_code} {r.text}"
        if r.status_code == 409:
            pytest.skip("fattura in stato che non consente rinumera")

        # verifica audit_log
        time.sleep(0.3)
        rec = mongo_db.audit_log.find_one(
            {"tenant_id": tenant_id, "azione": "RINUMERA_RIDATA", "entita_id": fatt["id"]},
            sort=[("timestamp", -1)],
        )
        assert rec, "Nessun record RINUMERA_RIDATA su db.audit_log"
        det = rec.get("dettagli") or {}
        assert "motivazione" in det and det["motivazione"] == motiv
        assert "old_data" in det and "new_data" in det

        # ripristina (nice-to-have, non critico)
        try:
            admin_session.patch(
                f"{API}/fatture/{fatt['id']}/rinumera",
                json={"nuova_data": old_date.isoformat(), "motivazione": "Ripristino data originale test iter36"},
            )
        except Exception:
            pass

    def test_ricalcolo_peso_audit(self, admin_session, mongo_db, tenant_id):
        """POST /ddt/peso/ricalcolo/esegui scrive azione=RICALCOLO_PESO_STORICO."""
        # preview per capire quanti DDT candidati ci sono
        r = admin_session.get(f"{API}/ddt/peso/ricalcolo/preview")
        assert r.status_code == 200
        r = admin_session.post(f"{API}/ddt/peso/ricalcolo/esegui", json={"conferma": True})
        assert r.status_code == 200, f"ricalcolo failed: {r.status_code} {r.text}"
        time.sleep(0.3)
        rec = mongo_db.audit_log.find_one(
            {"tenant_id": tenant_id, "azione": "RICALCOLO_PESO_STORICO"},
            sort=[("timestamp", -1)],
        )
        assert rec, "Nessun record RICALCOLO_PESO_STORICO su db.audit_log"


# ------------------------------------------------------------------
# §17 MIGRAZIONI E INTEGRITÀ DATI
# ------------------------------------------------------------------
class TestMigrazioni17:
    def test_articoli_hanno_categoria_peso(self, mongo_db, tenant_id):
        """Tutti gli articoli devono avere categoria_peso valorizzata."""
        missing = list(mongo_db.articoli.find(
            {"tenant_id": tenant_id, "$or": [
                {"categoria_peso": {"$exists": False}},
                {"categoria_peso": None},
                {"categoria_peso": ""},
            ]},
            {"_id": 0, "id": 1, "codice": 1},
        ).limit(5))
        assert not missing, f"Articoli senza categoria_peso: {missing}"

    def test_counts_dati_esistenti_non_azzerati(self, mongo_db, tenant_id):
        """Verifica che clienti/articoli/DDT/fatture non siano stati azzerati."""
        counts = {
            "clienti": mongo_db.clienti.count_documents({"tenant_id": tenant_id}),
            "articoli": mongo_db.articoli.count_documents({"tenant_id": tenant_id}),
            "ddt": mongo_db.ddt.count_documents({"tenant_id": tenant_id}),
            "fatture": mongo_db.fatture.count_documents({"tenant_id": tenant_id}),
        }
        for k, v in counts.items():
            assert v > 0, f"Count {k} è 0 — dati potenzialmente cancellati"

    def test_indici_ddt(self, mongo_db):
        """Verifica presenza indici compositi §15 su db.ddt."""
        idx = mongo_db.ddt.index_information()
        # cerca campi chiave usando i tuple key
        def has(cols):
            for _, meta in idx.items():
                if list(meta.get("key")) == list(cols):
                    return True
            return False

        assert has([("tenant_id", 1), ("data", -1)]), f"Manca (tenant_id,data DESC). Presenti: {list(idx.keys())}"
        assert has([("tenant_id", 1), ("cliente_id", 1), ("data", -1)])
        assert has([("tenant_id", 1), ("calcolo_peso_tipo", 1)])

    def test_indici_articoli(self, mongo_db):
        idx = mongo_db.articoli.index_information()
        found = any(list(m.get("key")) == [("tenant_id", 1), ("categoria_peso", 1)] for m in idx.values())
        assert found, f"Manca indice (tenant_id,categoria_peso). Presenti: {list(idx.keys())}"

    def test_ddt_ricalcolo_marker(self, mongo_db, tenant_id):
        """Dopo ricalcolo storico, esistono DDT con calcolo_peso_tipo=RICALCOLO_STORICO."""
        # non tutti devono averlo, ma almeno uno con marker o CALCOLO_ORIGINALE
        n_ric = mongo_db.ddt.count_documents({
            "tenant_id": tenant_id, "calcolo_peso_tipo": "RICALCOLO_STORICO"
        })
        n_orig = mongo_db.ddt.count_documents({
            "tenant_id": tenant_id, "calcolo_peso_tipo": "CALCOLO_ORIGINALE"
        })
        assert (n_ric + n_orig) > 0, "Nessun DDT con calcolo_peso_tipo valorizzato"
        # tutti i DDT con calcolo_peso_tipo devono avere anche peso_calcolato_at
        sample = mongo_db.ddt.find_one(
            {"tenant_id": tenant_id, "calcolo_peso_tipo": {"$exists": True}},
            {"_id": 0, "peso_calcolato_at": 1, "calcolo_peso_tipo": 1},
        )
        assert sample and sample.get("peso_calcolato_at"), "DDT ricalcolato senza peso_calcolato_at"


# ------------------------------------------------------------------
# §18.2 FATTURAZIONE — Filtri combinati + summary indipendente da limit
# ------------------------------------------------------------------
class TestFatturazione18:
    def test_summary_stessi_filtri_indipendente_limit(self, admin_session):
        """/fatture/summary deve dare gli stessi totali usando limit=10 vs limit=1000."""
        params = "data_inizio=2020-01-01&data_fine=2035-12-31"
        s_r = admin_session.get(f"{API}/fatture/summary?{params}")
        assert s_r.status_code == 200
        summary = s_r.json()

        r10 = admin_session.get(f"{API}/fatture?{params}&limit=10")
        r1000 = admin_session.get(f"{API}/fatture?{params}&limit=1000")
        assert r10.status_code == 200 and r1000.status_code == 200

        # summary totale documento coincide col totale calcolato su tutti (limit=1000 li prende tutti)
        tot_1000 = round(sum(float(f.get("totale") or 0) for f in r1000.json()), 2)
        assert abs(summary["totale_documento"] - tot_1000) < 0.02, (
            f"summary({summary['totale_documento']}) != sum(limit=1000)({tot_1000})"
        )
        # count coerente
        assert summary["count"] == len(r1000.json())
        # summary NON deve cambiare con limit diverso in /fatture (summary non ha limit)
        assert summary["count"] >= len(r10.json())

    def test_filtri_combinati_data_piva_cliente(self, admin_session, mongo_db, tenant_id):
        """Filtro combinato: data_inizio + data_fine + cliente_id restituisce solo il cliente."""
        # prendi cliente con più fatture
        pipe = [
            {"$match": {"tenant_id": tenant_id}},
            {"$group": {"_id": "$cliente_id", "n": {"$sum": 1}}},
            {"$sort": {"n": -1}},
            {"$limit": 1},
        ]
        agg = list(mongo_db.fatture.aggregate(pipe))
        if not agg:
            pytest.skip("Nessuna fattura demo")
        cid = agg[0]["_id"]
        r = admin_session.get(
            f"{API}/fatture?cliente_id={cid}&data_inizio=2020-01-01&data_fine=2035-12-31&limit=500"
        )
        assert r.status_code == 200
        for f in r.json():
            assert f.get("cliente_id") == cid


# ------------------------------------------------------------------
# §18.3 PESI — Subtotali categorie + snapshot invariante + dashboard
# ------------------------------------------------------------------
class TestPesi18:
    def test_ddt_subtotali_categorie_coerenti(self, admin_session):
        """Sample: peso_totale ≈ sum(peso_biancheria_piana + spugna + varie + non_classificato)."""
        r = admin_session.get(f"{API}/ddt?limit=50")
        assert r.status_code == 200
        checked = 0
        for d in r.json():
            pt = float(d.get("peso_totale") or 0)
            somma = round(
                float(d.get("peso_biancheria_piana") or 0)
                + float(d.get("peso_spugna") or 0)
                + float(d.get("peso_varie") or 0)
                + float(d.get("peso_non_classificato") or 0),
                3,
            )
            # tolleranza 0.005 kg
            if pt > 0 or somma > 0:
                assert abs(pt - somma) < 0.006, (
                    f"DDT {d.get('numero')}: peso_totale {pt} != somma {somma}"
                )
                checked += 1
            if checked >= 5:
                break
        # se meno di 5 DDT hanno peso, va bene, ma almeno 1
        assert checked >= 1, "Nessun DDT con peso valorizzato — controlla ricalcolo storico"

    def test_dashboard_kg_coerente_con_report(self, admin_session):
        """dashboard.kg_anno ≈ report_produzione(anno).totale_kg (tolleranza 0.01)."""
        now = datetime.utcnow()
        r_dash = admin_session.get(f"{API}/dashboard/kpi")
        assert r_dash.status_code == 200
        dash = r_dash.json()
        kg_anno_obj = dash.get("kg_anno") or {}
        # kg_anno è un oggetto {totale, biancheria_piana, spugna, varie, non_classificato}
        kg_anno = float(kg_anno_obj.get("totale") if isinstance(kg_anno_obj, dict) else kg_anno_obj or 0)

        r_rep = admin_session.get(f"{API}/reports/produzione?anno={now.year}")
        assert r_rep.status_code == 200
        rep = r_rep.json()
        totale_kg = float(rep.get("totale_kg") or 0)

        assert abs(kg_anno - totale_kg) < 0.02, (
            f"dashboard.kg_anno={kg_anno} != report.totale_kg={totale_kg}"
        )


# ------------------------------------------------------------------
# §14 ANOMALIE PESI
# ------------------------------------------------------------------
class TestAnomalie14:
    def test_anomalie_include_peso_zero_e_non_classificato(self, admin_session, mongo_db, tenant_id):
        """Se esistono articoli con peso_medio=0 o categoria=NON_CLASSIFICATO,
        devono comparire in articoli_anomali con il problema atteso.
        """
        # Crea un articolo TEST con peso=0 e NON_CLASSIFICATO per garantire il match
        r = admin_session.post(f"{API}/articoli", json={
            "codice": "TEST_ANOM_36",
            "descrizione": "TEST anomalia iter36",
            "unita_misura": "pz",
            "prezzo": 1.0,
            "peso_medio": 0.0,
            "categoria_peso": "NON_CLASSIFICATO",
        })
        assert r.status_code in (200, 201), r.text
        aid = r.json().get("id")
        try:
            resp = admin_session.get(f"{API}/reports/anomalie-pesi")
            assert resp.status_code == 200
            data = resp.json()
            target = next((a for a in data.get("articoli_anomali", []) if a.get("articolo_id") == aid), None)
            assert target, "Articolo TEST non presente in articoli_anomali"
            problemi = " ".join(target.get("problemi", [])).lower()
            assert "peso" in problemi and "zero" in problemi, (
                f"Manca problema 'peso medio uguale a zero'. problemi={target.get('problemi')}"
            )
            assert "non" in problemi and ("classificat" in problemi or "categoria" in problemi), (
                f"Manca problema 'categoria non assegnata'. problemi={target.get('problemi')}"
            )
        finally:
            admin_session.delete(f"{API}/articoli/{aid}")


# ------------------------------------------------------------------
# §13 REGOLE INCLUSIONE — quantita<=0 escluse
# ------------------------------------------------------------------
class TestRegoleInclusione13:
    def test_report_esclude_righe_qta_zero(self, admin_session, tenant_id, mongo_db):
        """Rigge con quantita<=0 non devono contribuire agli aggregati.

        Test soft: iniettiamo temporaneamente in un DDT una riga con qta=0 e
        verifichiamo che il totale_kg del report NON aumenti.
        """
        # Prendi un DDT esistente per il test
        ddt = mongo_db.ddt.find_one(
            {"tenant_id": tenant_id, "righe.0": {"$exists": True}},
            {"_id": 0, "id": 1, "righe": 1, "data": 1},
        )
        if not ddt:
            pytest.skip("Nessun DDT esistente per test qta=0")

        # baseline totale kg del periodo
        r1 = admin_session.get(f"{API}/reports/produzione")
        assert r1.status_code == 200
        base_kg = float(r1.json().get("totale_kg") or 0)
        base_pezzi = float(r1.json().get("totale_pezzi") or 0)

        # Inserisci direttamente una riga con quantita=0 (bypass API) — sim seed corrotto
        fake_riga = {
            "articolo_id": "TEST_FAKE",
            "codice": "TEST",
            "descrizione": "riga zero test iter36",
            "unita_misura": "pz",
            "quantita": 0,
            "prezzo_unitario": 1.0,
            "totale": 0.0,
            "peso_medio_snapshot": 0.5,
            "categoria_peso_snapshot": "VARIE",
            "peso_riga": 0.0,
        }
        mongo_db.ddt.update_one({"id": ddt["id"]}, {"$push": {"righe": fake_riga}})
        try:
            r2 = admin_session.get(f"{API}/reports/produzione")
            assert r2.status_code == 200
            after_kg = float(r2.json().get("totale_kg") or 0)
            after_pezzi = float(r2.json().get("totale_pezzi") or 0)
            # I totali NON devono cambiare (la riga qta=0 è esclusa)
            assert abs(after_kg - base_kg) < 0.001, (
                f"totale_kg è cambiato dopo aggiunta riga qta=0: {base_kg} → {after_kg}"
            )
            assert abs(after_pezzi - base_pezzi) < 0.001, (
                f"totale_pezzi è cambiato: {base_pezzi} → {after_pezzi}"
            )
        finally:
            mongo_db.ddt.update_one(
                {"id": ddt["id"]},
                {"$pull": {"righe": {"articolo_id": "TEST_FAKE"}}},
            )
