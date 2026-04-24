"""FASE 3b — Ordinativi + Portale pubblico (Pytest)."""
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://wash-ops-central.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"


# ---------- helpers ----------
def _login(email, pwd):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin():
    return {"Authorization": f"Bearer {_login('admin@cleantec.it', 'admin123')}"}


@pytest.fixture(scope="module")
def contabilita():
    return {"Authorization": f"Bearer {_login('contabilita@cleantec.it', 'contabilita123')}"}


@pytest.fixture(scope="module")
def seed(admin):
    cli = requests.get(f"{API}/clienti", headers=admin).json()
    art = requests.get(f"{API}/articoli", headers=admin).json()
    assert cli and art, "Seed clienti/articoli mancante"
    return {"cliente_id": cli[0]["id"], "articolo_id": art[0]["id"],
            "articolo2_id": art[1]["id"] if len(art) > 1 else art[0]["id"]}


# ---------- Ordinativi CRUD interno ----------
class TestOrdinativiInterno:
    def test_create_ordinativo_auto_prices(self, admin, seed):
        payload = {
            "cliente_id": seed["cliente_id"],
            "data_consegna_richiesta": "2026-03-15",
            "righe": [{"articolo_id": seed["articolo_id"], "quantita": 10}],
            "note_interne": "TEST_iter16",
        }
        r = requests.post(f"{API}/ordinativi", json=payload, headers=admin)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["numero"].startswith("ORD-")
        assert d["stato"] == "nuovo"
        assert d["origine"] == "interno"
        assert d["totale"] > 0
        assert d["righe"][0]["prezzo_unitario"] > 0
        pytest.ORD_ID = d["id"]
        pytest.ORD_NUM = d["numero"]

    def test_get_and_list_filters(self, admin, seed):
        r = requests.get(f"{API}/ordinativi", headers=admin)
        assert r.status_code == 200
        assert any(o["id"] == pytest.ORD_ID for o in r.json())
        r2 = requests.get(f"{API}/ordinativi?stato=nuovo&cliente_id={seed['cliente_id']}", headers=admin)
        assert r2.status_code == 200 and all(o["stato"] == "nuovo" for o in r2.json())
        r3 = requests.get(f"{API}/ordinativi/{pytest.ORD_ID}", headers=admin)
        assert r3.status_code == 200 and r3.json()["numero"] == pytest.ORD_NUM

    def test_patch_stato_in_lavorazione(self, admin):
        r = requests.patch(f"{API}/ordinativi/{pytest.ORD_ID}",
                           json={"stato": "in_lavorazione"}, headers=admin)
        assert r.status_code == 200 and r.json()["stato"] == "in_lavorazione"

    def test_empty_righe_400(self, admin, seed):
        r = requests.post(f"{API}/ordinativi",
                          json={"cliente_id": seed["cliente_id"], "righe": []}, headers=admin)
        assert r.status_code in (400, 422)

    def test_converti_ddt_success(self, admin):
        r = requests.post(f"{API}/ordinativi/{pytest.ORD_ID}/converti-ddt", headers=admin)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["stato"] == "convertito_ddt"
        assert d["ddt_numero"] and d["ddt_numero"].startswith("DDT-")
        pytest.DDT_NUM = d["ddt_numero"]
        # verify DDT actually exists
        ddts = requests.get(f"{API}/ddt", headers=admin).json()
        assert any(x["numero"] == d["ddt_numero"] for x in ddts)

    def test_converti_ddt_twice_409(self, admin):
        r = requests.post(f"{API}/ordinativi/{pytest.ORD_ID}/converti-ddt", headers=admin)
        assert r.status_code == 409

    def test_patch_converted_409(self, admin):
        r = requests.patch(f"{API}/ordinativi/{pytest.ORD_ID}",
                           json={"note_interne": "x"}, headers=admin)
        assert r.status_code == 409

    def test_delete_converted_409(self, admin):
        r = requests.delete(f"{API}/ordinativi/{pytest.ORD_ID}", headers=admin)
        assert r.status_code == 409

    def test_delete_ok_on_nuovo(self, admin, seed):
        r = requests.post(f"{API}/ordinativi", json={
            "cliente_id": seed["cliente_id"],
            "righe": [{"articolo_id": seed["articolo_id"], "quantita": 1}],
        }, headers=admin)
        oid = r.json()["id"]
        r2 = requests.delete(f"{API}/ordinativi/{oid}", headers=admin)
        assert r2.status_code == 200
        r3 = requests.get(f"{API}/ordinativi/{oid}", headers=admin)
        assert r3.status_code == 404


# ---------- Portale token + public ----------
class TestPortalePubblico:
    def test_genera_token(self, admin, seed):
        r = requests.post(f"{API}/clienti/{seed['cliente_id']}/portale-token", headers=admin)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["token"] and len(d["token"]) >= 20
        assert d["url_path"] == f"/ordina/{d['token']}"
        pytest.TOKEN = d["token"]

    def test_contabilita_cannot_generate(self, contabilita, seed):
        r = requests.post(f"{API}/clienti/{seed['cliente_id']}/portale-token",
                          headers=contabilita)
        assert r.status_code == 403

    def test_public_get_info_NO_AUTH(self, seed):
        # IMPORTANT: no Authorization header
        r = requests.get(f"{API}/public/portale/{pytest.TOKEN}")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["cliente"]["ragione_sociale"]
        assert isinstance(d["articoli"], list) and len(d["articoli"]) > 0
        for a in d["articoli"]:
            assert "prezzo" in a and a["prezzo"] >= 0
        assert "fornitore" in d
        pytest.PUBLIC_ART = d["articoli"][0]["id"]

    def test_public_invalid_token_404(self):
        r = requests.get(f"{API}/public/portale/invalid-xyz-000")
        assert r.status_code == 404

    def test_public_post_ordinativo_NO_AUTH(self):
        payload = {
            "data_consegna_richiesta": "2026-04-01",
            "righe": [{"articolo_id": pytest.PUBLIC_ART, "quantita": 5}],
            "note_cliente": "TEST_portale",
        }
        r = requests.post(f"{API}/public/portale/{pytest.TOKEN}/ordinativo", json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["numero"].startswith("ORD-")
        assert d["stato"] == "nuovo"
        assert d["totale"] > 0

    def test_public_post_empty_righe_400(self):
        r = requests.post(f"{API}/public/portale/{pytest.TOKEN}/ordinativo",
                          json={"data_consegna_richiesta": "2026-04-01", "righe": []})
        assert r.status_code in (400, 422)

    def test_ordinativo_portale_visibile_ad_admin(self, admin):
        r = requests.get(f"{API}/ordinativi", headers=admin)
        assert any(o["origine"] == "portale" for o in r.json())

    def test_revoca_token(self, admin, seed):
        r = requests.delete(f"{API}/clienti/{seed['cliente_id']}/portale-token", headers=admin)
        assert r.status_code == 200
        r2 = requests.get(f"{API}/public/portale/{pytest.TOKEN}")
        assert r2.status_code == 404


# ---------- Smoke test fase precedenti ----------
class TestRegressionSmoke:
    def test_ddt_list(self, admin):
        assert requests.get(f"{API}/ddt", headers=admin).status_code == 200

    def test_offerte_list(self, admin):
        assert requests.get(f"{API}/offerte", headers=admin).status_code == 200

    def test_fatture_list(self, admin):
        assert requests.get(f"{API}/fatture", headers=admin).status_code == 200

    def test_dashboard_kpi(self, admin):
        assert requests.get(f"{API}/dashboard/kpi", headers=admin).status_code == 200
