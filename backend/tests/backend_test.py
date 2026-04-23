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



# =========== P2 HARDENING: atomic counter, real punctuality, modular structure ===========
from concurrent.futures import ThreadPoolExecutor
import importlib


def test_atomic_counter_ritiri_concurrent_unique_numero(tokens):
    """Create N ritiri in parallel and verify all numero values are distinct
    (atomic next_seq via findOneAndUpdate + $inc)."""
    clienti = requests.get(f"{API}/clienti", headers=H(tokens["admin"])).json()
    cli_id = clienti[0]["id"]
    headers = H(tokens["logistica"])
    payload = {
        "cliente_id": cli_id,
        "data_ritiro": "2026-01-22",
        "operatore": "ParallelOp",
        "peso_totale": 1.0,
        "quantita_totale": 1,
    }

    def _post(_i):
        return requests.post(f"{API}/ritiri", headers=headers, json=payload, timeout=30)

    N = 8
    with ThreadPoolExecutor(max_workers=N) as ex:
        responses = list(ex.map(_post, range(N)))

    numeri = []
    for r in responses:
        assert r.status_code == 200, r.text
        numeri.append(r.json()["numero"])

    # All must be distinct
    assert len(set(numeri)) == N, f"Duplicate numero detected: {numeri}"
    # All must share the RIT- prefix
    for n in numeri:
        assert n.startswith("RIT-")


def test_atomic_counter_consegne_concurrent_unique_numero(tokens):
    clienti = requests.get(f"{API}/clienti", headers=H(tokens["admin"])).json()
    headers = H(tokens["logistica"])
    payload = {
        "cliente_id": clienti[0]["id"],
        "lotti_ids": [],
        "data_prevista": "2026-02-10",
        "autista": "ParDrv",
    }

    def _post(_i):
        return requests.post(f"{API}/consegne", headers=headers, json=payload, timeout=30)

    N = 6
    with ThreadPoolExecutor(max_workers=N) as ex:
        responses = list(ex.map(_post, range(N)))

    numeri = [r.json()["numero"] for r in responses if r.status_code == 200]
    assert len(numeri) == N
    assert len(set(numeri)) == N, f"Duplicate consegna numero: {numeri}"
    for n in numeri:
        assert n.startswith("CON-")


def test_patch_consegna_consegnata_sets_data_effettiva(tokens):
    """PATCH stato='consegnata' auto-sets data_consegna_effettiva=today ISO date."""
    clienti = requests.get(f"{API}/clienti", headers=H(tokens["admin"])).json()
    payload = {
        "cliente_id": clienti[0]["id"],
        "lotti_ids": [],
        "data_prevista": "2026-03-01",
        "autista": "Test",
    }
    c = requests.post(f"{API}/consegne", headers=H(tokens["logistica"]), json=payload).json()
    cid = c["id"]

    # Before PATCH - no data_consegna_effettiva
    lst_before = requests.get(f"{API}/consegne", headers=H(tokens["admin"])).json()
    target = [x for x in lst_before if x["id"] == cid][0]
    assert target.get("data_consegna_effettiva") in (None, "")

    # PATCH -> consegnata
    p = requests.patch(f"{API}/consegne/{cid}", headers=H(tokens["logistica"]), json={"stato": "consegnata"})
    assert p.status_code == 200

    # Verify persisted
    lst_after = requests.get(f"{API}/consegne", headers=H(tokens["admin"])).json()
    target2 = [x for x in lst_after if x["id"] == cid][0]
    from datetime import datetime as _dt, timezone as _tz
    today_iso = _dt.now(_tz.utc).date().isoformat()
    assert target2["stato"] == "consegnata"
    # After datetime migration: serialized as full ISO 8601 string; date portion must match today.
    val = target2.get("data_consegna_effettiva")
    assert isinstance(val, str) and val.startswith(today_iso), (
        f"Expected data_consegna_effettiva starting with {today_iso}, got {val}"
    )


