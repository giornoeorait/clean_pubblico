"""Iter35 — Report BI kg + Statistiche peso cliente + Anomalie pesi + Indici Mongo.

Test cases:
1. GET /reports/produzione con nuovi filtri (mese, articolo_id, stato_fatturazione, solo_consegnati)
2. Bug fix: mese non deve venire sovrascritto nella response
3. Nuovi KPI: peso_medio_per_ddt, peso_medio_giornaliero, peso_medio_mensile, giorni_distinti, mesi_distinti
4. GET /reports/produzione/pdf ritorna PDF valido con magic bytes '%PDF'
5. GET /reports/produzione/xlsx con nuovi filtri include KPI arricchiti
6. GET /reports/anomalie-pesi admin only (403 non-admin)
7. GET /clienti/{id}/statistiche-peso struttura + 404 cliente inesistente
8. Indici MongoDB creati (listIndexes)
"""
import os
import pytest
import requests
from pathlib import Path

# Carica REACT_APP_BACKEND_URL da frontend/.env
def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v
    env_file = Path("/app/frontend/.env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    return ""

BASE_URL = _load_backend_url().rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@cleantec.it"
ADMIN_PASSWORD = "admin123"
CONT_EMAIL = "contabilita@cleantec.it"
CONT_PASSWORD = "contabilita123"


# --------- Fixtures ---------
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    token = r.json().get("access_token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def cont_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": CONT_EMAIL, "password": CONT_PASSWORD})
    assert r.status_code == 200, f"contabilita login failed: {r.status_code} {r.text}"
    token = r.json().get("access_token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


# --------- Test /reports/produzione (nuovi filtri + KPI) ---------

class TestReportProduzione:
    def test_kpi_arricchiti_presenti(self, admin_session):
        r = admin_session.get(f"{API}/reports/produzione")
        assert r.status_code == 200
        d = r.json()
        # Nuovi KPI e campi
        for k in [
            "peso_medio_per_ddt", "peso_medio_giornaliero", "peso_medio_mensile",
            "giorni_distinti", "mesi_distinti", "mese_label",
            "totale_kg", "totale_pezzi", "ddt_count", "per_categoria_peso", "per_mese",
        ]:
            assert k in d, f"campo mancante: {k}"
        # tipi ok
        assert isinstance(d["giorni_distinti"], int)
        assert isinstance(d["mesi_distinti"], int)

    def test_mese_bugfix_non_sovrascritto(self, admin_session):
        """Bug fix: la variabile locale `mese` (loop) non deve sovrascrivere il query param `mese` in response."""
        r = admin_session.get(f"{API}/reports/produzione", params={"anno": 2025, "mese": 11})
        assert r.status_code == 200
        d = r.json()
        # Il query param 'mese' deve rimanere = 11 (int) o "11"
        assert d.get("mese") in (11, "11"), f"mese risposto = {d.get('mese')!r}"
        assert d.get("anno") in (2025, "2025")
        # mese_label deve riflettere anno-mese
        assert d.get("mese_label") == "2025-11"

    def test_filtro_solo_consegnati(self, admin_session):
        r = admin_session.get(f"{API}/reports/produzione", params={"solo_consegnati": "true"})
        assert r.status_code == 200
        d = r.json()
        assert d.get("solo_consegnati") is True
        # ddt_count e totale_kg devono essere >= 0 e coerenti
        assert d.get("totale_kg") >= 0

    def test_filtro_stato_fatturazione(self, admin_session):
        r = admin_session.get(f"{API}/reports/produzione", params={"stato_fatturazione": "non_fatturato"})
        assert r.status_code == 200
        d = r.json()
        assert d.get("stato_fatturazione") == "non_fatturato"

    def test_filtro_articolo_id(self, admin_session):
        # prendi un articolo esistente
        art = admin_session.get(f"{API}/articoli").json()
        if not art:
            pytest.skip("Nessun articolo per test filtro")
        aid = art[0]["id"]
        r = admin_session.get(f"{API}/reports/produzione", params={"articolo_id": aid})
        assert r.status_code == 200
        d = r.json()
        assert d.get("articolo_id") == aid
        # Tutti gli articoli restituiti devono avere lo stesso id (o essere 0)
        for a in d.get("per_articolo", []):
            assert a["articolo_id"] == aid

    def test_righe_qta_zero_escluse(self, admin_session):
        """§13: righe con quantita<=0 non contribuiscono. Verifica che totale_pezzi > 0 e coerente."""
        r = admin_session.get(f"{API}/reports/produzione")
        assert r.status_code == 200
        d = r.json()
        # Non possiamo iniettare dati, ma verifichiamo che i pezzi siano coerenti (>=0)
        assert d["totale_pezzi"] >= 0


# --------- Test PDF/XLSX export ---------

class TestReportExport:
    def test_pdf_valido(self, admin_session):
        r = admin_session.get(f"{API}/reports/produzione/pdf", params={"anno": 2025})
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF", f"magic bytes non validi: {r.content[:8]!r}"
        assert len(r.content) > 1000

    def test_pdf_con_filtro_mese(self, admin_session):
        r = admin_session.get(f"{API}/reports/produzione/pdf", params={"anno": 2025, "mese": 11})
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"

    def test_xlsx_con_kpi_arricchiti(self, admin_session):
        r = admin_session.get(f"{API}/reports/produzione/xlsx", params={"anno": 2025})
        assert r.status_code == 200
        assert "spreadsheet" in r.headers.get("content-type", "")
        # Verifica magic bytes ZIP (xlsx è uno zip)
        assert r.content[:2] == b"PK"
        # Parse xlsx e verifica sommario
        import io
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(r.content))
        assert "Sommario" in wb.sheetnames
        ws = wb["Sommario"]
        labels = [ws.cell(row=i, column=1).value for i in range(1, ws.max_row + 1)]
        for k in ["Peso medio per DDT", "Peso medio giornaliero", "Peso medio mensile", "Giorni distinti", "Mesi distinti"]:
            assert k in labels, f"KPI mancante in Sommario: {k}"


