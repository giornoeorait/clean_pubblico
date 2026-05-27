"""Validazione pre-generazione XML Fattura Elettronica (FPR 1.2.2).

Tutti i controlli sono raggruppati qui per offrire all'utente un singolo elenco
di errori chiari prima ancora di tentare l'output XML.

Le regole implementate seguono le specifiche tecniche FatturaPA v1.7.1 (controlli
formali SdI), nonché i requisiti minimi di un soggetto B2B italiano.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


# Regex
PIVA_RE = re.compile(r"^\d{11}$")
CF_PF_RE = re.compile(r"^[A-Z]{6}\d{2}[A-EHLMPR-T]\d{2}[A-Z]\d{3}[A-Z]$")  # persona fisica
CAP_RE = re.compile(r"^\d{5}$")
PROVINCIA_RE = re.compile(r"^[A-Z]{2}$")
CODICE_SDI_RE = re.compile(r"^[A-Z0-9]{6,7}$")
DATE_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
NUMERO_DOC_RE = re.compile(r"^[A-Z0-9/\-.]{1,20}$", re.IGNORECASE)


class InvoiceValidationError(ValueError):
    """Sollevata quando una fattura non passa la validazione pre-XML."""

    def __init__(self, errors: List[Dict[str, str]]):
        self.errors = errors
        super().__init__(f"{len(errors)} errore/i di validazione")

    def to_dict(self) -> Dict[str, Any]:
        return {"detail": "validation_failed", "errors": self.errors}


def _err(code: str, field: str, message: str) -> Dict[str, str]:
    return {"code": code, "field": field, "message": message}


# --- helpers ----------------------------------------------------------------

def _clean(s: Any) -> str:
    """Sanitize input (matches services.fattura_elettronica._clean)."""
    if s is None:
        return ""
    txt = str(s).strip()
    # Caratteri Unicode invisibili (LTR/RTL marks ecc.)
    for ch in "\u200b\u200c\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e\ufeff\u00a0":
        txt = txt.replace(ch, "")
    return txt


def _piva_normalized(piva: Any) -> str:
    """Estrae le 11 cifre eliminando prefisso 'IT' e spazi."""
    txt = _clean(piva).upper()
    txt = re.sub(r"^IT\s*", "", txt)
    return re.sub(r"\D+", "", txt)


def _cf_normalized(cf: Any) -> str:
    txt = _clean(cf).upper()
    return re.sub(r"[^A-Z0-9]", "", txt)


# --- main validator ---------------------------------------------------------

def validate_invoice_data(
    fattura: Dict[str, Any],
    company: Dict[str, Any],
    cliente: Dict[str, Any],
    ddts: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, str]]:
    """Esegui tutti i controlli formali pre-XML. Restituisce la lista degli errori
    (vuota se la fattura è valida).
    """
    errors: List[Dict[str, str]] = []

    # ---- Cedente (azienda emittente) ----
    cedente_piva = _piva_normalized(company.get("partita_iva"))
    cedente_cf = _cf_normalized(company.get("codice_fiscale"))
    if not cedente_piva:
        errors.append(_err("E_CEDENTE_PIVA_MISSING", "company.partita_iva",
                           "Partita IVA del cedente (Anagrafica azienda) mancante."))
    elif not PIVA_RE.fullmatch(cedente_piva):
        errors.append(_err("E_CEDENTE_PIVA_INVALID", "company.partita_iva",
                           f"Partita IVA cedente non valida: '{cedente_piva}' (atteso 11 cifre)."))
    if not cedente_cf:
        errors.append(_err("E_CEDENTE_CF_MISSING", "company.codice_fiscale",
                           "Codice fiscale cedente mancante."))
    elif len(cedente_cf) not in (11, 16):
        errors.append(_err("E_CEDENTE_CF_LEN", "company.codice_fiscale",
                           f"Codice fiscale cedente con lunghezza errata ({len(cedente_cf)}): atteso 11 o 16 caratteri."))

    if not _clean(company.get("ragione_sociale")) and not (
        _clean(company.get("nome")) and _clean(company.get("cognome"))
    ):
        errors.append(_err("E_CEDENTE_DENOM_MISSING", "company.ragione_sociale",
                           "Denominazione/Ragione sociale del cedente mancante."))

    # Regime fiscale RF01..RF19
    regime = _clean(company.get("regime_fiscale") or "RF01").upper()
    if not re.fullmatch(r"RF\d{2}", regime):
        errors.append(_err("E_CEDENTE_REGIME", "company.regime_fiscale",
                           f"Regime fiscale non valido: '{regime}' (es. RF01)."))

    # Sede cedente (CAP, comune, provincia)
    _validate_address(company, errors, prefix="company", role="cedente")

    # ---- Cessionario (cliente) ----
    cli_piva = _piva_normalized(cliente.get("partita_iva"))
    cli_cf = _cf_normalized(cliente.get("codice_fiscale"))
    if not cli_piva and not cli_cf:
        errors.append(_err("E_CESSIONARIO_ID_MISSING", "cliente.partita_iva",
                           "Cliente senza P.IVA né Codice Fiscale: impossibile emettere fattura elettronica."))
    if cli_piva and not PIVA_RE.fullmatch(cli_piva):
        errors.append(_err("E_CESSIONARIO_PIVA_INVALID", "cliente.partita_iva",
                           f"Partita IVA cliente non valida: '{cli_piva}' (atteso 11 cifre)."))
    if cli_cf and len(cli_cf) not in (11, 16):
        errors.append(_err("E_CESSIONARIO_CF_LEN", "cliente.codice_fiscale",
                           f"Codice fiscale cliente con lunghezza errata ({len(cli_cf)}): atteso 11 o 16 caratteri."))
    if not _clean(cliente.get("ragione_sociale")) and not (
        _clean(cliente.get("nome")) and _clean(cliente.get("cognome"))
    ):
        errors.append(_err("E_CESSIONARIO_DENOM_MISSING", "cliente.ragione_sociale",
                           "Denominazione/Ragione sociale cliente mancante."))

    # Sede cessionario
    _validate_address(cliente, errors, prefix="cliente", role="cessionario")

    # Codice destinatario SDI: 7 char alfanumerici, oppure "0000000".
    # Per privati: se manca codice SDI è OBBLIGATORIA la PEC.
    sdi = _clean(cliente.get("codice_sdi")).upper()
    sdi = re.sub(r"[^A-Z0-9]", "", sdi)
    pec = _clean(cliente.get("pec"))
    if sdi:
        if len(sdi) not in (6, 7):  # 6 char = PA, 7 char = privati
            errors.append(_err("E_SDI_LEN", "cliente.codice_sdi",
                               f"Codice destinatario SDI deve essere 7 caratteri alfanumerici (ricevuto '{sdi}', lunghezza {len(sdi)})."))
    elif not pec:
        errors.append(_err("E_SDI_PEC_MISSING", "cliente.codice_sdi",
                           "Cliente senza Codice destinatario SDI né PEC: lo SdI non potrebbe recapitare la fattura."))

    if pec and not EMAIL_RE.fullmatch(pec):
        errors.append(_err("E_PEC_FORMAT", "cliente.pec",
                           f"PEC con formato non valido: '{pec}'."))

    # ---- Documento ----
    numero = _clean(fattura.get("numero"))
    if not numero:
        errors.append(_err("E_DOC_NUMERO_MISSING", "fattura.numero",
                           "Numero documento mancante."))
    elif not NUMERO_DOC_RE.fullmatch(numero):
        errors.append(_err("E_DOC_NUMERO_FORMAT", "fattura.numero",
                           f"Numero documento contiene caratteri non ammessi: '{numero}'."))

    data = _clean(fattura.get("data"))
    if not data:
        errors.append(_err("E_DOC_DATA_MISSING", "fattura.data",
                           "Data documento mancante."))
    else:
        # Accetta sia YYYY-MM-DD che ISO datetime completo (es. '2026-05-15T06:25:43Z' o '2026-05-15 06:25:43.162')
        if not DATE_ISO_RE.match(data[:10]) or len(data) < 10:
            errors.append(_err("E_DOC_DATA_FORMAT", "fattura.data",
                               f"Data documento non in formato ISO YYYY-MM-DD: '{data}'."))

    # Coerenza totali
    try:
        imp = round(float(fattura.get("imponibile", 0) or 0), 2)
        iva = round(float(fattura.get("iva", 0) or 0), 2)
        tot = round(float(fattura.get("totale", 0) or 0), 2)
    except (TypeError, ValueError):
        errors.append(_err("E_DOC_TOTALI_NUMERIC", "fattura.totale",
                           "Importi documento non numerici."))
    else:
        if abs(round(imp + iva, 2) - tot) > 0.05:
            errors.append(_err("E_DOC_TOTALE_COERENZA", "fattura.totale",
                               f"Totale documento ({tot:.2f}) non coerente con imponibile + IVA ({imp + iva:.2f})."))
        if tot < 0:
            errors.append(_err("E_DOC_TOTALE_NEGATIVO", "fattura.totale",
                               f"Totale documento negativo: {tot:.2f}."))

    return errors


def _validate_address(entity: Dict[str, Any], errors: List[Dict[str, str]],
                      *, prefix: str, role: str) -> None:
    """Verifica che CAP/Comune/Provincia siano formalmente validi."""
    cap = _clean(entity.get("cap"))
    comune = _clean(entity.get("comune"))
    provincia = _clean(entity.get("provincia")).upper()
    indirizzo = _clean(entity.get("indirizzo"))

    if not indirizzo:
        errors.append(_err("E_ADDR_INDIRIZZO_MISSING", f"{prefix}.indirizzo",
                           f"Indirizzo {role} mancante."))
    if not cap:
        errors.append(_err("E_ADDR_CAP_MISSING", f"{prefix}.cap",
                           f"CAP {role} mancante."))
    elif not CAP_RE.fullmatch(cap):
        errors.append(_err("E_ADDR_CAP_FORMAT", f"{prefix}.cap",
                           f"CAP {role} non valido: '{cap}' (atteso 5 cifre)."))
    if not comune:
        errors.append(_err("E_ADDR_COMUNE_MISSING", f"{prefix}.comune",
                           f"Comune {role} mancante."))
    if not provincia:
        errors.append(_err("E_ADDR_PROVINCIA_MISSING", f"{prefix}.provincia",
                           f"Provincia {role} mancante (sigla 2 lettere)."))
    elif not PROVINCIA_RE.fullmatch(provincia):
        errors.append(_err("E_ADDR_PROVINCIA_FORMAT", f"{prefix}.provincia",
                           f"Provincia {role} non valida: '{provincia}' (atteso 2 lettere maiuscole)."))
