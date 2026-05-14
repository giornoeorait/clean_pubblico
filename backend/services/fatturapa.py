"""FatturaPA XML generator (v1.2.2 FPR12 — fattura privata B2B).

Builds a SDI-compliant XML invoice from a CleanTec fattura document.

Usage:
    from services.fatturapa import build_fattura_pa_xml
    xml_bytes, filename = await build_fattura_pa_xml(fattura, company, cliente, ddts)
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, Any, List, Tuple
from xml.sax.saxutils import escape


NS = "http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA = "http://www.fatturapa.gov.it/sdi/fatturapa/v1.2/Schema_del_file_xml_FatturaPA_versione_1.2.2.xsd"


# --------------------------------------------------------------- Address parser

PROVINCIA_RE = re.compile(r"\b([A-Z]{2})\b")
CAP_RE = re.compile(r"\b(\d{5})\b")


def parse_address(indirizzo: str, cap_field: str = "") -> Dict[str, str]:
    """Best-effort parse of a free-form Italian address string.

    Expected formats include:
      "Via Roma, 12, 20100 Milano (MI)"
      "Via Roma 12, Milano MI 20100"
      "00054 Via Torre Clementina, 80, Fiumicino, RM, Italia"
    Returns dict with keys: indirizzo, cap, comune, provincia, nazione (default IT).
    """
    s = (indirizzo or "").strip()
    parts = [p.strip() for p in s.split(",") if p.strip()]
    cap = (cap_field or "").strip()
    provincia = ""
    comune = ""
    nazione = "IT"

    # Look for CAP in the field first, then in any part
    if not cap:
        for p in parts:
            m = CAP_RE.search(p)
            if m:
                cap = m.group(1)
                break

    # Look for provincia (2-letter uppercase token)
    for p in reversed(parts):
        m = PROVINCIA_RE.search(p)
        if m and m.group(1) not in {"IT", "ITALIA"}:
            provincia = m.group(1)
            break

    # Detect "Italia"/"IT" at the end → nazione
    if parts and parts[-1].upper() in {"ITALIA", "ITALY", "IT"}:
        parts = parts[:-1]

    # Heuristic: the part containing the provincia or CAP often also contains the comune
    for p in parts:
        # Strip provincia + CAP from the part to leave the comune
        candidate = p
        if cap:
            candidate = CAP_RE.sub("", candidate)
        if provincia:
            candidate = re.sub(rf"\b{provincia}\b", "", candidate)
        candidate = candidate.strip(" ,()-")
        if candidate and not any(ch.isdigit() for ch in candidate) and len(candidate) > 1:
            comune = candidate
            break

    # The first 1–2 parts make up the street
    if comune:
        street_parts = [p for p in parts if comune not in p]
    else:
        street_parts = parts[:2]
    street = ", ".join(street_parts).strip(" ,") or s

    # Fallbacks (mandatory in FatturaPA)
    return {
        "indirizzo": street[:60] or "—",
        "cap":       cap or "00000",
        "comune":    (comune or "Sconosciuto")[:60],
        "provincia": provincia or "",
        "nazione":   nazione,
    }


# --------------------------------------------------------------- Number / date

def fmt_money(v: float) -> str:
    return f"{round(float(v or 0), 2):.2f}"


def fmt_qty(v: float) -> str:
    return f"{round(float(v or 0), 2):.2f}"


def fmt_date(dt: Any) -> str:
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d")
    if isinstance(dt, str):
        try:
            return datetime.fromisoformat(dt.replace("Z", "+00:00")).strftime("%Y-%m-%d")
        except Exception:
            return dt[:10]
    return datetime.utcnow().strftime("%Y-%m-%d")


def progressivo_invio(numero_fattura: str) -> str:
    """Extract the progressivo from 'FT-2026-00046' or 'FT-2026-00046/L' → '00046'.

    Looks for the LAST run of digits in the standard PREFIX-YEAR-SEQ format
    (year is 4 digits, seq follows after the second hyphen).
    """
    s = numero_fattura or ""
    # Match: -YYYY-NNNNN  (4-digit year, then digits for seq)
    m = re.search(r"-\d{4}-(\d{1,8})", s)
    if m:
        return m.group(1).zfill(5)
    # Fallback: last numeric run in the string
    nums = re.findall(r"\d+", s)
    return (nums[-1] if nums else "00001").zfill(5)


def safe_partita_iva(piva: str) -> str:
    return re.sub(r"\D+", "", piva or "")[:11]


def _e(v: Any) -> str:
    """Escape XML text and strip newlines/control chars."""
    s = "" if v is None else str(v)
    s = s.replace("\r", " ").replace("\n", " ").strip()
    return escape(s)


def _tag(name: str, value: Any) -> str:
    """Render a leaf element only if value is non-empty."""
    s = "" if value is None else str(value).strip()
    if not s:
        return ""
    return f"<{name}>{_e(s)}</{name}>"


# --------------------------------------------------------------- Main builder

def build_fattura_pa_xml(
    fattura: Dict[str, Any],
    company: Dict[str, Any],
    cliente: Dict[str, Any],
    ddts: List[Dict[str, Any]],
) -> Tuple[bytes, str]:
    """Generate the full FatturaPA XML for a fattura.

    Returns (xml_bytes, filename).
    Filename convention: ITxxxxxxxxxxx_NNNNN.xml
    """
    # ----- Validations
    company_piva = safe_partita_iva(company.get("partita_iva"))
    if not company_piva:
        raise ValueError("Partita IVA azienda mancante in Anagrafica")
    if not company.get("ragione_sociale"):
        raise ValueError("Ragione sociale azienda mancante in Anagrafica")
    if not company.get("indirizzo"):
        raise ValueError("Indirizzo azienda mancante in Anagrafica")
    if not cliente.get("ragione_sociale"):
        raise ValueError("Ragione sociale cliente mancante")

    cliente_piva = safe_partita_iva(cliente.get("partita_iva"))
    cliente_cf = (cliente.get("codice_fiscale") or "").strip()
    if not cliente_piva and not cliente_cf:
        raise ValueError("Cliente senza P.IVA né Codice Fiscale: impossibile generare XML PA")

    # ----- Header components
    progressivo = progressivo_invio(fattura.get("numero", ""))
    codice_dest = (cliente.get("codice_sdi") or "").strip().upper() or "0000000"
    if len(codice_dest) not in (7,):
        codice_dest = "0000000"
    pec_dest = (cliente.get("pec") or "").strip()

    # ----- Addresses
    cedente_addr = parse_address(company.get("indirizzo", ""), company.get("cap", ""))
    cessionario_addr = parse_address(cliente.get("indirizzo", ""), cliente.get("cap", ""))

    regime_fiscale = (company.get("regime_fiscale") or "RF01").strip().upper()
    iva_pct = float(fattura.get("iva_pct") or 22.0)
    totale_doc = float(fattura.get("totale") or 0.0)
    imponibile = float(fattura.get("imponibile") or 0.0)
    imposta = float(fattura.get("iva") or round(imponibile * iva_pct / 100, 2))

    # ----- Line items: one per DDT
    lines_xml: List[str] = []
    if ddts:
        for idx, d in enumerate(ddts, start=1):
            d_num = d.get("numero") or f"DDT-{idx}"
            d_date = fmt_date(d.get("data"))
            d_imp = float(d.get("imponibile") or 0.0)
            descr = f"Servizi lavanderia industriale - DDT {d_num} del {d_date}"
            lines_xml.append(
                "<DettaglioLinee>"
                f"<NumeroLinea>{idx}</NumeroLinea>"
                f"<Descrizione>{_e(descr)}</Descrizione>"
                f"<Quantita>1.00</Quantita>"
                f"<PrezzoUnitario>{fmt_money(d_imp)}</PrezzoUnitario>"
                f"<PrezzoTotale>{fmt_money(d_imp)}</PrezzoTotale>"
                f"<AliquotaIVA>{fmt_money(iva_pct)}</AliquotaIVA>"
                "</DettaglioLinee>"
            )
    else:
        # Fallback: a single aggregated line
        lines_xml.append(
            "<DettaglioLinee>"
            "<NumeroLinea>1</NumeroLinea>"
            f"<Descrizione>Servizi lavanderia industriale</Descrizione>"
            f"<Quantita>1.00</Quantita>"
            f"<PrezzoUnitario>{fmt_money(imponibile)}</PrezzoUnitario>"
            f"<PrezzoTotale>{fmt_money(imponibile)}</PrezzoTotale>"
            f"<AliquotaIVA>{fmt_money(iva_pct)}</AliquotaIVA>"
            "</DettaglioLinee>"
        )

    # ----- Riepilogo IVA (one block per aliquota — here always one)
    riepilogo_xml = (
        "<DatiRiepilogo>"
        f"<AliquotaIVA>{fmt_money(iva_pct)}</AliquotaIVA>"
        f"<ImponibileImporto>{fmt_money(imponibile)}</ImponibileImporto>"
        f"<Imposta>{fmt_money(imposta)}</Imposta>"
        f"<EsigibilitaIVA>I</EsigibilitaIVA>"
        "</DatiRiepilogo>"
    )

    # ----- Cessionario IdFiscaleIVA OR CodiceFiscale
    cessionario_ident = ""
    if cliente_piva:
        cessionario_ident = (
            "<IdFiscaleIVA>"
            f"<IdPaese>IT</IdPaese>"
            f"<IdCodice>{_e(cliente_piva)}</IdCodice>"
            "</IdFiscaleIVA>"
        )
    if cliente_cf:
        cessionario_ident += f"<CodiceFiscale>{_e(cliente_cf)}</CodiceFiscale>"

    # ----- Build the XML
    fname = f"IT{company_piva}_{progressivo}.xml"
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<p:FatturaElettronica versione="FPR12" '
        f'xmlns:p="{NS}" '
        f'xmlns:xsi="{NS_XSI}" '
        f'xsi:schemaLocation="{NS} {SCHEMA}">'

        # ---------- HEADER ----------
        "<FatturaElettronicaHeader>"
        "<DatiTrasmissione>"
        "<IdTrasmittente>"
        "<IdPaese>IT</IdPaese>"
        f"<IdCodice>{_e(company_piva)}</IdCodice>"
        "</IdTrasmittente>"
        f"<ProgressivoInvio>{_e(progressivo)}</ProgressivoInvio>"
        "<FormatoTrasmissione>FPR12</FormatoTrasmissione>"
        f"<CodiceDestinatario>{_e(codice_dest)}</CodiceDestinatario>"
        + (f"<PECDestinatario>{_e(pec_dest)}</PECDestinatario>" if codice_dest == "0000000" and pec_dest else "")
        + "</DatiTrasmissione>"

        # CedentePrestatore (chi emette la fattura — la nostra azienda)
        "<CedentePrestatore>"
        "<DatiAnagrafici>"
        "<IdFiscaleIVA>"
        "<IdPaese>IT</IdPaese>"
        f"<IdCodice>{_e(company_piva)}</IdCodice>"
        "</IdFiscaleIVA>"
        + _tag("CodiceFiscale", company.get("codice_fiscale"))
        + "<Anagrafica>"
        f"<Denominazione>{_e(company.get('ragione_sociale'))}</Denominazione>"
        "</Anagrafica>"
        f"<RegimeFiscale>{_e(regime_fiscale)}</RegimeFiscale>"
        "</DatiAnagrafici>"
        "<Sede>"
        f"<Indirizzo>{_e(cedente_addr['indirizzo'])}</Indirizzo>"
        f"<CAP>{_e(cedente_addr['cap'])}</CAP>"
        f"<Comune>{_e(cedente_addr['comune'])}</Comune>"
        + (f"<Provincia>{_e(cedente_addr['provincia'])}</Provincia>" if cedente_addr['provincia'] else "")
        + f"<Nazione>{_e(cedente_addr['nazione'])}</Nazione>"
        "</Sede>"
        "</CedentePrestatore>"

        # CessionarioCommittente (chi riceve la fattura — il cliente)
        "<CessionarioCommittente>"
        "<DatiAnagrafici>"
        + cessionario_ident
        + "<Anagrafica>"
        f"<Denominazione>{_e(cliente.get('ragione_sociale'))}</Denominazione>"
        "</Anagrafica>"
        "</DatiAnagrafici>"
        "<Sede>"
        f"<Indirizzo>{_e(cessionario_addr['indirizzo'])}</Indirizzo>"
        f"<CAP>{_e(cessionario_addr['cap'])}</CAP>"
        f"<Comune>{_e(cessionario_addr['comune'])}</Comune>"
        + (f"<Provincia>{_e(cessionario_addr['provincia'])}</Provincia>" if cessionario_addr['provincia'] else "")
        + f"<Nazione>{_e(cessionario_addr['nazione'])}</Nazione>"
        "</Sede>"
        "</CessionarioCommittente>"
        "</FatturaElettronicaHeader>"

        # ---------- BODY ----------
        "<FatturaElettronicaBody>"
        "<DatiGenerali>"
        "<DatiGeneraliDocumento>"
        "<TipoDocumento>TD01</TipoDocumento>"
        "<Divisa>EUR</Divisa>"
        f"<Data>{_e(fmt_date(fattura.get('data')))}</Data>"
        f"<Numero>{_e(fattura.get('numero'))}</Numero>"
        f"<ImportoTotaleDocumento>{fmt_money(totale_doc)}</ImportoTotaleDocumento>"
        + _tag("Causale", fattura.get("note"))
        + "</DatiGeneraliDocumento>"
        + "".join(
            "<DatiDDT>"
            f"<NumeroDDT>{_e(d.get('numero'))}</NumeroDDT>"
            f"<DataDDT>{_e(fmt_date(d.get('data')))}</DataDDT>"
            "</DatiDDT>"
            for d in ddts if d.get("numero")
        )
        + "</DatiGenerali>"

        "<DatiBeniServizi>"
        + "".join(lines_xml)
        + riepilogo_xml
        + "</DatiBeniServizi>"

        # DatiPagamento (opzionale ma utile)
        + (
            "<DatiPagamento>"
            "<CondizioniPagamento>TP02</CondizioniPagamento>"
            "<DettaglioPagamento>"
            "<ModalitaPagamento>MP05</ModalitaPagamento>"
            + (f"<DataScadenzaPagamento>{_e(fmt_date(fattura.get('scadenza')))}</DataScadenzaPagamento>" if fattura.get('scadenza') else "")
            + f"<ImportoPagamento>{fmt_money(totale_doc)}</ImportoPagamento>"
            + (f"<IBAN>{_e(company.get('iban'))}</IBAN>" if company.get("iban") else "")
            + "</DettaglioPagamento>"
            "</DatiPagamento>"
        )
        + "</FatturaElettronicaBody>"
        "</p:FatturaElettronica>"
    )

    return xml.encode("utf-8"), fname
