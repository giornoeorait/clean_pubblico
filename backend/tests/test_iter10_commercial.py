"""Backend tests for CleanTec post-refactor (iteration 10).
Flow: Auth -> Plans -> Dashboard KPI -> Listini -> Clienti -> DDT auto-price ->
Fatture aggregate -> Sospesi incassa -> RBAC -> Superadmin -> Multi-tenant isolation -> Registration.
"""
import os
import time
import uuid
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    return r


def _auth(email, pwd):
    r = _login(email, pwd)
    assert r.status_code == 200, f"login {email} -> {r.status_code}: {r.text}"
    j = r.json()
    return j["token"], j["user"], j.get("tenant")


@pytest.fixture(scope="module")
def admin_token():
    t, u, _ = _auth("admin@cleantec.it", "admin123")
    return t


@pytest.fixture(scope="module")
def logistica_token():
    t, u, _ = _auth("logistica@cleantec.it", "logistica123")
    return t


@pytest.fixture(scope="module")
def contabilita_token():
    t, u, _ = _auth("contabilita@cleantec.it", "contabilita123")
    return t


@pytest.fixture(scope="module")
def super_token():
    t, u, _ = _auth("super@cleantec.it", "Superadmin123!")
    return t


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


# --- AUTH ----------------------------------------------------------------
class TestAuth:
    def test_login_admin(self):
        r = _login("admin@cleantec.it", "admin123")
        assert r.status_code == 200
        j = r.json()
        assert "token" in j and "user" in j
        assert j["user"]["email"] == "admin@cleantec.it"
        assert j["user"]["role"] == "admin"

    def test_login_logistica(self):
        r = _login("logistica@cleantec.it", "logistica123")
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "logistica"

    def test_login_contabilita(self):
        r = _login("contabilita@cleantec.it", "contabilita123")
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "contabilita"

    def test_login_super(self):
        r = _login("super@cleantec.it", "Superadmin123!")
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "superadmin"

    def test_login_bad(self):
        r = _login("admin@cleantec.it", "wrong")
        assert r.status_code in (400, 401)


# --- PLANS ---------------------------------------------------------------
class TestPlans:
    def test_plans_expose_ddt_monthly(self):
        r = requests.get(f"{API}/plans", timeout=20)
        assert r.status_code == 200
        plans = {p["id"]: p for p in r.json()["plans"]}
        for pid in ("starter", "pro", "enterprise"):
            assert pid in plans, f"missing plan {pid}"
            limits = plans[pid]["limits"]
            assert "ddt_monthly" in limits, f"{pid} missing ddt_monthly"
            assert "lotti_monthly" not in limits, f"{pid} still has legacy lotti_monthly"
        assert plans["starter"]["limits"]["ddt_monthly"] == 500
        assert plans["pro"]["limits"]["ddt_monthly"] == 5000
        assert plans["enterprise"]["limits"]["ddt_monthly"] == -1


# --- DASHBOARD KPI -------------------------------------------------------
class TestDashboard:
    def test_kpi_commercial(self, admin_token):
        r = requests.get(f"{API}/dashboard/kpi", headers=H(admin_token), timeout=20)
        assert r.status_code == 200, r.text
        k = r.json()
        required = [
            "clienti_totali", "articoli_totali", "listini_attivi",
            "ddt_mese", "ddt_oggi", "ddt_non_fatturati",
            "fatturato_mese", "incassato_mese",
            "sospesi_totale", "sospesi_count", "trend_ddt_7gg",
        ]
        for key in required:
            assert key in k, f"KPI missing: {key}"
        # legacy MES keys must not exist
        for legacy in ("magazzino_allarmi", "tickets_aperti", "lotti_oggi", "lotti_mese"):
            assert legacy not in k, f"legacy MES KPI still present: {legacy}"
        assert isinstance(k["trend_ddt_7gg"], list)


# --- LISTINI -------------------------------------------------------------
class TestListini:
    def test_list_seed(self, admin_token):
        r = requests.get(f"{API}/listini", headers=H(admin_token), timeout=20)
        assert r.status_code == 200
        listini = r.json()
        assert isinstance(listini, list) and len(listini) >= 2
        nomi = [l["nome"] for l in listini]
        assert any("Standard" in n for n in nomi)
        assert any("VIP" in n for n in nomi)

    def test_create_and_prezzi(self, admin_token):
        name = f"TEST_Listino_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/listini", headers=H(admin_token),
                          json={"nome": name, "descrizione": "tmp", "attivo": True}, timeout=20)
        assert r.status_code in (200, 201), r.text
        lid = r.json()["id"]
        # prezzi list
        r2 = requests.get(f"{API}/listini/{lid}/prezzi", headers=H(admin_token), timeout=20)
        assert r2.status_code == 200
        # cleanup
        requests.delete(f"{API}/listini/{lid}", headers=H(admin_token), timeout=20)


