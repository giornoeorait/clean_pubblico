"""Iteration 13 tests: Company anagrafica + PDF DDT/Fatture + DDT edit."""
import io
import os
import pytest
import requests
from PIL import Image

def _load_env():
    p = "/app/frontend/.env"
    if os.path.exists(p):
        for line in open(p):
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)
_load_env()
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@cleantec.it", "password": "admin123"}
LOG = {"email": "logistica@cleantec.it", "password": "logistica123"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def logistica_token():
    return _login(LOG)


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---- Company CRUD ---------------------------------------------------------
class TestCompany:
    def test_company_get_initial_or_incomplete(self, admin_token):
        r = requests.get(f"{API}/company", headers=_h(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert "setup_complete" in data
        assert "nome" in data
        # Either empty (first-run) or partial — no assertion on setup_complete value here

    def test_company_put_partial_setup_incomplete(self, admin_token):
        body = {"nome": "CleanTec", "ragione_sociale": "", "partita_iva": "",
                "indirizzo": "", "email": "", "telefono": ""}
        r = requests.put(f"{API}/company", json=body, headers=_h(admin_token))
        assert r.status_code == 200
        d = r.json()
        assert d["setup_complete"] is False
        assert d["nome"] == "CleanTec"

    def test_company_put_full_setup_complete(self, admin_token):
        body = {
            "nome": "CleanTec SpA",
            "ragione_sociale": "CleanTec Società per Azioni",
            "partita_iva": "IT01234567890",
            "codice_fiscale": "IT01234567890",
            "indirizzo": "Via Roma 1, 20100 Milano",
            "iban": "IT60X0542811101000000123456",
            "email": "info@cleantec.it",
            "pec": "cleantec@pec.it",
            "telefono": "+39 02 1234567",
            "sito_web": "https://cleantec.it",
        }
        r = requests.put(f"{API}/company", json=body, headers=_h(admin_token))
        assert r.status_code == 200
        d = r.json()
        assert d["setup_complete"] is True, f"Expected setup_complete=true; got {d}"
        assert d["partita_iva"] == "IT01234567890"

        # Verify GET reflects persistence
        r2 = requests.get(f"{API}/company", headers=_h(admin_token))
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["setup_complete"] is True
        assert d2["email"] == "info@cleantec.it"

    def test_company_rbac_logistica_forbidden(self, logistica_token):
        r = requests.get(f"{API}/company", headers=_h(logistica_token))
        assert r.status_code == 403


# ---- Logo upload/get/delete ----------------------------------------------
class TestLogo:
    @staticmethod
    def _make_png(size=(300, 300), color=(100, 50, 200)):
        img = Image.new("RGB", size, color)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    def test_logo_upload_png(self, admin_token):
        png = self._make_png()
        files = {"file": ("logo.png", png, "image/png")}
        r = requests.post(f"{API}/company/logo", headers=_h(admin_token), files=files)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["url"] == "/api/company/logo"
        # resize <= 512 (thumbnail may keep same size if <=512)
        assert d["width"] <= 512 and d["height"] <= 512
        assert d["size"] > 0

    def test_logo_get_returns_webp(self, admin_token):
        r = requests.get(f"{API}/company/logo", headers=_h(admin_token))
        assert r.status_code == 200
        assert "image" in r.headers.get("content-type", "")
        assert len(r.content) > 0

    def test_logo_delete_then_404(self, admin_token):
        r = requests.delete(f"{API}/company/logo", headers=_h(admin_token))
        assert r.status_code == 200
        r2 = requests.get(f"{API}/company/logo", headers=_h(admin_token))
        assert r2.status_code == 404


# ---- DDT PDF + Fattura PDF -----------------------------------------------
@pytest.fixture(scope="module")
def ddt_and_fattura(admin_token):
    """Find (or create) one non_fatturato DDT + one fattura."""
    # Find existing non_fatturato DDT
    r = requests.get(f"{API}/ddt?stato_fatturazione=non_fatturato", headers=_h(admin_token))
    assert r.status_code == 200
    ddts = r.json()
    ddt = ddts[0] if ddts else None

    r2 = requests.get(f"{API}/fatture", headers=_h(admin_token))
    assert r2.status_code == 200
    fatt_list = r2.json()
    fatt = fatt_list[0] if fatt_list else None

    return {"ddt": ddt, "fattura": fatt}


class TestPDF:
    def test_ddt_pdf(self, admin_token, ddt_and_fattura):
        ddt = ddt_and_fattura["ddt"]
        if not ddt:
            pytest.skip("Nessun DDT seed disponibile")
        r = requests.get(f"{API}/ddt/{ddt['id']}/pdf", headers=_h(admin_token))
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF"
        assert len(r.content) > 1000

    def test_fattura_pdf(self, admin_token, ddt_and_fattura):
        fatt = ddt_and_fattura["fattura"]
        if not fatt:
            pytest.skip("Nessuna fattura seed disponibile")
        r = requests.get(f"{API}/fatture/{fatt['id']}/pdf", headers=_h(admin_token))
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF"
        assert len(r.content) > 1000


# ---- DDT PATCH (edit, recompute, fatturato→409) --------------------------
class TestDDTEdit:
    def test_edit_non_fatturato_recompute(self, admin_token):
        r = requests.get(f"{API}/ddt?stato_fatturazione=non_fatturato", headers=_h(admin_token))
        ddts = r.json()
        if not ddts:
            pytest.skip("Nessun DDT non_fatturato")
        ddt = ddts[0]
        if not ddt.get("righe"):
            pytest.skip("DDT senza righe")
        # Prepare patch: increase qty of first row
        riga0 = ddt["righe"][0]
        new_qty = float(riga0.get("quantita", 1)) + 1
        patch = {
            "note": "TEST_patched",
            "righe": [{
                "articolo_id": riga0["articolo_id"],
                "quantita": new_qty,
            }],
        }
        rp = requests.patch(f"{API}/ddt/{ddt['id']}", json=patch, headers=_h(admin_token))
        assert rp.status_code == 200, rp.text
        # GET verify
        rg = requests.get(f"{API}/ddt/{ddt['id']}", headers=_h(admin_token))
        assert rg.status_code == 200
        updated = rg.json()
        assert updated["note"] == "TEST_patched"
        assert len(updated["righe"]) == 1
        assert float(updated["righe"][0]["quantita"]) == new_qty
        # Imponibile recomputed = prezzo * qty
        expected = round(updated["righe"][0]["prezzo_unitario"] * new_qty, 2)
        assert abs(updated["imponibile"] - expected) < 0.02

    def test_edit_fatturato_forbidden(self, admin_token):
        r = requests.get(f"{API}/ddt?stato_fatturazione=fatturato", headers=_h(admin_token))
        ddts = r.json()
        if not ddts:
            pytest.skip("Nessun DDT fatturato disponibile")
        ddt = ddts[0]
        patch = {"note": "TEST_should_fail"}
        rp = requests.patch(f"{API}/ddt/{ddt['id']}", json=patch, headers=_h(admin_token))
        assert rp.status_code in (400, 409), f"Expected 400/409, got {rp.status_code}"
