"""Backend tests for Totem Produzione feature (iter38)."""
import os
import jwt
import pytest
import requests
from datetime import datetime, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

API = f"{BASE_URL}/api"

TOTEM_EMAIL = "totem@cleantec.it"
TOTEM_PASSWORD = "totem123"
ADMIN_EMAIL = "admin@cleantec.it"
ADMIN_PASSWORD = "admin123"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="module")
def totem_session():
    data = _login(TOTEM_EMAIL, TOTEM_PASSWORD)
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {data['token']}"})
    return {"session": s, "token": data["token"], "user": data["user"]}


@pytest.fixture(scope="module")
def admin_session():
    data = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {data['token']}"})
    return {"session": s, "token": data["token"], "user": data["user"]}


# ---- Login / JWT ----

def test_totem_login_returns_produzione_role_and_90d_exp():
    data = _login(TOTEM_EMAIL, TOTEM_PASSWORD)
    assert data["user"]["role"] == "produzione"
    payload = jwt.decode(data["token"], options={"verify_signature": False})
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    delta_days = (exp - datetime.now(timezone.utc)).days
    assert 85 <= delta_days <= 91, f"Expected ~90d, got {delta_days}"


def test_admin_login_still_12h():
    data = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    payload = jwt.decode(data["token"], options={"verify_signature": False})
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    delta_h = (exp - datetime.now(timezone.utc)).total_seconds() / 3600
    assert 10 <= delta_h <= 13, f"Expected ~12h, got {delta_h}h"


# ---- Ordinativi access ----

def test_produzione_can_list_ordinativi(totem_session):
    r = totem_session["session"].get(f"{API}/ordinativi", timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def _get_or_create_order(admin_session):
    s = admin_session["session"]
    # Try to find an existing "nuovo" order
    r = s.get(f"{API}/ordinativi?stato=nuovo", timeout=15)
    assert r.status_code == 200
    lst = r.json()
    if lst:
        return lst[0]
    # Create one
    clienti = s.get(f"{API}/clienti", timeout=15).json()
    articoli = s.get(f"{API}/articoli", timeout=15).json()
    assert clienti and articoli
    cli = clienti[0]
    payload = {
        "cliente_id": cli["id"],
        "data_consegna_richiesta": "2026-12-31",
        "righe": [{"articolo_id": articoli[0]["id"], "quantita": 5}],
    }
    r = s.post(f"{API}/ordinativi", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def test_produzione_get_ordinativo_detail(totem_session, admin_session):
    ord_doc = _get_or_create_order(admin_session)
    r = totem_session["session"].get(f"{API}/ordinativi/{ord_doc['id']}", timeout=15)
    assert r.status_code == 200
    assert r.json()["id"] == ord_doc["id"]


def test_produzione_patch_metti_in_lavorazione(totem_session, admin_session):
    ord_doc = _get_or_create_order(admin_session)
    r = totem_session["session"].patch(
        f"{API}/ordinativi/{ord_doc['id']}/produzione",
        json={"stato": "in_lavorazione", "operatore": "Mario Rossi"}, timeout=15,
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["stato"] == "in_lavorazione"
    assert j.get("operatore_produzione") == "Mario Rossi"


def test_produzione_patch_righe_eseguite(totem_session, admin_session):
    # Fresh order in lavorazione
    ord_doc = _get_or_create_order(admin_session)
    s = totem_session["session"]
    s.patch(f"{API}/ordinativi/{ord_doc['id']}/produzione",
            json={"stato": "in_lavorazione", "operatore": "Test"}, timeout=15)
    n = len(ord_doc["righe"])
    flags = [True] + [False] * (n - 1) if n > 1 else [True]
    r = s.patch(f"{API}/ordinativi/{ord_doc['id']}/produzione",
                json={"righe_eseguite": flags}, timeout=15)
    assert r.status_code == 200
    assert r.json()["righe_eseguite"] == flags


def test_produzione_patch_righe_eseguite_wrong_length_422(totem_session, admin_session):
    ord_doc = _get_or_create_order(admin_session)
    r = totem_session["session"].patch(
        f"{API}/ordinativi/{ord_doc['id']}/produzione",
        json={"righe_eseguite": [True] * (len(ord_doc["righe"]) + 5)}, timeout=15,
    )
    assert r.status_code == 422, r.text


def test_produzione_converti_ddt_and_pdf(totem_session, admin_session):
    # Need a fresh order
    ord_doc = _get_or_create_order(admin_session)
    s = totem_session["session"]
    # Ensure not already converted
    cur = s.get(f"{API}/ordinativi/{ord_doc['id']}", timeout=15).json()
    if cur["stato"] == "convertito_ddt":
        ord_doc = _get_or_create_order(admin_session)
    r = s.post(f"{API}/ordinativi/{ord_doc['id']}/converti-ddt", timeout=20)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["stato"] == "convertito_ddt"
    assert j["ddt_id"] and j["ddt_numero"]
    # PDF download with produzione token
    pdf = s.get(f"{API}/ddt/{j['ddt_id']}/pdf", timeout=20)
    assert pdf.status_code == 200
    assert pdf.headers.get("content-type", "").startswith("application/pdf")
    assert pdf.content[:4] == b"%PDF"


def test_produzione_converti_conflict_when_already_converted(totem_session, admin_session):
    ord_doc = _get_or_create_order(admin_session)
    s = totem_session["session"]
    s.patch(f"{API}/ordinativi/{ord_doc['id']}/produzione",
            json={"stato": "in_lavorazione", "operatore": "X"}, timeout=15)
    s.post(f"{API}/ordinativi/{ord_doc['id']}/converti-ddt", timeout=20)
    # Try to patch produzione again -> 409
    r = s.patch(f"{API}/ordinativi/{ord_doc['id']}/produzione",
                json={"righe_eseguite": [True]}, timeout=15)
    assert r.status_code == 409


# ---- RBAC ----

def test_produzione_cannot_access_fatture(totem_session):
    r = totem_session["session"].get(f"{API}/fatture", timeout=15)
    assert r.status_code == 403, f"Expected 403 got {r.status_code}"


def test_produzione_cannot_access_costi(totem_session):
    r = totem_session["session"].get(f"{API}/costi", timeout=15)
    assert r.status_code == 403, f"Expected 403 got {r.status_code}"


def test_produzione_can_access_ddt_list(totem_session):
    r = totem_session["session"].get(f"{API}/ddt", timeout=15)
    # ddt is view-only for produzione — should be 200
    assert r.status_code == 200
