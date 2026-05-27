"""Validazione XSD ufficiale FatturaPA + mappatura codici errore SdI.

Carica lo schema `Schema_VFPR12.xsd` da `services/xsd/` una volta sola e fornisce
una funzione `validate_xml_against_xsd` che restituisce la lista di errori XSD
(o lista vuota se l'XML è valido).
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any, Dict, List

from lxml import etree

logger = logging.getLogger(__name__)

_XSD_DIR = os.path.join(os.path.dirname(__file__), "xsd")
_XSD_MAIN = os.path.join(_XSD_DIR, "Schema_VFPR12.xsd")


@lru_cache(maxsize=1)
def _load_schema() -> etree.XMLSchema:
    """Carica e cache lo schema XSD FatturaPA v1.2."""
    if not os.path.exists(_XSD_MAIN):
        raise FileNotFoundError(f"Schema XSD non trovato: {_XSD_MAIN}")
    parser = etree.XMLParser(load_dtd=False, no_network=True)
    with open(_XSD_MAIN, "rb") as f:
        # parse() risolve `xs:import schemaLocation="xmldsig-core-schema.xsd"`
        # relativamente alla cartella dello XSD principale
        schema_doc = etree.parse(f, parser, base_url=_XSD_MAIN)
    return etree.XMLSchema(schema_doc)


def validate_xml_against_xsd(xml_bytes: bytes) -> List[Dict[str, Any]]:
    """Valida l'XML contro lo XSD ufficiale FatturaPA.

    Ritorna una lista di errori in forma:
      [{ "line": int, "column": int, "message": str, "path": str }]
    Lista vuota = XML valido.
    """
    try:
        schema = _load_schema()
    except Exception as e:
        logger.error(f"Impossibile caricare lo schema XSD: {e}")
        return [{
            "line": 0, "column": 0, "path": "/",
            "message": f"Schema XSD non disponibile sul server: {e}",
        }]

    parser = etree.XMLParser(no_network=True, resolve_entities=False)
    try:
        doc = etree.fromstring(xml_bytes, parser)
    except etree.XMLSyntaxError as e:
        return [{
            "line": e.lineno or 0,
            "column": getattr(e, "offset", 0) or 0,
            "path": "/",
            "message": f"XML mal formato: {e.msg}",
        }]

    if schema.validate(doc):
        return []

    return [
        {
            "line": err.line or 0,
            "column": err.column or 0,
            "path": err.path or "/",
            "message": err.message or "Errore di validazione",
        }
        for err in schema.error_log
    ]


# ---------------------------------------------------------------------------
# Mappa codici errore SdI ufficiali → messaggi italiani user-friendly.
# Fonte: "Codici errore - Specifiche tecniche operatori SdI v1.7.1"
# ---------------------------------------------------------------------------
SDI_ERROR_MAP: Dict[str, str] = {
    "00001": "Nome file non conforme (es. ITxxxxxxxxxxx_NNNNN.xml).",
    "00002": "Nome file duplicato (già inviato in precedenza).",
    "00003": "Le dimensioni del file superano i limiti consentiti.",
    "00100": "Certificato di firma scaduto o assente.",
    "00101": "Certificato di firma revocato.",
    "00102": "CA (Autorità di certificazione) della firma non affidabile.",
    "00103": "La firma del file XML non risulta valida.",
    "00104": "L'algoritmo di firma utilizzato non è ammesso.",
    "00105": "Riferimento temporale (data firma) non valido.",
    "00106": "Contenuto firmato non corrispondente al file XML.",
    "00200": "File XML non conforme allo schema XSD.",
    "00201": "Errore di tipo XSD (vedere dettagli in fondo).",
    "00300": "Identificativo IdFiscaleIVA del trasmittente non valido.",
    "00301": "Partita IVA del trasmittente non valida.",
    "00302": "Codice fiscale del trasmittente non valido.",
    "00303": "Identificativo Paese ProgressivoInvio non valido.",
    "00305": "Codice fiscale CedentePrestatore non valido.",
    "00306": "Codice destinatario diverso da 7 caratteri.",
    "00311": "Codice destinatario PA diverso da 6 caratteri.",
    "00320": "Partita IVA del CedentePrestatore non valida.",
    "00321": "Partita IVA del CessionarioCommittente non valida.",
    "00322": "Codice fiscale CessionarioCommittente non valido.",
    "00323": "Codice fiscale del CedentePrestatore non corretto.",
    "00325": "Codice destinatario incompatibile con FormatoTrasmissione.",
    "00400": "L'aliquota IVA delle linee non corrisponde a quella indicata nei dati di riepilogo.",
    "00401": "Non corrispondenza tra Natura e Aliquota IVA.",
    "00403": "Data fattura successiva alla data di trasmissione.",
    "00404": "Importo totale documento non corrisponde a imponibile + IVA.",
    "00411": "Ritenuta indicata senza i Dati Ritenuta valorizzati.",
    "00413": "Natura non ammessa con aliquota IVA diversa da zero.",
    "00415": "Imposta indicata con natura non IVA.",
    "00417": "P.IVA e Codice Fiscale del CessionarioCommittente non valorizzati.",
    "00418": "Data fattura non compatibile con la data di trasmissione.",
    "00419": "Riepilogo IVA non presente.",
    "00420": "ImponibileImporto non coerente con i totali delle linee.",
    "00421": "Imposta non coerente con imponibile × aliquota.",
    "00422": "Descrizione linea non valorizzata.",
    "00423": "PrezzoTotale non coerente con PrezzoUnitario × Quantità.",
    "00424": "Data non valida o non plausibile.",
    "00425": "Numero fattura non valorizzato.",
    "00426": "Tipo documento non riconosciuto.",
    "00427": "Modalità di pagamento non riconosciuta.",
    "00428": "Causale di pagamento non corretta.",
    "00429": "Natura non valida.",
    "00430": "Aliquota IVA non valorizzata correttamente.",
    "00432": "Sezionale FatturaElettronicaBody non corretto.",
    "00437": "TipoCassa non valido.",
    "00471": "Una fattura senza riepilogo per quell'aliquota.",
    "00472": "Sezione Allegati senza nome o contenuto.",
    "00473": "Allegato con base64 non valido.",
    "00474": "PEC/SDI non in linea con FormatoTrasmissione.",
    "00475": "Riferimento DDT non valorizzato correttamente.",
    "00476": "DataDDT successiva a Data fattura.",
}


def translate_sdi_error(code: str) -> str:
    """Restituisce un messaggio leggibile per un codice errore SdI."""
    code = (code or "").strip()
    return SDI_ERROR_MAP.get(code, f"Errore SdI sconosciuto ({code})")
