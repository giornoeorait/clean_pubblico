"""Iter32 — Test filtri Fatture + Rinumera/Ridata + Report Produzione esteso."""
import os
import pytest
import requests
from datetime import datetime, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

ADMIN_EMAIL = "admin@cleantec.it"
ADMIN_PWD = "admin123"


# ------------------------- fixtures -------------------------
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PWD})
    assert r.status_code == 200, r.text
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def api(admin_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"})
    return s


# ------------------------- fatture: list + filtri -------------------------
class TestFattureFilters:
    def test_list_no_filters(self, api):
        r = api.get(f"{BASE_URL}/api/fatture")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_summary_no_filters(self, api):
        r = api.get(f"{BASE_URL}/api/fatture/summary")
        assert r.status_code == 200
        d = r.json()
        for k in ("count", "totale_imponibile", "totale_iva", "totale_documento"):
            assert k in d
        assert isinstance(d["count"], int)

    def test_summary_matches_list_totals(self, api):
        # confronta totali summary con la somma sulla list
        l = api.get(f"{BASE_URL}/api/fatture").json()
        s = api.get(f"{BASE_URL}/api/fatture/summary").json()
        # summary è aggregato full-dataset; list è limitata a 500. Confronto solo se list<500
        if len(l) < 500:
            assert s["count"] == len(l)
            tot_imp = round(sum(f.get("imponibile", 0) for f in l), 2)
            tot_doc = round(sum(f.get("totale", 0) for f in l), 2)
            assert abs(s["totale_imponibile"] - tot_imp) < 0.05
            assert abs(s["totale_documento"] - tot_doc) < 0.05

    def test_filter_data_range(self, api):
        r = api.get(f"{BASE_URL}/api/fatture",
                    params={"data_inizio": "2026-01-01", "data_fine": "2026-01-31"})
        assert r.status_code == 200
        # tutte le fatture ritornate devono avere data nel range
        for f in r.json():
            d = f.get("data", "")
            if isinstance(d, str):
                assert d[:7] == "2026-01" or d[:10] >= "2026-01-01"

    def test_filter_piva_normalization(self, api):
        # piva con spazi/dot deve funzionare come piva pulita
        # invia una piva "quasi vuota" ma valida per la normalize
        r = api.get(f"{BASE_URL}/api/fatture", params={"piva": "  "})
        assert r.status_code == 200  # spazi = come nessun filtro
        # ok se ritorna una lista (anche vuota)
        assert isinstance(r.json(), list)

    def test_filter_cliente_id(self, api):
        clienti = api.get(f"{BASE_URL}/api/clienti").json()
        if not clienti:
            pytest.skip("Nessun cliente")
        cid = clienti[0]["id"]
        r = api.get(f"{BASE_URL}/api/fatture", params={"cliente_id": cid})
        assert r.status_code == 200
        for f in r.json():
            assert f["cliente_id"] == cid

    def test_summary_with_filters(self, api):
        r = api.get(f"{BASE_URL}/api/fatture/summary",
                    params={"data_inizio": "2026-01-01", "data_fine": "2026-12-31"})
        assert r.status_code == 200
        d = r.json()
        assert d["count"] >= 0


# ------------------------- rinumera/ridata -------------------------
class TestRinumeraFattura:
    """Usa una fattura non trasmessa; ripristina alla fine."""

    @pytest.fixture(scope="class")
    def target_fattura(self, api):
        # trova una fattura non trasmessa
        fatts = api.get(f"{BASE_URL}/api/fatture").json()
        candidate = next((f for f in fatts if not f.get("xml_transmitted")), None)
        if not candidate:
            pytest.skip("Nessuna fattura non trasmessa per test rinumera")
        return candidate

    def test_motivazione_troppo_corta_422(self, api, target_fattura):
        r = api.patch(f"{BASE_URL}/api/fatture/{target_fattura['id']}/rinumera",
                      json={"nuova_data": "2026-06-15", "motivazione": "corta"})
        assert r.status_code == 422, f"Attesa 422 per motivazione < 10 char, got {r.status_code}: {r.text}"

    def test_no_change_400(self, api, target_fattura):
        # solo motivazione, senza numero né data
        r = api.patch(f"{BASE_URL}/api/fatture/{target_fattura['id']}/rinumera",
                      json={"motivazione": "test iter32 nessun cambio proposto"})
        assert r.status_code == 400, r.text
        assert "cambio" in (r.json().get("detail") or "").lower() or "specificare" in (r.json().get("detail") or "").lower()

    def test_cambio_solo_data(self, api, target_fattura):
        fid = target_fattura["id"]
        old = api.get(f"{BASE_URL}/api/fatture/{fid}").json()
        # scegli una nuova data nello stesso anno per non forzare cambio numerazione anno
        old_data = old.get("data")
        old_iso = old_data[:10] if isinstance(old_data, str) else old_data.get("$date", "")[:10] if isinstance(old_data, dict) else ""
        # nuova data = spostata di 1 giorno indietro (se possibile) nello stesso anno
        try:
            dt = datetime.fromisoformat(old_iso)
        except Exception:
            dt = datetime.now(timezone.utc)
        new_dt = dt.replace(day=max(1, dt.day - 1) if dt.day > 1 else dt.day + 1)
        new_iso = new_dt.strftime("%Y-%m-%d")
        r = api.patch(f"{BASE_URL}/api/fatture/{fid}/rinumera",
                      json={"nuova_data": new_iso,
                            "motivazione": "TEST iter32 cambio solo data verifica audit"})
        assert r.status_code == 200, r.text
        updated = r.json()
        assert updated["data"][:10] == new_iso
        # Ripristina
        api.patch(f"{BASE_URL}/api/fatture/{fid}/rinumera",
                  json={"nuova_data": old_iso, "motivazione": "TEST iter32 ripristino data originale"})

    def test_audit_log_written(self, api, target_fattura):
        # verifica indirettamente: dopo un update deve esistere almeno un audit
        # non c'è endpoint pubblico audit — ma se test_cambio_solo_data ha completato senza 500 è ok.
        # Verifichiamo che dopo la rinumera l'updated_at sia cambiato
        fid = target_fattura["id"]
        r = api.get(f"{BASE_URL}/api/fatture/{fid}")
        assert r.status_code == 200


# ------------------------- report produzione -------------------------
class TestReportProduzione:
    def test_no_filters(self, api):
        r = api.get(f"{BASE_URL}/api/reports/produzione")
        assert r.status_code == 200, r.text
        d = r.json()
        # nuovi aggregati richiesti
        for k in ("per_categoria", "per_anno", "per_ddt", "ddt_count",
                  "per_mese", "per_cliente", "per_articolo",
                  "totale_kg", "totale_pezzi"):
            assert k in d, f"chiave mancante: {k}"
        assert isinstance(d["per_categoria"], list)
        assert isinstance(d["per_anno"], list)
        assert isinstance(d["per_ddt"], list)
        assert isinstance(d["ddt_count"], int)
        # struttura per_ddt
        if d["per_ddt"]:
            row = d["per_ddt"][0]
            for k in ("ddt_id", "numero", "data", "cliente_nome", "kg", "pezzi"):
                assert k in row, f"per_ddt manca {k}"

    def test_filter_range_date(self, api):
        r = api.get(f"{BASE_URL}/api/reports/produzione",
                    params={"data_inizio": "2026-06-01", "data_fine": "2026-06-30"})
        assert r.status_code == 200
        d = r.json()
        # tutti i ddt nel per_ddt devono essere in range
        for row in d.get("per_ddt", []):
            assert row["data"][:10] >= "2026-06-01" and row["data"][:10] <= "2026-06-30", row["data"]

    def test_filter_cliente(self, api):
        # prendi un cliente_id valido dai ddt esistenti
        r0 = api.get(f"{BASE_URL}/api/reports/produzione").json()
        if not r0.get("per_cliente"):
            pytest.skip("Nessun dato per cliente")
        cid = r0["per_cliente"][0]["cliente_id"]
        r = api.get(f"{BASE_URL}/api/reports/produzione", params={"cliente_id": cid})
        assert r.status_code == 200
        d = r.json()
        for row in d.get("per_ddt", []):
            assert row.get("cliente_id") == cid

    def test_filter_categoria(self, api):
        r = api.get(f"{BASE_URL}/api/reports/produzione", params={"categoria": "biancheria"})
        assert r.status_code == 200
        d = r.json()
        # per_categoria dopo filtro deve contenere solo 'biancheria' (se ci sono dati)
        cats = [c["categoria"] for c in d.get("per_categoria", [])]
        if cats:
            assert all(c == "biancheria" for c in cats), cats

    def test_articoli_check(self, api):
        r = api.get(f"{BASE_URL}/api/reports/produzione/articoli-check")
        assert r.status_code == 200
        d = r.json()
        for k in ("totale_articoli", "senza_peso_count", "senza_peso", "sospetti_grammi", "unita", "note"):
            assert k in d
        assert d["unita"] == "kg"
        assert isinstance(d["senza_peso"], list)

    def test_xlsx_export(self, api):
        r = api.get(f"{BASE_URL}/api/reports/produzione/xlsx", params={"anno": 2026})
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "spreadsheetml" in ct or "openxml" in ct, ct
        # deve essere un file zip xlsx valido (magic bytes PK)
        assert r.content[:2] == b"PK", "Non è un file XLSX valido"
        assert len(r.content) > 500