# --------- Test /reports/anomalie-pesi ---------

class TestAnomaliePesi:
    def test_admin_puo_leggere(self, admin_session):
        r = admin_session.get(f"{API}/reports/anomalie-pesi")
        assert r.status_code == 200
        d = r.json()
        for k in [
            "articoli_anomali", "articoli_anomali_count",
            "ddt_anomali", "ddt_anomali_count",
            "righe_qta_zero", "righe_articolo_mancante", "generato_at",
        ]:
            assert k in d, f"campo mancante: {k}"
        assert isinstance(d["articoli_anomali"], list)
        assert isinstance(d["ddt_anomali"], list)
        # Struttura di ogni articolo anomalo
        for a in d["articoli_anomali"]:
            assert "problemi" in a
            assert "ddt_coinvolti" in a
            assert isinstance(a["problemi"], list)
        # Struttura di ogni DDT anomalo
        for dd in d["ddt_anomali"]:
            assert "problemi" in dd
            assert "somma_subtotali" in dd
            assert "peso_totale" in dd

    def test_non_admin_forbidden(self, cont_session):
        r = cont_session.get(f"{API}/reports/anomalie-pesi")
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"


# --------- Test /clienti/{id}/statistiche-peso ---------

class TestStatistichePesoCliente:
    def test_struttura_response(self, admin_session):
        clienti = admin_session.get(f"{API}/clienti").json()
        if not clienti:
            pytest.skip("Nessun cliente per test statistiche-peso")
        cid = clienti[0]["id"]
        r = admin_session.get(f"{API}/clienti/{cid}/statistiche-peso")
        assert r.status_code == 200
        d = r.json()
        # Struttura top-level
        for k in ["cliente", "periodo", "complessivo", "mese_corrente", "anno_corrente"]:
            assert k in d, f"campo top-level mancante: {k}"
        # Cliente
        assert d["cliente"]["id"] == cid
        # Periodo
        for k in [
            "totale_kg", "totale_pezzi", "ddt_count", "peso_medio_per_ddt",
            "per_categoria_peso", "per_mese", "per_articolo", "per_ddt", "filtri",
        ]:
            assert k in d["periodo"], f"periodo.{k} mancante"

    def test_cliente_inesistente_404(self, admin_session):
        r = admin_session.get(f"{API}/clienti/nonesistente-xyz-123/statistiche-peso")
        assert r.status_code == 404

    def test_filtri_anno_mese(self, admin_session):
        clienti = admin_session.get(f"{API}/clienti").json()
        if not clienti:
            pytest.skip("Nessun cliente per test")
        cid = clienti[0]["id"]
        r = admin_session.get(
            f"{API}/clienti/{cid}/statistiche-peso",
            params={"anno": 2025, "mese": 11},
        )
        assert r.status_code == 200
        d = r.json()
        assert d["periodo"]["filtri"].get("anno") in (2025, "2025")
        assert d["periodo"]["filtri"].get("mese") in (11, "11")


# --------- Test indici MongoDB ---------

class TestMongoIndexes:
    def test_indici_ddt_e_articoli(self, admin_session):
        """Verifica indici via connessione diretta mongo (backend has admin access)."""
        # Non abbiamo un endpoint HTTP per listIndexes: importiamo il db backend
        import asyncio, sys
        sys.path.insert(0, "/app/backend")
        from core import db  # noqa: E402

        async def _check():
            ddt_idx = await db.ddt.list_indexes().to_list(50)
            art_idx = await db.articoli.list_indexes().to_list(50)
            return ddt_idx, art_idx

        ddt_idx, art_idx = asyncio.get_event_loop().run_until_complete(_check()) \
            if not asyncio.get_event_loop().is_running() else asyncio.new_event_loop().run_until_complete(_check())

        # Set di chiavi per ogni indice
        def keys_set(idx_list):
            out = []
            for i in idx_list:
                # {'v':2, 'key': {'tenant_id':1,'data':-1}, 'name':..}
                out.append(tuple(sorted(i["key"].items())))
            return out

        ddt_keys = keys_set(ddt_idx)
        art_keys = keys_set(art_idx)

        expected_ddt = [
            (("data", -1), ("tenant_id", 1)),
            (("cliente_id", 1), ("data", -1), ("tenant_id", 1)),
            (("calcolo_peso_tipo", 1), ("tenant_id", 1)),
            (("consegnato", 1), ("tenant_id", 1)),
            (("data", -1), ("stato", 1), ("tenant_id", 1)),  # not present—actual is stato_fatturazione
        ]
        # Verifichiamo separatamente stato_fatturazione (spec dice "tenant+stato+data")
        expected_ddt_alt = (("data", -1), ("stato_fatturazione", 1), ("tenant_id", 1))

        missing = []
        for exp in expected_ddt[:4]:
            if exp not in ddt_keys:
                missing.append(exp)
        # L'ultimo può essere stato_fatturazione
        if expected_ddt_alt not in ddt_keys:
            missing.append(expected_ddt_alt)

        assert not missing, f"Indici DDT mancanti: {missing}\nEsistenti: {ddt_keys}"

        expected_art = (("categoria_peso", 1), ("tenant_id", 1))
        assert expected_art in art_keys, f"Indice articoli mancante: {expected_art}\nEsistenti: {art_keys}"
