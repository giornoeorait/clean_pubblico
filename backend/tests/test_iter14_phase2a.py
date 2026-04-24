"""FASE 2a — Anagrafiche potenziate: Clienti (SDI/PEC/struttura), Articoli (noleggio/lavaggio/giacenza),
Listini (tipo binario noleggio|lavaggio), /clienti/{id}/profilo."""
import os
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN = {"email": "admin@cleantec.it", "password": "admin123"}


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("token")
    assert tok
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# ---------------- ARTICOLI ------------------------------------------------
class TestArticoli:
    def test_list_has_new_fields(self, client):
        r = client.get(f"{BASE}/api/articoli", timeout=20)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list) and len(items) >= 1, "expected at least 1 seed articolo"
        for a in items:
            assert "prezzo_noleggio" in a, f"missing prezzo_noleggio in {a.get('codice')}"
            assert "prezzo_lavaggio" in a, f"missing prezzo_lavaggio in {a.get('codice')}"
            assert "giacenza" in a, f"missing giacenza in {a.get('codice')}"

    def test_create_with_new_fields_and_get(self, client):
        payload = {
            "codice": "TEST_PH2_A1",
            "descrizione": "TEST_PH2 articolo con driver",
            "prezzo": 3.0,
            "prezzo_noleggio": 2.5,
            "prezzo_lavaggio": 1.5,
            "giacenza": 100,
        }
        r = client.post(f"{BASE}/api/articoli", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        created = r.json()
        assert created["prezzo_noleggio"] == 2.5
        assert created["prezzo_lavaggio"] == 1.5
        assert created["giacenza"] == 100
        aid = created["id"]

        # verify persistence
        g = client.get(f"{BASE}/api/articoli/{aid}", timeout=20)
        assert g.status_code == 200
        got = g.json()
        assert got["prezzo_noleggio"] == 2.5
        assert got["giacenza"] == 100

        # PATCH prezzo_noleggio
        p = client.patch(f"{BASE}/api/articoli/{aid}", json={"prezzo_noleggio": 9.99}, timeout=20)
        assert p.status_code == 200, p.text
        g2 = client.get(f"{BASE}/api/articoli/{aid}", timeout=20)
        assert g2.json()["prezzo_noleggio"] == 9.99

        # cleanup
        client.delete(f"{BASE}/api/articoli/{aid}", timeout=20)


# ---------------- LISTINI -------------------------------------------------
class TestListini:
    def test_create_without_tipo_422(self, client):
        r = client.post(f"{BASE}/api/listini", json={"nome": "TEST_PH2 no-tipo"}, timeout=20)
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"

    def test_create_tipo_altro_422(self, client):
        r = client.post(f"{BASE}/api/listini", json={"nome": "TEST_PH2 bad-tipo", "tipo": "altro"}, timeout=20)
        assert r.status_code == 422, r.text

    @pytest.mark.parametrize("tipo", ["noleggio", "lavaggio"])
    def test_create_valid_tipo(self, client, tipo):
        r = client.post(f"{BASE}/api/listini", json={"nome": f"TEST_PH2 {tipo}", "tipo": tipo}, timeout=20)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["tipo"] == tipo
        lid = doc["id"]

        # PATCH tipo must be ignored (ListinoPatch has no tipo)
        p = client.patch(f"{BASE}/api/listini/{lid}", json={"tipo": "altro", "descrizione": "patched"}, timeout=20)
        assert p.status_code == 200, p.text
        g = client.get(f"{BASE}/api/listini/{lid}", timeout=20)
        assert g.status_code == 200
        assert g.json()["tipo"] == tipo, "tipo must be immutable after create"
        assert g.json()["descrizione"] == "patched"

        # GET /prezzi new shape
        pr = client.get(f"{BASE}/api/listini/{lid}/prezzi", timeout=20)
        assert pr.status_code == 200
        data = pr.json()
        assert set(data.keys()) >= {"listino", "rows"}, data.keys()
        assert data["listino"]["id"] == lid
        assert data["listino"]["tipo"] == tipo
        assert isinstance(data["rows"], list)
        if data["rows"]:
            row0 = data["rows"][0]
            assert {"articolo_id", "codice", "descrizione", "prezzo", "prezzo_default"}.issubset(row0.keys())
            # prezzo_default must match tipo source on backing articolo
            art = client.get(f"{BASE}/api/articoli/{row0['articolo_id']}", timeout=20).json()
            expected_key = "prezzo_noleggio" if tipo == "noleggio" else "prezzo_lavaggio"
            expected = art.get(expected_key) or art.get("prezzo", 0)
            assert abs(float(row0["prezzo_default"]) - float(expected)) < 0.001, (
                f"prezzo_default mismatch for {tipo}: row={row0['prezzo_default']} expected={expected}"
            )

        # cleanup
        client.delete(f"{BASE}/api/listini/{lid}", timeout=20)


# ---------------- CLIENTI -------------------------------------------------
class TestClienti:
    def test_create_missing_piva_422(self, client):
        r = client.post(f"{BASE}/api/clienti", json={
            "ragione_sociale": "TEST_PH2 no-piva", "indirizzo": "Via X", "email": "a@b.it", "telefono": "123"
        }, timeout=20)
        assert r.status_code == 422, r.text

    def test_create_bad_email_422(self, client):
        r = client.post(f"{BASE}/api/clienti", json={
            "ragione_sociale": "TEST_PH2 bad-email", "partita_iva": "IT123", "indirizzo": "Via X",
            "email": "not-an-email", "telefono": "123"
        }, timeout=20)
        assert r.status_code == 422, r.text

    def test_create_missing_telefono_422(self, client):
        r = client.post(f"{BASE}/api/clienti", json={
            "ragione_sociale": "TEST_PH2 no-tel", "partita_iva": "IT123", "indirizzo": "Via X",
            "email": "a@b.it"
        }, timeout=20)
        assert r.status_code == 422, r.text

    def test_create_full_and_patch(self, client):
        payload = {
            "ragione_sociale": "TEST_PH2 Full SRL",
            "partita_iva": "IT11112222333",
            "indirizzo": "Via Roma 1, 20100 Milano",
            "email": "testph2@example.com",
            "telefono": "+39 02 1234567",
            "pec": "testph2@pec.example.com",
            "codice_sdi": "ABCDE12",
            "denominazione_struttura": "Hotel Test - lavanderia",
            "indirizzo_scarico": "Via Scarico 99, Milano",
            "sla_ore": 999,  # must be ignored (sla removed)
        }
        r = client.post(f"{BASE}/api/clienti", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        cli = r.json()
        assert cli["codice_sdi"] == "ABCDE12"
        assert cli["denominazione_struttura"] == "Hotel Test - lavanderia"
        assert cli["pec"] == "testph2@pec.example.com"
        assert "sla_ore" not in cli, "sla_ore must no longer exist in schema response"
        cid = cli["id"]

        # PATCH fields
        p = client.patch(f"{BASE}/api/clienti/{cid}", json={
            "denominazione_struttura": "Hotel Test v2",
            "codice_sdi": "ZZZZZ99",
            "pec": "new@pec.example.com",
        }, timeout=20)
        assert p.status_code == 200, p.text
        g = client.get(f"{BASE}/api/clienti/{cid}", timeout=20).json()
        assert g["denominazione_struttura"] == "Hotel Test v2"
        assert g["codice_sdi"] == "ZZZZZ99"
        assert g["pec"] == "new@pec.example.com"

        # cleanup
        client.delete(f"{BASE}/api/clienti/{cid}", timeout=20)

    def test_profilo_structure_on_seed_client(self, client):
        """Use a seed client with actual DDTs/fatture to validate stats aggregation."""
        clienti = client.get(f"{BASE}/api/clienti", timeout=20).json()
        assert clienti, "no clienti in DB"
        # pick one that has fatture if possible
        target = None
        for c in clienti:
            fats = client.get(f"{BASE}/api/fatture", params={"cliente_id": c["id"]}, timeout=20)
            if fats.status_code == 200 and fats.json():
                target = c
                break
        if target is None:
            target = clienti[0]

        r = client.get(f"{BASE}/api/clienti/{target['id']}/profilo", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert set(data.keys()) >= {"cliente", "listino", "ddts", "fatture", "stats"}, data.keys()
        stats = data["stats"]
        for k in ("ddt_totali", "ddt_non_fatturati", "fatture_totali",
                  "fatturato_totale", "incassato_totale", "sospeso_totale"):
            assert k in stats, f"missing stats.{k}"
        # Validate aggregation
        tot = sum(f.get("totale", 0) for f in data["fatture"])
        inc = sum(f.get("totale", 0) for f in data["fatture"] if f.get("stato_incasso") == "incassata")
        assert abs(stats["fatturato_totale"] - round(tot, 2)) < 0.01
        assert abs(stats["incassato_totale"] - round(inc, 2)) < 0.01
        assert stats["ddt_totali"] == len(data["ddts"])
        assert stats["fatture_totali"] == len(data["fatture"])
