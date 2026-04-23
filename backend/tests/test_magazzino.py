"""Magazzino (detergenti/DPI) - CRUD, movimenti, allarmi, RBAC, dashboard KPI."""
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
    "cliente": ("cliente@cleantec.it", "cliente123"),
}


@pytest.fixture(scope="module")
def tokens():
    out = {}
    for role, (email, pwd) in CREDS.items():
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=20)
        assert r.status_code == 200, f"login failed for {role}"
        out[role] = r.json()["token"]
    return out


def H(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


# ============ LIST + computed flags ============
def test_list_magazzino_seeded_items(tokens):
    r = requests.get(f"{API}/magazzino", headers=H(tokens["admin"]))
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) >= 8, f"Expected >=8 seeded items, got {len(items)}"
    for it in items:
        assert "scorta_stato" in it and it["scorta_stato"] in ("ok", "bassa", "esaurita")
        assert "scadenza_stato" in it and it["scadenza_stato"] in ("ok", "prossima", "scaduto", "na")
        assert "in_allarme" in it and isinstance(it["in_allarme"], bool)
        assert "_id" not in it


def test_list_magazzino_filter_categoria_detergente(tokens):
    r = requests.get(f"{API}/magazzino?categoria=detergente", headers=H(tokens["admin"]))
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 3, f"Expected 3 detergente items, got {len(items)}"
    assert all(it["categoria"] == "detergente" for it in items)


def test_list_magazzino_solo_allarmi(tokens):
    r = requests.get(f"{API}/magazzino?solo_allarmi=true", headers=H(tokens["admin"]))
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 1
    assert all(it["in_allarme"] is True for it in items)


# ============ Seed-data specific flag logic ============
def _items_by_codice(tokens):
    r = requests.get(f"{API}/magazzino", headers=H(tokens["admin"]))
    assert r.status_code == 200
    return {it["codice"]: it for it in r.json()}


def test_scorta_stato_logic_ok_bassa_esaurita(tokens):
    d = _items_by_codice(tokens)
    assert d["DET-UNI-25"]["scorta_stato"] == "ok"          # 140 > 50
    assert d["DET-SAN-10"]["scorta_stato"] == "bassa"       # 18 <= 20
    assert d["AMM-SOF-20"]["scorta_stato"] == "esaurita"    # 0
    assert d["DPI-MSK-FFP2"]["scorta_stato"] == "bassa"     # 8 <= 15


def test_scadenza_stato_logic(tokens):
    d = _items_by_codice(tokens)
    assert d["SBI-CLO-5"]["scadenza_stato"] == "prossima"   # +25 days
    assert d["DET-UNI-25"]["scadenza_stato"] == "ok"        # +320
    assert d["DPI-GUA-M"]["scadenza_stato"] == "na"         # None


# ============ /allarmi aggregate ============
def test_allarmi_aggregate_counts(tokens):
    r = requests.get(f"{API}/magazzino/allarmi", headers=H(tokens["admin"]))
    assert r.status_code == 200
    j = r.json()
    for k in ("totale", "scorta_bassa", "scorta_esaurita", "scadenza_prossima", "scaduti", "items"):
        assert k in j
    assert j["totale"] == 4, f"Expected totale=4, got {j['totale']}"
    assert j["scorta_esaurita"] == 1
    assert j["scorta_bassa"] == 2
    assert j["scadenza_prossima"] == 1
    assert isinstance(j["items"], list) and len(j["items"]) == 4


# ============ Dashboard KPI ============
def test_dashboard_kpi_includes_magazzino_allarmi(tokens):
    r = requests.get(f"{API}/dashboard/kpi", headers=H(tokens["admin"]))
    assert r.status_code == 200
    j = r.json()
    assert "magazzino_allarmi" in j
    assert j["magazzino_allarmi"] == 4


# ============ POST RBAC ============
def test_post_magazzino_qualita_forbidden(tokens):
    body = {"codice": "TEST_Q_001", "descrizione": "quality test", "categoria": "detergente"}
    r = requests.post(f"{API}/magazzino", headers=H(tokens["qualita"]), json=body)
    assert r.status_code == 403


def test_post_magazzino_cliente_forbidden(tokens):
    body = {"codice": "TEST_C_001", "descrizione": "cliente test", "categoria": "detergente"}
    r = requests.post(f"{API}/magazzino", headers=H(tokens["cliente"]), json=body)
    assert r.status_code == 403


