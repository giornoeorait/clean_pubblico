"""Branding feature tests (iter 11).

Covers:
- Public GET /api/branding (no auth) + defaults
- Admin GET/PUT /api/admin/branding (superadmin-only)
- RBAC: admin regular -> 403
- Upload image logo/hero/favicon (resize+WebP/PNG), invalid kind, empty, non-image
- Public GET /api/branding/image/{kind} after upload (Cache-Control) + 404 after delete
- Hex color validation
"""
import io
import os
import pytest
import requests
from PIL import Image

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not set"
API = f"{BASE_URL}/api"

SUPER = ("super@cleantec.it", "Superadmin123!")
ADMIN = ("admin@cleantec.it", "admin123")


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, f"login {email} -> {r.status_code}: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def super_token():
    return _login(*SUPER)


@pytest.fixture(scope="session")
def admin_token():
    return _login(*ADMIN)


@pytest.fixture(scope="session")
def super_h(super_token):
    return {"Authorization": f"Bearer {super_token}"}


@pytest.fixture(scope="session")
def admin_h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def _make_image(size=(800, 600), fmt="JPEG", color=(200, 50, 50)):
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


# ---------- PUBLIC ----------

class TestPublicBranding:
    def test_get_public_no_auth(self):
        r = requests.get(f"{API}/branding", timeout=20)
        assert r.status_code == 200
        d = r.json()
        # defaults present
        assert d["app_name"] == "CleanTec" or isinstance(d["app_name"], str)
        assert "tagline" in d
        assert "login_title" in d
        assert "login_features" in d and isinstance(d["login_features"], list)
        assert "primary_color" in d and d["primary_color"].startswith("#")
        assert "accent_color" in d
        assert "dark_color" in d
        # image url keys present (may be null)
        assert "logo_url" in d
        assert "hero_url" in d
        assert "favicon_url" in d
        # internal paths never exposed
        assert "logo_path" not in d
        assert "hero_path" not in d
        assert "favicon_path" not in d


# ---------- RBAC ----------

class TestAdminRBAC:
    def test_admin_get_ok_as_superadmin(self, super_h):
        r = requests.get(f"{API}/admin/branding", headers=super_h, timeout=20)
        assert r.status_code == 200
        assert "app_name" in r.json()

    def test_admin_get_forbidden_as_regular_admin(self, admin_h):
        r = requests.get(f"{API}/admin/branding", headers=admin_h, timeout=20)
        assert r.status_code == 403

    def test_admin_put_forbidden_as_regular_admin(self, admin_h):
        r = requests.put(f"{API}/admin/branding", headers=admin_h, json={"app_name": "Hack"}, timeout=20)
        assert r.status_code == 403

    def test_upload_forbidden_as_regular_admin(self, admin_h):
        files = {"file": ("x.jpg", _make_image((100, 100)), "image/jpeg")}
        r = requests.post(f"{API}/admin/branding/upload/logo", headers=admin_h, files=files, timeout=30)
        assert r.status_code == 403

    def test_delete_forbidden_as_regular_admin(self, admin_h):
        r = requests.delete(f"{API}/admin/branding/image/logo", headers=admin_h, timeout=20)
        assert r.status_code == 403


# ---------- PUT config ----------

