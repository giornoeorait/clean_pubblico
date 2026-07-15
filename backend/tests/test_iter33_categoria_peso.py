"""Test suite iter33 — Categoria peso articoli (BIANCHERIA_PIANA/SPUGNA/VARIE/NON_CLASSIFICATO).

Verifica:
- POST /api/articoli accetta categoria_peso (case-insensitive) e valida enum.
- PATCH /api/articoli/{id} aggiorna e normalizza.
- Migration seed applica NON_CLASSIFICATO su articoli esistenti.
- GET /api/reports/produzione ritorna `per_categoria_peso` con 4 categorie in ordine fisso.
- Ogni riga per_ddt ha subtotali kg per categoria peso (somma = kg totali DDT).
- GET /api/reports/produzione/articoli-check ritorna non_classificati_count e non_classificati[].
- GET /api/reports/produzione/xlsx include sheet 'Per categoria peso' e 8 sheet totali.
"""
import os
import io
import pytest
import requests
from openpyxl import load_workbook

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@cleantec.it"
ADMIN_PASSWORD = "admin123"

CATEGORIE_PESO = ("BIANCHERIA_PIANA", "SPUGNA", "VARIE", "NON_CLASSIFICATO")


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    j = r.json()
    return j.get("access_token") or j.get("token")


@pytest.fixture(scope="module")
def h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ============== ARTICOLI: categoria_peso ==============

class TestArticoliCategoriaPeso:

    def test_create_articolo_default_non_classificato(self, h):
        payload = {
            "codice": "TEST_CATP_1",
            "descrizione": "TEST articolo default",
            "peso_medio": 0.4,
        }
        r = requests.post(f"{BASE_URL}/api/articoli", headers=h, json=payload)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert data["categoria_peso"] == "NON_CLASSIFICATO"
        # cleanup
        requests.delete(f"{BASE_URL}/api/articoli/{data['id']}", headers=h)

    def test_create_articolo_lowercase_normalized(self, h):
        payload = {
            "codice": "TEST_CATP_2",
            "descrizione": "TEST articolo lowercase",
            "peso_medio": 0.5,
            "categoria_peso": "biancheria_piana",
        }
        r = requests.post(f"{BASE_URL}/api/articoli", headers=h, json=payload)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert data["categoria_peso"] == "BIANCHERIA_PIANA"
        # verify persistence via GET
        aid = data["id"]
        g = requests.get(f"{BASE_URL}/api/articoli", headers=h)
        assert g.status_code == 200
        found = [a for a in g.json() if a["id"] == aid]
        assert found and found[0]["categoria_peso"] == "BIANCHERIA_PIANA"
        requests.delete(f"{BASE_URL}/api/articoli/{aid}", headers=h)

    @pytest.mark.parametrize("value,expected", [
        ("SPUGNA", "SPUGNA"),
        ("spugna", "SPUGNA"),
        ("Varie", "VARIE"),
        ("NON_CLASSIFICATO", "NON_CLASSIFICATO"),
    ])
    def test_create_articolo_all_values(self, h, value, expected):
        payload = {
            "codice": f"TEST_CATP_{value}",
            "descrizione": f"TEST {value}",
            "peso_medio": 0.3,
            "categoria_peso": value,
        }
        r = requests.post(f"{BASE_URL}/api/articoli", headers=h, json=payload)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert data["categoria_peso"] == expected
        requests.delete(f"{BASE_URL}/api/articoli/{data['id']}", headers=h)

    def test_create_articolo_invalid_returns_422(self, h):
        payload = {
            "codice": "TEST_CATP_INV",
            "descrizione": "TEST invalid",
            "peso_medio": 0.5,
            "categoria_peso": "INVALID_VALUE",
        }
        r = requests.post(f"{BASE_URL}/api/articoli", headers=h, json=payload)
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"

    def test_patch_articolo_lowercase_normalized(self, h):
        # Create first
        c = requests.post(f"{BASE_URL}/api/articoli", headers=h, json={
            "codice": "TEST_PATCH_1", "descrizione": "TEST patch", "peso_medio": 0.5,
        })
        assert c.status_code in (200, 201)
        aid = c.json()["id"]
        try:
            r = requests.patch(f"{BASE_URL}/api/articoli/{aid}", headers=h,
                               json={"categoria_peso": "biancheria_piana"})
            assert r.status_code == 200, r.text
            # GET to verify persistence
            g = requests.get(f"{BASE_URL}/api/articoli", headers=h)
            found = [a for a in g.json() if a["id"] == aid]
            assert found and found[0]["categoria_peso"] == "BIANCHERIA_PIANA"
        finally:
            requests.delete(f"{BASE_URL}/api/articoli/{aid}", headers=h)

    def test_patch_articolo_invalid_returns_422(self, h):
        c = requests.post(f"{BASE_URL}/api/articoli", headers=h, json={
            "codice": "TEST_PATCH_2", "descrizione": "TEST patch inv", "peso_medio": 0.5,
        })
        aid = c.json()["id"]
        try:
            r = requests.patch(f"{BASE_URL}/api/articoli/{aid}", headers=h,
                               json={"categoria_peso": "INVALID"})
            assert r.status_code == 422, r.text
        finally:
            requests.delete(f"{BASE_URL}/api/articoli/{aid}", headers=h)


# ============== MIGRATION (seed) verification ==============