def test_post_magazzino_logistica_forbidden(tokens):
    # logistica NOT in _WRITE_ROLES
    body = {"codice": "TEST_L_001", "descrizione": "log test", "categoria": "detergente"}
    r = requests.post(f"{API}/magazzino", headers=H(tokens["logistica"]), json=body)
    assert r.status_code == 403


# ============ CRUD happy path + persistence ============
@pytest.fixture(scope="module")
def created_item(tokens):
    body = {
        "codice": "TEST_MAG_001",
        "descrizione": "Test item creato da pytest",
        "categoria": "detergente",
        "unita_misura": "L",
        "scorta_attuale": 50,
        "scorta_minima": 20,
        "prezzo_unitario": 3.5,
        "fornitore": "TestFornitore",
        "scadenza": "2026-12-31T00:00:00Z",
    }
    r = requests.post(f"{API}/magazzino", headers=H(tokens["produzione"]), json=body)
    assert r.status_code == 200, f"{r.status_code}: {r.text}"
    doc = r.json()
    assert doc["codice"] == "TEST_MAG_001"
    assert "id" in doc
    assert doc["scorta_stato"] == "ok"
    yield doc
    # teardown
    requests.delete(f"{API}/magazzino/{doc['id']}", headers=H(tokens["admin"]))


def test_post_magazzino_produzione_allowed_and_persisted(tokens, created_item):
    r = requests.get(f"{API}/magazzino/{created_item['id']}", headers=H(tokens["admin"]))
    assert r.status_code == 200
    d = r.json()
    assert d["codice"] == "TEST_MAG_001"
    assert d["scadenza_stato"] in ("ok", "prossima", "scaduto")


def test_patch_magazzino_updates_fields(tokens, created_item):
    r = requests.patch(
        f"{API}/magazzino/{created_item['id']}",
        headers=H(tokens["contabilita"]),
        json={"scorta_minima": 100, "note": "updated note"},
    )
    assert r.status_code == 200
    assert r.json().get("ok") is True
    # verify persistence + flag recompute (scorta_attuale=50 <= minima=100 → bassa)
    g = requests.get(f"{API}/magazzino/{created_item['id']}", headers=H(tokens["admin"]))
    assert g.status_code == 200
    doc = g.json()
    assert doc["scorta_minima"] == 100
    assert doc["note"] == "updated note"
    assert doc["scorta_stato"] == "bassa"


def test_patch_magazzino_contabilita_allowed(tokens, created_item):
    # contabilita in _WRITE_ROLES
    r = requests.patch(
        f"{API}/magazzino/{created_item['id']}",
        headers=H(tokens["contabilita"]),
        json={"prezzo_unitario": 9.99},
    )
    assert r.status_code == 200


def test_patch_magazzino_qualita_forbidden(tokens, created_item):
    r = requests.patch(
        f"{API}/magazzino/{created_item['id']}",
        headers=H(tokens["qualita"]),
        json={"note": "hack"},
    )
    assert r.status_code == 403


# ============ Movimenti ============
def test_movimento_carico_produzione(tokens, created_item):
    item_id = created_item["id"]
    pre = requests.get(f"{API}/magazzino/{item_id}", headers=H(tokens["admin"])).json()
    pre_stock = float(pre["scorta_attuale"])
    r = requests.post(
        f"{API}/magazzino/{item_id}/movimento",
        headers=H(tokens["produzione"]),
        json={"tipo": "carico", "quantita": 15, "motivo": "acquisto", "lotto_fornitore": "LOT-001"},
    )
    assert r.status_code == 200, f"{r.status_code}: {r.text}"
    mov = r.json()
    assert mov["tipo"] == "carico"
    assert mov["quantita"] == 15
    assert mov["scorta_prima"] == pre_stock
    assert mov["scorta_dopo"] == pre_stock + 15
    assert "id" in mov and "operatore_id" in mov
    # Verify persistence via atomic $inc
    post = requests.get(f"{API}/magazzino/{item_id}", headers=H(tokens["admin"])).json()
    assert float(post["scorta_attuale"]) == pre_stock + 15


def test_movimento_scarico_decreases(tokens, created_item):
    item_id = created_item["id"]
    pre = requests.get(f"{API}/magazzino/{item_id}", headers=H(tokens["admin"])).json()
    pre_stock = float(pre["scorta_attuale"])
    r = requests.post(
        f"{API}/magazzino/{item_id}/movimento",
        headers=H(tokens["logistica"]),
        json={"tipo": "scarico", "quantita": 5, "motivo": "lavaggio"},
    )
    assert r.status_code == 200
    mov = r.json()
    assert mov["scorta_dopo"] == pre_stock - 5


