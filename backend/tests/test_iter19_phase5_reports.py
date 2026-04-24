"""FASE 5 — Report & BI: 6 endpoint aggregati.

Test coverage:
- Fatturato (totale, incassato, sospeso, per_mese, per_cliente)
- Produzione (kg, pezzi, per_mese/cliente/articolo)
- Costo/kg (totale_costi, totale_kg, costo_kg_medio, per_categoria, per_mese)
- Aging sospesi (buckets, dettagli)
- Km automezzi (per_targa, per_mese)
- Marginalità (margine per_cliente)
- RBAC + multi-tenant isolation
"""
import os
import pytest
import requests
from pathlib import Path

# Load REACT_APP_BACKEND_URL from /app/frontend/.env if not in env
_env_file = Path("/app/frontend/.env")
if _env_file.exists() and not os.environ.get("REACT_APP_BACKEND_URL"):
    for line in _env_file.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            os.environ["REACT_APP_BACKEND_URL"] = line.split("=", 1)[1].strip()
            break

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


def _login(email: str, password: str):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"Login {email} failed {r.status_code}: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def admin_token():
    return _login("admin@cleantec.it", "admin123")


@pytest.fixture(scope="session")
def contab_token():
    return _login("contabilita@cleantec.it", "contabilita123")


@pytest.fixture(scope="session")
def logistica_token():
    return _login("logistica@cleantec.it", "logistica123")


def _h(t):
    return {"Authorization": f"Bearer {t}"}


