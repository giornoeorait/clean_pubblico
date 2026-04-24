"""
Iteration 22 - Phase P3 backend tests
- Dipendenti CRUD + RBAC
- Automezzi CRUD + unique targa
- genera-stipendi (idempotent + regex validation)
- Costi mese_riferimento regex validation
- Alerts aggregator (fattura_scaduta already seeded by main agent)
- Report PDF export (6 types)
- Regression: core routes still reachable
"""
import os
import re
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


def _login(email: str, password: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers():
    return {"Authorization": f"Bearer {_login('admin@cleantec.it', 'admin123')}"}


@pytest.fixture(scope="module")
def contab_headers():
    return {"Authorization": f"Bearer {_login('contabilita@cleantec.it', 'contabilita123')}"}


@pytest.fixture(scope="module")
def logi_headers():
    return {"Authorization": f"Bearer {_login('logistica@cleantec.it', 'logistica123')}"}


# ================== DIPENDENTI ==================
class TestDipendenti:
    created_id = None

    def test_list_initial(self, admin_headers):
        r = requests.get(f"{API}/dipendenti", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_admin(self, admin_headers):
        payload = {
            "nome": "TEST_Luigi Verdi",
            "stipendio_mensile": 1800,
            "ore_contrattuali": 160,
            "tipo_contratto": "indeterminato",
            "data_assunzione": "2025-01-15",
            "attivo": True,
        }
        r = requests.post(f"{API}/dipendenti", json=payload, headers=admin_headers, timeout=15)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert data["nome"] == "TEST_Luigi Verdi"
        assert data["stipendio_mensile"] == 1800
        assert "id" in data
        TestDipendenti.created_id = data["id"]
        # GET verify
        r2 = requests.get(f"{API}/dipendenti", headers=admin_headers, timeout=15)
        assert any(d["id"] == data["id"] for d in r2.json())

    def test_rbac_logistica_cannot_create(self, logi_headers):
        r = requests.post(f"{API}/dipendenti",
                          json={"nome": "X", "stipendio_mensile": 0},
                          headers=logi_headers, timeout=15)
        assert r.status_code == 403

    def test_rbac_logistica_can_list(self, logi_headers):
        r = requests.get(f"{API}/dipendenti", headers=logi_headers, timeout=15)
        assert r.status_code == 200

    def test_patch_toggle_attivo(self, admin_headers):
        assert TestDipendenti.created_id
        r = requests.patch(
            f"{API}/dipendenti/{TestDipendenti.created_id}",
            json={"attivo": False}, headers=admin_headers, timeout=15,
        )
        assert r.status_code == 200
        r2 = requests.get(f"{API}/dipendenti", headers=admin_headers, timeout=15)
        d = next(d for d in r2.json() if d["id"] == TestDipendenti.created_id)
        assert d["attivo"] is False

    def test_delete_rbac_contabilita_forbidden(self, contab_headers):
        assert TestDipendenti.created_id
        r = requests.delete(f"{API}/dipendenti/{TestDipendenti.created_id}",
                            headers=contab_headers, timeout=15)
        assert r.status_code == 403

    def test_delete_admin_ok(self, admin_headers):
        assert TestDipendenti.created_id
        r = requests.delete(f"{API}/dipendenti/{TestDipendenti.created_id}",
                            headers=admin_headers, timeout=15)
        assert r.status_code == 200
        # verify gone
        r2 = requests.get(f"{API}/dipendenti", headers=admin_headers, timeout=15)
        assert not any(d["id"] == TestDipendenti.created_id for d in r2.json())


# ================== GENERA STIPENDI ==================
class TestGeneraStipendi:
    def test_invalid_mese_format(self, admin_headers):
        r = requests.post(f"{API}/dipendenti/genera-stipendi",
                          json={"mese_riferimento": "2026-13"},
                          headers=admin_headers, timeout=15)
        assert r.status_code == 400

    def test_invalid_mese_string(self, admin_headers):
        r = requests.post(f"{API}/dipendenti/genera-stipendi",
                          json={"mese_riferimento": "invalido"},
                          headers=admin_headers, timeout=15)
        assert r.status_code == 400

    def test_genera_valid_and_idempotent(self, admin_headers):
        # 1st call
        r = requests.post(f"{API}/dipendenti/genera-stipendi",
                          json={"mese_riferimento": "2026-06"},
                          headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        data1 = r.json()
        assert data1["mese_riferimento"] == "2026-06"
        # 2nd call - should skip all
        r2 = requests.post(f"{API}/dipendenti/genera-stipendi",
                           json={"mese_riferimento": "2026-06"},
                           headers=admin_headers, timeout=30)
        assert r2.status_code == 200
        data2 = r2.json()
        assert data2["n_creati"] == 0
        assert data2["n_skippati"] >= data1["n_creati"]

    def test_rbac_logistica_cannot_genera(self, logi_headers):
        r = requests.post(f"{API}/dipendenti/genera-stipendi",
                          json={"mese_riferimento": "2026-06"},
                          headers=logi_headers, timeout=15)
        assert r.status_code == 403


# ================== AUTOMEZZI ==================
class TestAutomezzi:
    created_id = None

    def test_list(self, admin_headers):
        r = requests.get(f"{API}/automezzi", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create(self, admin_headers):
        payload = {
            "targa": "TEST123XY",
            "marca_modello": "Fiat Ducato",
            "anno": 2022,
            "alimentazione": "diesel",
            "km_attuali": 10000,
            "attivo": True,
        }
        r = requests.post(f"{API}/automezzi", json=payload, headers=admin_headers, timeout=15)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert data["targa"] == "TEST123XY"
        TestAutomezzi.created_id = data["id"]

    def test_duplicate_targa_409(self, admin_headers):
        payload = {"targa": "TEST123XY", "marca_modello": "Altro", "km_attuali": 0, "attivo": True}
        r = requests.post(f"{API}/automezzi", json=payload, headers=admin_headers, timeout=15)
        assert r.status_code == 409

    def test_rbac_logistica_cannot_create(self, logi_headers):
        r = requests.post(f"{API}/automezzi",
                          json={"targa": "ZZZ999XX", "marca_modello": "X"},
                          headers=logi_headers, timeout=15)
        assert r.status_code == 403

    def test_patch(self, admin_headers):
        r = requests.patch(f"{API}/automezzi/{TestAutomezzi.created_id}",
                          json={"km_attuali": 12000},
                          headers=admin_headers, timeout=15)
        assert r.status_code == 200

    def test_delete_rbac_contab_forbidden(self, contab_headers):
        r = requests.delete(f"{API}/automezzi/{TestAutomezzi.created_id}",
                            headers=contab_headers, timeout=15)
        assert r.status_code == 403

    def test_delete_admin(self, admin_headers):
        r = requests.delete(f"{API}/automezzi/{TestAutomezzi.created_id}",
                            headers=admin_headers, timeout=15)
        assert r.status_code == 200


# ================== COSTI mese_riferimento regex ==================
class TestCostiRegex:
    def test_invalid_month_13(self, admin_headers):
        payload = {
            "categoria": "personale", "data": "2026-06-01",
            "mese_riferimento": "2026-13", "descrizione": "TEST", "importo": 100,
        }
        r = requests.post(f"{API}/costi", json=payload, headers=admin_headers, timeout=15)
        assert r.status_code == 422

    def test_invalid_string(self, admin_headers):
        payload = {
            "categoria": "personale", "data": "2026-06-01",
            "mese_riferimento": "invalido", "descrizione": "TEST", "importo": 100,
        }
        r = requests.post(f"{API}/costi", json=payload, headers=admin_headers, timeout=15)
        assert r.status_code == 422

    def test_valid_month(self, admin_headers):
        payload = {
            "categoria": "personale", "data": "2026-06-01",
            "mese_riferimento": "2026-06", "descrizione": "TEST_regex", "importo": 50,
        }
        r = requests.post(f"{API}/costi", json=payload, headers=admin_headers, timeout=15)
        assert r.status_code in (200, 201), r.text
        cid = r.json().get("id")
        if cid:
            requests.delete(f"{API}/costi/{cid}", headers=admin_headers, timeout=15)


# ================== ALERTS ==================
class TestAlerts:
    def test_alerts_shape(self, admin_headers):
        r = requests.get(f"{API}/alerts", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "totale" in data and "per_severity" in data and "alerts" in data
        assert set(["error", "warning", "info"]).issubset(set(data["per_severity"].keys()))
        assert isinstance(data["alerts"], list)

    def test_fattura_scaduta_present(self, admin_headers):
        r = requests.get(f"{API}/alerts", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        alerts = r.json()["alerts"]
        # main agent seeded FORN-FT-2026-00001 scaduta
        fs = [a for a in alerts if a.get("tipo") == "fattura_scaduta"]
        assert len(fs) >= 1, f"expected fattura_scaduta alert, got alerts={alerts}"
        assert fs[0]["severity"] == "error"


# ================== REPORT PDF ==================
class TestReportPDF:
    @pytest.mark.parametrize("tipo", ["fatturato", "produzione", "costo_kg", "marginalita", "aging", "km"])
    def test_pdf_download(self, admin_headers, tipo):
        r = requests.get(f"{API}/reports/{tipo}/pdf?anno=2026", headers=admin_headers, timeout=30)
        assert r.status_code == 200, f"{tipo}: {r.status_code} {r.text[:200]}"
        assert r.headers.get("content-type", "").startswith("application/pdf"), \
            f"{tipo} content-type: {r.headers.get('content-type')}"
        disp = r.headers.get("content-disposition", "")
        assert "attachment" in disp.lower(), f"{tipo} disp={disp}"
        assert r.content[:5] == b"%PDF-", f"{tipo} bytes={r.content[:20]}"


# ================== REGRESSION: core routes ==================
class TestRegression:
    @pytest.mark.parametrize("endpoint", [
        "/clienti", "/articoli", "/listini", "/ddt", "/offerte", "/ordinativi",
        "/fatture", "/sospesi", "/fornitori", "/costi",
    ])
    def test_endpoint_reachable(self, admin_headers, endpoint):
        r = requests.get(f"{API}{endpoint}", headers=admin_headers, timeout=15)
        assert r.status_code == 200, f"{endpoint}: {r.status_code} {r.text[:200]}"

    def test_reports_json_endpoints(self, admin_headers):
        for tipo in ["fatturato", "produzione", "costo-kg", "marginalita", "aging-sospesi", "km-automezzi"]:
            ep = f"/reports/{tipo}"
            if tipo == "aging-sospesi":
                r = requests.get(f"{API}{ep}", headers=admin_headers, timeout=15)
            else:
                r = requests.get(f"{API}{ep}?anno=2026", headers=admin_headers, timeout=15)
            assert r.status_code == 200, f"{ep}: {r.status_code}"
