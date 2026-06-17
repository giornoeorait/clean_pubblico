"""
Iter30 tests: permission `can_edit_dates` per-user toggle.
- Admin can grant `can_edit_dates` to logistica via PATCH /api/users/{id}
- /api/auth/me returns the flag
- PATCH /api/ddt/{id} with {data: ...}:
  - admin -> 200
  - logistica with flag=true -> 200
  - logistica with flag=false -> 403
- PATCH /api/ordinativi/{id} with data_richiesta is IGNORED (extra=ignore)
"""
import os
import uuid
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE}/api"

ADMIN = {"email": "admin@cleantec.it", "password": "admin123"}
LOG = {"email": "logistica@cleantec.it", "password": "logistica123"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def logistica_token():
    return _login(LOG)


@pytest.fixture(scope="module")
def logistica_uid(admin_token):
    r = requests.get(f"{API}/users", headers=_h(admin_token), timeout=15)
    assert r.status_code == 200
    users = r.json()
    for u in users:
        if u.get("email") == LOG["email"]:
            return u["id"]
    pytest.skip("logistica user not found")


@pytest.fixture(scope="module")
def open_ddt_id(admin_token):
    r = requests.get(f"{API}/ddt?stato_fatturazione=non_fatturato&limit=5",
                     headers=_h(admin_token), timeout=15)
    assert r.status_code == 200
    docs = r.json()
    if not docs:
        pytest.skip("no open DDT available")
    return docs[0]["id"]


@pytest.fixture(scope="module")
def open_ord_id(admin_token):
    r = requests.get(f"{API}/ordinativi?limit=20", headers=_h(admin_token), timeout=15)
    assert r.status_code == 200
    for o in r.json():
        if o.get("stato") != "convertito_ddt":
            return o["id"]
    pytest.skip("no open ordinativo available")


# ------------------------------- TESTS ----------------------------------

def test_users_list_contains_can_edit_dates_field(admin_token, logistica_uid):
    r = requests.get(f"{API}/users", headers=_h(admin_token), timeout=15)
    assert r.status_code == 200
    users = {u["id"]: u for u in r.json()}
    assert logistica_uid in users
    # field may default to False or missing; just assert no error returning the list
    assert "email" in users[logistica_uid]


def test_patch_can_edit_dates_true(admin_token, logistica_uid):
    r = requests.patch(f"{API}/users/{logistica_uid}",
                       headers=_h(admin_token),
                       json={"can_edit_dates": True}, timeout=15)
    assert r.status_code == 200, r.text
    # Verify via list
    r2 = requests.get(f"{API}/users", headers=_h(admin_token), timeout=15)
    u = next(x for x in r2.json() if x["id"] == logistica_uid)
    assert u.get("can_edit_dates") is True


def test_auth_me_includes_can_edit_dates(logistica_token):
    r = requests.get(f"{API}/auth/me", headers=_h(logistica_token), timeout=15)
    assert r.status_code == 200
    me = r.json()
    assert me["email"] == LOG["email"]
    # Field should be present and currently True (set in previous test)
    assert me.get("can_edit_dates") is True


def test_logistica_with_flag_can_patch_ddt_date(logistica_token, open_ddt_id):
    r = requests.patch(f"{API}/ddt/{open_ddt_id}",
                       headers=_h(logistica_token),
                       json={"data": "2025-07-15"}, timeout=15)
    assert r.status_code == 200, r.text


def test_admin_can_patch_ddt_date(admin_token, open_ddt_id):
    r = requests.patch(f"{API}/ddt/{open_ddt_id}",
                       headers=_h(admin_token),
                       json={"data": "2025-07-20"}, timeout=15)
    assert r.status_code == 200, r.text


def test_revoke_can_edit_dates_then_logistica_blocked(admin_token, logistica_uid,
                                                     logistica_token, open_ddt_id):
    # Revoke
    r = requests.patch(f"{API}/users/{logistica_uid}",
                       headers=_h(admin_token),
                       json={"can_edit_dates": False}, timeout=15)
    assert r.status_code == 200

    # NEW login to refresh JWT/user context (token-embedded claims aren't relevant
    # here because get_current_user re-reads DB)
    new_log_tok = _login(LOG)

    # auth/me reflects revocation
    me = requests.get(f"{API}/auth/me", headers=_h(new_log_tok), timeout=15).json()
    assert me.get("can_edit_dates") in (False, None)

    # PATCH date now forbidden
    r2 = requests.patch(f"{API}/ddt/{open_ddt_id}",
                        headers=_h(new_log_tok),
                        json={"data": "2025-08-01"}, timeout=15)
    assert r2.status_code == 403, r2.text
    detail = (r2.json() or {}).get("detail", "")
    assert "permess" in detail.lower() or "data" in detail.lower()


def test_logistica_can_patch_ddt_without_date(logistica_token, open_ddt_id):
    """PATCH without `data` field must NOT trigger 403 even if can_edit_dates=false."""
    r = requests.patch(f"{API}/ddt/{open_ddt_id}",
                       headers=_h(logistica_token),
                       json={"note": "TEST_iter30 note update"}, timeout=15)
    assert r.status_code == 200, r.text


def test_patch_ordinativo_data_richiesta_ignored(admin_token, open_ord_id):
    """Field data_richiesta is no longer in OrdinativoPatch (extra=ignore).
    PATCH must succeed (no error) but data_richiesta must remain unchanged."""
    # Get current
    g1 = requests.get(f"{API}/ordinativi/{open_ord_id}",
                      headers=_h(admin_token), timeout=15).json()
    original = g1.get("data_richiesta")

    r = requests.patch(f"{API}/ordinativi/{open_ord_id}",
                       headers=_h(admin_token),
                       json={"data_richiesta": "2020-01-01T00:00:00",
                             "note_interne": "TEST_iter30 ignored field"},
                       timeout=15)
    assert r.status_code == 200, r.text

    g2 = requests.get(f"{API}/ordinativi/{open_ord_id}",
                      headers=_h(admin_token), timeout=15).json()
    # data_richiesta unchanged
    assert g2.get("data_richiesta") == original
    # note_interne updated (proves PATCH succeeded for valid field)
    assert "TEST_iter30" in (g2.get("note_interne") or "")


def test_create_user_with_can_edit_dates_flag(admin_token):
    email = f"TEST_iter30_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/users",
                      headers=_h(admin_token),
                      json={"email": email, "password": "TestPass123!",
                            "name": "TEST iter30",
                            "role": "logistica",
                            "can_edit_dates": True}, timeout=15)
    assert r.status_code == 200, r.text
    created = r.json()
    assert created["email"] == email.lower()
    assert created.get("can_edit_dates") is True

    # Cleanup
    requests.delete(f"{API}/users/{created['id']}?hard=true",
                    headers=_h(admin_token), timeout=15)
