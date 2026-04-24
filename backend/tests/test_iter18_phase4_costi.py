"""FASE 4 — Costi. Backend API tests.

Copre:
- CRUD /api/costi (POST/GET list/GET singolo/PATCH/DELETE)
- Validazione categoria (VALID) + fornitore_id inesistente (400)
- Validazione importo (ge=0)
- Filtri list: categoria / mese_riferimento / anno / fornitore_id
- /api/costi/summary: totale_generale, per_categoria (4 chiavi), per_mese, stack
- Summary filtrato per singolo mese
- RBAC: admin+contabilita OK, logistica 403 su POST
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://wash-ops-central.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def _login(email: str, password: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login {email} → {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers():
    return {"Authorization": f"Bearer {_login('admin@cleantec.it', 'admin123')}"}


@pytest.fixture(scope="module")
def contab_headers():
    return {"Authorization": f"Bearer {_login('contabilita@cleantec.it', 'contabilita123')}"}


@pytest.fixture(scope="module")
def logistica_headers():
    return {"Authorization": f"Bearer {_login('logistica@cleantec.it', 'logistica123')}"}


@pytest.fixture(scope="module")
def created_ids(admin_headers):
    """Crea 3 costi su 2026-05 (diversi da quelli di 2026-04 creati dal main agent) per test isolati."""
    ids: list[str] = []
    payloads = [
        {"categoria": "personale", "data": "2026-05-10", "mese_riferimento": "2026-05",
         "descrizione": "TEST_personale_iter18", "importo": 1500.0,
         "dipendente_nome": "Mario Rossi", "tipo_rapporto": "stipendio", "ore_lavorate": 160},
        {"categoria": "utenze", "data": "2026-05-12", "mese_riferimento": "2026-05",
         "descrizione": "TEST_utenze_iter18", "importo": 300.25,
         "tipo_utenza": "luce", "consumo": 1200, "unita_consumo": "kWh"},
        {"categoria": "prodotti", "data": "2026-05-15", "mese_riferimento": "2026-05",
         "descrizione": "TEST_prodotti_iter18", "importo": 99.9,
         "articolo_codice": "DET-001", "quantita": 10},
    ]
    for p in payloads:
        r = requests.post(f"{API}/costi", json=p, headers=admin_headers, timeout=20)
        assert r.status_code == 200, f"create {p['categoria']} failed: {r.status_code} {r.text}"
        d = r.json()
        assert "id" in d and d["categoria"] == p["categoria"]
        ids.append(d["id"])
    yield ids
    # Cleanup
    for cid in ids:
        requests.delete(f"{API}/costi/{cid}", headers=admin_headers, timeout=20)


# ============ POST /api/costi ============

class TestCreateCosto:
    def test_create_personale_valid(self, admin_headers):
        payload = {"categoria": "personale", "data": "2026-06-01", "mese_riferimento": "2026-06",
                   "descrizione": "TEST_create_pers", "importo": 500.0,
                   "dipendente_nome": "Luigi", "tipo_rapporto": "straordinario"}
        r = requests.post(f"{API}/costi", json=payload, headers=admin_headers, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["descrizione"] == "TEST_create_pers"
        assert d["importo"] == 500.0
        assert d["tenant_id"].startswith("demo-tenant")
        # GET verify persistence
        g = requests.get(f"{API}/costi/{d['id']}", headers=admin_headers, timeout=20)
        assert g.status_code == 200 and g.json()["descrizione"] == "TEST_create_pers"
        requests.delete(f"{API}/costi/{d['id']}", headers=admin_headers, timeout=20)

    def test_create_only_common_fields(self, admin_headers):
        """campi specifici OPZIONALI: solo comuni deve passare"""
        payload = {"categoria": "utenze", "data": "2026-06-02", "mese_riferimento": "2026-06",
                   "descrizione": "TEST_minimal", "importo": 50.0}
        r = requests.post(f"{API}/costi", json=payload, headers=admin_headers, timeout=20)
        assert r.status_code == 200, r.text
        requests.delete(f"{API}/costi/{r.json()['id']}", headers=admin_headers, timeout=20)

    def test_create_invalid_category_400(self, admin_headers):
        payload = {"categoria": "pippo", "data": "2026-06-01", "mese_riferimento": "2026-06",
                   "descrizione": "x", "importo": 10}
        r = requests.post(f"{API}/costi", json=payload, headers=admin_headers, timeout=20)
        assert r.status_code == 400, r.text
        assert "Categoria" in r.text or "categoria" in r.text.lower()

    def test_create_negative_amount_422(self, admin_headers):
        payload = {"categoria": "utenze", "data": "2026-06-01", "mese_riferimento": "2026-06",
                   "descrizione": "neg", "importo": -5}
        r = requests.post(f"{API}/costi", json=payload, headers=admin_headers, timeout=20)
        assert r.status_code == 422, r.text  # Pydantic Field(ge=0)

    def test_create_with_invalid_fornitore_400(self, admin_headers):
        payload = {"categoria": "utenze", "data": "2026-06-01", "mese_riferimento": "2026-06",
                   "descrizione": "bad-forn", "importo": 10,
                   "fornitore_id": "fornitore-inesistente-xyz-999"}
        r = requests.post(f"{API}/costi", json=payload, headers=admin_headers, timeout=20)
        assert r.status_code == 400, r.text
        assert "ornitore" in r.text


# ============ GET list + filters ============

class TestListAndFilters:
    def test_list_all(self, admin_headers, created_ids):
        r = requests.get(f"{API}/costi?anno=2026", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        got = {c["id"] for c in items}
        for cid in created_ids:
            assert cid in got

    def test_filter_categoria(self, admin_headers, created_ids):
        r = requests.get(f"{API}/costi?categoria=personale&anno=2026", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        items = r.json()
        assert all(c["categoria"] == "personale" for c in items)

    def test_filter_invalid_categoria_400(self, admin_headers):
        r = requests.get(f"{API}/costi?categoria=xxx", headers=admin_headers, timeout=20)
        assert r.status_code == 400

    def test_filter_mese(self, admin_headers, created_ids):
        r = requests.get(f"{API}/costi?mese_riferimento=2026-05", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        items = r.json()
        assert all(c["mese_riferimento"] == "2026-05" for c in items)
        got = {c["id"] for c in items}
        for cid in created_ids:
            assert cid in got

    def test_filter_anno(self, admin_headers):
        r = requests.get(f"{API}/costi?anno=2026", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        for c in r.json():
            assert c["mese_riferimento"].startswith("2026-")


# ============ GET /costi/summary ============

class TestSummary:
    def test_summary_anno(self, admin_headers, created_ids):
        r = requests.get(f"{API}/costi/summary?anno=2026", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        s = r.json()
        # Struttura attesa
        assert "totale_generale" in s
        assert "per_categoria" in s and "per_mese" in s and "stack" in s
        # per_categoria contiene TUTTE le 4 categorie
        assert set(s["per_categoria"].keys()) == {"personale", "automezzi", "utenze", "prodotti"}
        # totale_generale >= somma del nostro seed 2026-05 (1500 + 300.25 + 99.9 = 1900.15) + seed iter main (2800.50)
        assert s["totale_generale"] >= 1900.15
        # per_mese ordinato
        mesi = [m["mese"] for m in s["per_mese"]]
        assert mesi == sorted(mesi)
        # stack contiene chiavi mese + categoria
        for st in s["stack"]:
            assert "mese" in st and "categoria" in st and "totale" in st

    def test_summary_single_month(self, admin_headers, created_ids):
        r = requests.get(f"{API}/costi/summary?mese_riferimento=2026-05", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        s = r.json()
        # 1500 + 300.25 + 99.9 == 1900.15 (solo nostri 3 costi di maggio 2026, a meno di altri creati)
        assert s["totale_generale"] >= 1900.15
        # Tutte le chiavi delle 4 categorie presenti
        assert set(s["per_categoria"].keys()) == {"personale", "automezzi", "utenze", "prodotti"}
        # per_categoria.personale.totale deve essere >= 1500 (il nostro)
        assert s["per_categoria"]["personale"]["totale"] >= 1500.0
        # per_mese singolo
        assert len(s["per_mese"]) == 1 and s["per_mese"][0]["mese"] == "2026-05"


# ============ GET single / PATCH / DELETE ============

class TestSingleAndUpdate:
    def test_get_not_found(self, admin_headers):
        r = requests.get(f"{API}/costi/non-existent-xyz", headers=admin_headers, timeout=20)
        assert r.status_code == 404

    def test_patch_update_importo(self, admin_headers):
        # crea
        p = {"categoria": "automezzi", "data": "2026-06-05", "mese_riferimento": "2026-06",
             "descrizione": "TEST_patch", "importo": 100.0}
        cid = requests.post(f"{API}/costi", json=p, headers=admin_headers, timeout=20).json()["id"]
        r = requests.patch(f"{API}/costi/{cid}", json={"importo": 150.5, "descrizione": "TEST_patched"},
                           headers=admin_headers, timeout=20)
        assert r.status_code == 200
        g = requests.get(f"{API}/costi/{cid}", headers=admin_headers, timeout=20).json()
        assert g["importo"] == 150.5 and g["descrizione"] == "TEST_patched"
        requests.delete(f"{API}/costi/{cid}", headers=admin_headers, timeout=20)

    def test_patch_invalid_category_400(self, admin_headers, created_ids):
        r = requests.patch(f"{API}/costi/{created_ids[0]}", json={"categoria": "xxx"},
                           headers=admin_headers, timeout=20)
        assert r.status_code == 400

    def test_patch_not_found_404(self, admin_headers):
        r = requests.patch(f"{API}/costi/nope-xxx", json={"importo": 1}, headers=admin_headers, timeout=20)
        assert r.status_code == 404

    def test_delete_and_404(self, admin_headers):
        p = {"categoria": "prodotti", "data": "2026-06-06", "mese_riferimento": "2026-06",
             "descrizione": "TEST_del", "importo": 1}
        cid = requests.post(f"{API}/costi", json=p, headers=admin_headers, timeout=20).json()["id"]
        r = requests.delete(f"{API}/costi/{cid}", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        # secondo delete 404
        r2 = requests.delete(f"{API}/costi/{cid}", headers=admin_headers, timeout=20)
        assert r2.status_code == 404


# ============ RBAC ============

class TestRBAC:
    def test_contabilita_can_create(self, contab_headers):
        p = {"categoria": "utenze", "data": "2026-06-10", "mese_riferimento": "2026-06",
             "descrizione": "TEST_contab", "importo": 25}
        r = requests.post(f"{API}/costi", json=p, headers=contab_headers, timeout=20)
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        # contab può anche cancellare
        d = requests.delete(f"{API}/costi/{cid}", headers=contab_headers, timeout=20)
        assert d.status_code == 200

    def test_logistica_post_forbidden(self, logistica_headers):
        p = {"categoria": "utenze", "data": "2026-06-10", "mese_riferimento": "2026-06",
             "descrizione": "TEST_logi", "importo": 25}
        r = requests.post(f"{API}/costi", json=p, headers=logistica_headers, timeout=20)
        assert r.status_code == 403

    def test_logistica_patch_forbidden(self, logistica_headers, created_ids):
        r = requests.patch(f"{API}/costi/{created_ids[0]}", json={"importo": 10},
                           headers=logistica_headers, timeout=20)
        assert r.status_code == 403

    def test_logistica_delete_forbidden(self, logistica_headers, created_ids):
        r = requests.delete(f"{API}/costi/{created_ids[0]}", headers=logistica_headers, timeout=20)
        assert r.status_code == 403

    def test_logistica_can_read(self, logistica_headers):
        """Secondo il note del main agent: logistica può GET con get_current_user"""
        r = requests.get(f"{API}/costi?anno=2026", headers=logistica_headers, timeout=20)
        assert r.status_code == 200