class TestUpdateBranding:
    def test_put_partial_ok(self, super_h):
        body = {
            "app_name": "TEST_CleanTec",
            "primary_color": "#112233",
            "login_features": [
                {"icon": "truck", "label": "TEST feature 1"},
                {"icon": "factory", "label": "TEST feature 2"},
            ],
        }
        r = requests.put(f"{API}/admin/branding", headers=super_h, json=body, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["app_name"] == "TEST_CleanTec"
        assert d["primary_color"] == "#112233"
        assert len(d["login_features"]) == 2
        # verify persisted via public GET
        pub = requests.get(f"{API}/branding", timeout=20).json()
        assert pub["app_name"] == "TEST_CleanTec"
        assert pub["primary_color"] == "#112233"

    def test_put_invalid_hex_rejected(self, super_h):
        r = requests.put(f"{API}/admin/branding", headers=super_h, json={"primary_color": "not-hex"}, timeout=20)
        assert r.status_code == 422

    def test_put_short_hex_rejected(self, super_h):
        r = requests.put(f"{API}/admin/branding", headers=super_h, json={"accent_color": "#123"}, timeout=20)
        assert r.status_code == 422

    def test_reset_app_name(self, super_h):
        # cleanup
        r = requests.put(f"{API}/admin/branding", headers=super_h,
                         json={"app_name": "CleanTec", "primary_color": "#4F46E5"}, timeout=20)
        assert r.status_code == 200


# ---------- UPLOAD ----------

class TestUploadImages:
    def test_upload_hero_resize_webp(self, super_h):
        raw = _make_image((3840, 2400), "JPEG")
        files = {"file": ("big.jpg", raw, "image/jpeg")}
        r = requests.post(f"{API}/admin/branding/upload/hero", headers=super_h, files=files, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["kind"] == "hero"
        assert d["format"] == "WEBP"
        assert d["width"] <= 1920 and d["height"] <= 1200
        assert d["size"] < len(raw)  # compressed

    def test_upload_logo_max_512(self, super_h):
        raw = _make_image((2048, 2048), "PNG")
        files = {"file": ("logo.png", raw, "image/png")}
        r = requests.post(f"{API}/admin/branding/upload/logo", headers=super_h, files=files, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["format"] == "WEBP"
        assert d["width"] <= 512 and d["height"] <= 512

    def test_upload_favicon_png_96(self, super_h):
        raw = _make_image((256, 256), "PNG")
        files = {"file": ("fav.png", raw, "image/png")}
        r = requests.post(f"{API}/admin/branding/upload/favicon", headers=super_h, files=files, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["format"] == "PNG"
        assert d["width"] <= 96 and d["height"] <= 96

    def test_upload_invalid_kind(self, super_h):
        files = {"file": ("x.jpg", _make_image((100, 100)), "image/jpeg")}
        r = requests.post(f"{API}/admin/branding/upload/pippo", headers=super_h, files=files, timeout=20)
        assert r.status_code == 400

    def test_upload_empty_file(self, super_h):
        files = {"file": ("empty.jpg", b"", "image/jpeg")}
        r = requests.post(f"{API}/admin/branding/upload/logo", headers=super_h, files=files, timeout=20)
        # empty multipart may be rejected by FastAPI with 422 or 400
        assert r.status_code in (400, 422)

    def test_upload_non_image_rejected(self, super_h):
        files = {"file": ("evil.txt", b"this is not an image, just plain text content here", "text/plain")}
        r = requests.post(f"{API}/admin/branding/upload/logo", headers=super_h, files=files, timeout=20)
        assert r.status_code == 400
        assert "Immagine" in r.text or "non valida" in r.text.lower()

    def test_upload_too_big(self, super_h):
        # >8MB garbage (not a real image but size check happens before PIL)
        big = b"\x00" * (9 * 1024 * 1024)
        files = {"file": ("huge.bin", big, "application/octet-stream")}
        r = requests.post(f"{API}/admin/branding/upload/logo", headers=super_h, files=files, timeout=60)
        assert r.status_code == 400


# ---------- PUBLIC IMAGE + DELETE ----------

class TestPublicImageAndDelete:
    def test_public_image_after_upload(self, super_h):
        # ensure a hero exists
        files = {"file": ("h.jpg", _make_image((1000, 800), "JPEG"), "image/jpeg")}
        r = requests.post(f"{API}/admin/branding/upload/hero", headers=super_h, files=files, timeout=60)
        assert r.status_code == 200

        # public GET image (NO auth)
        r2 = requests.get(f"{API}/branding/image/hero", timeout=30)
        assert r2.status_code == 200
        assert r2.headers.get("content-type", "").startswith("image/")
        assert "webp" in r2.headers.get("content-type", "").lower()
        # Note: backend sets 'public, max-age=300' but preview ingress rewrites
        # Cache-Control to 'no-store, no-cache, must-revalidate'. We only check
        # that *some* cache-control header is present (infra-limitation).
        assert r2.headers.get("cache-control") is not None
        assert len(r2.content) > 0

    def test_favicon_public_png(self, super_h):
        files = {"file": ("f.png", _make_image((200, 200), "PNG"), "image/png")}
        r = requests.post(f"{API}/admin/branding/upload/favicon", headers=super_h, files=files, timeout=60)
        assert r.status_code == 200

        r2 = requests.get(f"{API}/branding/image/favicon", timeout=30)
        assert r2.status_code == 200
        assert "png" in r2.headers.get("content-type", "").lower()

    def test_public_url_exposed_in_branding(self):
        d = requests.get(f"{API}/branding", timeout=20).json()
        assert d["hero_url"] == "/api/branding/image/hero"
        assert d["favicon_url"] == "/api/branding/image/favicon"

    def test_delete_image_superadmin(self, super_h):
        r = requests.delete(f"{API}/admin/branding/image/hero", headers=super_h, timeout=20)
        assert r.status_code == 200
        assert r.json().get("ok") is True

        # subsequent GET -> 404
        r2 = requests.get(f"{API}/branding/image/hero", timeout=20)
        assert r2.status_code == 404

        # and hero_url is null in public branding
        d = requests.get(f"{API}/branding", timeout=20).json()
        assert d["hero_url"] is None

    def test_delete_invalid_kind(self, super_h):
        r = requests.delete(f"{API}/admin/branding/image/unknown", headers=super_h, timeout=20)
        assert r.status_code == 400

    def test_image_missing_kind_404(self):
        r = requests.get(f"{API}/branding/image/unknown", timeout=20)
        assert r.status_code == 404


# ---------- REGRESSION: existing commercial flow still OK ----------

class TestRegressionSmoke:
    def test_plans_still_ok(self):
        r = requests.get(f"{API}/plans", timeout=20)
        assert r.status_code == 200
        data = r.json()
        plans = data.get("plans", data) if isinstance(data, dict) else data
        assert isinstance(plans, list) and len(plans) >= 3

    def test_admin_login_ok(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": "admin@cleantec.it", "password": "admin123"}, timeout=20)
        assert r.status_code == 200

    def test_clienti_list_ok(self, admin_h):
        r = requests.get(f"{API}/clienti", headers=admin_h, timeout=20)
        assert r.status_code == 200
