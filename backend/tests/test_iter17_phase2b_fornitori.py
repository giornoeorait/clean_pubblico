"""FASE 2b — Fornitori + DDT ricevuti + Fatture passive."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:3000").rstrip("/")
API = f"{BASE_URL}/api"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def admin_token():
    return _login("admin@cleantec.it", "admin123")


@pytest.fixture(scope="session")
def cont_token():
    return _login("contabilita@cleantec.it", "contabilita123")


@pytest.fixture(scope="session")
def logistica_token():
    return _login("logistica@cleantec.it", "logistica123")


def H(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ======================== FORNITORI CRUD ========================

@pytest.fixture(scope="session")
def created_fornitore(admin_token):
    body = {
        "ragione_sociale": f"TEST Fornitore {uuid.uuid4().hex[:6]}",
        "partita_iva": f"IT{uuid.uuid4().int % 10**11:011d}",
        "indirizzo": "Via Test 1",
        "email": f"test_{uuid.uuid4().hex[:6]}@fornitore.it",
        "telefono": "+39 000 000",
        "categoria": "prodotti",
    }
    r = requests.post(f"{API}/fornitori", json=body, headers=H(admin_token))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ragione_sociale"] == body["ragione_sociale"]
    assert "id" in data
    return data


def test_01_list_fornitori(admin_token, created_fornitore):
    r = requests.get(f"{API}/fornitori", headers=H(admin_token))
    assert r.status_code == 200
    ids = [f["id"] for f in r.json()]
    assert created_fornitore["id"] in ids


def test_02_filter_q_and_categoria(admin_token, created_fornitore):
    r = requests.get(f"{API}/fornitori?q=TEST", headers=H(admin_token))
    assert r.status_code == 200
    r2 = requests.get(f"{API}/fornitori?categoria=prodotti", headers=H(admin_token))
    assert r2.status_code == 200
    assert any(f["id"] == created_fornitore["id"] for f in r2.json())


def test_03_get_fornitore_404(admin_token):
    r = requests.get(f"{API}/fornitori/nonexistent", headers=H(admin_token))
    assert r.status_code == 404


def test_04_patch_fornitore(admin_token, created_fornitore):
    r = requests.patch(f"{API}/fornitori/{created_fornitore['id']}",
                       json={"note": "TEST updated"}, headers=H(admin_token))
    assert r.status_code == 200
    r2 = requests.get(f"{API}/fornitori/{created_fornitore['id']}", headers=H(admin_token))
    assert r2.json()["note"] == "TEST updated"


def test_05_rbac_logistica_cannot_create_fornitore(logistica_token):
    body = {
        "ragione_sociale": "TEST Nope",
        "partita_iva": "IT12345678901",
        "indirizzo": "Via",
        "email": "nope@test.it",
        "telefono": "000",
        "categoria": "prodotti",
    }
    r = requests.post(f"{API}/fornitori", json=body, headers=H(logistica_token))
    assert r.status_code == 403


def test_06_rbac_contabilita_can_create_fornitore(cont_token):
    body = {
        "ragione_sociale": f"TEST Cont {uuid.uuid4().hex[:6]}",
        "partita_iva": f"IT{uuid.uuid4().int % 10**11:011d}",
        "indirizzo": "Via Cont 1",
        "email": f"cont_{uuid.uuid4().hex[:6]}@test.it",
        "telefono": "111",
        "categoria": "servizi",
    }
    r = requests.post(f"{API}/fornitori", json=body, headers=H(cont_token))
    assert r.status_code == 200


# ======================== DDT FORNITORE ========================

@pytest.fixture(scope="session")
def created_ddt_forn(admin_token, created_fornitore):
    body = {
        "fornitore_id": created_fornitore["id"],
        "numero_fornitore": f"FOR-DDT-{uuid.uuid4().hex[:4]}",
        "data": "2026-01-15",
        "righe": [
            {"descrizione": "Detergente X", "quantita": 10, "unita_misura": "L", "prezzo_unitario": 12.5},
            {"descrizione": "DPI Guanti", "quantita": 5, "unita_misura": "pz", "prezzo_unitario": 3.4},
        ],
        "note": "TEST DDT",
    }
    r = requests.post(f"{API}/ddt-fornitore", json=body, headers=H(admin_token))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["numero"].startswith("FORN-DDT-")
    assert d["totale"] == round(10 * 12.5 + 5 * 3.4, 2)
    assert d["stato_fatturazione"] == "non_fatturato"
    assert d["fornitore_snapshot"]["ragione_sociale"] == created_fornitore["ragione_sociale"]
    return d


def test_10_ddt_created_with_progressive_number(created_ddt_forn):
    assert "FORN-DDT-" in created_ddt_forn["numero"]


def test_11_ddt_list_filter_fornitore(admin_token, created_fornitore, created_ddt_forn):
    r = requests.get(f"{API}/ddt-fornitore?fornitore_id={created_fornitore['id']}", headers=H(admin_token))
    assert r.status_code == 200
    assert any(d["id"] == created_ddt_forn["id"] for d in r.json())


def test_12_patch_ddt_righe(admin_token, created_ddt_forn):
    body = {"righe": [{"descrizione": "Nuovo", "quantita": 2, "unita_misura": "pz", "prezzo_unitario": 10}]}
    r = requests.patch(f"{API}/ddt-fornitore/{created_ddt_forn['id']}", json=body, headers=H(admin_token))
    assert r.status_code == 200
    assert r.json()["totale"] == 20.0


def test_13_cannot_delete_fornitore_with_ddt(admin_token, created_fornitore):
    r = requests.delete(f"{API}/fornitori/{created_fornitore['id']}", headers=H(admin_token))
    assert r.status_code == 409


# ======================== FATTURE FORNITORE ========================

@pytest.fixture(scope="session")
def created_fattura_forn(admin_token, created_fornitore, created_ddt_forn):
    # ddt-fatturabili endpoint
    r = requests.get(f"{API}/fatture-fornitore/ddt-fatturabili/{created_fornitore['id']}", headers=H(admin_token))
    assert r.status_code == 200
    ids = [d["id"] for d in r.json()]
    assert created_ddt_forn["id"] in ids

    body = {
        "fornitore_id": created_fornitore["id"],
        "numero_fornitore": f"FT-{uuid.uuid4().hex[:4]}",
        "data": "2026-01-20",
        "data_scadenza": "2026-02-20",
        "ddt_fornitore_ids": [created_ddt_forn["id"]],
        "iva_perc": 22.0,
    }
    r = requests.post(f"{API}/fatture-fornitore", json=body, headers=H(admin_token))
    assert r.status_code == 200, r.text
    f = r.json()
    assert f["numero"].startswith("FORN-FT-")
    # imponibile = 20 (dopo patch_ddt_righe) o 142. Usiamo quanto calcolato dal server
    assert f["iva"] == round(f["imponibile"] * 0.22, 2)
    assert f["totale"] == round(f["imponibile"] + f["iva"], 2)
    assert f["stato_pagamento"] == "da_pagare"
    return f


def test_20_ddt_marked_fatturato_after_invoice(admin_token, created_ddt_forn, created_fattura_forn):
    r = requests.get(f"{API}/ddt-fornitore", headers=H(admin_token))
    assert r.status_code == 200
    d = next((x for x in r.json() if x["id"] == created_ddt_forn["id"]), None)
    assert d is not None
    assert d["stato_fatturazione"] == "fatturato"
    assert d["fattura_fornitore_id"] == created_fattura_forn["id"]


def test_21_cannot_patch_ddt_already_fatturato(admin_token, created_ddt_forn):
    r = requests.patch(f"{API}/ddt-fornitore/{created_ddt_forn['id']}",
                       json={"note": "nope"}, headers=H(admin_token))
    assert r.status_code == 409


def test_22_cannot_delete_ddt_already_fatturato(admin_token, created_ddt_forn):
    r = requests.delete(f"{API}/ddt-fornitore/{created_ddt_forn['id']}", headers=H(admin_token))
    assert r.status_code == 409


def test_23_fattura_righe_inline_mode(admin_token, created_fornitore):
    body = {
        "fornitore_id": created_fornitore["id"],
        "numero_fornitore": f"MAN-{uuid.uuid4().hex[:4]}",
        "data": "2026-01-22",
        "righe": [
            {"descrizione": "Servizio", "quantita": 1, "unita_misura": "pz", "prezzo_unitario": 100.0},
        ],
        "iva_perc": 22.0,
    }
    r = requests.post(f"{API}/fatture-fornitore", json=body, headers=H(admin_token))
    assert r.status_code == 200, r.text
    f = r.json()
    assert f["imponibile"] == 100.0
    assert f["iva"] == 22.0
    assert f["totale"] == 122.0
    assert f["ddt_fornitore_ids"] == []


def test_24_paga_fattura(admin_token, created_fattura_forn):
    r = requests.patch(f"{API}/fatture-fornitore/{created_fattura_forn['id']}/paga", headers=H(admin_token))
    assert r.status_code == 200
    assert r.json()["stato_pagamento"] == "pagata"
    assert r.json()["data_pagamento"] is not None


def test_25_paga_twice_409(admin_token, created_fattura_forn):
    r = requests.patch(f"{API}/fatture-fornitore/{created_fattura_forn['id']}/paga", headers=H(admin_token))
    assert r.status_code == 409


def test_26_profilo_fornitore(admin_token, created_fornitore):
    r = requests.get(f"{API}/fornitori/{created_fornitore['id']}/profilo", headers=H(admin_token))
    assert r.status_code == 200
    p = r.json()
    assert p["fornitore"]["id"] == created_fornitore["id"]
    assert "ddts" in p and "fatture" in p
    assert p["stats"]["ddt_totali"] >= 1
    assert p["stats"]["fatture_totali"] >= 1
    assert p["stats"]["pagato_totale"] >= 0
    assert p["stats"]["spesa_totale"] > 0


def test_27_delete_fattura_reopens_ddt(admin_token, created_fornitore):
    # Create fresh DDT + fattura for this test
    ddt_body = {
        "fornitore_id": created_fornitore["id"],
        "numero_fornitore": f"R-{uuid.uuid4().hex[:4]}",
        "data": "2026-01-23",
        "righe": [{"descrizione": "X", "quantita": 1, "unita_misura": "pz", "prezzo_unitario": 50}],
    }
    ddt = requests.post(f"{API}/ddt-fornitore", json=ddt_body, headers=H(admin_token)).json()

    ft_body = {
        "fornitore_id": created_fornitore["id"],
        "numero_fornitore": f"RF-{uuid.uuid4().hex[:4]}",
        "data": "2026-01-24",
        "ddt_fornitore_ids": [ddt["id"]],
    }
    ft = requests.post(f"{API}/fatture-fornitore", json=ft_body, headers=H(admin_token)).json()

    r = requests.delete(f"{API}/fatture-fornitore/{ft['id']}", headers=H(admin_token))
    assert r.status_code == 200

    # DDT should be reopened
    r2 = requests.get(f"{API}/ddt-fornitore", headers=H(admin_token))
    d = next((x for x in r2.json() if x["id"] == ddt["id"]), None)
    assert d["stato_fatturazione"] == "non_fatturato"
    assert d["fattura_fornitore_id"] is None


def test_28_rbac_logistica_cannot_create_fattura(logistica_token, created_fornitore):
    body = {
        "fornitore_id": created_fornitore["id"],
        "numero_fornitore": "X",
        "data": "2026-01-01",
        "righe": [{"descrizione": "X", "quantita": 1, "unita_misura": "pz", "prezzo_unitario": 1}],
    }
    r = requests.post(f"{API}/fatture-fornitore", json=body, headers=H(logistica_token))
    assert r.status_code == 403


def test_29_rbac_contabilita_cannot_delete_fornitore(cont_token, created_fornitore):
    r = requests.delete(f"{API}/fornitori/{created_fornitore['id']}", headers=H(cont_token))
    assert r.status_code == 403


def test_30_regression_smoke_other_endpoints(admin_token):
    for ep in ["/clienti", "/articoli", "/listini", "/ddt", "/offerte", "/ordinativi", "/fatture", "/dashboard/kpi"]:
        r = requests.get(f"{API}{ep}", headers=H(admin_token))
        assert r.status_code == 200, f"regression {ep}: {r.status_code}"
