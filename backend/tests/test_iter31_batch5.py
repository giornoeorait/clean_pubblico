"""
Iter31 tests - CleanTec batch 5 features:
1) POST /api/fatture aggregates ddt_dettagli + riepilogo_articoli
2) GET /api/fatture/{fid} backfill on the fly
3) GET /api/fatture/{fid}/pdf works (PDF bytes returned)
4) GET /api/ordinativi/recap returns aggregated items + counters
5) PATCH /api/ddt/{id}/operativi sets consegnato / ritirato_sporco + timestamp + user
6) GET /api/dashboard/kpi exposes new fields (fatturare_mese_*, fatturato_anno_*)
7) Storico pre-app: insert fatturato_storico fixture and verify it is added to anno
"""
import os
import uuid
import pytest
import requests
from datetime import datetime, timezone

BASE = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE}/api"

ADMIN = {"email": "admin@cleantec.it", "password": "admin123"}
LOG = {"email": "logistica@cleantec.it", "password": "logistica123"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---------------- Fixtures ----------------

@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def log_token():
    return _login(LOG)


@pytest.fixture(scope="module")
def cliente_id(admin_token):
    r = requests.get(f"{API}/clienti?limit=5", headers=_h(admin_token), timeout=15)
    assert r.status_code == 200
    items = r.json()
    assert items, "No clienti found"
    return items[0]["id"]


@pytest.fixture(scope="module")
def articoli(admin_token):
    r = requests.get(f"{API}/articoli?limit=5", headers=_h(admin_token), timeout=15)
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 2, "Need at least 2 articoli"
    return items[:2]


def _create_ddt(token, cliente_id, righe):
    payload = {
        "cliente_id": cliente_id,
        "note": "TEST iter31",
        "righe": righe,
    }
    r = requests.post(f"{API}/ddt", headers=_h(token), json=payload, timeout=15)
    assert r.status_code in (200, 201), f"DDT create failed: {r.status_code} {r.text}"
    return r.json()


# ---------------- 1) Fattura: aggregazione articoli same/diff ----------------

class TestFatturaAggregation:
    def test_fattura_same_article_two_ddt(self, admin_token, cliente_id, articoli):
        a1 = articoli[0]
        d1 = _create_ddt(admin_token, cliente_id, [
            {"articolo_id": a1["id"], "quantita": 5, "prezzo_unitario": 2.0},
        ])
        d2 = _create_ddt(admin_token, cliente_id, [
            {"articolo_id": a1["id"], "quantita": 3, "prezzo_unitario": 2.0},
        ])
        r = requests.post(f"{API}/fatture", headers=_h(admin_token),
                          json={"cliente_id": cliente_id, "ddt_ids": [d1["id"], d2["id"]]}, timeout=20)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text}"
        f = r.json()
        # ddt_dettagli
        assert "ddt_dettagli" in f
        assert isinstance(f["ddt_dettagli"], list) and len(f["ddt_dettagli"]) == 2
        det = f["ddt_dettagli"][0]
        for k in ("id", "numero", "data", "imponibile", "righe_count"):
            assert k in det, f"missing key {k} in ddt_dettagli"
        # riepilogo_articoli aggregated
        riep = f.get("riepilogo_articoli")
        assert isinstance(riep, list) and len(riep) == 1
        e = riep[0]
        assert e["articolo_id"] == a1["id"]
        assert e["quantita_totale"] == 8  # 5 + 3
        assert e["prezzo_unitario_medio"] == 2.0
        assert e["totale"] == 16.0
        # Save fattura id for backfill test? We'll test via this newly-created.
        TestFatturaAggregation.fid = f["id"]

    def test_fattura_different_articles(self, admin_token, cliente_id, articoli):
        a1, a2 = articoli[0], articoli[1]
        d1 = _create_ddt(admin_token, cliente_id, [
            {"articolo_id": a1["id"], "quantita": 2, "prezzo_unitario": 1.0},
            {"articolo_id": a2["id"], "quantita": 4, "prezzo_unitario": 3.0},
        ])
        d2 = _create_ddt(admin_token, cliente_id, [
            {"articolo_id": a2["id"], "quantita": 1, "prezzo_unitario": 3.0},
        ])
        r = requests.post(f"{API}/fatture", headers=_h(admin_token),
                          json={"cliente_id": cliente_id, "ddt_ids": [d1["id"], d2["id"]]}, timeout=20)
        assert r.status_code in (200, 201)
        f = r.json()
        riep = f["riepilogo_articoli"]
        assert len(riep) == 2
        by_aid = {x["articolo_id"]: x for x in riep}
        assert by_aid[a1["id"]]["quantita_totale"] == 2
        assert by_aid[a2["id"]]["quantita_totale"] == 5
        assert len(f["ddt_dettagli"]) == 2


