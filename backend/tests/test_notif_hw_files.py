"""Iteration 8: Notifications + Hardware + Files (Object Storage)."""
import os
import base64
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://wash-ops-central.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


# ---- Fixtures ---------------------------------------------------------------
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@cleantec.it", "password": "admin123"}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def cliente_token():
    r = requests.post(f"{API}/auth/login", json={"email": "cliente@cleantec.it", "password": "cliente123"}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def logistica_token():
    r = requests.post(f"{API}/auth/login", json={"email": "logistica@cleantec.it", "password": "logistica123"}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def H(t):
    return {"Authorization": f"Bearer {t}"}


# ---- Notifications ----------------------------------------------------------
class TestNotifications:
    def test_status_stub(self, admin_token):
        r = requests.get(f"{API}/notifications/status", headers=H(admin_token), timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["twilio_enabled"] is False, "Twilio must be in stub mode"
        assert isinstance(data["templates"], list) and len(data["templates"]) > 0
        assert "consegna_in_transito" in data["templates"]

    def test_send_free_body(self, admin_token):
        r = requests.post(f"{API}/notifications/send", headers=H(admin_token),
                          json={"kind": "sms", "to": "+393331234567", "body": "TEST iter8 body libero"}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "logged"
        assert d["provider"] == "stub"
        assert d["to"] == "+393331234567"
        assert "TEST iter8" in d["body"]

    def test_send_with_template(self, admin_token):
        r = requests.post(f"{API}/notifications/send", headers=H(admin_token), json={
            "kind": "whatsapp", "to": "+393337654321",
            "template": "consegna_in_transito",
            "template_vars": {"nome": "Hotel Excelsior", "numero": "CON-TEST"},
        }, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "logged"
        assert "Hotel Excelsior" in d["body"]
        assert "CON-TEST" in d["body"]

    def test_send_missing_var(self, admin_token):
        r = requests.post(f"{API}/notifications/send", headers=H(admin_token), json={
            "kind": "sms", "to": "+39333", "template": "consegna_in_transito", "template_vars": {"nome": "X"},
        }, timeout=15)
        assert r.status_code == 400

    def test_send_bad_template(self, admin_token):
        r = requests.post(f"{API}/notifications/send", headers=H(admin_token), json={
            "kind": "sms", "to": "+39333", "template": "not_exists",
        }, timeout=15)
        assert r.status_code == 400

    def test_send_no_body_no_template(self, admin_token):
        r = requests.post(f"{API}/notifications/send", headers=H(admin_token),
                          json={"kind": "sms", "to": "+39333"}, timeout=15)
        assert r.status_code == 400

    def test_list_admin(self, admin_token):
        r = requests.get(f"{API}/notifications", headers=H(admin_token), timeout=15)
        assert r.status_code == 200
        lst = r.json()
        assert isinstance(lst, list)
        assert any("TEST iter8" in (n.get("body") or "") for n in lst)

    def test_rbac_cliente_cannot_send(self, cliente_token):
        r = requests.post(f"{API}/notifications/send", headers=H(cliente_token),
                          json={"kind": "sms", "to": "+39333", "body": "x"}, timeout=15)
        assert r.status_code == 403

    def test_rbac_cliente_can_list(self, cliente_token):
        r = requests.get(f"{API}/notifications", headers=H(cliente_token), timeout=15)
        assert r.status_code == 200
        # must be filtered to own cliente_id
        assert isinstance(r.json(), list)


# ---- Consegna auto-trigger SMS ---------------------------------------------
class TestConsegnaAutoSMS:
    def test_auto_sms_on_in_transito(self, admin_token, logistica_token):
        # Find a cliente with phone starting with +
        clienti = requests.get(f"{API}/clienti", headers=H(admin_token), timeout=15).json()
        target = next((c for c in clienti if (c.get("telefono") or "").startswith("+")), None)
        if not target:
            # set phone on first client
            c0 = clienti[0]
            rp = requests.patch(f"{API}/clienti/{c0['id']}", headers=H(admin_token),
                                json={"telefono": "+393339998877"}, timeout=15)
            assert rp.status_code in (200, 204), rp.text
            target = {**c0, "telefono": "+393339998877"}

        # Create consegna
        rc = requests.post(f"{API}/consegne", headers=H(admin_token), json={
            "cliente_id": target["id"], "indirizzo": "Via Test 1",
            "data_prevista": "2026-01-20T10:00:00",
        }, timeout=15)
        assert rc.status_code == 200, rc.text
        cid = rc.json()["id"]
        numero = rc.json()["numero"]

        # Patch to in_transito
        rp = requests.patch(f"{API}/consegne/{cid}", headers=H(logistica_token),
                            json={"stato": "in_transito"}, timeout=15)
        assert rp.status_code == 200

        # Verify notif record created
        import time
        time.sleep(0.5)
        lst = requests.get(f"{API}/notifications", headers=H(admin_token), timeout=15).json()
        found = [n for n in lst if n.get("context", {}).get("consegna_id") == cid]
        assert found, f"No auto-notification for consegna {numero}"
        n = found[0]
        assert n["status"] == "logged"
        assert n["provider"] == "stub"
        assert n["kind"] == "sms"


# ---- Hardware ---------------------------------------------------------------
class TestHardware:
    def test_scan_lotto(self, admin_token):
        lotti = requests.get(f"{API}/lotti?limit=5", headers=H(admin_token), timeout=15).json()
        if not lotti:
            pytest.skip("No lotti")
        numero = lotti[0]["numero"]
        r = requests.post(f"{API}/hardware/scan", headers=H(admin_token),
                          json={"code": numero, "station": "test"}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["match"] == "lotto"

    def test_scan_articolo(self, admin_token):
        articoli = requests.get(f"{API}/articoli?limit=5", headers=H(admin_token), timeout=15).json()
        if not articoli:
            pytest.skip("No articoli")
        code = articoli[0].get("codice") or articoli[0].get("barcode")
        if not code:
            pytest.skip("No codice")
        r = requests.post(f"{API}/hardware/scan", headers=H(admin_token),
                          json={"code": code}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["match"] == "articolo"

    def test_scan_unknown_404(self, admin_token):
        r = requests.post(f"{API}/hardware/scan", headers=H(admin_token),
                          json={"code": "ZZZ-NON-EXIST-999"}, timeout=15)
        assert r.status_code == 404

    def test_scale_with_lotto(self, admin_token):
        lotti = requests.get(f"{API}/lotti?limit=5", headers=H(admin_token), timeout=15).json()
        if not lotti:
            pytest.skip("No lotti")
        lid = lotti[0]["id"]
        r = requests.post(f"{API}/hardware/scale", headers=H(admin_token),
                          json={"peso_kg": 12.5, "lotto_id": lid, "stable": True}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["applied_to"]["type"] == "lotto"
        # Verify persisted
        lg = requests.get(f"{API}/lotti/{lid}", headers=H(admin_token), timeout=15).json()
        assert lg["peso_kg"] == 12.5

    def test_scale_free_reading(self, admin_token):
        r = requests.post(f"{API}/hardware/scale", headers=H(admin_token),
                          json={"peso_kg": 7.3, "station": "test"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["applied_to"] is None

    def test_scale_missing_lotto(self, admin_token):
        r = requests.post(f"{API}/hardware/scale", headers=H(admin_token),
                          json={"peso_kg": 1.0, "lotto_id": "nope-xxx"}, timeout=15)
        assert r.status_code == 404

    def test_rfid_single(self, admin_token):
        r = requests.post(f"{API}/hardware/rfid", headers=H(admin_token),
                          json={"tag": "RFID-TEST-001"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["tag"] == "RFID-TEST-001"

    def test_rfid_batch(self, admin_token):
        r = requests.post(f"{API}/hardware/rfid/batch", headers=H(admin_token),
                          json={"tags": ["A1", "B2", "C3", "A1"]}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["count"] == 3  # deduped

    def test_rfid_batch_empty(self, admin_token):
        r = requests.post(f"{API}/hardware/rfid/batch", headers=H(admin_token),
                          json={"tags": []}, timeout=15)
        assert r.status_code == 400

    def test_events_filter(self, admin_token):
        r = requests.get(f"{API}/hardware/events?kind=scale", headers=H(admin_token), timeout=15)
        assert r.status_code == 200
        assert all(e["kind"] == "scale" for e in r.json())

    def test_rbac_cliente_cannot_scan(self, cliente_token):
        r = requests.post(f"{API}/hardware/scan", headers=H(cliente_token),
                          json={"code": "x"}, timeout=15)
        assert r.status_code == 403

    def test_rbac_cliente_can_read_events(self, cliente_token):
        r = requests.get(f"{API}/hardware/events", headers=H(cliente_token), timeout=15)
        assert r.status_code == 200


# ---- Files / Object Storage -------------------------------------------------
# A tiny valid 1x1 PNG (base64)
PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgAAIAAAUAAeImBZsAAAAASUVORK5CYII="
)


class TestFiles:
    def test_signature_upload(self, admin_token):
        data_url = f"data:image/png;base64,{PNG_B64}"
        r = requests.post(f"{API}/files/signature", headers=H(admin_token),
                          json={"data_url": data_url, "context": "signature"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["id"]
        assert d["storage_path"]
        TestFiles.file_id = d["id"]
        TestFiles.file_path = d["storage_path"]

    def test_file_download_with_auth_query(self, admin_token):
        path = getattr(TestFiles, "file_path", None)
        if not path:
            pytest.skip("No signature uploaded")
        url = f"{API}/files/{path}?auth={admin_token}"
        r = requests.get(url, timeout=30)
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("image/")
        assert len(r.content) > 20

    def test_file_download_no_auth(self):
        path = getattr(TestFiles, "file_path", None)
        if not path:
            pytest.skip("No signature uploaded")
        r = requests.get(f"{API}/files/{path}", timeout=15)
        assert r.status_code == 401

    def test_upload_multipart(self, admin_token):
        png = base64.b64decode(PNG_B64)
        files = {"file": ("pixel.png", png, "image/png")}
        r = requests.post(f"{API}/files/upload?context=test", headers=H(admin_token), files=files, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["id"]
        TestFiles.upload_id = d["id"]

    def test_upload_bad_ext(self, admin_token):
        files = {"file": ("x.exe", b"bin", "application/octet-stream")}
        r = requests.post(f"{API}/files/upload", headers=H(admin_token), files=files, timeout=15)
        assert r.status_code == 400

    def test_file_soft_delete(self, admin_token):
        fid = getattr(TestFiles, "upload_id", None)
        if not fid:
            pytest.skip("No upload")
        r = requests.delete(f"{API}/files/{fid}", headers=H(admin_token), timeout=15)
        assert r.status_code == 200


# ---- Regression -------------------------------------------------------------
class TestRegression:
    def test_dashboard_kpi(self, admin_token):
        r = requests.get(f"{API}/dashboard/kpi", headers=H(admin_token), timeout=15)
        assert r.status_code == 200

    def test_clienti_list(self, admin_token):
        r = requests.get(f"{API}/clienti", headers=H(admin_token), timeout=15)
        assert r.status_code == 200

    def test_lotti_list(self, admin_token):
        r = requests.get(f"{API}/lotti", headers=H(admin_token), timeout=15)
        assert r.status_code == 200

    def test_ticket_critica_no_phone(self, admin_token):
        # Create a ticket with priority critica — must not break even w/o MAINTENANCE_ALERT_PHONE
        macchine = requests.get(f"{API}/macchine", headers=H(admin_token), timeout=15).json()
        if not macchine:
            pytest.skip("No macchine")
        r = requests.post(f"{API}/tickets", headers=H(admin_token), json={
            "macchina_id": macchine[0]["id"],
            "titolo": "TEST ticket critica iter8",
            "descrizione": "test",
            "priorita": "critica",
        }, timeout=15)
        assert r.status_code == 200, r.text
