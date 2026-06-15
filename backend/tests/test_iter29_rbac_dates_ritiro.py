"""Iter29: RBAC sulle date (DDT/ordinativi) + ritiro_lavanderia + ordinamento clienti.

Test coverage:
- PATCH /api/ddt/{id} con 'data' come admin OK / come logistica 403
- PATCH /api/ordinativi/{id} con 'data_richiesta' come admin OK / come logistica 403
- POST /api/public/portale/{token}/ordinativo con ritiro_lavanderia:true salva e ritorna il flag
- GET /api/clienti ritorna clienti (UI usa sort lato client su denominazione_struttura/ragione_sociale)
"""
import os
import pytest
import requests
from datetime import datetime, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


def _login(email: str, password: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"Login failed {email}: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login("admin@cleantec.it", "admin123")


@pytest.fixture(scope="module")
def logistica_token():
    return _login("logistica@cleantec.it", "logistica123")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def logistica_headers(logistica_token):
    return {"Authorization": f"Bearer {logistica_token}"}


# ------------------- RBAC: data DDT -------------------
class TestDdtDateRbac:
    def test_admin_can_update_ddt_date(self, admin_headers):
        # Find a non-fatturato DDT
        r = requests.get(f"{API}/ddt", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        ddts = [d for d in r.json() if d.get("stato_fatturazione") != "fatturato"]
        if not ddts:
            pytest.skip("Nessun DDT non fatturato disponibile")
        did = ddts[0]["id"]
        new_date = "2025-06-15T10:00:00"
        r = requests.patch(f"{API}/ddt/{did}", json={"data": new_date}, headers=admin_headers, timeout=15)
        assert r.status_code == 200, f"PATCH admin failed: {r.status_code} {r.text}"
        # verify
        g = requests.get(f"{API}/ddt/{did}", headers=admin_headers, timeout=15)
        assert g.status_code == 200
        data_field = g.json().get("data")
        assert data_field and "2025-06-15" in str(data_field), f"Data non aggiornata: {data_field}"

    def test_logistica_cannot_update_ddt_date(self, admin_headers, logistica_headers):
        r = requests.get(f"{API}/ddt", headers=admin_headers, timeout=15)
        ddts = [d for d in r.json() if d.get("stato_fatturazione") != "fatturato"]
        if not ddts:
            pytest.skip("Nessun DDT non fatturato disponibile")
        did = ddts[0]["id"]
        r = requests.patch(f"{API}/ddt/{did}", json={"data": "2024-01-01T00:00:00"},
                           headers=logistica_headers, timeout=15)
        assert r.status_code == 403, f"Atteso 403, ottenuto {r.status_code} {r.text}"
        body = r.json()
        msg = (body.get("detail") or body.get("message") or "").lower()
        assert "amministrat" in msg or "admin" in msg, f"Messaggio inatteso: {body}"

    def test_logistica_can_update_other_fields_on_ddt(self, admin_headers, logistica_headers):
        # logistica can still patch DDT (e.g. note) -- only 'data' is restricted
        r = requests.get(f"{API}/ddt", headers=admin_headers, timeout=15)
        ddts = [d for d in r.json() if d.get("stato_fatturazione") != "fatturato"]
        if not ddts:
            pytest.skip("Nessun DDT non fatturato")
        did = ddts[0]["id"]
        r = requests.patch(f"{API}/ddt/{did}", json={"note": "TEST_iter29_logistica_note"},
                           headers=logistica_headers, timeout=15)
        assert r.status_code in (200, 204), f"Logistica deve poter aggiornare note: {r.status_code} {r.text}"


# ------------------- RBAC: data_richiesta ordinativi -------------------
class TestOrdinativoDateRbac:
    def _get_editable_ord(self, headers):
        r = requests.get(f"{API}/ordinativi", headers=headers, timeout=15)
        assert r.status_code == 200
        ords = [o for o in r.json() if o.get("stato") != "convertito_ddt"]
        return ords[0] if ords else None

    def test_admin_can_update_ordinativo_data_richiesta(self, admin_headers):
        o = self._get_editable_ord(admin_headers)
        if not o:
            pytest.skip("Nessun ordinativo editabile")
        oid = o["id"]
        new_date = "2025-05-10T08:30:00"
        r = requests.patch(f"{API}/ordinativi/{oid}", json={"data_richiesta": new_date},
                           headers=admin_headers, timeout=15)
        assert r.status_code == 200, f"PATCH admin data_richiesta failed: {r.status_code} {r.text}"
        body = r.json()
        assert "2025-05-10" in str(body.get("data_richiesta", "")), \
            f"data_richiesta non aggiornata: {body.get('data_richiesta')}"

    def test_logistica_cannot_update_data_richiesta(self, admin_headers, logistica_headers):
        o = self._get_editable_ord(admin_headers)
        if not o:
            pytest.skip("Nessun ordinativo editabile")
        oid = o["id"]
        r = requests.patch(f"{API}/ordinativi/{oid}",
                           json={"data_richiesta": "2024-02-02T00:00:00"},
                           headers=logistica_headers, timeout=15)
        assert r.status_code == 403, f"Atteso 403, ottenuto {r.status_code} {r.text}"
        body = r.json()
        msg = (body.get("detail") or body.get("message") or "").lower()
        assert "amministrat" in msg or "admin" in msg, f"Messaggio inatteso: {body}"

    def test_logistica_can_update_note_interne(self, admin_headers, logistica_headers):
        o = self._get_editable_ord(admin_headers)
        if not o:
            pytest.skip("Nessun ordinativo")
        oid = o["id"]
        r = requests.patch(f"{API}/ordinativi/{oid}",
                           json={"note_interne": "TEST_iter29_note"},
                           headers=logistica_headers, timeout=15)
        assert r.status_code == 200, f"Atteso 200, ottenuto {r.status_code} {r.text}"


# ------------------- Portale pubblico + ritiro_lavanderia -------------------
class TestPortaleRitiroLavanderia:
    @pytest.fixture(scope="class")
    def portale_token(self, admin_headers):
        # Pick a cliente with listino_id
        r = requests.get(f"{API}/clienti", headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        cli_list = r.json()
        cli = None
        for c in cli_list:
            if c.get("listino_id"):
                cli = c
                break
        if not cli:
            pytest.skip("Nessun cliente con listino")

        # Generate token
        r = requests.post(f"{API}/clienti/{cli['id']}/portale-token",
                          headers=admin_headers, timeout=15)
        if r.status_code != 200:
            # may already have a token - try GET
            pytest.skip(f"Impossibile generare token: {r.status_code} {r.text}")
        body = r.json()
        tok = body.get("token") or body.get("portale_token")
        if not tok:
            pytest.skip(f"Token non in response: {body}")
        return {"token": tok, "cliente_id": cli["id"]}

    def test_portale_info_loads(self, portale_token):
        r = requests.get(f"{API}/public/portale/{portale_token['token']}", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "articoli" in body and len(body["articoli"]) > 0, "Nessun articolo nel portale"

    def test_portale_create_ordinativo_with_ritiro_lavanderia(self, portale_token):
        info = requests.get(f"{API}/public/portale/{portale_token['token']}", timeout=15).json()
        articoli = info["articoli"]
        # Pick the cheapest article with multiplo_quantita = 1
        cheap = sorted([a for a in articoli if a.get("multiplo_quantita", 1) == 1],
                       key=lambda a: a.get("prezzo", 0))
        if not cheap:
            cheap = articoli
        art = cheap[0]
        payload = {
            "data_consegna_richiesta": "2025-12-31",
            "righe": [{"articolo_id": art["id"], "quantita": 1}],
            "note_cliente": "TEST_iter29_ritiro",
            "ritiro_lavanderia": True,
        }
        r = requests.post(f"{API}/public/portale/{portale_token['token']}/ordinativo",
                          json=payload, timeout=15)
        assert r.status_code == 200, f"POST ordine portale failed: {r.status_code} {r.text}"
        body = r.json()
        assert body.get("ritiro_lavanderia") is True, \
            f"ritiro_lavanderia non presente in response: {body}"
        assert body.get("numero", "").startswith("ORD-"), f"Numero mancante: {body}"

    def test_portale_create_no_ritiro(self, portale_token):
        info = requests.get(f"{API}/public/portale/{portale_token['token']}", timeout=15).json()
        art = info["articoli"][0]
        # multiplo
        qty = int(art.get("multiplo_quantita") or 1)
        payload = {
            "data_consegna_richiesta": "2025-12-31",
            "righe": [{"articolo_id": art["id"], "quantita": qty}],
            "note_cliente": "TEST_iter29_normale",
        }
        r = requests.post(f"{API}/public/portale/{portale_token['token']}/ordinativo",
                          json=payload, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        # default False
        assert body.get("ritiro_lavanderia") is False, f"Default ritiro_lavanderia != False: {body}"

    def test_ritiro_flag_persisted_in_get(self, admin_headers, portale_token):
        # Find the order with TEST_iter29_ritiro note
        r = requests.get(f"{API}/ordinativi", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        ords = [o for o in r.json() if "TEST_iter29_ritiro" in (o.get("note_cliente") or "")]
        assert ords, "Ordine di test non trovato"
        # Should have ritiro_lavanderia=True
        ritiro_orders = [o for o in ords if o.get("ritiro_lavanderia") is True]
        assert ritiro_orders, f"Nessun ordine con ritiro_lavanderia=True: {[o.get('ritiro_lavanderia') for o in ords]}"


# ------------------- Clienti list (frontend sort lato client) -------------------
class TestClientiList:
    def test_clienti_returned_for_admin(self, admin_headers):
        r = requests.get(f"{API}/clienti", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        clienti = r.json()
        assert isinstance(clienti, list)
        for c in clienti:
            # Need ragione_sociale or denominazione_struttura field for sorting
            assert "ragione_sociale" in c or "denominazione_struttura" in c
