"""Iter34 — Snapshot peso DDT + Ricalcolo storico + Dashboard KPI kg.

Tests backend endpoints for weight snapshot on DDT lines, historical recalc,
dashboard kg KPI structure, and reports fallback logic.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://wash-ops-central.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@cleantec.it"
ADMIN_PASSWORD = "admin123"
CONTABILITA_EMAIL = "contabilita@cleantec.it"
CONTABILITA_PASSWORD = "contabilita123"


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def s_admin():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    token = data.get("access_token") or data.get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def s_contab():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": CONTABILITA_EMAIL, "password": CONTABILITA_PASSWORD})
    if r.status_code != 200:
        pytest.skip("Contabilita login not available")
    data = r.json()
    token = data.get("access_token") or data.get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def articoli(s_admin):
    r = s_admin.get(f"{BASE_URL}/api/articoli")
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def cliente_id(s_admin):
    r = s_admin.get(f"{BASE_URL}/api/clienti")
    assert r.status_code == 200
    lst = r.json()
    assert len(lst) > 0, "Nessun cliente disponibile"
    return lst[0]["id"]


def _pick_articolo(articoli, cat=None, with_peso=True):
    for a in articoli:
        if with_peso and float(a.get("peso_medio") or 0) <= 0:
            continue
        if cat and (a.get("categoria_peso") or "").upper() != cat:
            continue
        return a
    return None


# ---------- (1) POST /api/ddt salva snapshot + subtotali ----------
class TestDDTCreateSnapshot:
    def test_create_ddt_saves_snapshot_and_subtotals(self, s_admin, articoli, cliente_id):
        # Trova almeno un articolo con peso_medio > 0
        art = _pick_articolo(articoli, with_peso=True)
        if not art:
            pytest.skip("Nessun articolo con peso_medio > 0")
        payload = {
            "cliente_id": cliente_id,
            "note": "TEST_iter34_snap",
            "righe": [{"articolo_id": art["id"], "quantita": 5}],
        }
        r = s_admin.post(f"{BASE_URL}/api/ddt", json=payload)
        assert r.status_code == 200, r.text
        doc = r.json()
        try:
            # subtotali su doc
            assert "peso_totale" in doc
            assert "peso_biancheria_piana" in doc
            assert "peso_spugna" in doc
            assert "peso_varie" in doc
            assert "peso_non_classificato" in doc
            assert doc.get("calcolo_peso_tipo") == "CALCOLO_ORIGINALE"
            assert doc.get("peso_calcolato_at")

            # snapshot su riga
            riga = doc["righe"][0]
            assert "peso_medio_snapshot" in riga
            assert "categoria_peso_snapshot" in riga
            assert "peso_riga" in riga
            assert riga["categoria_peso_snapshot"] == riga["categoria_peso_snapshot"].upper()

            # peso_riga = quantita * peso_medio (3 decimali)
            expected = round(float(art["peso_medio"]) * 5, 3)
            assert abs(riga["peso_riga"] - expected) < 0.001, f"peso_riga {riga['peso_riga']} != {expected}"

            # somma subtotali == peso_totale
            somma = round(
                doc["peso_biancheria_piana"] + doc["peso_spugna"] + doc["peso_varie"] + doc["peso_non_classificato"],
                3,
            )
            assert abs(somma - doc["peso_totale"]) < 0.01, f"Somma subtotali {somma} != peso_totale {doc['peso_totale']}"
        finally:
            s_admin.delete(f"{BASE_URL}/api/ddt/{doc['id']}")

    def test_patch_ddt_recomputes_snapshot(self, s_admin, articoli, cliente_id):
        art = _pick_articolo(articoli, with_peso=True)
        if not art:
            pytest.skip("Nessun articolo con peso_medio > 0")
        payload = {
            "cliente_id": cliente_id,
            "note": "TEST_iter34_patch",
            "righe": [{"articolo_id": art["id"], "quantita": 2}],
        }
        r = s_admin.post(f"{BASE_URL}/api/ddt", json=payload)
        assert r.status_code == 200
        did = r.json()["id"]
        first_ts = r.json().get("peso_calcolato_at")
        try:
            time.sleep(1.1)
            # patch con quantita differente
            r2 = s_admin.patch(f"{BASE_URL}/api/ddt/{did}", json={"righe": [{"articolo_id": art["id"], "quantita": 10}]})
            assert r2.status_code == 200, r2.text

            r3 = s_admin.get(f"{BASE_URL}/api/ddt/{did}")
            doc = r3.json()
            assert doc["calcolo_peso_tipo"] == "CALCOLO_ORIGINALE"
            assert doc["peso_calcolato_at"] != first_ts, "peso_calcolato_at deve aggiornarsi"
            expected = round(float(art["peso_medio"]) * 10, 3)
            assert abs(doc["righe"][0]["peso_riga"] - expected) < 0.001
            assert abs(doc["peso_totale"] - expected) < 0.001
        finally:
            s_admin.delete(f"{BASE_URL}/api/ddt/{did}")


# ---------- (2) Snapshot congelato: modifica articolo dopo save non tocca DDT ----------
class TestSnapshotFrozen:
    def test_articolo_change_after_ddt_does_not_alter_snapshot(self, s_admin, articoli, cliente_id):
        art = _pick_articolo(articoli, with_peso=True)
        if not art:
            pytest.skip("Nessun articolo con peso_medio > 0")
        original_peso = float(art["peso_medio"])
        # Crea DDT
        payload = {
            "cliente_id": cliente_id,
            "note": "TEST_iter34_frozen",
            "righe": [{"articolo_id": art["id"], "quantita": 3}],
        }
        r = s_admin.post(f"{BASE_URL}/api/ddt", json=payload)
        assert r.status_code == 200
        ddt = r.json()
        did = ddt["id"]
        original_peso_riga = ddt["righe"][0]["peso_riga"]
        try:
            # Modifica peso articolo (raddoppia)
            new_peso = round(original_peso * 2, 3)
            rp = s_admin.patch(f"{BASE_URL}/api/articoli/{art['id']}", json={"peso_medio": new_peso})
            assert rp.status_code == 200, rp.text
            try:
                # Rileggi DDT: deve mantenere il vecchio peso_riga
                rget = s_admin.get(f"{BASE_URL}/api/ddt/{did}")
                doc = rget.json()
                assert abs(doc["righe"][0]["peso_riga"] - original_peso_riga) < 0.001, \
                    f"Snapshot DDT non congelato: got {doc['righe'][0]['peso_riga']} expected {original_peso_riga}"
                assert abs(doc["righe"][0]["peso_medio_snapshot"] - original_peso) < 0.001
            finally:
                # ripristina peso articolo
                s_admin.patch(f"{BASE_URL}/api/articoli/{art['id']}", json={"peso_medio": original_peso})
        finally:
            s_admin.delete(f"{BASE_URL}/api/ddt/{did}")


# ---------- (3) Preview endpoint ----------
class TestRicalcoloPreview:
    def test_preview_shape_admin(self, s_admin):
        r = s_admin.get(f"{BASE_URL}/api/ddt/peso/ricalcolo/preview")
        assert r.status_code == 200, r.text
        data = r.json()
        required = [
            "ddt_totali", "ddt_da_ricalcolare",
            "ddt_con_calcolo_originale", "ddt_con_ricalcolo_storico",
            "articoli_senza_peso", "articoli_non_classificati",
            "anomalie_count", "anomalie",
        ]
        for k in required:
            assert k in data, f"Missing key {k}"
        assert isinstance(data["anomalie"], list)
        assert isinstance(data["ddt_totali"], int)
        assert isinstance(data["ddt_da_ricalcolare"], int)

    def test_preview_forbidden_non_admin(self, s_contab):
        r = s_contab.get(f"{BASE_URL}/api/ddt/peso/ricalcolo/preview")
        assert r.status_code == 403, f"Non-admin should get 403 not {r.status_code}"


# ---------- (4) Ricalcolo esegui: idempotenza + 400 senza conferma ----------
class TestRicalcoloEsegui:
    def test_missing_conferma_returns_400(self, s_admin):
        r = s_admin.post(f"{BASE_URL}/api/ddt/peso/ricalcolo/esegui", json={})
        assert r.status_code == 400
        r2 = s_admin.post(f"{BASE_URL}/api/ddt/peso/ricalcolo/esegui", json={"conferma": False})
        assert r2.status_code == 400

    def test_idempotent_conferma_true(self, s_admin):
        # Fetch preview first
        pv = s_admin.get(f"{BASE_URL}/api/ddt/peso/ricalcolo/preview").json()
        r = s_admin.post(f"{BASE_URL}/api/ddt/peso/ricalcolo/esegui", json={"conferma": True})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "aggiornati" in data
        assert "saltati_gia_calcolati" in data
        # Idempotenza: seconda chiamata deve saltare tutti quelli già calcolati
        r2 = s_admin.post(f"{BASE_URL}/api/ddt/peso/ricalcolo/esegui", json={"conferma": True})
        assert r2.status_code == 200
        data2 = r2.json()
        assert data2["aggiornati"] == 0, f"Seconda esecuzione dovrebbe non aggiornare nulla, got aggiornati={data2['aggiornati']}"
        assert data2["saltati_gia_calcolati"] >= pv["ddt_totali"] - pv["ddt_da_ricalcolare"], \
            "saltati_gia_calcolati deve includere almeno i già calcolati precedenti"

    def test_esegui_forbidden_non_admin(self, s_contab):
        r = s_contab.post(f"{BASE_URL}/api/ddt/peso/ricalcolo/esegui", json={"conferma": True})
        assert r.status_code == 403


# ---------- (5) Report produzione preferisce snapshot ----------
class TestReportProduzioneSnapshot:
    def test_produzione_shape_and_values(self, s_admin):
        r = s_admin.get(f"{BASE_URL}/api/reports/produzione")
        assert r.status_code == 200, r.text
        data = r.json()
        # Ha totali kg e per_categoria_peso
        assert "totale_kg" in data or "totale" in data
        assert "per_categoria_peso" in data
        cats = data["per_categoria_peso"]
        assert isinstance(cats, list)
        assert len(cats) == 4
        keys = [c["categoria_peso"] for c in cats]
        for expected in ["BIANCHERIA_PIANA", "SPUGNA", "VARIE", "NON_CLASSIFICATO"]:
            assert expected in keys


# ---------- (6) Dashboard KPI: kg_mese / kg_anno / kg_serie_mensile ----------
class TestDashboardKgKPI:
    def test_dashboard_kpi_has_kg_fields(self, s_admin):
        r = s_admin.get(f"{BASE_URL}/api/dashboard/kpi")
        assert r.status_code == 200, r.text
        data = r.json()
        for key in ("kg_mese", "kg_anno"):
            assert key in data, f"Missing {key}"
            obj = data[key]
            for sub in ("totale", "biancheria_piana", "spugna", "varie", "non_classificato"):
                assert sub in obj, f"Missing sub {sub} in {key}"
                assert isinstance(obj[sub], (int, float))
            somma = round(obj["biancheria_piana"] + obj["spugna"] + obj["varie"] + obj["non_classificato"], 3)
            assert abs(somma - obj["totale"]) < 0.1, f"{key}: somma {somma} != totale {obj['totale']}"

        assert "kg_serie_mensile" in data
        serie = data["kg_serie_mensile"]
        assert isinstance(serie, list)
        assert len(serie) == 12, f"kg_serie_mensile deve avere 12 elementi, got {len(serie)}"
        for entry in serie:
            for k in ("mese", "biancheria_piana", "spugna", "varie", "non_classificato", "totale"):
                assert k in entry, f"Missing key {k} in serie entry"