def test_consegna_past_prevista_is_NOT_puntuale(tokens):
    """Delivery with past data_prevista then stato=consegnata today -> NOT puntuale
    (today > data_prevista)."""
    clienti = requests.get(f"{API}/clienti", headers=H(tokens["admin"])).json()
    past_date = "2020-01-01"
    payload = {
        "cliente_id": clienti[0]["id"],
        "lotti_ids": [],
        "data_prevista": past_date,
        "autista": "Late",
    }
    c = requests.post(f"{API}/consegne", headers=H(tokens["logistica"]), json=payload).json()
    cid = c["id"]

    # Snapshot KPI before
    kpi_before = requests.get(f"{API}/dashboard/kpi", headers=H(tokens["admin"])).json()
    consegnate_before = kpi_before["consegne_consegnate"]
    puntuali_before = kpi_before["consegne_puntuali"]

    p = requests.patch(f"{API}/consegne/{cid}", headers=H(tokens["logistica"]), json={"stato": "consegnata"})
    assert p.status_code == 200

    kpi_after = requests.get(f"{API}/dashboard/kpi", headers=H(tokens["admin"])).json()
    assert kpi_after["consegne_consegnate"] == consegnate_before + 1
    # Not puntuale -> puntuali counter unchanged
    assert kpi_after["consegne_puntuali"] == puntuali_before


def test_consegna_future_prevista_IS_puntuale(tokens):
    """Delivery with future data_prevista then stato=consegnata today -> puntuale."""
    clienti = requests.get(f"{API}/clienti", headers=H(tokens["admin"])).json()
    future_date = "2099-12-31"
    payload = {
        "cliente_id": clienti[0]["id"],
        "lotti_ids": [],
        "data_prevista": future_date,
        "autista": "OnTime",
    }
    c = requests.post(f"{API}/consegne", headers=H(tokens["logistica"]), json=payload).json()
    cid = c["id"]

    kpi_before = requests.get(f"{API}/dashboard/kpi", headers=H(tokens["admin"])).json()
    consegnate_before = kpi_before["consegne_consegnate"]
    puntuali_before = kpi_before["consegne_puntuali"]

    p = requests.patch(f"{API}/consegne/{cid}", headers=H(tokens["logistica"]), json={"stato": "consegnata"})
    assert p.status_code == 200

    kpi_after = requests.get(f"{API}/dashboard/kpi", headers=H(tokens["admin"])).json()
    assert kpi_after["consegne_consegnate"] == consegnate_before + 1
    assert kpi_after["consegne_puntuali"] == puntuali_before + 1

    # puntualita_pct recomputed correctly
    if kpi_after["consegne_consegnate"] > 0:
        expected_pct = round(
            kpi_after["consegne_puntuali"] / kpi_after["consegne_consegnate"] * 100, 1
        )
        assert kpi_after["puntualita_pct"] == expected_pct


def test_dashboard_kpi_has_punctuality_fields(tokens):
    r = requests.get(f"{API}/dashboard/kpi", headers=H(tokens["admin"]))
    assert r.status_code == 200
    j = r.json()
    for key in ["consegne_consegnate", "consegne_puntuali", "puntualita_pct"]:
        assert key in j, f"missing dashboard KPI field: {key}"
    assert isinstance(j["consegne_consegnate"], int)
    assert isinstance(j["consegne_puntuali"], int)
    assert isinstance(j["puntualita_pct"], (int, float))
    # Relationship
    assert j["consegne_puntuali"] <= j["consegne_consegnate"]
    # Default: 100.0 when zero delivered (cannot easily force zero in shared env,
    # but the math must hold whenever consegnate > 0)
    if j["consegne_consegnate"] > 0:
        expected = round(j["consegne_puntuali"] / j["consegne_consegnate"] * 100, 1)
        assert j["puntualita_pct"] == expected
    else:
        assert j["puntualita_pct"] == 100.0