# ---------------- 2) GET /api/fatture/{fid} backfill ----------------

class TestFatturaBackfill:
    def test_backfill_get_fattura(self, admin_token, cliente_id, articoli):
        a1 = articoli[0]
        d1 = _create_ddt(admin_token, cliente_id, [
            {"articolo_id": a1["id"], "quantita": 7, "prezzo_unitario": 1.5},
        ])
        r = requests.post(f"{API}/fatture", headers=_h(admin_token),
                          json={"cliente_id": cliente_id, "ddt_ids": [d1["id"]]}, timeout=20)
        assert r.status_code in (200, 201)
        fid = r.json()["id"]

        # Simulate "vecchia fattura" by removing ddt_dettagli + riepilogo_articoli directly via Mongo
        from pymongo import MongoClient
        mc = MongoClient(os.environ.get("MONGO_URL"))
        db_name = os.environ.get("DB_NAME")
        coll = mc[db_name]["fatture"]
        coll.update_one({"id": fid}, {"$unset": {"ddt_dettagli": "", "riepilogo_articoli": ""}})

        # GET should backfill on the fly
        r2 = requests.get(f"{API}/fatture/{fid}", headers=_h(admin_token), timeout=15)
        assert r2.status_code == 200
        f = r2.json()
        assert f.get("ddt_dettagli"), "ddt_dettagli not backfilled"
        assert f.get("riepilogo_articoli"), "riepilogo_articoli not backfilled"
        assert f["riepilogo_articoli"][0]["quantita_totale"] == 7

        # PDF endpoint
        r3 = requests.get(f"{API}/fatture/{fid}/pdf", headers=_h(admin_token), timeout=30)
        assert r3.status_code == 200
        assert r3.content[:4] == b"%PDF", "PDF magic bytes missing"


# ---------------- 3) /api/ordinativi/recap ----------------

