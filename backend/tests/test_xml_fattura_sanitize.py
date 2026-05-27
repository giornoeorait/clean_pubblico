"""Regression tests per il generatore XML Fattura Elettronica.

Verifica che:
1. Caratteri Unicode invisibili (LTR/RTL marks, ZWSP, BOM) vengano rimossi
   dai campi anagrafici (CF, P.IVA, codice SDI, IBAN).
2. Il parser indirizzi distingua correttamente via, civico, CAP, comune, provincia.
3. I prefissi tipo "Sede Legale:" vengano rimossi.
"""
import xml.etree.ElementTree as ET

from services.fattura_elettronica import (
    build_fattura_elettronica_xml,
    parse_address,
    _clean_cf,
    _clean_alnum,
    _clean,
    safe_numero,
)


NS = {"p": "http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2"}


def _make_inputs(company_overrides=None, cliente_overrides=None):
    company = {
        "ragione_sociale": "TEST SRL",
        "partita_iva": "12345678901",
        "codice_fiscale": "12345678901",
        "indirizzo": "Via Roma 1",
        "cap": "20100",
        "comune": "Milano",
        "provincia": "MI",
        "regime_fiscale": "RF01",
        "iban": "IT60X0542811101000000123456",
    }
    company.update(company_overrides or {})

    cliente = {
        "ragione_sociale": "Cliente Test Srl",
        "partita_iva": "03051240608",
        "indirizzo": "Via degli Etruschi 7",
        "cap": "03100",
        "comune": "Frosinone",
        "provincia": "FR",
        "codice_sdi": "SUBM70N",
    }
    cliente.update(cliente_overrides or {})

    fattura = {
        "numero": "FT-2026-00066",
        "data": "2026-05-27",
        "totale": 1170.38,
        "imponibile": 959.33,
        "iva": 211.05,
        "iva_pct": 22.0,
    }
    ddts = [
        {"numero": "DDT-2026-00017", "data": "2026-05-25", "imponibile": 335.10},
    ]
    return fattura, company, cliente, ddts


def test_unicode_invisible_chars_removed():
    """U+202A, U+202C ecc. devono essere rimossi dal CF del cedente."""
    cf_dirty = "\u202a01234567890\u202c"
    fattura, company, cliente, ddts = _make_inputs(company_overrides={"codice_fiscale": cf_dirty})
    xml_bytes, _ = build_fattura_elettronica_xml(fattura, company, cliente, ddts, validate_xsd=False)
    text = xml_bytes.decode("utf-8")
    assert "\u202a" not in text
    assert "\u202c" not in text
    assert "<CodiceFiscale>01234567890</CodiceFiscale>" in text


def test_xml_is_well_formed():
    fattura, company, cliente, ddts = _make_inputs()
    xml_bytes, _ = build_fattura_elettronica_xml(fattura, company, cliente, ddts, validate_xsd=False)
    # Should parse without error
    root = ET.fromstring(xml_bytes)
    assert root.tag.endswith("FatturaElettronica")
    assert root.attrib["versione"] == "FPR12"


def test_address_parser_corrects_inverted():
    """Bug pre-fix: '03100 Via degli Etruschi, 7, Frosinone, FR, Italia'
    veniva parsato come Comune='Via degli Etruschi', Indirizzo='7, Frosinone, FR'."""
    addr = parse_address("03100 Via degli Etruschi, 7, Frosinone, FR, Italia", "03100")
    assert addr["cap"] == "03100"
    assert addr["comune"] == "Frosinone"
    assert addr["provincia"] == "FR"
    assert addr["nazione"] == "IT"
    assert "Via degli Etruschi" in addr["indirizzo"]
    assert "7" in addr["indirizzo"]
    # Comune NON deve contenere "Via"
    assert "Via" not in addr["comune"]


def test_address_parser_strips_preamble():
    """'Sede Legale: Via X, ...' deve essere normalizzato."""
    addr = parse_address("Sede Legale: Via della Foce 12, 00054 Fiumicino RM", "")
    assert addr["cap"] == "00054"
    assert addr["comune"] == "Fiumicino"
    assert addr["provincia"] == "RM"
    assert "Sede Legale" not in addr["indirizzo"]
    assert "Via della Foce" in addr["indirizzo"]