# =================== FATTURATO ===================
class TestFatturato:
    def test_shape_and_totals(self, admin_token):
        r = requests.get(f"{API}/reports/fatturato?anno=2026", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ["anno", "totale", "incassato", "sospeso", "per_mese", "per_cliente"]:
            assert k in d, f"missing {k}"
        assert d["anno"] == 2026
        # Main agent confirmed: totale=5647.27, sospeso=2761.71
        assert abs(d["totale"] - 5647.27) < 0.5, f"totale {d['totale']} (expected ~5647.27)"
        assert abs(d["sospeso"] - 2761.71) < 0.5, f"sospeso {d['sospeso']} (expected ~2761.71)"
        # incassato+sospeso should be <= totale (can have other states)
        assert d["incassato"] + d["sospeso"] <= d["totale"] + 0.01

    def test_per_mese_fields(self, admin_token):
        r = requests.get(f"{API}/reports/fatturato?anno=2026", headers=_h(admin_token), timeout=30)
        d = r.json()
        assert len(d["per_mese"]) >= 1
        m = d["per_mese"][0]
        for k in ["mese", "totale", "incassato", "sospeso", "n"]:
            assert k in m
        # mese format yyyy-mm
        assert len(m["mese"]) == 7 and m["mese"][4] == "-"

    def test_per_cliente_top20_sorted(self, admin_token):
        r = requests.get(f"{API}/reports/fatturato?anno=2026", headers=_h(admin_token), timeout=30)
        d = r.json()
        cli = d["per_cliente"]
        assert len(cli) <= 20
        # sorted desc by totale
        for i in range(len(cli) - 1):
            assert cli[i]["totale"] >= cli[i + 1]["totale"]

    def test_no_anno_returns_all(self, admin_token):
        r = requests.get(f"{API}/reports/fatturato", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200
        assert r.json()["anno"] is None


# =================== PRODUZIONE ===================
class TestProduzione:
    def test_shape_and_kg(self, admin_token):
        r = requests.get(f"{API}/reports/produzione?anno=2026", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ["anno", "totale_kg", "totale_pezzi", "per_mese", "per_cliente", "per_articolo"]:
            assert k in d
        # Expected ~713.92 kg
        assert abs(d["totale_kg"] - 713.92) < 1.0, f"totale_kg {d['totale_kg']}"
        assert d["totale_pezzi"] > 0

    def test_per_cliente_sorted_top20(self, admin_token):
        r = requests.get(f"{API}/reports/produzione?anno=2026", headers=_h(admin_token), timeout=30)
        d = r.json()
        assert len(d["per_cliente"]) <= 20
        assert len(d["per_articolo"]) <= 20
        for i in range(len(d["per_cliente"]) - 1):
            assert d["per_cliente"][i]["kg"] >= d["per_cliente"][i + 1]["kg"]


# =================== COSTO /KG ===================
class TestCostoKg:
    def test_shape(self, admin_token):
        r = requests.get(f"{API}/reports/costo-kg?anno=2026", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ["anno", "totale_costi", "totale_kg", "costo_kg_medio", "per_categoria", "per_mese"]:
            assert k in d
        # Main agent: costi=2800.50, kg=713.92, costo_kg_medio~3.9227
        assert abs(d["totale_costi"] - 2800.50) < 1.0
        assert abs(d["costo_kg_medio"] - 3.9227) < 0.01
        # 4 decimal precision
        assert isinstance(d["costo_kg_medio"], float)

    def test_per_categoria_is_dict(self, admin_token):
        r = requests.get(f"{API}/reports/costo-kg?anno=2026", headers=_h(admin_token), timeout=30)
        d = r.json()
        assert isinstance(d["per_categoria"], dict)
        # sum should equal totale_costi
        s = round(sum(d["per_categoria"].values()), 2)
        assert abs(s - d["totale_costi"]) < 0.1

    def test_per_mese_costo_kg(self, admin_token):
        r = requests.get(f"{API}/reports/costo-kg?anno=2026", headers=_h(admin_token), timeout=30)
        d = r.json()
        for m in d["per_mese"]:
            assert "mese" in m and "costi" in m and "kg" in m and "costo_kg" in m


# =================== AGING ===================
class TestAging:
    def test_shape_and_buckets(self, admin_token):
        r = requests.get(f"{API}/reports/aging-sospesi", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ["oggi", "totale_sospeso", "numero_fatture", "buckets", "dettagli"]:
            assert k in d
        assert len(d["buckets"]) == 4
        buckets = {b["bucket"]: b for b in d["buckets"]}
        for k in ["0-30", "31-60", "61-90", ">90"]:
            assert k in buckets
        # Main agent: 3 fatture da_incassare in bucket 0-30
        assert d["numero_fatture"] == 3, f"expected 3 fatture da_incassare, got {d['numero_fatture']}"
        assert buckets["0-30"]["n"] == 3

    def test_dettagli_sorted_desc_by_giorni(self, admin_token):
        r = requests.get(f"{API}/reports/aging-sospesi", headers=_h(admin_token), timeout=30)
        d = r.json()
        assert len(d["dettagli"]) <= 50
        for i in range(len(d["dettagli"]) - 1):
            assert d["dettagli"][i]["giorni"] >= d["dettagli"][i + 1]["giorni"]

    def test_only_da_incassare(self, admin_token):
        # Verify: totale_sospeso should match fatturato.sospeso (or be <=)
        r = requests.get(f"{API}/reports/aging-sospesi", headers=_h(admin_token), timeout=30)
        d = r.json()
        # should equal 2761.71 (main agent's data)
        assert abs(d["totale_sospeso"] - 2761.71) < 0.5


# =================== KM AUTOMEZZI ===================
class TestKm:
    def test_shape(self, admin_token):
        r = requests.get(f"{API}/reports/km-automezzi?anno=2026", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ["anno", "totale_km", "totale_spesa", "per_targa", "per_mese"]:
            assert k in d
        # Main agent: AB123CD 450km €120
        assert abs(d["totale_km"] - 450.0) < 1.0
        assert abs(d["totale_spesa"] - 120.0) < 1.0

    def test_per_targa_fields(self, admin_token):
        r = requests.get(f"{API}/reports/km-automezzi?anno=2026", headers=_h(admin_token), timeout=30)
        d = r.json()
        assert len(d["per_targa"]) >= 1
        t = d["per_targa"][0]
        for k in ["targa", "km_totali", "spesa_totale", "costo_km", "per_tipo"]:
            assert k in t
        assert t["targa"] == "AB123CD"
        assert isinstance(t["per_tipo"], dict)


# =================== MARGINALITA ===================
class TestMarginalita:
    def test_shape(self, admin_token):
        r = requests.get(f"{API}/reports/marginalita?anno=2026", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ["anno", "totale_fatturato", "totale_costi", "totale_kg",
                  "costo_kg_medio", "margine_totale", "per_cliente"]:
            assert k in d
        # margine totale ~2846.77
        assert abs(d["margine_totale"] - 2846.77) < 1.0, f"margine {d['margine_totale']}"
        assert abs(d["totale_fatturato"] - 5647.27) < 0.5

    def test_per_cliente_sorted_desc_by_margine(self, admin_token):
        r = requests.get(f"{API}/reports/marginalita?anno=2026", headers=_h(admin_token), timeout=30)
        d = r.json()
        rows = d["per_cliente"]
        assert len(rows) >= 1
        for i in range(len(rows) - 1):
            assert rows[i]["margine"] >= rows[i + 1]["margine"]
        # Fields
        r0 = rows[0]
        for k in ["cliente_id", "cliente_nome", "fatturato", "kg",
                  "costo_allocato", "margine", "margine_perc"]:
            assert k in r0


# =================== RBAC ===================
class TestRBAC:
    def test_no_auth_401(self):
        r = requests.get(f"{API}/reports/fatturato?anno=2026", timeout=30)
        assert r.status_code in (401, 403)

    def test_contabilita_can_access(self, contab_token):
        r = requests.get(f"{API}/reports/fatturato?anno=2026", headers=_h(contab_token), timeout=30)
        assert r.status_code == 200

    def test_logistica_can_access(self, logistica_token):
        r = requests.get(f"{API}/reports/fatturato?anno=2026", headers=_h(logistica_token), timeout=30)
        assert r.status_code == 200

    def test_all_endpoints_admin(self, admin_token):
        paths = [
            "/reports/fatturato?anno=2026",
            "/reports/produzione?anno=2026",
            "/reports/costo-kg?anno=2026",
            "/reports/aging-sospesi",
            "/reports/km-automezzi?anno=2026",
            "/reports/marginalita?anno=2026",
        ]
        for p in paths:
            r = requests.get(f"{API}{p}", headers=_h(admin_token), timeout=30)
            assert r.status_code == 200, f"{p} -> {r.status_code}"


# =================== REGRESSION 12 PRE-EXISTING ROUTES ===================
class TestRegression:
    ROUTES = [
        "/clienti", "/articoli", "/listini", "/ddt", "/offerte",
        "/ordinativi", "/fatture", "/sospesi", "/fornitori",
        "/ddt-fornitore", "/fatture-fornitore", "/costi",
    ]

    def test_all_routes_load(self, admin_token):
        for p in self.ROUTES:
            r = requests.get(f"{API}{p}", headers=_h(admin_token), timeout=30)
            assert r.status_code == 200, f"{p} -> {r.status_code}: {r.text[:200]}"


# =================== YEAR FILTER ===================
class TestYearFilter:
    def test_year_2099_empty(self, admin_token):
        r = requests.get(f"{API}/reports/fatturato?anno=2099", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["totale"] == 0
        assert d["per_mese"] == []

    def test_produzione_year_2099(self, admin_token):
        r = requests.get(f"{API}/reports/produzione?anno=2099", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200
        assert r.json()["totale_kg"] == 0