class TestOrdinativiRecap:
    def test_recap_shape(self, admin_token):
        r = requests.get(f"{API}/ordinativi/recap", headers=_h(admin_token), timeout=15)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        data = r.json()
        for k in ("items", "totale_pezzi", "totale_articoli",
                  "ordinativi_aperti", "ordinativi_nuovo", "ordinativi_in_lavorazione"):
            assert k in data, f"missing key {k}"
        assert isinstance(data["items"], list)
        # Confirm filter excludes convertito_ddt / annullato
        r2 = requests.get(f"{API}/ordinativi?limit=500", headers=_h(admin_token), timeout=15)
        assert r2.status_code == 200
        ords = r2.json()
        aperti = [o for o in ords if o.get("stato") in ("nuovo", "in_lavorazione")]
        assert data["ordinativi_aperti"] == len(aperti)

    def test_recap_excludes_after_conversion(self, admin_token, cliente_id, articoli):
        # Create a fresh ordinativo, get recap, convert to DDT, get recap again
        a1 = articoli[0]
        payload = {
            "cliente_id": cliente_id,
            "note": "TEST iter31 recap",
            "righe": [{"articolo_id": a1["id"], "quantita": 11, "prezzo_unitario": 1.0}],
        }
        r = requests.post(f"{API}/ordinativi", headers=_h(admin_token), json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text
        oid = r.json()["id"]

        recap1 = requests.get(f"{API}/ordinativi/recap", headers=_h(admin_token), timeout=15).json()
        pieces_before = recap1["totale_pezzi"]

        r2 = requests.post(f"{API}/ordinativi/{oid}/converti-ddt", headers=_h(admin_token), timeout=20)
        assert r2.status_code in (200, 201), f"convert failed: {r2.status_code} {r2.text}"

        recap2 = requests.get(f"{API}/ordinativi/recap", headers=_h(admin_token), timeout=15).json()
        # totale_pezzi should drop by 11 (assuming stato=convertito_ddt now)
        assert recap2["totale_pezzi"] == pieces_before - 11, \
            f"recap pieces not reduced: before={pieces_before} after={recap2['totale_pezzi']}"


# ---------------- 4) PATCH /api/ddt/{id}/operativi ----------------

class TestDDTOperativi:
    def test_set_consegnato_true_then_false(self, admin_token, cliente_id, articoli):
        a1 = articoli[0]
        d = _create_ddt(admin_token, cliente_id, [
            {"articolo_id": a1["id"], "quantita": 1, "prezzo_unitario": 1.0},
        ])
        did = d["id"]
        imponibile_initial = d.get("imponibile")

        r = requests.patch(f"{API}/ddt/{did}/operativi", headers=_h(admin_token),
                           json={"consegnato": True}, timeout=15)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["consegnato"] is True
        assert doc.get("consegnato_at"), "consegnato_at missing"
        assert doc.get("consegnato_by"), "consegnato_by missing"
        # imponibile unchanged
        assert doc.get("imponibile") == imponibile_initial

        # Reset
        r2 = requests.patch(f"{API}/ddt/{did}/operativi", headers=_h(admin_token),
                            json={"consegnato": False}, timeout=15)
        assert r2.status_code == 200
        doc2 = r2.json()
        assert doc2["consegnato"] is False
        assert doc2.get("consegnato_at") in (None, "")
        assert doc2.get("consegnato_by") in (None, "")

    def test_set_ritirato_sporco_true(self, admin_token, cliente_id, articoli):
        a1 = articoli[0]
        d = _create_ddt(admin_token, cliente_id, [
            {"articolo_id": a1["id"], "quantita": 2, "prezzo_unitario": 1.0},
        ])
        did = d["id"]
        r = requests.patch(f"{API}/ddt/{did}/operativi", headers=_h(admin_token),
                           json={"ritirato_sporco": True}, timeout=15)
        assert r.status_code == 200
        doc = r.json()
        assert doc["ritirato_sporco"] is True
        assert doc.get("ritirato_sporco_at")
        assert doc.get("ritirato_sporco_by")

    def test_operativi_works_on_fatturato_ddt(self, admin_token, cliente_id, articoli):
        a1 = articoli[0]
        d = _create_ddt(admin_token, cliente_id, [
            {"articolo_id": a1["id"], "quantita": 1, "prezzo_unitario": 1.0},
        ])
        did = d["id"]
        imponibile_pre = d.get("imponibile")
        righe_pre = d.get("righe")
        # Fatturalo
        r = requests.post(f"{API}/fatture", headers=_h(admin_token),
                          json={"cliente_id": cliente_id, "ddt_ids": [did]}, timeout=20)
        assert r.status_code in (200, 201)
        # Now PATCH operativi
        r2 = requests.patch(f"{API}/ddt/{did}/operativi", headers=_h(admin_token),
                            json={"consegnato": True}, timeout=15)
        assert r2.status_code == 200, f"PATCH on fatturato DDT failed: {r2.status_code} {r2.text}"
        # Re-fetch DDT and verify imponibile + righe unchanged
        r3 = requests.get(f"{API}/ddt/{did}", headers=_h(admin_token), timeout=15)
        assert r3.status_code == 200
        doc = r3.json()
        assert doc.get("imponibile") == imponibile_pre
        assert doc.get("righe") == righe_pre
        assert doc.get("stato_fatturazione") == "fatturato"
        assert doc.get("consegnato") is True


# ---------------- 5) Dashboard KPI fields ----------------

class TestDashboardKPI:
    def test_kpi_fields_present(self, admin_token):
        r = requests.get(f"{API}/dashboard/kpi", headers=_h(admin_token), timeout=15)
        assert r.status_code == 200
        d = r.json()
        required = [
            "fatturare_mese_importo", "fatturare_mese_count", "fatturare_mese_serie_cumul",
            "fatturato_anno", "fatturato_anno_fatture", "fatturato_anno_storico",
            "storico_totale_anno", "storico_mesi_inclusi", "anno_corrente",
        ]
        for k in required:
            assert k in d, f"missing key {k}"
        assert isinstance(d["fatturare_mese_serie_cumul"], list)
        if d["fatturare_mese_serie_cumul"]:
            row = d["fatturare_mese_serie_cumul"][0]
            for k in ("giorno", "valore_giorno", "cumulato"):
                assert k in row

    def test_fatturare_mese_importo_matches_direct_count(self, admin_token):
        r = requests.get(f"{API}/dashboard/kpi", headers=_h(admin_token), timeout=15)
        kpi = r.json()
        # Fetch DDT of current month non_fatturato by querying ddt list
        rd = requests.get(f"{API}/ddt?limit=5000", headers=_h(admin_token), timeout=20)
        assert rd.status_code == 200
        ddts = rd.json()
        now = datetime.now(timezone.utc)
        first = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        total = 0.0
        for d in ddts:
            if d.get("stato_fatturazione") == "fatturato":
                continue
            data = d.get("data")
            if not data:
                continue
            try:
                dt = datetime.fromisoformat(data.replace("Z", "+00:00")) if isinstance(data, str) else data
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if dt >= first:
                total += float(d.get("imponibile", 0) or 0)
        assert abs(round(total, 2) - float(kpi["fatturare_mese_importo"])) < 0.5, \
            f"manual {total} vs kpi {kpi['fatturare_mese_importo']}"

    def test_fatturato_anno_storico_with_fixture(self, admin_token):
        # Insert a fatturato_storico record for Jan 2026 then verify kpi picks it up
        from pymongo import MongoClient
        mc = MongoClient(os.environ.get("MONGO_URL"))
        db_name = os.environ.get("DB_NAME")
        coll = mc[db_name]["fatturato_storico"]

        # Determine tenant_id from admin auth/me
        rme = requests.get(f"{API}/auth/me", headers=_h(admin_token), timeout=10)
        assert rme.status_code == 200
        tenant_id = rme.json().get("tenant_id")
        assert tenant_id

        # Determine current year. If not 2026, skip (storico window is hardcoded 2026 Q1)
        now = datetime.now(timezone.utc)
        if now.year != 2026:
            pytest.skip("STORICO_PREAPP_MONTHS targets 2026; current year is different")

        # Pre-fetch kpi
        kpi0 = requests.get(f"{API}/dashboard/kpi", headers=_h(admin_token), timeout=15).json()
        storico_before = float(kpi0.get("fatturato_anno_storico", 0))

        unique_amount = 1234.56
        # Use mese that has no real fatture: try to find a month in {1,2,3} where no fattura exists
        rf = requests.get(f"{API}/fatture?limit=5000", headers=_h(admin_token), timeout=20)
        fatture = rf.json() if rf.status_code == 200 else []
        months_with_fatt = set()
        for f in fatture:
            data = f.get("data")
            if not data:
                continue
            try:
                dt = datetime.fromisoformat(data.replace("Z", "+00:00")) if isinstance(data, str) else data
                if dt.year == 2026:
                    months_with_fatt.add(dt.month)
            except Exception:
                continue
        candidate = None
        for m in (1, 2, 3):
            if m not in months_with_fatt:
                candidate = m
                break
        if candidate is None:
            pytest.skip("No free 2026 Q1 month for storico fixture (all months already have fatture)")

        doc = {
            "id": f"TEST_iter31_{uuid.uuid4()}",
            "tenant_id": tenant_id,
            "cliente_id": "TEST_iter31_client",
            "anno": 2026,
            "mese": candidate,
            "totale_netto": unique_amount,
            "origine": "test_iter31",
        }
        coll.insert_one(doc)
        try:
            kpi1 = requests.get(f"{API}/dashboard/kpi", headers=_h(admin_token), timeout=15).json()
            storico_after = float(kpi1.get("fatturato_anno_storico", 0))
            assert round(storico_after - storico_before, 2) == unique_amount, \
                f"expected delta {unique_amount}, got {storico_after - storico_before}"
            assert candidate in kpi1.get("storico_mesi_inclusi", [])
        finally:
            coll.delete_one({"id": doc["id"]})

    def test_logistica_can_call_kpi(self, log_token):
        # The gating "canSeePrices" is frontend-only; backend kpi works for logistica
        r = requests.get(f"{API}/dashboard/kpi", headers=_h(log_token), timeout=15)
        assert r.status_code == 200
