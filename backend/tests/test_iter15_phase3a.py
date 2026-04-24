"""FASE 3a — Offerte & Preventivi + conversione in Contratto + PDF.

Endpoints:
- /api/termini-templates (GET/POST/DELETE)
- /api/offerte (GET list, GET one, POST, PATCH, DELETE)
- /api/offerte/{id}/converti-contratto
- /api/offerte/{id}/pdf?tipo=offerta|contratto
"""
import os
import pytest
import requests

def _load_base_url():
    url = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if url:
        return url.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not configured")


BASE_URL = _load_base_url()
API = f"{BASE_URL}/api"


# ------- auth fixtures -------
def _login(email: str, password: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login("admin@cleantec.it", "admin123")


@pytest.fixture(scope="module")
def conta_token():
    return _login("contabilita@cleantec.it", "contabilita123")


@pytest.fixture(scope="module")
def logi_token():
    return _login("logistica@cleantec.it", "logistica123")


def _h(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def seed_refs(admin_token):
    cli = requests.get(f"{API}/clienti", headers=_h(admin_token), timeout=30).json()
    art = requests.get(f"{API}/articoli", headers=_h(admin_token), timeout=30).json()
    assert cli and art, "Seed data missing (clienti/articoli)"
    return {"cliente_id": cli[0]["id"], "articoli": art}


# ------- Termini templates -------
class TestTerminiTemplates:
    def test_list_seed_four_templates_admin(self, admin_token):
        r = requests.get(f"{API}/termini-templates", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200
        data = r.json()
        titoli = [t["titolo"] for t in data]
        assert len(data) >= 4
        # Seed titles start with "1. Modalità di pagamento" etc
        joined = " | ".join(titoli)
        for kw in ["Modalità di pagamento", "Durata e rinnovo", "Responsabilità", "Foro competente"]:
            assert kw in joined, f"Seed template missing: {kw}"

    def test_list_accessible_contabilita(self, conta_token):
        r = requests.get(f"{API}/termini-templates", headers=_h(conta_token), timeout=30)
        assert r.status_code == 200

    def test_post_admin_creates_template(self, admin_token):
        body = {"titolo": "TEST_clausola_X", "testo": "Testo di test per clausola extra."}
        r = requests.post(f"{API}/termini-templates", headers=_h(admin_token), json=body, timeout=30)
        assert r.status_code in (200, 201), r.text
        d = r.json()
        assert d["titolo"] == body["titolo"]
        assert d["testo"] == body["testo"]
        assert "id" in d
        # cleanup
        requests.delete(f"{API}/termini-templates/{d['id']}", headers=_h(admin_token), timeout=30)

    def test_post_contabilita_forbidden(self, conta_token):
        r = requests.post(
            f"{API}/termini-templates",
            headers=_h(conta_token),
            json={"titolo": "should_fail", "testo": "x"},
            timeout=30,
        )
        assert r.status_code == 403


# ------- Offerte CRUD + calculations -------
class TestOfferte:
    def test_create_full(self, admin_token, seed_refs):
        body = {
            "cliente_id": seed_refs["cliente_id"],
            "durata_mesi": 24,
            "data_scadenza": "2026-12-31",
            "note": "TEST_off_full",
            "termini_condizioni": [{"titolo": "T1", "testo": "TestoT1"}],
            "righe": [
                {"articolo_id": seed_refs["articoli"][0]["id"], "quantita": 10,
                 "sconto_perc": 10, "sconto_eur": 0.5},
                {"articolo_id": seed_refs["articoli"][1]["id"], "quantita": 5,
                 "sconto_perc": 0, "sconto_eur": 0},
            ],
        }
        r = requests.post(f"{API}/offerte", headers=_h(admin_token), json=body, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["numero"].startswith("OF-") and len(d["numero"].split("-")[-1]) == 5
        assert d["stato"] == "bozza"
        assert d["cliente_snapshot"]["ragione_sociale"]
        assert d["imponibile"] >= 0
        assert d["sconto_totale"] >= 0
        # Formula check on row 0
        r0 = d["righe"][0]
        expected_final = max(0.0, round(r0["prezzo_unitario"] * 0.9 - 0.5, 4))
        assert abs(r0["prezzo_finale"] - expected_final) < 0.01, f"formula mismatch {r0}"
        assert abs(r0["totale"] - round(r0["prezzo_finale"] * r0["quantita"], 2)) < 0.01
        pytest.offerta_id = d["id"]
        pytest.offerta_numero = d["numero"]

    def test_create_invalid_cliente(self, admin_token, seed_refs):
        r = requests.post(
            f"{API}/offerte", headers=_h(admin_token),
            json={"cliente_id": "does-not-exist",
                  "righe": [{"articolo_id": seed_refs["articoli"][0]["id"], "quantita": 1}]},
            timeout=30,
        )
        assert r.status_code == 404

    def test_create_empty_rows(self, admin_token, seed_refs):
        r = requests.post(
            f"{API}/offerte", headers=_h(admin_token),
            json={"cliente_id": seed_refs["cliente_id"], "righe": []},
            timeout=30,
        )
        assert r.status_code == 400
        assert "riga" in r.json().get("detail", "").lower()

    def test_create_invalid_articolo(self, admin_token, seed_refs):
        r = requests.post(
            f"{API}/offerte", headers=_h(admin_token),
            json={"cliente_id": seed_refs["cliente_id"],
                  "righe": [{"articolo_id": "bogus", "quantita": 1}]},
            timeout=30,
        )
        assert r.status_code == 400

    def test_rbac_logistica_cannot_post(self, logi_token, seed_refs):
        r = requests.post(
            f"{API}/offerte", headers=_h(logi_token),
            json={"cliente_id": seed_refs["cliente_id"],
                  "righe": [{"articolo_id": seed_refs["articoli"][0]["id"], "quantita": 1}]},
            timeout=30,
        )
        assert r.status_code == 403

    def test_list_and_filters(self, admin_token, seed_refs):
        r = requests.get(f"{API}/offerte", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200
        ids = [o["id"] for o in r.json()]
        assert pytest.offerta_id in ids

        r2 = requests.get(f"{API}/offerte?stato=bozza", headers=_h(admin_token), timeout=30)
        assert r2.status_code == 200
        assert all(o["stato"] == "bozza" for o in r2.json())

        r3 = requests.get(
            f"{API}/offerte?cliente_id={seed_refs['cliente_id']}",
            headers=_h(admin_token), timeout=30,
        )
        assert r3.status_code == 200
        assert all(o["cliente_id"] == seed_refs["cliente_id"] for o in r3.json())

    def test_patch_bozza_to_inviata_then_accettata(self, admin_token):
        r = requests.patch(
            f"{API}/offerte/{pytest.offerta_id}",
            headers=_h(admin_token), json={"stato": "inviata"}, timeout=30,
        )
        assert r.status_code == 200 and r.json()["stato"] == "inviata"

        r2 = requests.patch(
            f"{API}/offerte/{pytest.offerta_id}",
            headers=_h(admin_token), json={"stato": "accettata"}, timeout=30,
        )
        assert r2.status_code == 200 and r2.json()["stato"] == "accettata"


# ------- Conversione contratto + PDF -------
class TestContratto:
    def test_pdf_offerta(self, admin_token):
        r = requests.get(
            f"{API}/offerte/{pytest.offerta_id}/pdf",
            headers=_h(admin_token), timeout=60,
        )
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:8].startswith(b"%PDF-1.4"), f"Not PDF-1.4: {r.content[:8]}"
        assert len(r.content) > 10_000

    def test_pdf_contratto_before_conversion(self, admin_token):
        r = requests.get(
            f"{API}/offerte/{pytest.offerta_id}/pdf?tipo=contratto",
            headers=_h(admin_token), timeout=30,
        )
        assert r.status_code == 400

    def test_converti_contratto_ok(self, admin_token):
        r = requests.post(
            f"{API}/offerte/{pytest.offerta_id}/converti-contratto",
            headers=_h(admin_token), timeout=30,
        )
        assert r.status_code == 200
        d = r.json()
        assert d["stato"] == "contratto"
        assert d["contratto_numero"].startswith("CT-") and len(d["contratto_numero"].split("-")[-1]) == 5

    def test_pdf_contratto_after(self, admin_token):
        r = requests.get(
            f"{API}/offerte/{pytest.offerta_id}/pdf?tipo=contratto",
            headers=_h(admin_token), timeout=60,
        )
        assert r.status_code == 200
        assert r.content[:8].startswith(b"%PDF-1.4")
        assert len(r.content) > 10_000

    def test_double_conversion_409(self, admin_token):
        r = requests.post(
            f"{API}/offerte/{pytest.offerta_id}/converti-contratto",
            headers=_h(admin_token), timeout=30,
        )
        assert r.status_code == 409

    def test_patch_on_contratto_409(self, admin_token):
        r = requests.patch(
            f"{API}/offerte/{pytest.offerta_id}",
            headers=_h(admin_token), json={"note": "nope"}, timeout=30,
        )
        assert r.status_code == 409

    def test_delete_contratto_409(self, admin_token):
        r = requests.delete(
            f"{API}/offerte/{pytest.offerta_id}",
            headers=_h(admin_token), timeout=30,
        )
        assert r.status_code == 409


# ------- Rifiutata cannot convert -------
class TestRifiutata:
    def test_converti_rifiutata_400(self, admin_token, seed_refs):
        body = {
            "cliente_id": seed_refs["cliente_id"],
            "righe": [{"articolo_id": seed_refs["articoli"][0]["id"], "quantita": 1}],
        }
        r = requests.post(f"{API}/offerte", headers=_h(admin_token), json=body, timeout=30)
        assert r.status_code == 200
        oid = r.json()["id"]
        # bozza -> inviata -> rifiutata
        requests.patch(f"{API}/offerte/{oid}", headers=_h(admin_token), json={"stato": "inviata"}, timeout=30)
        requests.patch(f"{API}/offerte/{oid}", headers=_h(admin_token), json={"stato": "rifiutata"}, timeout=30)
        rc = requests.post(f"{API}/offerte/{oid}/converti-contratto", headers=_h(admin_token), timeout=30)
        assert rc.status_code == 400
        # cleanup
        requests.delete(f"{API}/offerte/{oid}", headers=_h(admin_token), timeout=30)
