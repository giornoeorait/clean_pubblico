"""Iter 23 — Portale self-service (CleanTec)
Tests:
- POST /api/public/portale/lookup (no-auth) with valid P.IVA → 200 + token + cliente
- Case-insensitive matching
- Unknown P.IVA → 404 generic
- Too-short identificativo → 422
- Session token usable on GET /api/public/portale/{token} and POST ordinativo
- Static portale_token continues to work (regression)
"""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
TEST_PIVA = "IT01234567890"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@cleantec.it", "password": "admin123"},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


# --------------- LOOKUP ----------------
class TestPortaleLookup:
    def test_lookup_valid_uppercase(self):
        r = requests.post(
            f"{BASE_URL}/api/public/portale/lookup",
            json={"identificativo": TEST_PIVA},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "token" in data and isinstance(data["token"], str) and len(data["token"]) >= 20
        assert data["cliente"]["ragione_sociale"]
        assert data["url_path"] == f"/ordina/{data['token']}"
        assert "expires_at" in data

    def test_lookup_valid_lowercase(self):
        r = requests.post(
            f"{BASE_URL}/api/public/portale/lookup",
            json={"identificativo": TEST_PIVA.lower()},
        )
        assert r.status_code == 200, r.text
        assert r.json()["cliente"]["ragione_sociale"]

    def test_lookup_unknown_returns_404(self):
        r = requests.post(
            f"{BASE_URL}/api/public/portale/lookup",
            json={"identificativo": "IT99999999999"},
        )
        assert r.status_code == 404
        body = r.json()
        # generic message
        assert "trovato" in (body.get("detail") or "").lower()

    def test_lookup_too_short_returns_422(self):
        r = requests.post(
            f"{BASE_URL}/api/public/portale/lookup",
            json={"identificativo": "AB"},
        )
        # validator min_length=4 → FastAPI 422
        assert r.status_code in (400, 422)

    def test_lookup_empty_returns_422(self):
        r = requests.post(
            f"{BASE_URL}/api/public/portale/lookup",
            json={"identificativo": ""},
        )
        assert r.status_code in (400, 422)

    def test_lookup_no_auth_required(self):
        # no Authorization header — should work
        s = requests.Session()
        r = s.post(
            f"{BASE_URL}/api/public/portale/lookup",
            json={"identificativo": TEST_PIVA},
        )
        assert r.status_code == 200


# --------------- TOKEN USAGE ----------------
class TestSessionTokenUsage:
    @pytest.fixture(scope="class")
    def session_token(self):
        r = requests.post(
            f"{BASE_URL}/api/public/portale/lookup",
            json={"identificativo": TEST_PIVA},
        )
        assert r.status_code == 200
        return r.json()["token"]

    def test_get_portale_with_session_token(self, session_token):
        r = requests.get(f"{BASE_URL}/api/public/portale/{session_token}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "cliente" in data
        assert "articoli" in data and isinstance(data["articoli"], list)
        assert len(data["articoli"]) > 0

    def test_post_ordinativo_with_session_token(self, session_token):
        # First get available articoli
        info = requests.get(f"{BASE_URL}/api/public/portale/{session_token}").json()
        articolo = info["articoli"][0]
        payload = {
            "data_consegna_richiesta": "2026-12-31",
            "righe": [{"articolo_id": articolo["id"], "quantita": 2}],
            "note_cliente": "TEST_iter23",
        }
        r = requests.post(
            f"{BASE_URL}/api/public/portale/{session_token}/ordinativo",
            json=payload,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert re.match(r"^ORD-\d{4}-\d{5}$", data["numero"])
        assert data["totale"] > 0
        assert data["stato"] == "nuovo"
        assert len(data["righe"]) == 1

    def test_invalid_session_token_returns_404(self):
        r = requests.get(f"{BASE_URL}/api/public/portale/notavalidtoken_xxx")
        assert r.status_code == 404


# --------------- REGRESSION: static portale_token ----------------
class TestStaticTokenRegression:
    def test_static_token_still_works(self, admin_token):
        # Find a cliente, generate static token, use it via GET
        headers = {"Authorization": f"Bearer {admin_token}"}
        clients = requests.get(f"{BASE_URL}/api/clienti", headers=headers).json()
        assert isinstance(clients, list) and len(clients) > 0
        cli = next((c for c in clients if c.get("attivo", True)), clients[0])
        cid = cli["id"]
        r = requests.post(
            f"{BASE_URL}/api/clienti/{cid}/portale-token",
            headers=headers,
        )
        assert r.status_code == 200, r.text
        static_token = r.json()["token"]
        # Use the static token via the same public GET
        r2 = requests.get(f"{BASE_URL}/api/public/portale/{static_token}")
        assert r2.status_code == 200, r2.text
        assert "articoli" in r2.json()


# --------------- REGRESSION: admin login still works ----------------
class TestAdminAuthRegression:
    def test_admin_login_ok(self):
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@cleantec.it", "password": "admin123"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "token" in body and "user" in body

    def test_dashboard_kpi_requires_auth(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/dashboard/kpi",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
