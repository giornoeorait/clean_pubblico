"""Iter28: Numerazione documenti + FatturaPA XML export tests.

Covers:
- GET /api/company/numerazione (7 kinds, current_seq + suffix)
- PUT /api/company/numerazione (update, suffix persistence, validation errors)
- POST /api/fatture (uses configured seq + suffix, uses company.iva_default_pct)
- GET /api/fatture/{id}/xml-pa (well-formed XML, key elements, filename)
- PUT /api/company with regime_fiscale + iva_default_pct
- RBAC: admin-only on numerazione endpoints
"""
import os
import re
import xml.etree.ElementTree as ET

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not set"

# ---------- Auth fixtures ----------

def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login("admin@cleantec.it", "admin123")


@pytest.fixture(scope="module")
def contab_token():
    return _login("contabilita@cleantec.it", "contabilita123")


@pytest.fixture(scope="module")
def logistica_token():
    return _login("logistica@cleantec.it", "logistica123")


def H(t):
    return {"Authorization": f"Bearer {t}"}


# ---------- Test state holder ----------

class State:
    original_numerazione = None
    original_company = None


# ---------- Numerazione GET ----------

class TestNumerazioneGet:
    def test_returns_7_kinds(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/company/numerazione",
                         headers=H(admin_token), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "entries" in data
        keys = [e["key"] for e in data["entries"]]
        expected = {"fattura", "ddt", "offerta", "contratto",
                    "ordinativo", "ddt_fornitore", "fattura_fornitore"}
        assert set(keys) == expected, f"keys mismatch: {keys}"
        for e in data["entries"]:
            assert {"key", "prefix", "label", "current_seq", "suffix"} <= set(e.keys())
        # snapshot for cleanup
        State.original_numerazione = {e["key"]: {"seq": e["current_seq"], "suffix": e["suffix"]}
                                      for e in data["entries"]}

    def test_admin_only_403(self, contab_token):
        r = requests.get(f"{BASE_URL}/api/company/numerazione",
                         headers=H(contab_token), timeout=15)
        assert r.status_code == 403, r.text

    def test_unauthenticated_401(self):
        r = requests.get(f"{BASE_URL}/api/company/numerazione", timeout=15)
        assert r.status_code == 401


# ---------- Numerazione PUT ----------

class TestNumerazionePut:
    def test_update_fattura_seq_and_suffix(self, admin_token):
        # Bump fattura seq by 5 with suffix /L
        cur = State.original_numerazione["fattura"]["seq"]
        new_seq = cur + 5
        r = requests.put(
            f"{BASE_URL}/api/company/numerazione",
            headers=H(admin_token),
            json={"entries": [
                {"key": "fattura", "seq": new_seq, "suffix": "/L"},
                {"key": "ddt", "seq": State.original_numerazione["ddt"]["seq"] + 3, "suffix": ""},
            ]},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        f_entry = next(e for e in data["entries"] if e["key"] == "fattura")
        assert f_entry["current_seq"] == new_seq
        assert f_entry["suffix"] == "/L"

    def test_reject_lower_seq(self, admin_token):
        # Now fattura is at seq=cur+5, try setting it to cur (below current)
        r = requests.put(
            f"{BASE_URL}/api/company/numerazione",
            headers=H(admin_token),
            json={"entries": [
                {"key": "fattura", "seq": 1, "suffix": "/L"},
            ]},
            timeout=15,
        )
        assert r.status_code == 400
        assert "inferiore al corrente" in r.json().get("detail", "")

    def test_reject_unknown_kind(self, admin_token):
        r = requests.put(
            f"{BASE_URL}/api/company/numerazione",
            headers=H(admin_token),
            json={"entries": [{"key": "bogus_kind", "seq": 99, "suffix": ""}]},
            timeout=15,
        )
        assert r.status_code == 400
        assert "non riconosciuto" in r.json().get("detail", "")

    def test_non_admin_forbidden(self, contab_token):
        r = requests.put(
            f"{BASE_URL}/api/company/numerazione",
            headers=H(contab_token),
            json={"entries": [{"key": "fattura", "seq": 999, "suffix": ""}]},
            timeout=15,
        )
        assert r.status_code == 403


# ---------- Company anagrafica with regime_fiscale + iva_default ----------

class TestCompanyFields:
    def test_get_company_snapshot(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/company", headers=H(admin_token), timeout=15)
        assert r.status_code == 200
        State.original_company = r.json()
        assert "regime_fiscale" in State.original_company
        assert "iva_default_pct" in State.original_company

    def test_put_company_regime_and_iva(self, admin_token):
        body = dict(State.original_company)
        body.pop("logo_url", None)
        body.pop("setup_complete", None)
        body.pop("updated_at", None)
        body["regime_fiscale"] = "RF19"
        body["iva_default_pct"] = 10
        r = requests.put(f"{BASE_URL}/api/company",
                         headers=H(admin_token), json=body, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["regime_fiscale"] == "RF19"
        assert float(data["iva_default_pct"]) == 10.0

        # Persistence check
        r2 = requests.get(f"{BASE_URL}/api/company",
                          headers=H(admin_token), timeout=15)
        assert r2.json()["regime_fiscale"] == "RF19"
        assert float(r2.json()["iva_default_pct"]) == 10.0


# ---------- Fattura: numero uses suffix and IVA default ----------

class TestFatturaCreationUsesConfig:
    def test_create_fattura_uses_suffix_and_iva_default(self, admin_token):
        # Find a cliente with a non-fatturato DDT (or create the chain)
        # 1) Get any cliente
        r = requests.get(f"{BASE_URL}/api/clienti?limit=50",
                         headers=H(admin_token), timeout=15)
        clienti = r.json()
        target_cli = None
        ddts = []
        for c in clienti:
            cid = c["id"]
            r2 = requests.get(f"{BASE_URL}/api/fatture/fatturabili?cliente_id={cid}",
                              headers=H(admin_token), timeout=15)
            j = r2.json()
            if j.get("count", 0) > 0:
                target_cli = c
                ddts = j["ddts"]
                break
        if not target_cli:
            pytest.skip("No client with fatturabili DDTs available — cannot test numero/iva resolution")

        # Numerazione: bump seq for fattura by +1 with suffix '/T'
        rcur = requests.get(f"{BASE_URL}/api/company/numerazione",
                            headers=H(admin_token), timeout=15).json()
        cur_seq = next(e for e in rcur["entries"] if e["key"] == "fattura")["current_seq"]
        new_seq = cur_seq + 1
        requests.put(
            f"{BASE_URL}/api/company/numerazione",
            headers=H(admin_token),
            json={"entries": [{"key": "fattura", "seq": new_seq, "suffix": "/T"}]},
            timeout=15,
        ).raise_for_status()

        # POST /api/fatture without iva_pct → should use company.iva_default_pct=10
        body = {
            "cliente_id": target_cli["id"],
            "ddt_ids": [ddts[0]["id"]],
            # iva_pct intentionally omitted
        }
        r3 = requests.post(f"{BASE_URL}/api/fatture",
                           headers=H(admin_token), json=body, timeout=20)
        assert r3.status_code == 200, r3.text
        f = r3.json()
        assert f["numero"].endswith("/T"), f"numero={f['numero']}"
        # Expected: seq new_seq+1
        m = re.search(r"-(\d{4})-(\d{5})/T$", f["numero"])
        assert m, f"numero pattern mismatch: {f['numero']}"
        assert int(m.group(2)) == new_seq + 1, (m.group(2), new_seq + 1)
        # IVA fallback: must match the company default (10)
        assert float(f["iva_pct"]) == 10.0, f"iva_pct={f['iva_pct']} (expected 10)"
        State.last_fattura_id = f["id"]
        State.last_fattura_numero = f["numero"]


# ---------- FatturaPA XML export ----------

class TestXmlPa:
    def test_xml_pa_well_formed_and_required_elements(self, admin_token):
        if not hasattr(State, "last_fattura_id"):
            # try to pick any existing fattura
            r = requests.get(f"{BASE_URL}/api/fatture?limit=1",
                             headers=H(admin_token), timeout=15)
            if not r.json():
                pytest.skip("No fatture available")
            State.last_fattura_id = r.json()[0]["id"]
            State.last_fattura_numero = r.json()[0]["numero"]

        r = requests.get(
            f"{BASE_URL}/api/fatture/{State.last_fattura_id}/xml-pa",
            headers=H(admin_token), timeout=20,
        )
        assert r.status_code == 200, r.text
        ct = r.headers.get("Content-Type", "")
        assert "application/xml" in ct, f"content-type={ct}"
        cd = r.headers.get("Content-Disposition", "")
        assert "attachment" in cd and "filename=" in cd
        # filename pattern: ITxxxxxxxxxxx_NNNNN.xml
        m = re.search(r'filename="(IT\d+_\d{5}\.xml)"', cd)
        assert m, f"filename pattern fail: {cd}"

        # Parse XML — must be well-formed
        root = ET.fromstring(r.content)
        ns = "{http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2}"
        # Root tag and versione
        assert root.tag.endswith("FatturaElettronica")
        assert root.attrib.get("versione") == "FPR12"

        # ProgressivoInvio MUST match seq portion (5 digits), NOT the year
        prog = root.find(f".//ProgressivoInvio")
        assert prog is not None
        # Extract NNNNN from numero
        seq_match = re.search(r"-\d{4}-(\d{5})", State.last_fattura_numero)
        if seq_match:
            assert prog.text == seq_match.group(1), \
                f"ProgressivoInvio={prog.text!r} but numero seq={seq_match.group(1)!r}"
            # negative: must NOT equal year
            year_match = re.search(r"-(\d{4})-", State.last_fattura_numero)
            assert prog.text != year_match.group(1)

        # FormatoTrasmissione
        ft = root.find(".//FormatoTrasmissione")
        assert ft is not None and ft.text == "FPR12"

        # CedentePrestatore/IdFiscaleIVA/IdPaese=IT
        idp = root.find(".//CedentePrestatore/DatiAnagrafici/IdFiscaleIVA/IdPaese")
        assert idp is not None and idp.text == "IT"
        idc = root.find(".//CedentePrestatore/DatiAnagrafici/IdFiscaleIVA/IdCodice")
        assert idc is not None and idc.text  # not empty

        rf = root.find(".//RegimeFiscale")
        assert rf is not None and rf.text.startswith("RF")

        cess = root.find(".//CessionarioCommittente")
        assert cess is not None

        td = root.find(".//TipoDocumento")
        assert td is not None and td.text == "TD01"

        dv = root.find(".//Divisa")
        assert dv is not None and dv.text == "EUR"

        lines = root.findall(".//DettaglioLinee")
        assert len(lines) >= 1
        riep = root.find(".//DatiRiepilogo")
        assert riep is not None
        assert riep.find("AliquotaIVA") is not None
        assert riep.find("ImponibileImporto") is not None
        assert riep.find("Imposta") is not None

    def test_xml_pa_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/fatture/any/xml-pa", timeout=15)
        assert r.status_code == 401


# ---------- Cleanup ----------

class TestZCleanup:
    """Restore original numerazione suffix to empty and company fields.

    Note: we cannot lower seq below current_seq (by design), so leave seq as-is
    but reset suffix to original (likely empty).
    """

    def test_restore_numerazione_suffix(self, admin_token):
        if not State.original_numerazione:
            pytest.skip("no snapshot")
        # Get current seqs
        rcur = requests.get(f"{BASE_URL}/api/company/numerazione",
                            headers=H(admin_token), timeout=15).json()
        cur_by_key = {e["key"]: e["current_seq"] for e in rcur["entries"]}
        entries = []
        for k, orig in State.original_numerazione.items():
            # Use current seq (cannot lower) but restore original suffix
            entries.append({
                "key": k,
                "seq": cur_by_key.get(k, orig["seq"]),
                "suffix": orig["suffix"],
            })
        r = requests.put(f"{BASE_URL}/api/company/numerazione",
                         headers=H(admin_token),
                         json={"entries": entries}, timeout=15)
        assert r.status_code == 200, r.text

    def test_restore_company_fields(self, admin_token):
        if not State.original_company:
            pytest.skip("no snapshot")
        body = dict(State.original_company)
        body.pop("logo_url", None)
        body.pop("setup_complete", None)
        body.pop("updated_at", None)
        r = requests.put(f"{BASE_URL}/api/company",
                         headers=H(admin_token), json=body, timeout=15)
        assert r.status_code == 200, r.text