# =========== PATCH typing refactor (iteration 3) ===========
def _new_cliente(tokens):
    payload = {"ragione_sociale": "TEST_PatchCliente", "tipologia": "hotel"}
    r = requests.post(f"{API}/clienti", headers=H(tokens["contabilita"]), json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def test_patch_cliente_empty_body_is_ok(tokens):
    """Empty body must return 200 (no-op PATCH) and not 422."""
    c = _new_cliente(tokens)
    r = requests.patch(f"{API}/clienti/{c['id']}", headers=H(tokens["contabilita"]), json={})
    assert r.status_code == 200, r.text
    # Unchanged
    g = requests.get(f"{API}/clienti/{c['id']}", headers=H(tokens["admin"])).json()
    assert g["ragione_sociale"] == "TEST_PatchCliente"


def test_patch_cliente_unknown_fields_ignored(tokens):
    """extra='ignore' -> unknown fields must not cause 4xx and must not be persisted."""
    c = _new_cliente(tokens)
    body = {"ragione_sociale": "TEST_PatchCliente_Renamed", "zzz_unknown": "x", "another": 123}
    r = requests.patch(f"{API}/clienti/{c['id']}", headers=H(tokens["contabilita"]), json=body)
    assert r.status_code == 200, r.text
    g = requests.get(f"{API}/clienti/{c['id']}", headers=H(tokens["admin"])).json()
    assert g["ragione_sociale"] == "TEST_PatchCliente_Renamed"
    assert "zzz_unknown" not in g
    assert "another" not in g


def test_patch_cliente_invalid_type_returns_422(tokens):
    c = _new_cliente(tokens)
    # sla_ore expects int
    r = requests.patch(f"{API}/clienti/{c['id']}", headers=H(tokens["contabilita"]),
                       json={"sla_ore": "not-an-int"})
    assert r.status_code == 422, r.text


def test_patch_articolo_invalid_prezzo_returns_422(tokens):
    articoli = requests.get(f"{API}/articoli", headers=H(tokens["admin"])).json()
    aid = articoli[0]["id"]
    r = requests.patch(f"{API}/articoli/{aid}", headers=H(tokens["contabilita"]),
                       json={"prezzo": "abc"})
    assert r.status_code == 422, r.text


def test_patch_articolo_valid_partial(tokens):
    articoli = requests.get(f"{API}/articoli", headers=H(tokens["admin"])).json()
    aid = articoli[0]["id"]
    r = requests.patch(f"{API}/articoli/{aid}", headers=H(tokens["contabilita"]),
                       json={"prezzo": 9.99, "ignored_field": True})
    assert r.status_code == 200, r.text
    g = requests.get(f"{API}/articoli/{aid}", headers=H(tokens["admin"])).json()
    assert g["prezzo"] == 9.99
    assert "ignored_field" not in g


def test_patch_macchina_invalid_capacita_returns_422(tokens):
    m = requests.get(f"{API}/macchine", headers=H(tokens["admin"])).json()
    mid = m[0]["id"]
    r = requests.patch(f"{API}/macchine/{mid}", headers=H(tokens["admin"]),
                       json={"capacita_kg": "heavy"})
    assert r.status_code == 422, r.text


def test_patch_macchina_valid(tokens):
    m = requests.get(f"{API}/macchine", headers=H(tokens["admin"])).json()
    mid = m[0]["id"]
    r = requests.patch(f"{API}/macchine/{mid}", headers=H(tokens["admin"]),
                       json={"stato": "manutenzione", "extra_garbage": "x"})
    assert r.status_code == 200, r.text
    g = [x for x in requests.get(f"{API}/macchine", headers=H(tokens["admin"])).json() if x["id"] == mid][0]
    assert g["stato"] == "manutenzione"


def test_patch_consegna_empty_body_ok_and_unknown_ignored(tokens):
    clienti = requests.get(f"{API}/clienti", headers=H(tokens["admin"])).json()
    c = requests.post(f"{API}/consegne", headers=H(tokens["logistica"]),
                      json={"cliente_id": clienti[0]["id"], "lotti_ids": [],
                            "data_prevista": "2026-04-01", "autista": "X"}).json()
    cid = c["id"]
    # Empty body
    r = requests.patch(f"{API}/consegne/{cid}", headers=H(tokens["logistica"]), json={})
    assert r.status_code == 200
    # Unknown field ignored, autista updated
    r2 = requests.patch(f"{API}/consegne/{cid}", headers=H(tokens["logistica"]),
                        json={"autista": "Y", "foo": "bar"})
    assert r2.status_code == 200
    lst = requests.get(f"{API}/consegne", headers=H(tokens["admin"])).json()
    target = [x for x in lst if x["id"] == cid][0]
    assert target["autista"] == "Y"
    assert "foo" not in target


def test_patch_lavorazione_autosets_inizio_and_fine(tokens):
    """stato=in_corso auto-sets inizio; stato=completato auto-sets fine."""
    lotti = requests.get(f"{API}/lotti", headers=H(tokens["admin"])).json()
    lav = requests.post(f"{API}/lavorazioni", headers=H(tokens["produzione"]),
                        json={"lotto_id": lotti[0]["id"], "tipo": "lavaggio"}).json()
    lid = lav["id"]

    # in_corso -> inizio set
    r = requests.patch(f"{API}/lavorazioni/{lid}", headers=H(tokens["produzione"]),
                       json={"stato": "in_corso"})
    assert r.status_code == 200
    all_lav = requests.get(f"{API}/lavorazioni", headers=H(tokens["admin"])).json()
    target = [x for x in all_lav if x["id"] == lid][0]
    assert target["stato"] == "in_corso"
    assert target.get("inizio"), f"inizio not set: {target}"

    # completato -> fine set
    r2 = requests.patch(f"{API}/lavorazioni/{lid}", headers=H(tokens["produzione"]),
                        json={"stato": "completato", "unknown_x": 1})
    assert r2.status_code == 200
    all_lav2 = requests.get(f"{API}/lavorazioni", headers=H(tokens["admin"])).json()
    t2 = [x for x in all_lav2 if x["id"] == lid][0]
    assert t2["stato"] == "completato"
    assert t2.get("fine"), f"fine not set: {t2}"
    assert "unknown_x" not in t2


def test_patch_lavorazione_invalid_type_422(tokens):
    lotti = requests.get(f"{API}/lotti", headers=H(tokens["admin"])).json()
    lav = requests.post(f"{API}/lavorazioni", headers=H(tokens["produzione"]),
                        json={"lotto_id": lotti[0]["id"], "tipo": "lavaggio"}).json()
    r = requests.patch(f"{API}/lavorazioni/{lav['id']}", headers=H(tokens["produzione"]),
                       json={"tempo_min": "sixty"})
    assert r.status_code == 422, r.text


def test_patch_nonconformita_valid_and_unknown_ignored(tokens):
    nc = requests.post(f"{API}/non-conformita", headers=H(tokens["qualita"]),
                       json={"tipo_difetto": "Macchia", "gravita": "bassa"}).json()
    nid = nc["id"]
    r = requests.patch(f"{API}/non-conformita/{nid}", headers=H(tokens["qualita"]),
                       json={"stato": "risolta", "garbage": 1})
    assert r.status_code == 200
    lst = requests.get(f"{API}/non-conformita", headers=H(tokens["admin"])).json()
    target = [x for x in lst if x["id"] == nid][0]
    assert target["stato"] == "risolta"
    assert "garbage" not in target


def test_patch_fattura_valid_and_unknown_ignored(tokens):
    clienti = requests.get(f"{API}/clienti", headers=H(tokens["admin"])).json()
    f = requests.post(f"{API}/fatture", headers=H(tokens["contabilita"]),
                      json={"cliente_id": clienti[0]["id"], "data": "2026-02-01",
                            "righe": [{"descrizione": "X", "quantita": 1, "prezzo": 10}],
                            "iva_pct": 22}).json()
    fid = f["id"]
    r = requests.patch(f"{API}/fatture/{fid}", headers=H(tokens["contabilita"]),
                       json={"stato": "pagata", "ghost_field": "x"})
    assert r.status_code == 200
    lst = requests.get(f"{API}/fatture", headers=H(tokens["admin"])).json()
    target = [x for x in lst if x["id"] == fid][0]
    assert target["stato"] == "pagata"
    assert "ghost_field" not in target


def test_patch_fattura_invalid_iva_pct_422(tokens):
    clienti = requests.get(f"{API}/clienti", headers=H(tokens["admin"])).json()
    f = requests.post(f"{API}/fatture", headers=H(tokens["contabilita"]),
                      json={"cliente_id": clienti[0]["id"], "data": "2026-02-02",
                            "righe": [], "iva_pct": 22}).json()
    r = requests.patch(f"{API}/fatture/{f['id']}", headers=H(tokens["contabilita"]),
                       json={"iva_pct": "twenty"})
    assert r.status_code == 422, r.text


def test_patch_user_password_hashed_and_reloginable(tokens):
    """Admin PATCH user password -> old pwd rejected, new pwd works, hash not leaked."""
    # Unique email per run (DELETE is a soft-delete so reusing the same email would 400)
    import uuid as _uuid
    unique = _uuid.uuid4().hex[:8]
    email = f"test_patchuser_{unique}@cleantec.it"
    create_payload = {
        "email": email,
        "password": "initial123",
        "name": "TEST_Patch_User",
        "role": "produzione",
    }

    r = requests.post(f"{API}/users", headers=H(tokens["admin"]), json=create_payload)
    assert r.status_code == 200, r.text
    new_user = r.json()
    assert "password_hash" not in new_user
    uid = new_user["id"]

    # Verify initial login
    lg1 = requests.post(f"{API}/auth/login", json={"email": email, "password": "initial123"})
    assert lg1.status_code == 200, lg1.text

    # PATCH password with unknown extras
    pat = requests.patch(f"{API}/users/{uid}", headers=H(tokens["admin"]),
                         json={"password": "newpass456", "phantom_field": True})
    assert pat.status_code == 200, pat.text
    patched = pat.json()
    assert "password_hash" not in patched
    assert "phantom_field" not in patched

    # Old pwd rejected, new works
    lg_old = requests.post(f"{API}/auth/login", json={"email": email, "password": "initial123"})
    assert lg_old.status_code == 401
    lg_new = requests.post(f"{API}/auth/login", json={"email": email, "password": "newpass456"})
    assert lg_new.status_code == 200, lg_new.text

    # Cleanup (soft delete)
    requests.delete(f"{API}/users/{uid}", headers=H(tokens["admin"]))


def test_patch_user_invalid_type_422(tokens):
    users_all = requests.get(f"{API}/users", headers=H(tokens["admin"])).json()
    uid = [u for u in users_all if u["email"] == "produzione@cleantec.it"][0]["id"]
    r = requests.patch(f"{API}/users/{uid}", headers=H(tokens["admin"]),
                       json={"attivo": "yes-please"})  # bool expected
    assert r.status_code == 422, r.text


def test_patch_user_empty_body_ok(tokens):
    users_all = requests.get(f"{API}/users", headers=H(tokens["admin"])).json()
    uid = [u for u in users_all if u["email"] == "admin@cleantec.it"][0]["id"]
    r = requests.patch(f"{API}/users/{uid}", headers=H(tokens["admin"]), json={})
    assert r.status_code == 200, r.text


def test_modular_file_structure_importable():
    """Verify the refactored modular layout is loadable (core, schemas, seed, routers)."""
    import sys
    sys.path.insert(0, "/app/backend")
    for mod in [
        "core",
        "schemas",
        "seed",
        "routers.auth",
        "routers.users",
        "routers.catalog",
        "routers.operations",
        "routers.billing",
        "routers.dashboard",
    ]:
        m = importlib.import_module(mod)
        assert m is not None, f"Cannot import {mod}"
    # server.py must stay thin (<= ~80 lines)
    with open("/app/backend/server.py") as f:
        line_count = sum(1 for _ in f)
    assert line_count <= 80, f"server.py is {line_count} lines, expected <= 80"



# =========== P2: Datetime migration (BSON native datetime) ===========
import asyncio as _asyncio
import re as _re
from datetime import datetime as _dt, timezone as _tz, timedelta as _td


def _mongo_db():
    """Direct pymongo client to verify native BSON types."""
    from pymongo import MongoClient
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    name = os.environ.get("DB_NAME", "test_database")
    return MongoClient(url)[name]


# regex for ISO 8601 strings returned by FastAPI/pydantic for datetime
_ISO_RE = _re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(\+\d{2}:\d{2}|Z)?$")


def test_to_dt_helper_parses_all_forms():
    """Unit-test core.to_dt() directly for None / '' / YYYY-MM-DD / ISO Z / ISO +00:00 / datetime passthrough."""
    import sys
    sys.path.insert(0, "/app/backend")
    from core import to_dt
    assert to_dt(None) is None
    assert to_dt("") is None
    assert to_dt("not-a-date") is None
    d1 = to_dt("2026-04-23")
    assert d1 is not None and d1.tzinfo is not None
    assert (d1.year, d1.month, d1.day, d1.hour, d1.minute, d1.second) == (2026, 4, 23, 0, 0, 0)
    d2 = to_dt("2026-04-23T10:15:00Z")
    assert d2 is not None and d2.tzinfo is not None
    assert d2.hour == 10 and d2.minute == 15
    d3 = to_dt("2026-04-23T10:15:00+00:00")
    assert d3 is not None and d3 == d2
    now = _dt.now(_tz.utc)
    d4 = to_dt(now)
    assert d4 == now
    # naive datetime is tagged UTC
    naive = _dt(2026, 4, 23, 12, 0, 0)
    d5 = to_dt(naive)
    assert d5.tzinfo is not None and d5.replace(tzinfo=None) == naive


def test_ritiri_created_at_and_data_ritiro_are_bson_datetime(tokens):
    clienti = requests.get(f"{API}/clienti", headers=H(tokens["admin"])).json()
    payload = {"cliente_id": clienti[0]["id"], "data_ritiro": "2026-01-20", "operatore": "BSONTest"}
    r = requests.post(f"{API}/ritiri", headers=H(tokens["logistica"]), json=payload)
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    db = _mongo_db()
    doc = db.ritiri.find_one({"id": rid})
    assert doc is not None
    assert isinstance(doc["created_at"], _dt), f"created_at not datetime: {type(doc['created_at'])}"
    assert isinstance(doc["data_ritiro"], _dt), f"data_ritiro not datetime: {type(doc['data_ritiro'])}"


def test_lotti_created_at_and_storico_timestamp_are_bson_datetime(tokens):
    clienti = requests.get(f"{API}/clienti", headers=H(tokens["admin"])).json()
    articoli = requests.get(f"{API}/articoli", headers=H(tokens["admin"])).json()
    rit = requests.post(f"{API}/ritiri", headers=H(tokens["logistica"]),
                        json={"cliente_id": clienti[0]["id"], "data_ritiro": "2026-01-20", "operatore": "X"}).json()
    lot = requests.post(f"{API}/lotti", headers=H(tokens["produzione"]), json={
        "ritiro_id": rit["id"], "cliente_id": clienti[0]["id"],
        "articolo_id": articoli[0]["id"], "quantita": 10, "peso": 5.0,
    }).json()
    lid = lot["id"]

    # cambia-stato appends another history entry
    r = requests.post(f"{API}/lotti/{lid}/cambia-stato", headers=H(tokens["produzione"]),
                      json={"nuovo_stato": "ricevuto", "esito": "ok"})
    assert r.status_code == 200

    db = _mongo_db()
    doc = db.lotti.find_one({"id": lid})
    assert isinstance(doc["created_at"], _dt)
    assert isinstance(doc["storico_stati"], list) and len(doc["storico_stati"]) >= 2
    for entry in doc["storico_stati"]:
        assert isinstance(entry["timestamp"], _dt), f"storico timestamp not datetime: {type(entry['timestamp'])}"


def test_consegne_dates_are_bson_datetime(tokens):
    clienti = requests.get(f"{API}/clienti", headers=H(tokens["admin"])).json()
    c = requests.post(f"{API}/consegne", headers=H(tokens["logistica"]), json={
        "cliente_id": clienti[0]["id"], "lotti_ids": [], "data_prevista": "2026-05-01", "autista": "BSON"
    }).json()
    cid = c["id"]
    p = requests.patch(f"{API}/consegne/{cid}", headers=H(tokens["logistica"]), json={"stato": "consegnata"})
    assert p.status_code == 200
    db = _mongo_db()
    doc = db.consegne.find_one({"id": cid})
    assert isinstance(doc["created_at"], _dt)
    assert isinstance(doc["data_prevista"], _dt)
    assert isinstance(doc["data_consegna_effettiva"], _dt)


def test_fatture_dates_are_bson_datetime(tokens):
    clienti = requests.get(f"{API}/clienti", headers=H(tokens["admin"])).json()
    f = requests.post(f"{API}/fatture", headers=H(tokens["contabilita"]), json={
        "cliente_id": clienti[0]["id"], "data": "2026-01-20",
        "scadenza": "2026-02-20",
        "righe": [{"descrizione": "X", "quantita": 1, "prezzo": 10}], "iva_pct": 22,
    }).json()
    fid = f["id"]
    db = _mongo_db()
    doc = db.fatture.find_one({"id": fid})
    assert isinstance(doc["created_at"], _dt)
    assert isinstance(doc["data"], _dt)
    assert isinstance(doc["scadenza"], _dt)


def test_non_conformita_created_at_is_bson_datetime(tokens):
    nc = requests.post(f"{API}/non-conformita", headers=H(tokens["qualita"]),
                       json={"tipo_difetto": "BSON_NC", "gravita": "bassa"}).json()
    db = _mongo_db()
    doc = db.non_conformita.find_one({"id": nc["id"]})
    assert isinstance(doc["created_at"], _dt)


def test_lavorazioni_inizio_fine_are_bson_datetime(tokens):
    lotti = requests.get(f"{API}/lotti", headers=H(tokens["admin"])).json()
    lav = requests.post(f"{API}/lavorazioni", headers=H(tokens["produzione"]),
                        json={"lotto_id": lotti[0]["id"], "tipo": "lavaggio"}).json()
    lid = lav["id"]
    requests.patch(f"{API}/lavorazioni/{lid}", headers=H(tokens["produzione"]), json={"stato": "in_corso"})
    requests.patch(f"{API}/lavorazioni/{lid}", headers=H(tokens["produzione"]), json={"stato": "completato"})
    db = _mongo_db()
    doc = db.lavorazioni.find_one({"id": lid})
    assert isinstance(doc["created_at"], _dt)
    assert isinstance(doc["inizio"], _dt), f"inizio type: {type(doc.get('inizio'))}"
    assert isinstance(doc["fine"], _dt), f"fine type: {type(doc.get('fine'))}"


def test_audit_log_timestamp_is_bson_datetime(tokens):
    # Trigger any audited action to ensure audit insert
    clienti = requests.get(f"{API}/clienti", headers=H(tokens["admin"])).json()
    c = requests.post(f"{API}/clienti", headers=H(tokens["contabilita"]),
                      json={"ragione_sociale": "TEST_AuditDT", "tipologia": "hotel"}).json()
    requests.delete(f"{API}/clienti/{c['id']}", headers=H(tokens["contabilita"]))
    db = _mongo_db()
    entries = list(db.audit_log.find().sort("timestamp", -1).limit(5))
    assert entries, "audit_log empty"
    for e in entries:
        assert isinstance(e["timestamp"], _dt), f"audit timestamp not datetime: {type(e['timestamp'])}"


def test_api_responses_serialize_datetime_as_iso_strings(tokens):
    """FastAPI default: datetime → ISO 8601 string in JSON responses."""
    clienti = requests.get(f"{API}/clienti", headers=H(tokens["admin"])).json()
    assert clienti, "no clienti seeded"
    first = clienti[0]
    assert "created_at" in first
    assert isinstance(first["created_at"], str)
    assert _ISO_RE.match(first["created_at"]), f"created_at not ISO: {first['created_at']}"


def test_migrate_dates_left_no_string_date_fields_in_seeded_collections():
    """After startup migrate_dates() + all new inserts use datetime, no $type:string should remain
    in configured datetime fields."""
    db = _mongo_db()
    collections = {
        "users": ["created_at"],
        "clienti": ["created_at"],
        "articoli": ["created_at"],
        "macchine": ["created_at", "manutenzione_prossima"],
        "ritiri": ["created_at", "data_ritiro"],
        "lotti": ["created_at"],
        "consegne": ["created_at", "data_prevista", "data_consegna_effettiva"],
        "fatture": ["created_at", "data", "scadenza"],
        "lavorazioni": ["created_at", "inizio", "fine"],
        "non_conformita": ["created_at"],
        "audit_log": ["timestamp"],
    }
    offenders = []
    for coll, fields in collections.items():
        for f in fields:
            n = db[coll].count_documents({f: {"$type": "string"}})
            if n:
                offenders.append(f"{coll}.{f}={n}")
    assert not offenders, f"String datetime fields remaining: {offenders}"

    # Nested lotti.storico_stati[].timestamp
    n = db.lotti.count_documents({"storico_stati.timestamp": {"$type": "string"}})
    assert n == 0, f"lotti.storico_stati[].timestamp still string in {n} docs"


def test_indexes_on_datetime_fields_exist():
    db = _mongo_db()
    expected = {
        "users": ["created_at"],
        "clienti": ["created_at"],
        "lotti": ["created_at"],
        "ritiri": ["data_ritiro"],
        "consegne": ["data_prevista", "data_consegna_effettiva"],
        "fatture": ["data"],
        "lavorazioni": ["created_at"],
        "non_conformita": ["created_at"],
        "audit_log": ["timestamp"],
    }
    missing = []
    for coll, fields in expected.items():
        idxs = db[coll].index_information()
        indexed_fields = set()
        for name, info in idxs.items():
            for k, _ in info.get("key", []):
                indexed_fields.add(k)
        for f in fields:
            if f not in indexed_fields:
                missing.append(f"{coll}.{f}")
    assert not missing, f"Missing indexes: {missing}"


def test_kpi_range_queries_use_datetime_correctly(tokens):
    """POST a fattura dated today and verify fatturato_mese increases; KPI uses $gte first_of_month."""
    clienti = requests.get(f"{API}/clienti", headers=H(tokens["admin"])).json()
    kpi_before = requests.get(f"{API}/dashboard/kpi", headers=H(tokens["admin"])).json()

    today = _dt.now(_tz.utc).date().isoformat()
    body = {
        "cliente_id": clienti[0]["id"], "data": today,
        "righe": [{"descrizione": "KPI", "quantita": 1, "prezzo": 17.0}], "iva_pct": 0,
    }
    r = requests.post(f"{API}/fatture", headers=H(tokens["contabilita"]), json=body)
    assert r.status_code == 200, r.text
    created_total = r.json()["totale"]

    kpi_after = requests.get(f"{API}/dashboard/kpi", headers=H(tokens["admin"])).json()
    # fatturato_mese must increase by at least `created_total` (allow rounding slack)
    delta = round(kpi_after["fatturato_mese"] - kpi_before["fatturato_mese"], 2)
    assert delta >= created_total - 0.01, (
        f"fatturato_mese did not include today's fattura: before={kpi_before['fatturato_mese']} "
        f"after={kpi_after['fatturato_mese']} delta={delta} expected>={created_total}"
    )


def test_kpi_consegne_oggi_counts_today_range(tokens):
    """POST consegna with data_prevista=today and verify consegne_oggi KPI increments by >=1."""
    clienti = requests.get(f"{API}/clienti", headers=H(tokens["admin"])).json()
    kpi_before = requests.get(f"{API}/dashboard/kpi", headers=H(tokens["admin"])).json()
    today = _dt.now(_tz.utc).date().isoformat()
    r = requests.post(f"{API}/consegne", headers=H(tokens["logistica"]), json={
        "cliente_id": clienti[0]["id"], "lotti_ids": [], "data_prevista": today, "autista": "KPI"
    })
    assert r.status_code == 200, r.text
    kpi_after = requests.get(f"{API}/dashboard/kpi", headers=H(tokens["admin"])).json()
    assert kpi_after["consegne_oggi"] >= kpi_before["consegne_oggi"] + 1


def test_kpi_trend_kg_7gg_has_7_buckets(tokens):
    kpi = requests.get(f"{API}/dashboard/kpi", headers=H(tokens["admin"])).json()
    assert len(kpi["trend_kg_7gg"]) == 7
    # last bucket corresponds to today (MM-DD)
    today_mmdd = _dt.now(_tz.utc).strftime("%m-%d")
    assert kpi["trend_kg_7gg"][-1]["giorno"] == today_mmdd


def test_users_created_at_is_bson_datetime(tokens):
    db = _mongo_db()
    for u in db.users.find({}, {"_id": 0, "password_hash": 0}):
        assert isinstance(u["created_at"], _dt), f"users.created_at not datetime: {u.get('email')}"
