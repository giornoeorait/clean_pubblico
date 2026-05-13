"""Iter-25: Backup failure notification settings — backend test suite.

Covers:
  - GET /api/company/notifications defaults
  - PUT /api/company/notifications validation (invalid email, dedupe+lowercase, max 20)
  - POST /api/company/notifications/test (sent rows w/ status logged|sent)
  - Auth guards (401)
  - Tenant isolation via direct Mongo doc injection
  - backup_service._send_failure_alert pipeline: 1 email_events row per recipient
"""
import asyncio
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

ADMIN_EMAIL = "admin@cleantec.it"
ADMIN_PASS = "admin123"


# ---------------- fixtures ----------------
@pytest.fixture(scope="session")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def tenant_id(mongo):
    u = mongo.users.find_one({"email": ADMIN_EMAIL}, {"_id": 0, "tenant_id": 1})
    assert u, "admin user not found"
    return u["tenant_id"]


@pytest.fixture
def api_client(admin_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(autouse=True)
def reset_notifications(mongo, tenant_id):
    """Ensure clean state before+after each test."""
    mongo.company.update_one(
        {"tenant_id": tenant_id},
        {"$set": {"notifications": {"recipients": [], "include_admin": True}}},
        upsert=True,
    )
    yield
    mongo.company.update_one(
        {"tenant_id": tenant_id},
        {"$set": {"notifications": {"recipients": [], "include_admin": True}}},
    )


# ---------------- auth ----------------
class TestAuthGuards:
    def test_get_requires_auth(self):
        r = requests.get(f"{API}/company/notifications")
        assert r.status_code in (401, 403)

    def test_put_requires_auth(self):
        r = requests.put(f"{API}/company/notifications", json={"recipients": [], "include_admin": True})
        assert r.status_code in (401, 403)

    def test_post_test_requires_auth(self):
        r = requests.post(f"{API}/company/notifications/test")
        assert r.status_code in (401, 403)


# ---------------- GET ----------------
class TestGetDefaults:
    def test_default_shape(self, api_client):
        r = api_client.get(f"{API}/company/notifications")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data == {"recipients": [], "include_admin": True}


# ---------------- PUT ----------------
class TestPut:
    def test_save_and_persist(self, api_client, mongo, tenant_id):
        payload = {"recipients": ["a@b.com", "c@d.com"], "include_admin": True}
        r = api_client.put(f"{API}/company/notifications", json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["recipients"] == ["a@b.com", "c@d.com"]
        assert body["include_admin"] is True

        # GET-after-PUT persistence
        r2 = api_client.get(f"{API}/company/notifications")
        assert r2.json() == body

        # mongo state
        doc = mongo.company.find_one({"tenant_id": tenant_id}, {"_id": 0, "notifications": 1})
        assert doc["notifications"]["recipients"] == ["a@b.com", "c@d.com"]

    def test_invalid_email_returns_400(self, api_client):
        r = api_client.put(f"{API}/company/notifications",
                           json={"recipients": ["notanemail"], "include_admin": True})
        assert r.status_code == 400
        body = r.json()
        msg = body.get("detail") or body.get("message") or ""
        assert "Email non valida" in msg, f"Got: {msg}"

    def test_dedupe_and_lowercase(self, api_client):
        r = api_client.put(f"{API}/company/notifications",
                           json={"recipients": ["FOO@BAR.com", "foo@bar.com", "x@y.it"],
                                 "include_admin": False})
        assert r.status_code == 200, r.text
        body = r.json()
        # Lowercased + deduped, order preserved
        assert body["recipients"] == ["foo@bar.com", "x@y.it"]
        assert body["include_admin"] is False

    def test_max_20_recipients(self, api_client):
        # 20 should succeed
        recs20 = [f"user{i}@example.com" for i in range(20)]
        r = api_client.put(f"{API}/company/notifications",
                           json={"recipients": recs20, "include_admin": True})
        assert r.status_code == 200, r.text
        assert len(r.json()["recipients"]) == 20

        # 21 should fail
        recs21 = [f"user{i}@example.com" for i in range(21)]
        r2 = api_client.put(f"{API}/company/notifications",
                            json={"recipients": recs21, "include_admin": True})
        assert r2.status_code == 400
        msg = r2.json().get("detail", "")
        assert "20" in msg or "Massimo" in msg


# ---------------- TEST EMAIL ----------------
class TestNotificationTest:
    def test_send_test_to_admin_by_default(self, api_client, mongo, tenant_id):
        # Wipe prior notification_test events
        mongo.email_events.delete_many({"tenant_id": tenant_id, "context.type": "notification_test"})

        r = api_client.post(f"{API}/company/notifications/test")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert isinstance(body["sent"], list)
        assert len(body["sent"]) >= 1  # at least the tenant admin
        for s in body["sent"]:
            assert s["status"] in ("sent", "logged", "failed")
            assert "@" in s["to"]

        # email_events rows persisted
        cnt = mongo.email_events.count_documents(
            {"tenant_id": tenant_id, "context.type": "notification_test"}
        )
        assert cnt == len(body["sent"])

    def test_send_test_with_no_recipients_returns_400(self, api_client):
        # No additional recipients + include_admin=False → empty → 400
        api_client.put(f"{API}/company/notifications",
                       json={"recipients": [], "include_admin": False})
        r = api_client.post(f"{API}/company/notifications/test")
        assert r.status_code == 400

    def test_send_test_with_custom_recipients(self, api_client, mongo, tenant_id):
        mongo.email_events.delete_many({"tenant_id": tenant_id, "context.type": "notification_test"})
        api_client.put(f"{API}/company/notifications",
                       json={"recipients": ["ops@example.com", "ceo@example.com"],
                             "include_admin": True})
        r = api_client.post(f"{API}/company/notifications/test")
        assert r.status_code == 200
        sent = r.json()["sent"]
        tos = {s["to"] for s in sent}
        assert "ops@example.com" in tos
        assert "ceo@example.com" in tos
        assert ADMIN_EMAIL in tos


# ---------------- TENANT ISOLATION ----------------
class TestTenantIsolation:
    def test_other_tenant_recipients_invisible(self, api_client, mongo, tenant_id):
        fake_tid = f"TEST_FAKE_TENANT_{uuid.uuid4().hex[:8]}"
        mongo.company.insert_one({
            "tenant_id": fake_tid,
            "nome": "Fake Co",
            "notifications": {"recipients": ["leak@evil.com"], "include_admin": False},
        })
        try:
            r = api_client.get(f"{API}/company/notifications")
            assert r.status_code == 200
            data = r.json()
            assert "leak@evil.com" not in (data.get("recipients") or [])
        finally:
            mongo.company.delete_one({"tenant_id": fake_tid})


# ---------------- BACKUP FAILURE PIPELINE ----------------
class TestFailureAlertPipeline:
    def test_send_failure_alert_persists_events(self, api_client, mongo, tenant_id):
        # Configure recipients + include_admin
        api_client.put(f"{API}/company/notifications",
                       json={"recipients": ["alerts@example.com", "sysadmin@example.com"],
                             "include_admin": True})

        # Clean prior backup_failure events
        mongo.email_events.delete_many(
            {"tenant_id": tenant_id, "context.type": "backup_failure"}
        )

        # Invoke directly via in-process import — backup_service operates on the SAME db
        import sys
        sys.path.insert(0, "/app/backend")
        from backup_service import _send_failure_alert, resolve_alert_recipients  # noqa: E402

        loop = asyncio.new_event_loop()
        try:
            recipients = loop.run_until_complete(resolve_alert_recipients(tenant_id))
            loop.run_until_complete(_send_failure_alert(tenant_id, "simulated error"))
        finally:
            loop.close()

        assert "alerts@example.com" in recipients
        assert "sysadmin@example.com" in recipients
        assert ADMIN_EMAIL in recipients  # admin email auto-included

        # Allow async tasks to settle
        import time
        time.sleep(0.5)

        events = list(mongo.email_events.find(
            {"tenant_id": tenant_id, "context.type": "backup_failure"},
            {"_id": 0}
        ))
        assert len(events) == len(recipients), f"events={len(events)}, recipients={len(recipients)}"
        event_recipients = {e.get("to") for e in events}
        for r in recipients:
            assert r in event_recipients
        for e in events:
            assert e.get("status") in ("sent", "logged", "failed")