def test_clean_strips_invisible_chars():
    assert _clean("\u202aabc\u202c") == "abc"
    assert _clean("a\u200bb") == "ab"
    assert _clean("a\nb\nc") == "a b c"


def test_clean_cf_normalizes():
    assert _clean_cf("\u202a17400491001\u202c") == "17400491001"
    assert _clean_cf("rssmra80a01h501u") == "RSSMRA80A01H501U"


def test_clean_alnum_strips():
    assert _clean_alnum("subm70n") == "SUBM70N"
    assert _clean_alnum("IT60 X05 4281 1101") == "IT60X0542811101"


def test_safe_numero_keeps_slash_dash():
    assert safe_numero("FT-2026-00066/L") == "FT-2026-00066/L"
    assert safe_numero("\u202aFT-2026-00066/L\u202c") == "FT-2026-00066/L"


def test_piva_strips_eu_prefix():
    """Bug: P.IVA salvata come 'IT17400491001' veniva troncata a 'IT174004910'."""
    from services.fattura_elettronica import safe_partita_iva
    assert safe_partita_iva("IT17400491001") == "17400491001"
    assert safe_partita_iva("it 17400491001") == "17400491001"
    assert safe_partita_iva("17400491001") == "17400491001"
    # Already clean
    assert safe_partita_iva("12345678901") == "12345678901"


def test_address_strips_company_name_prefix():
    """Bug: 'WATERWELL SRL Sede Legale: Via della Foce' → 'Via della Foce'."""
    addr = parse_address("WATERWELL FCO Cleaning Tech SRL Sede Legale: Via della Foce 12", "00054")
    assert "WATERWELL" not in addr["indirizzo"]
    assert "Sede Legale" not in addr["indirizzo"]
    assert "Via della Foce" in addr["indirizzo"]


def test_xml_validates_against_official_xsd():
    """Test critico: l'XML generato deve validare contro lo schema XSD ufficiale FatturaPA."""
    from services.xsd_validator import validate_xml_against_xsd
    fattura, company, cliente, ddts = _make_inputs(
        cliente_overrides={
            "cap": "03100", "comune": "Frosinone", "provincia": "FR",
            "indirizzo": "Via degli Etruschi 7",
            "ragione_sociale": "Cliente Test Srl",
        },
        company_overrides={
            "cap": "20100", "comune": "Milano", "provincia": "MI",
            "indirizzo": "Via Roma 1",
        },
    )
    xml_bytes, _ = build_fattura_elettronica_xml(fattura, company, cliente, ddts, validate_xsd=False)
    errors = validate_xml_against_xsd(xml_bytes)
    assert errors == [], f"XML non valido contro XSD: {errors}"


def test_xml_includes_correct_cessionario_address():
    fattura, company, cliente, ddts = _make_inputs()
    xml_bytes, _ = build_fattura_elettronica_xml(fattura, company, cliente, ddts, validate_xsd=False)
    root = ET.fromstring(xml_bytes)
    # Lo schema FatturaPA usa elementFormDefault="unqualified": i child di
    # FatturaElettronica sono in no-namespace.
    sede = root.find(".//CessionarioCommittente/Sede")
    assert sede is not None, "Sede del cessionario non trovata"
    assert sede.find("CAP").text == "03100"
    assert sede.find("Comune").text == "Frosinone"
    assert sede.find("Provincia").text == "FR"
    indirizzo = sede.find("Indirizzo").text
    assert "Via degli Etruschi" in indirizzo


def test_filename_convention():
    fattura, company, cliente, ddts = _make_inputs()
    _, filename = build_fattura_elettronica_xml(fattura, company, cliente, ddts, validate_xsd=False)
    # Must follow ITxxxxxxxxxxx_NNNNN.xml
    assert filename.startswith("IT12345678901_")
    assert filename.endswith(".xml")
    assert "00066" in filename
