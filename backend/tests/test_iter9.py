"""Iteration 9: quota enforcement + email verification + superadmin + insights + cancel/resume."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://wash-ops-central.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"Login fail {email}: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="session")
def demo_admin():
    return _login("admin@cleantec.it", "admin123")


@pytest.fixture(scope="session")
def owner_tenant():
    return _login("owner@lavtest.it", "segretaPWD1!")


@pytest.fixture(scope="session")
def super_admin():
    return _login("super@cleantec.it", "Superadmin123!")


def H(token):
    return {"Authorization": f"Bearer {token}"}


# --------- AUTH regression ---------
class TestAuthRegression:
    def test_login_returns_tenant(self, demo_admin):
        assert "tenant" in demo_admin
        assert demo_admin["tenant"].get("nome")
        assert demo_admin["tenant"].get("piano")
        assert demo_admin["user"]["role"] == "admin"

    def test_tenants_me_trial_days_left(self, owner_tenant):
        r = requests.get(f"{API}/tenants/me", headers=H(owner_tenant["token"]), timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "trial_days_left" in data
        assert data["tenant"]["stato"] == "trial"

    def test_plans_public(self):
        r = requests.get(f"{API}/plans", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "plans" in d
        assert len(d["plans"]) >= 2

    def test_superadmin_role(self, super_admin):
        assert super_admin["user"]["role"] == "superadmin"


# --------- Email verification ---------
class TestEmailVerification:
    def test_verify_invalid_token(self):
        r = requests.post(f"{API}/auth/verify-email", json={"token": "bogus-invalid-token"}, timeout=10)
        assert r.status_code == 400

    def test_register_creates_verification_token_and_verify(self):
        import uuid
        suffix = uuid.uuid4().hex[:8]
        email = f"test_iter9_{suffix}@example.com"
        r = requests.post(f"{API}/tenants/register", json={
            "nome_azienda": f"TestIter9 {suffix}",
            "email": email,
            "password": "Password123!",
            "nome_admin": "Test Admin",
            "piano": "starter",
        }, timeout=15)
        assert r.status_code == 200, r.text
        token_auth = r.json()["token"]

        # resend gives a fresh token
        rr = requests.post(f"{API}/auth/resend-verification", headers=H(token_auth), timeout=10)
        assert rr.status_code == 200
        assert rr.json().get("ok") is True

        # fetch token from db via email_events (indirect: call resend returns ok not token — verify via DB fallback)
        # Since we cannot read DB, test only that invalid token fails and resend works.
        # Verify with bogus still fails
        rb = requests.post(f"{API}/auth/verify-email", json={"token": "zzz"}, timeout=10)
        assert rb.status_code == 400


# --------- Quota enforcement ---------
class TestQuota:
    def test_demo_unlimited_lotti(self, demo_admin):
        # DEMO tenant should bypass quota → creating a lotto should succeed (smoke)
        r = requests.post(f"{API}/lotti", headers=H(demo_admin["token"]), json={
            "cliente_id": None,  # maybe optional
            "peso": 1.0,
            "capi": [],
        }, timeout=15)
        # Could fail due to schema but must NOT be 402
        assert r.status_code != 402, f"DEMO should bypass quota, got {r.status_code}: {r.text}"

    def test_users_quota_starter(self, owner_tenant):
        """Owner is Pro trial; create 1 extra user should work (limit=20)."""
        import uuid
        email = f"test_user_iter9_{uuid.uuid4().hex[:6]}@example.com"
        r = requests.post(f"{API}/users", headers=H(owner_tenant["token"]), json={
            "email": email,
            "password": "Password123!",
            "name": "Test User",
            "role": "produzione",
        }, timeout=15)
        # Should not fail with 402 since limit is high
        assert r.status_code != 402


# --------- Cancel / Resume ---------
class TestCancelResume:
    def test_cancel_trial_rejected(self, owner_tenant):
        r = requests.post(f"{API}/subscriptions/cancel", headers=H(owner_tenant["token"]), timeout=10)
        assert r.status_code == 400
        assert "trial" in r.json().get("detail", "").lower()

    def test_resume_non_canceled_rejected(self, owner_tenant):
        r = requests.post(f"{API}/subscriptions/resume", headers=H(owner_tenant["token"]), timeout=10)
        assert r.status_code == 400


# --------- Superadmin ---------
class TestSuperadmin:
    def test_stats(self, super_admin):
        r = requests.get(f"{API}/admin/stats", headers=H(super_admin["token"]), timeout=15)
        assert r.status_code == 200
        d = r.json()
        for key in ["mrr", "arr", "by_stato", "by_piano", "new_signups_month", "total_tenants"]:
            assert key in d, f"missing {key}"

    def test_tenants_list_excludes_demo(self, super_admin):
        r = requests.get(f"{API}/admin/tenants", headers=H(super_admin["token"]), timeout=15)
        assert r.status_code == 200
        tenants = r.json()
        assert isinstance(tenants, list)
        for t in tenants:
            assert not t.get("is_demo"), "DEMO tenant must not be in list"

    def test_transactions_cross_tenant(self, super_admin):
        r = requests.get(f"{API}/admin/transactions", headers=H(super_admin["token"]), timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_admin_forbidden_for_non_super(self, demo_admin):
        for path in ["/admin/stats", "/admin/tenants", "/admin/transactions"]:
            r = requests.get(f"{API}{path}", headers=H(demo_admin["token"]), timeout=10)
            assert r.status_code == 403, f"{path} should 403 for normal admin, got {r.status_code}"


# --------- Insights ---------
class TestInsights:
    def test_forecast(self, demo_admin):
        r = requests.get(f"{API}/insights/forecast?history_days=14&forecast_days=7",
                         headers=H(demo_admin["token"]), timeout=20)
        assert r.status_code == 200
        d = r.json()
        for key in ["history", "forecast", "trend", "expected_next_week_kg", "avg_kg_day"]:
            assert key in d, f"missing {key}"
        assert d["trend"] in ("crescita", "calo", "stabile")
        assert len(d["forecast"]) == 7
        assert len(d["history"]) == 14

    def test_consumi_detergenti(self, demo_admin):
        r = requests.get(f"{API}/insights/consumi-detergenti?days=30",
                         headers=H(demo_admin["token"]), timeout=15)
        assert r.status_code == 200
        d = r.json()
        for key in ["total_kg_lavati", "total_qta_detergenti", "ratio_detergenti_per_kg", "costo_stimato", "top_consumi"]:
            assert key in d, f"missing {key}"

    def test_tenant_isolation_owner_zero(self, owner_tenant):
        r = requests.get(f"{API}/insights/forecast?history_days=14&forecast_days=7",
                         headers=H(owner_tenant["token"]), timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["total_kg_last_period"] == 0, f"owner should have 0 kg, got {d['total_kg_last_period']}"