def test_movimento_rettifica_sets_absolute(tokens, created_item):
    item_id = created_item["id"]
    r = requests.post(
        f"{API}/magazzino/{item_id}/movimento",
        headers=H(tokens["admin"]),
        json={"tipo": "rettifica", "quantita": 77, "motivo": "inventario"},
    )
    assert r.status_code == 200
    mov = r.json()
    assert mov["scorta_dopo"] == 77
    g = requests.get(f"{API}/magazzino/{item_id}", headers=H(tokens["admin"])).json()
    assert float(g["scorta_attuale"]) == 77


def test_movimento_invalid_tipo_400(tokens, created_item):
    r = requests.post(
        f"{API}/magazzino/{created_item['id']}/movimento",
        headers=H(tokens["admin"]),
        json={"tipo": "invalido", "quantita": 1},
    )
    assert r.status_code == 400


def test_movimento_negative_quantita_400(tokens, created_item):
    r = requests.post(
        f"{API}/magazzino/{created_item['id']}/movimento",
        headers=H(tokens["admin"]),
        json={"tipo": "carico", "quantita": -5},
    )
    assert r.status_code == 400


def test_movimento_contabilita_forbidden(tokens, created_item):
    # contabilita NOT in _MOV_ROLES
    r = requests.post(
        f"{API}/magazzino/{created_item['id']}/movimento",
        headers=H(tokens["contabilita"]),
        json={"tipo": "carico", "quantita": 1},
    )
    assert r.status_code == 403


def test_movimento_qualita_forbidden(tokens, created_item):
    r = requests.post(
        f"{API}/magazzino/{created_item['id']}/movimento",
        headers=H(tokens["qualita"]),
        json={"tipo": "carico", "quantita": 1},
    )
    assert r.status_code == 403


def test_movimento_logistica_allowed(tokens, created_item):
    # positive: logistica in _MOV_ROLES
    r = requests.post(
        f"{API}/magazzino/{created_item['id']}/movimento",
        headers=H(tokens["logistica"]),
        json={"tipo": "carico", "quantita": 2, "motivo": "test"},
    )
    assert r.status_code == 200


# ============ Movimenti history ============
def test_list_movimenti_sorted_desc(tokens, created_item):
    r = requests.get(
        f"{API}/magazzino/{created_item['id']}/movimenti",
        headers=H(tokens["admin"]),
    )
    assert r.status_code == 200
    movs = r.json()
    assert isinstance(movs, list) and len(movs) >= 3
    # timestamps desc
    ts = [m["timestamp"] for m in movs]
    assert ts == sorted(ts, reverse=True)
    # Check required fields present
    for m in movs:
        for k in ("tipo", "quantita", "scorta_prima", "scorta_dopo", "operatore_id", "timestamp"):
            assert k in m


# ============ DELETE ============
def test_delete_magazzino_and_404_after(tokens):
    # create fresh
    body = {"codice": "TEST_DEL_001", "descrizione": "to delete", "categoria": "altro"}
    cr = requests.post(f"{API}/magazzino", headers=H(tokens["admin"]), json=body)
    assert cr.status_code == 200
    item_id = cr.json()["id"]
    # delete
    dr = requests.delete(f"{API}/magazzino/{item_id}", headers=H(tokens["admin"]))
    assert dr.status_code == 200
    # verify gone
    gr = requests.get(f"{API}/magazzino/{item_id}", headers=H(tokens["admin"]))
    assert gr.status_code == 404


# ============ Audit log entries ============
def test_audit_log_has_magazzino_entries(tokens):
    r = requests.get(f"{API}/audit-log?limit=300", headers=H(tokens["admin"]))
    assert r.status_code == 200
    logs = r.json()
    actions = {(lg.get("azione"), lg.get("entita")) for lg in logs}
    assert ("CREATE", "magazzino") in actions
    assert ("CARICO", "magazzino") in actions
    assert ("SCARICO", "magazzino") in actions
    assert ("RETTIFICA", "magazzino") in actions


# ============ 404 on unknown item movement ============
def test_movimento_unknown_item_404(tokens):
    r = requests.post(
        f"{API}/magazzino/does-not-exist/movimento",
        headers=H(tokens["admin"]),
        json={"tipo": "carico", "quantita": 1},
    )
    assert r.status_code == 404