class TestMigrationSeed:

    def test_all_existing_articoli_have_categoria_peso(self, h):
        r = requests.get(f"{BASE_URL}/api/articoli", headers=h)
        assert r.status_code == 200
        articoli = r.json()
        assert len(articoli) > 0, "Nessun articolo trovato — impossibile verificare migration"
        for a in articoli:
            assert "categoria_peso" in a, f"Articolo {a.get('codice')} manca campo categoria_peso"
            assert a["categoria_peso"] in CATEGORIE_PESO, \
                f"Articolo {a.get('codice')} ha categoria_peso non valido: {a['categoria_peso']}"


# ============== REPORT PRODUZIONE ==============

class TestReportProduzione:

    def test_per_categoria_peso_present_and_ordered(self, h):
        r = requests.get(f"{BASE_URL}/api/reports/produzione", headers=h)
        assert r.status_code == 200
        d = r.json()
        assert "per_categoria_peso" in d
        pcp = d["per_categoria_peso"]
        assert isinstance(pcp, list)
        assert len(pcp) == 4, f"Attesi 4 elementi, trovati {len(pcp)}"
        # Ordine fisso: BIANCHERIA_PIANA → SPUGNA → VARIE → NON_CLASSIFICATO
        expected_order = ["BIANCHERIA_PIANA", "SPUGNA", "VARIE", "NON_CLASSIFICATO"]
        for i, k in enumerate(expected_order):
            assert pcp[i]["categoria_peso"] == k, f"Posizione {i}: atteso {k}, trovato {pcp[i]['categoria_peso']}"
            assert "label" in pcp[i]
            assert "kg" in pcp[i]
            assert "pezzi" in pcp[i]

    def test_per_categoria_peso_sum_matches_totale_kg(self, h):
        r = requests.get(f"{BASE_URL}/api/reports/produzione", headers=h)
        assert r.status_code == 200
        d = r.json()
        somma = sum(c["kg"] for c in d["per_categoria_peso"])
        # tolleranza floating point
        assert abs(somma - d["totale_kg"]) < 0.05, \
            f"Somma per_categoria_peso ({somma}) != totale_kg ({d['totale_kg']})"

    def test_per_ddt_subtotali_by_catpeso(self, h):
        r = requests.get(f"{BASE_URL}/api/reports/produzione", headers=h)
        assert r.status_code == 200
        d = r.json()
        assert "per_ddt" in d
        if len(d["per_ddt"]) == 0:
            pytest.skip("Nessun DDT nel periodo")
        for row in d["per_ddt"]:
            for k in ("kg_biancheria_piana", "kg_spugna", "kg_varie", "kg_non_classificato"):
                assert k in row, f"DDT {row.get('numero')} manca campo {k}"
            somma = (row["kg_biancheria_piana"] + row["kg_spugna"]
                     + row["kg_varie"] + row["kg_non_classificato"])
            assert abs(somma - row["kg"]) < 0.05, \
                f"DDT {row['numero']}: somma subtotali ({somma}) != kg totali ({row['kg']})"


class TestArticoliCheckEndpoint:

    def test_articoli_check_has_non_classificati(self, h):
        r = requests.get(f"{BASE_URL}/api/reports/produzione/articoli-check", headers=h)
        assert r.status_code == 200
        d = r.json()
        assert "non_classificati_count" in d
        assert "non_classificati" in d
        assert isinstance(d["non_classificati"], list)
        assert isinstance(d["non_classificati_count"], int)
        # Ogni elemento deve avere id/codice/descrizione
        for a in d["non_classificati"]:
            assert "id" in a
            assert "codice" in a
            assert "descrizione" in a
        # categorie_peso enum returned
        assert set(d.get("categorie_peso", [])) == set(CATEGORIE_PESO)


class TestReportXlsx:

    def test_xlsx_has_8_sheets_including_per_categoria_peso(self, h):
        r = requests.get(f"{BASE_URL}/api/reports/produzione/xlsx", headers=h)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith(
            "application/vnd.openxmlformats-officedocument")
        wb = load_workbook(io.BytesIO(r.content))
        sheets = wb.sheetnames
        expected = ["Sommario", "Per mese", "Per anno", "Per cliente",
                    "Per categoria", "Per categoria peso", "Per articolo", "Per DDT"]
        for name in expected:
            assert name in sheets, f"Sheet '{name}' mancante. Presenti: {sheets}"
        assert len(sheets) == 8, f"Attesi 8 sheet, trovati {len(sheets)}: {sheets}"

    def test_xlsx_ddt_sheet_has_categoria_peso_columns(self, h):
        r = requests.get(f"{BASE_URL}/api/reports/produzione/xlsx", headers=h)
        wb = load_workbook(io.BytesIO(r.content))
        ws = wb["Per DDT"]
        headers = [c.value for c in ws[1]]
        for expected_col in ("Kg biancheria", "Kg spugna", "Kg varie", "Kg non class.", "Kg totale", "Pezzi"):
            assert expected_col in headers, f"Colonna '{expected_col}' mancante in sheet 'Per DDT'. Trovate: {headers}"

    def test_xlsx_per_categoria_peso_sheet_has_4_rows(self, h):
        r = requests.get(f"{BASE_URL}/api/reports/produzione/xlsx", headers=h)
        wb = load_workbook(io.BytesIO(r.content))
        ws = wb["Per categoria peso"]
        # row 1 = header, rows 2-5 = 4 categorie
        # Check header
        headers = [c.value for c in ws[1]]
        assert "Categoria peso" in headers
        assert "Kg" in headers
        assert "Pezzi" in headers
        # Count data rows
        data_rows = [row for row in ws.iter_rows(min_row=2, values_only=True) if row[0]]
        assert len(data_rows) == 4, f"Attese 4 righe in 'Per categoria peso', trovate {len(data_rows)}"
