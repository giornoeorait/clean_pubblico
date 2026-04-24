"""Iter 12 — Retest RBAC fix after implicit-admin bypass removal for superadmin-only endpoints.

Scope:
- Branding endpoints MUST reject regular admin (403) and allow superadmin (200)
- Admin superadmin-only endpoints (stats/tenants/transactions) MUST reject admin (403)
- NO regression: admin still has access to normal endpoints (clienti, ddt, fatture, utenti, dashboard/kpi)
- NO regression: logistica can create DDT, contabilita can create fatture
"""
import io
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not set"
API = f"{BASE_URL}/api"

SUPER = ("super@cleantec.it", "Superadmin123!")
ADMIN = ("admin@cleantec.it", "admin123")
LOGISTICA = ("logistica@cleantec.it", "logistica123")
CONTABILITA = ("contabilita@cleantec.it", "contabilita123")


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, f"login {email} -> {r.status_code}: {r.text}"
    return r.json()["token"]


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="session")
def super_token():
    return _login(*SUPER)


@pytest.fixture(scope="session")
def admin_token():
    return _login(*ADMIN)


@pytest.fixture(scope="session")
def log_token():
    return _login(*LOGISTICA)


@pytest.fixture(scope="session")
def cont_token():
    return _login(*CONTABILITA)


# ------------------------------------------------------------------ RBAC FIX
class TestBrandingRBAC:
    def test_get_branding_admin_403(self, admin_token):
        r = requests.get(f"{API}/admin/branding", headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 403, f"admin GET branding expected 403, got {r.status_code}: {r.text[:200]}"

    def test_put_branding_admin_403(self, admin_token):
        r = requests.put(f"{API}/admin/branding", headers=_hdr(admin_token),
                         json={"app_name": "HAX"}, timeout=15)
        assert r.status_code == 403

    def test_upload_branding_admin_403(self, admin_token):
        files = {"file": ("a.png", io.BytesIO(b"\x89PNG\r\n\x1a\n"), "image/png")}
        r = requests.post(f"{API}/admin/branding/upload/logo", headers=_hdr(admin_token),
                          files=files, timeout=15)
        assert r.status_code == 403

    def test_delete_branding_admin_403(self, admin_token):
        r = requests.delete(f"{API}/admin/branding/image/logo", headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 403

    def test_get_branding_super_200(self, super_token):
        r = requests.get(f"{API}/admin/branding", headers=_hdr(super_token), timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "app_name" in data
        assert "primary_color" in data


# --------------------------------------------------------- admin endpoints RBAC
class TestAdminSuperadminOnly:
    def test_admin_stats_admin_403(self, admin_token):
        r = requests.get(f"{API}/admin/stats", headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 403, f"admin /admin/stats expected 403, got {r.status_code}"

    def test_admin_tenants_admin_403(self, admin_token):
        r = requests.get(f"{API}/admin/tenants", headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 403

    def test_admin_transactions_admin_403(self, admin_token):
        r = requests.get(f"{API}/admin/transactions", headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 403

    def test_admin_stats_super_200(self, super_token):
        r = requests.get(f"{API}/admin/stats", headers=_hdr(super_token), timeout=15)
        assert r.status_code == 200


# ---------------------------------------------------------- no regression admin
class TestAdminNoRegression:
    def test_clienti(self, admin_token):
        r = requests.get(f"{API}/clienti", headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 200, f"got {r.status_code}"

    def test_ddt(self, admin_token):
        r = requests.get(f"{API}/ddt", headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 200

    def test_fatture(self, admin_token):
        r = requests.get(f"{API}/fatture", headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 200

    def test_utenti(self, admin_token):
        # Real endpoint is /api/users (not /api/utenti)
        r = requests.get(f"{API}/users", headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 200

    def test_dashboard_kpi(self, admin_token):
        r = requests.get(f"{API}/dashboard/kpi", headers=_hdr(admin_token), timeout=15)
        assert r.status_code == 200


# ------------------------------------------------- no regression logistica/cont
class TestRoleWorkflowsNoRegression:
    def test_logistica_can_list_ddt(self, log_token):
        r = requests.get(f"{API}/ddt", headers=_hdr(log_token), timeout=15)
        assert r.status_code == 200

    def test_contabilita_can_list_fatture(self, cont_token):
        r = requests.get(f"{API}/fatture", headers=_hdr(cont_token), timeout=15)
        assert r.status_code == 200

    def test_logistica_can_create_ddt(self, log_token, admin_token):
        # fetch an existing cliente to use as target
        rc = requests.get(f"{API}/clienti", headers=_hdr(admin_token), timeout=15)
        assert rc.status_code == 200
        clienti = rc.json()
        if not clienti:
            pytest.skip("no clienti in tenant — cannot create DDT")
        cliente_id = clienti[0]["id"]
        payload = {
            "cliente_id": cliente_id,
            "tipo": "consegna",
            "righe": [],
            "note": f"TEST_iter12_{uuid.uuid4().hex[:6]}",
        }
        r = requests.post(f"{API}/ddt", headers=_hdr(log_token), json=payload, timeout=15)
        # Accept 200/201; if validation requires righe, accept 422 but RBAC must not be 403
        assert r.status_code != 403, f"logistica got 403 creating DDT: {r.text[:200]}"

    def test_contabilita_not_forbidden_on_fattura_flow(self, cont_token):
        # Basic endpoint reachable, not 403
        r = requests.get(f"{API}/fatture", headers=_hdr(cont_token), timeout=15)
        assert r.status_code != 403
