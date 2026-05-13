"""Backend tests for Cloud Backups (Iter 24).

Covers:
- POST/GET/RESTORE/DELETE /api/company/backup/cloud
- Confirm guard, invalid snapshot_id
- Retention enforcement (keep 7)
- Multi-tenant isolation
- Auth required
"""
import os
import time
import json
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN = {"email": "admin@cleantec.it", "password": "admin123"}
RETENTION = 7

# Direct mongo for inserting cross-tenant fake snapshot
MONGO_URL = os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
DB_NAME = os.environ.get("DB_NAME") or "cleantec_db"


@pytest.fixture(scope="module")
def base_url():
    assert BASE_URL, "REACT_APP_BACKEND_URL not configured"
    return BASE_URL


@pytest.fixture(scope="module")
def admin_session(base_url):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{base_url}/api/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    s.headers.update({"Authorization": f"Bearer {data['token']}"})
    s.tenant_id = data["user"]["tenant_id"]
    return s


@pytest.fixture(scope="module", autouse=True)
def cleanup_after(admin_session, base_url):
    """Cleanup all cloud_backups for the tenant before & after the test module."""
    # Pre-cleanup: delete all existing snapshots for predictable retention testing
    try:
        cli = MongoClient(MONGO_URL, serverSelectionTimeoutMS=2000)
        cli[DB_NAME].cloud_backups.delete_many({"tenant_id": admin_session.tenant_id})
        # Also clean any cross-tenant fake we may insert
        cli[DB_NAME].cloud_backups.delete_many({"tenant_id": "TEST_OTHER_TENANT"})
    except Exception as e:
        pytest.skip(f"Mongo not reachable: {e}")
    yield
    try:
        cli[DB_NAME].cloud_backups.delete_many({"tenant_id": admin_session.tenant_id})
        cli[DB_NAME].cloud_backups.delete_many({"tenant_id": "TEST_OTHER_TENANT"})
    except Exception:
        pass


# -------- Auth --------
class TestAuth:
    def test_unauth_create_returns_401_or_403(self, base_url):
        r = requests.post(f"{base_url}/api/company/backup/cloud", timeout=10)
        assert r.status_code in (401, 403), f"got {r.status_code}"

    def test_unauth_list_returns_401_or_403(self, base_url):
        r = requests.get(f"{base_url}/api/company/backup/cloud/list", timeout=10)
        assert r.status_code in (401, 403)