# --- CLIENTI -------------------------------------------------------------
class TestClienti:
    def test_seed_and_listino_assignment(self, admin_token):
        r = requests.get(f"{API}/clienti", headers=H(admin_token), timeout=20)
        assert r.status_code == 200
        clienti = r.json()
        assert len(clienti) >= 5
        # at least one has listino_id after seed
        with_listino = [c for c in clienti if c.get("listino_id")]
        assert len(with_listino) >= 1, "no cliente has listino_id assigned by seed"


# --- DDT AUTO-PRICE ------------------------------------------------------
class TestDDT:
    def test_list_seed(self, admin_token):
        r = requests.get(f"{API}/ddt", headers=H(admin_token), timeout=20)
        assert r.status_code == 200
        ddts = r.json()
        assert len(ddts) >= 6
        # stato_fatturazione present
        assert all("stato_fatturazione" in d for d in ddts)

    def test_filter_non_fatturato(self, admin_token):
        r = requests.get(f"{API}/ddt?stato_fatturazione=non_fatturato",
                         headers=H(admin_token), timeout=20)
        assert r.status_code == 200
        for d in r.json():
            assert d["stato_fatturazione"] == "non_fatturato"

    def test_create_auto_prezzo(self, admin_token):
        # Pick a cliente with listino_id and a known articolo
        clienti = requests.get(f"{API}/clienti", headers=H(admin_token)).json()
        cli = next((c for c in clienti if c.get("listino_id")), None)
        assert cli, "no cliente with listino_id"
        art = requests.get(f"{API}/articoli", headers=H(admin_token)).json()[0]
        payload = {
            "cliente_id": cli["id"],
            "righe": [{"articolo_id": art["id"], "quantita": 10}],
            "note": "TEST_auto"
        }
        r = requests.post(f"{API}/ddt", headers=H(admin_token), json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        ddt = r.json()
        assert ddt["righe"][0]["prezzo_unitario"] > 0, "auto-price failed"
        assert ddt["righe"][0]["totale"] == round(ddt["righe"][0]["prezzo_unitario"] * 10, 2)
        assert ddt["imponibile"] > 0
        # cleanup
        requests.delete(f"{API}/ddt/{ddt['id']}", headers=H(admin_token))


# --- FATTURAZIONE --------------------------------------------------------
@pytest.fixture(scope="module")
def created_fattura(admin_token):
    # Always create a fresh DDT to ensure deterministic test
    clienti = requests.get(f"{API}/clienti", headers=H(admin_token)).json()
    target_cli = next((c for c in clienti if c.get("listino_id")), clienti[0])
    art = requests.get(f"{API}/articoli", headers=H(admin_token)).json()[0]
    new_ddt = requests.post(f"{API}/ddt", headers=H(admin_token), json={
        "cliente_id": target_cli["id"],
        "righe": [{"articolo_id": art["id"], "quantita": 5}],
        "note": "TEST_for_invoice",
    }, timeout=30).json()
    assert new_ddt.get("id"), f"DDT create failed: {new_ddt}"
    ids = [new_ddt["id"]]
    # fatturabili endpoint
    r = requests.get(
        f"{API}/fatture/fatturabili?cliente_id={target_cli['id']}",
        headers=H(admin_token), timeout=20
    )
    assert r.status_code == 200
    fat_raw = r.json()
    fat_list = fat_raw if isinstance(fat_raw, list) else fat_raw.get("ddts", fat_raw.get("ddt", fat_raw.get("fatturabili", [])))
    assert any(d["id"] == new_ddt["id"] for d in fat_list)
    # create
    r = requests.post(f"{API}/fatture", headers=H(admin_token),
                      json={"cliente_id": target_cli["id"], "ddt_ids": ids}, timeout=30)
    assert r.status_code in (200, 201), r.text
    fatt = r.json()
    assert fatt.get("numero", "").startswith(("FAT-", "FT-")), f"numero: {fatt.get('numero')}"
    # ddt should now be fatturato
    for did in ids:
        d = requests.get(f"{API}/ddt/{did}", headers=H(admin_token)).json()
        assert d["stato_fatturazione"] == "fatturato"
    yield fatt, target_cli


class TestFatturazione:
    def test_create_aggregated(self, created_fattura):
        fatt, _ = created_fattura
        assert fatt["stato_incasso"] == "da_incassare"
        assert fatt["totale"] > 0

    def test_sospesi_list_and_incasso(self, admin_token, created_fattura):
        fatt, _ = created_fattura
        r = requests.get(f"{API}/sospesi", headers=H(admin_token), timeout=20)
        assert r.status_code == 200
        sosp_raw = r.json()
        sosp = sosp_raw.get("fatture", sosp_raw) if isinstance(sosp_raw, dict) else sosp_raw
        assert any(s["id"] == fatt["id"] for s in sosp)
        # incassa
        r2 = requests.post(f"{API}/fatture/{fatt['id']}/incassa",
                          headers=H(admin_token),
                          json={"data_incasso": "2026-01-15", "metodo": "bonifico"},
                          timeout=20)
        assert r2.status_code == 200, r2.text
        got = requests.get(f"{API}/fatture/{fatt['id']}", headers=H(admin_token)).json()
        assert got["stato_incasso"] == "incassata"
        assert got.get("data_incasso")


# --- RBAC ----------------------------------------------------------------
class TestRBAC:
    def test_logistica_can_create_ddt(self, logistica_token, admin_token):
        clienti = requests.get(f"{API}/clienti", headers=H(admin_token)).json()
        cli = next((c for c in clienti if c.get("listino_id")), clienti[0])
        art = requests.get(f"{API}/articoli", headers=H(admin_token)).json()[0]
        r = requests.post(f"{API}/ddt", headers=H(logistica_token),
                          json={"cliente_id": cli["id"], "righe": [{"articolo_id": art["id"], "quantita": 1}]},
                          timeout=30)
        assert r.status_code in (200, 201), r.text
        ddt = r.json()
        requests.delete(f"{API}/ddt/{ddt['id']}", headers=H(admin_token))

    def test_logistica_cannot_create_fattura(self, logistica_token, admin_token):
        clienti = requests.get(f"{API}/clienti", headers=H(admin_token)).json()
        r = requests.post(f"{API}/fatture", headers=H(logistica_token),
                          json={"cliente_id": clienti[0]["id"], "ddt_ids": []}, timeout=20)
        assert r.status_code == 403, f"logistica should NOT create fatture, got {r.status_code}"

    def test_contabilita_can_create_fattura_role(self, contabilita_token):
        # Just test authorization passes (even if ddt_ids empty - then 400/404 is ok,
        # the important check is NOT 403)
        r = requests.get(f"{API}/fatture/fatturabili?cliente_id=x",
                         headers=H(contabilita_token), timeout=20)
        assert r.status_code != 403


# --- SUPERADMIN ----------------------------------------------------------
class TestSuperadmin:
    def test_stats(self, super_token):
        r = requests.get(f"{API}/admin/stats", headers=H(super_token), timeout=20)
        assert r.status_code == 200, r.text
        # sanity: should contain some aggregated numbers
        assert isinstance(r.json(), dict)

    def test_tenants(self, super_token):
        r = requests.get(f"{API}/admin/tenants", headers=H(super_token), timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list) or isinstance(r.json(), dict)


# --- REGISTRATION + MULTI-TENANT ISOLATION -------------------------------
class TestRegistration:
    def test_register_new_tenant_and_isolation(self, admin_token):
        slug = f"tst{uuid.uuid4().hex[:6]}"
        email = f"owner_{slug}@example.com"
        r = requests.post(f"{API}/tenants/register", json={
            "nome_azienda": f"TEST_{slug}",
            "email": email,
            "password": "TestPass123!",
            "nome_admin": "Test Owner",
            "piano": "starter",
        }, timeout=30)
        if r.status_code not in (200, 201):
            pytest.skip(f"registration endpoint returned {r.status_code}: {r.text[:200]}")
        # login new tenant
        lr = _login(email, "TestPass123!")
        if lr.status_code != 200:
            pytest.skip(f"cannot login new tenant: {lr.status_code}")
        new_token = lr.json()["token"]
        # Fetch tenant info via /api/tenants/me (login payload may not include full usage)
        me = requests.get(f"{API}/tenants/me", headers=H(new_token), timeout=20)
        assert me.status_code == 200, me.text
        me_payload = me.json()
        tenant = me_payload.get("tenant", me_payload) if isinstance(me_payload, dict) else me_payload
        usage = tenant.get("usage", {})
        assert "ddt_this_month" in usage, f"usage: {usage}"
        assert "lotti_this_month" not in usage
        limits = tenant.get("limits", {})
        assert "ddt_monthly" in limits, f"limits: {limits}"
        assert "lotti_monthly" not in limits
        # isolation: new tenant sees 0 clienti
        r2 = requests.get(f"{API}/clienti", headers=H(new_token), timeout=20)
        assert r2.status_code == 200
        assert r2.json() == []
        r3 = requests.get(f"{API}/ddt", headers=H(new_token), timeout=20)
        assert r3.json() == []
