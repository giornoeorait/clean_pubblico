"""
CleanTec backend API regression tests.
Covers: auth, RBAC, CRUD (clienti, articoli, macchine), ritiri, lotti + stato chain,
lavorazioni, consegne, non-conformita, fatture, dashboard KPI, users, audit-log, health.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://wash-ops-central.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

CREDS = {
    "admin": ("admin@cleantec.it", "admin123"),
    "produzione": ("produzione@cleantec.it", "produzione123"),
    "logistica": ("logistica@cleantec.it", "logistica123"),
    "qualita": ("qualita@cleantec.it", "qualita123"),
    "contabilita": ("contabilita@cleantec.it", "contabilita123"),
}

STATI_LOTTO = ["ritirato", "ricevuto", "smistato", "lavato", "asciugato", "stirato", "confezionato", "pronto", "consegnato"]


# =========== Fixtures ===========
@pytest.fixture(scope="session")
def tokens():
    out = {}
    for role, (email, pwd) in CREDS.items():
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=20)
        assert r.status_code == 200, f"Login failed for {role}: {r.status_code} {r.text}"
        data = r.json()
        assert "token" in data and "user" in data
        out[role] = data["token"]
    return out


def H(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# =========== Health ===========
def test_health():
    r = requests.get(f"{API}/health", timeout=10)
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "ok"
    assert j["db"] == "ok"


# =========== Auth ===========
def test_login_admin_returns_user_and_token():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@cleantec.it", "password": "admin123"})
    assert r.status_code == 200
    j = r.json()
    assert "token" in j and isinstance(j["token"], str) and len(j["token"]) > 20
    assert "user" in j
    assert j["user"]["email"] == "admin@cleantec.it"
    assert j["user"]["role"] == "admin"
    assert "password_hash" not in j["user"]
    assert "_id" not in j["user"]


def test_login_invalid_credentials():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@cleantec.it", "password": "wrong"})
    assert r.status_code == 401


def test_auth_me_requires_auth():
    r = requests.get(f"{API}/auth/me")
    assert r.status_code == 401


def test_auth_me_with_token(tokens):
    r = requests.get(f"{API}/auth/me", headers=H(tokens["admin"]))
    assert r.status_code == 200
    u = r.json()
    assert u["email"] == "admin@cleantec.it"
    assert "password_hash" not in u
    assert "_id" not in u


@pytest.mark.parametrize("role", ["admin", "produzione", "logistica", "qualita", "contabilita"])
def test_all_roles_login(role, tokens):
    # tokens fixture already validates each login; just assert role is correct
    r = requests.get(f"{API}/auth/me", headers=H(tokens[role]))
    assert r.status_code == 200
    assert r.json()["role"] == role


# =========== Clienti ===========
def test_list_clienti_seeded(tokens):
    r = requests.get(f"{API}/clienti", headers=H(tokens["admin"]))
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 5
    for c in data:
        assert "_id" not in c
        assert "id" in c


def test_create_update_delete_cliente(tokens):
    payload = {
        "ragione_sociale": "TEST_Cliente_X",
        "partita_iva": "IT00000000001",
        "tipologia": "hotel",
    }
    # Create (contabilita allowed)
    r = requests.post(f"{API}/clienti", headers=H(tokens["contabilita"]), json=payload)
    assert r.status_code == 200, r.text
    c = r.json()
    cid = c["id"]
    assert c["ragione_sociale"] == "TEST_Cliente_X"

    # GET by id
    g = requests.get(f"{API}/clienti/{cid}", headers=H(tokens["admin"]))
    assert g.status_code == 200
    assert g.json()["ragione_sociale"] == "TEST_Cliente_X"

    # PATCH
    p = requests.patch(f"{API}/clienti/{cid}", headers=H(tokens["contabilita"]), json={"ragione_sociale": "TEST_Cliente_Y"})
    assert p.status_code == 200
    g2 = requests.get(f"{API}/clienti/{cid}", headers=H(tokens["admin"])).json()
    assert g2["ragione_sociale"] == "TEST_Cliente_Y"

    # DELETE
    d = requests.delete(f"{API}/clienti/{cid}", headers=H(tokens["contabilita"]))
    assert d.status_code == 200
    g3 = requests.get(f"{API}/clienti/{cid}", headers=H(tokens["admin"]))
    assert g3.status_code == 404


# =========== Articoli / Macchine ===========
def test_articoli_seeded(tokens):
    r = requests.get(f"{API}/articoli", headers=H(tokens["admin"]))
    assert r.status_code == 200
    assert len(r.json()) >= 6


def test_macchine_seeded(tokens):
    r = requests.get(f"{API}/macchine", headers=H(tokens["admin"]))
    assert r.status_code == 200
    assert len(r.json()) >= 7


# =========== Ritiri ===========
def test_create_ritiro(tokens):
    clienti = requests.get(f"{API}/clienti", headers=H(tokens["admin"])).json()
    cli = clienti[0]
    payload = {
        "cliente_id": cli["id"],
        "data_ritiro": "2026-01-20",
        "operatore": "Test Op",
        "peso_totale": 50.0,
        "quantita_totale": 25,
    }
    r = requests.post(f"{API}/ritiri", headers=H(tokens["logistica"]), json=payload)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["numero"].startswith("RIT-") and len(doc["numero"]) >= 12
    assert doc["stato"] == "creato"


# =========== Lotti + stato chain ===========
def test_lotto_creation_and_state_transitions(tokens):
    clienti = requests.get(f"{API}/clienti", headers=H(tokens["admin"])).json()
    articoli = requests.get(f"{API}/articoli", headers=H(tokens["admin"])).json()
    ritiro_payload = {
        "cliente_id": clienti[0]["id"],
        "data_ritiro": "2026-01-20",
        "operatore": "Test Op",
    }
    rit = requests.post(f"{API}/ritiri", headers=H(tokens["logistica"]), json=ritiro_payload).json()

    lot_payload = {
        "ritiro_id": rit["id"],
        "cliente_id": clienti[0]["id"],
        "articolo_id": articoli[0]["id"],
        "quantita": 50,
        "peso": 30.0,
    }
    r = requests.post(f"{API}/lotti", headers=H(tokens["produzione"]), json=lot_payload)
    assert r.status_code == 200, r.text
    lotto = r.json()
    lid = lotto["id"]
    assert lotto["stato_corrente"] == "ritirato"
    assert isinstance(lotto["storico_stati"], list) and len(lotto["storico_stati"]) == 1
    assert lotto["storico_stati"][0]["stato"] == "ritirato"

    # Chain transitions
    for target in STATI_LOTTO[1:]:
        r = requests.post(f"{API}/lotti/{lid}/cambia-stato", headers=H(tokens["produzione"]),
                          json={"nuovo_stato": target, "esito": "ok", "note": f"to {target}"})
        assert r.status_code == 200, f"Failed transition to {target}: {r.text}"
        assert r.json()["nuovo_stato"] == target

    final = requests.get(f"{API}/lotti/{lid}", headers=H(tokens["admin"])).json()
    assert final["stato_corrente"] == "consegnato"
    assert len(final["storico_stati"]) == len(STATI_LOTTO)

    # Invalid state
    r = requests.post(f"{API}/lotti/{lid}/cambia-stato", headers=H(tokens["admin"]),
                      json={"nuovo_stato": "invalid_state"})
    assert r.status_code == 400


def test_lotti_filter_by_stato(tokens):
    r = requests.get(f"{API}/lotti?stato=pronto", headers=H(tokens["admin"]))
    assert r.status_code == 200
    for l in r.json():
        assert l["stato_corrente"] == "pronto"


# =========== Lavorazioni ===========
def test_create_lavorazione(tokens):
    lotti = requests.get(f"{API}/lotti", headers=H(tokens["admin"])).json()
    assert lotti
    payload = {"lotto_id": lotti[0]["id"], "tipo": "lavaggio", "temperatura": 60, "tempo_min": 45}
    r = requests.post(f"{API}/lavorazioni", headers=H(tokens["produzione"]), json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["stato"] == "pending"


# =========== Consegne ===========
def test_create_update_consegna(tokens):
    clienti = requests.get(f"{API}/clienti", headers=H(tokens["admin"])).json()
    payload = {"cliente_id": clienti[0]["id"], "lotti_ids": [], "data_prevista": "2026-01-25", "autista": "Test Driver"}
    r = requests.post(f"{API}/consegne", headers=H(tokens["logistica"]), json=payload)
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    assert r.json()["stato"] == "pianificata"

    p = requests.patch(f"{API}/consegne/{cid}", headers=H(tokens["logistica"]), json={"stato": "consegnata"})
    assert p.status_code == 200


# =========== Non-conformita ===========
def test_create_nc(tokens):
    payload = {"tipo_difetto": "Macchia persistente", "gravita": "media"}
    r = requests.post(f"{API}/non-conformita", headers=H(tokens["qualita"]), json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["stato"] == "aperta"


# =========== Fatture ===========
def test_create_fattura_autocalc(tokens):
    clienti = requests.get(f"{API}/clienti", headers=H(tokens["admin"])).json()
    payload = {
        "cliente_id": clienti[0]["id"],
        "data": "2026-01-20",
        "righe": [
            {"descrizione": "Lav", "quantita": 10, "prezzo": 5.0},
            {"descrizione": "Lav2", "quantita": 4, "prezzo": 12.5},
        ],
        "iva_pct": 22,
    }
    r = requests.post(f"{API}/fatture", headers=H(tokens["contabilita"]), json=payload)
    assert r.status_code == 200, r.text
    f = r.json()
    # imponibile = 10*5 + 4*12.5 = 50 + 50 = 100
    assert f["imponibile"] == 100.0
    assert f["iva"] == 22.0
    assert f["totale"] == 122.0
    assert f["numero"].startswith("FT-")


# =========== Dashboard KPI ===========
def test_dashboard_kpi(tokens):
    r = requests.get(f"{API}/dashboard/kpi", headers=H(tokens["admin"]))
    assert r.status_code == 200, r.text
    j = r.json()
    for key in [
        "kg_oggi", "lotti_totali", "lotti_attivi", "macchine_in_uso",
        "macchine_disponibili", "macchine_totali", "nc_aperte", "consegne_oggi",
        "puntualita_pct", "fatturato_mese", "trend_kg_7gg", "stati_distribution",
    ]:
        assert key in j, f"missing {key}"
    assert isinstance(j["trend_kg_7gg"], list) and len(j["trend_kg_7gg"]) == 7
    assert isinstance(j["stati_distribution"], list) and len(j["stati_distribution"]) == 9
    assert {s["stato"] for s in j["stati_distribution"]} == set(STATI_LOTTO)


# =========== Users / Audit-log admin ===========
def test_users_admin_only(tokens):
    r = requests.get(f"{API}/users", headers=H(tokens["admin"]))
    assert r.status_code == 200
    users = r.json()
    assert len(users) >= 5
    for u in users:
        assert "password_hash" not in u
        assert "_id" not in u


def test_users_non_admin_forbidden(tokens):
    r = requests.get(f"{API}/users", headers=H(tokens["produzione"]))
    assert r.status_code == 403


def test_audit_log_admin(tokens):
    r = requests.get(f"{API}/audit-log", headers=H(tokens["admin"]))
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    if len(items) >= 2:
        # sorted desc by timestamp
        assert items[0]["timestamp"] >= items[-1]["timestamp"]


# =========== RBAC ===========
def test_rbac_produzione_cannot_post_fattura(tokens):
    clienti = requests.get(f"{API}/clienti", headers=H(tokens["admin"])).json()
    payload = {"cliente_id": clienti[0]["id"], "data": "2026-01-20", "righe": [], "iva_pct": 22}
    r = requests.post(f"{API}/fatture", headers=H(tokens["produzione"]), json=payload)
    assert r.status_code == 403


def test_rbac_logistica_cannot_delete_articoli(tokens):
    articoli = requests.get(f"{API}/articoli", headers=H(tokens["admin"])).json()
    r = requests.delete(f"{API}/articoli/{articoli[0]['id']}", headers=H(tokens["logistica"]))
    assert r.status_code == 403