# -------- Happy paths --------
class TestHappyFlow:
    def test_create_snapshot(self, admin_session, base_url):
        r = admin_session.post(f"{base_url}/api/company/backup/cloud", timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        snap = data["snapshot"]
        for k in ("id", "storage_path", "size_bytes", "total_records",
                  "source", "created_by", "azienda_nome", "created_at"):
            assert k in snap, f"missing field {k}"
        assert snap["source"] == "manual"
        assert snap["created_by"] == ADMIN["email"]
        assert isinstance(snap["size_bytes"], int) and snap["size_bytes"] > 0
        assert data["retention"] == RETENTION
        assert data["pruned"] == 0  # first snapshot, no pruning
        pytest.snapshot_id_happy = snap["id"]

    def test_list_contains_snapshot(self, admin_session, base_url):
        r = admin_session.get(f"{base_url}/api/company/backup/cloud/list", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert data["retention_days"] == RETENTION
        ids = [s["id"] for s in data["snapshots"]]
        assert pytest.snapshot_id_happy in ids

    def test_restore_merge(self, admin_session, base_url):
        sid = pytest.snapshot_id_happy
        r = admin_session.post(
            f"{base_url}/api/company/backup/cloud/{sid}/restore",
            json={"confirm": "RESTORE", "mode": "merge"}, timeout=120
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["mode"] == "merge"
        assert data["total_wiped"] == 0
        assert "total_inserted" in data and "total_updated" in data

    def test_restore_replace(self, admin_session, base_url):
        sid = pytest.snapshot_id_happy
        r = admin_session.post(
            f"{base_url}/api/company/backup/cloud/{sid}/restore",
            json={"confirm": "RESTORE", "mode": "replace"}, timeout=180
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["mode"] == "replace"
        assert data["total_wiped"] > 0, "replace mode should wipe existing records"

    def test_restore_missing_confirm(self, admin_session, base_url):
        sid = pytest.snapshot_id_happy
        r = admin_session.post(
            f"{base_url}/api/company/backup/cloud/{sid}/restore",
            json={"confirm": "wrong", "mode": "merge"}, timeout=20
        )
        assert r.status_code == 400

    def test_restore_invalid_id(self, admin_session, base_url):
        r = admin_session.post(
            f"{base_url}/api/company/backup/cloud/non-existent-id/restore",
            json={"confirm": "RESTORE", "mode": "merge"}, timeout=20
        )
        assert r.status_code == 404

    def test_delete_snapshot(self, admin_session, base_url):
        sid = pytest.snapshot_id_happy
        r = admin_session.delete(f"{base_url}/api/company/backup/cloud/{sid}", timeout=20)
        assert r.status_code == 200
        assert r.json().get("ok") is True
        # Verify removal
        r2 = admin_session.get(f"{base_url}/api/company/backup/cloud/list", timeout=20)
        ids = [s["id"] for s in r2.json()["snapshots"]]
        assert sid not in ids

    def test_delete_invalid_id(self, admin_session, base_url):
        r = admin_session.delete(f"{base_url}/api/company/backup/cloud/non-existent", timeout=20)
        assert r.status_code == 404


# -------- Retention --------
class TestRetention:
    def test_retention_keeps_only_7(self, admin_session, base_url):
        # Clean before
        cli = MongoClient(MONGO_URL)
        cli[DB_NAME].cloud_backups.delete_many({"tenant_id": admin_session.tenant_id})

        created_ids = []
        pruned_total = 0
        for i in range(9):
            r = admin_session.post(f"{base_url}/api/company/backup/cloud", timeout=60)
            assert r.status_code == 200, r.text
            d = r.json()
            created_ids.append(d["snapshot"]["id"])
            pruned_total += d.get("pruned", 0)
            # tiny delay to ensure distinct created_at ordering
            time.sleep(0.6)

        # After creating 9, list should only contain 7
        r = admin_session.get(f"{base_url}/api/company/backup/cloud/list", timeout=20)
        assert r.status_code == 200
        snaps = r.json()["snapshots"]
        assert len(snaps) == RETENTION, f"Expected {RETENTION} after retention, got {len(snaps)}"
        # The 2 oldest must have been pruned
        kept_ids = {s["id"] for s in snaps}
        assert created_ids[0] not in kept_ids
        assert created_ids[1] not in kept_ids
        # 7 most recent should be kept
        for cid in created_ids[2:]:
            assert cid in kept_ids
        # Cumulative pruned should be >= 2
        assert pruned_total >= 2, f"pruned_total={pruned_total}"


# -------- Multi-tenant isolation --------
class TestTenantIsolation:
    def test_admin_cannot_see_other_tenant_snapshot(self, admin_session, base_url):
        # Inject a fake snapshot for a different tenant directly
        cli = MongoClient(MONGO_URL)
        fake_id = "fake-cross-tenant-snap-id-001"
        cli[DB_NAME].cloud_backups.insert_one({
            "id": fake_id,
            "tenant_id": "TEST_OTHER_TENANT",
            "storage_path": "cleantec/backups/TEST_OTHER_TENANT/fake.json",
            "size_bytes": 100,
            "total_records": 0,
            "source": "manual",
            "created_by": "other@example.com",
            "azienda_nome": "OtherCo",
            "created_at": __import__("datetime").datetime.utcnow(),
        })

        # List must NOT include it
        r = admin_session.get(f"{base_url}/api/company/backup/cloud/list", timeout=20)
        ids = [s["id"] for s in r.json()["snapshots"]]
        assert fake_id not in ids

        # Restore must 404
        r = admin_session.post(
            f"{base_url}/api/company/backup/cloud/{fake_id}/restore",
            json={"confirm": "RESTORE", "mode": "merge"}, timeout=20
        )
        assert r.status_code == 404

        # Delete must 404
        r = admin_session.delete(f"{base_url}/api/company/backup/cloud/{fake_id}", timeout=20)
        assert r.status_code == 404
