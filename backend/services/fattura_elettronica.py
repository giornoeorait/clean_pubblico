"""Fattura Elettronica XML generator (v1.2.2 FPR12 — fattura privata B2B/B2C).

Builds a SDI-compliant XML invoice from a CleanTec fattura document.
Note: FPR12 = formato per privati (B2B/B2C). FPA12 = formato per PA.

Usage:
    from services.fattura_elettronica import build_fattura_elettronica_xml
    xml_bytes, filename = build_fattura_elettronica_xml(fattura, company, cliente, ddts)
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Dict, Any, List, Tuple
from xml.sax.saxutils import escape


NS = "http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA = "http://www.fatturapa.gov.it/sdi/fatturapa/v1.2/Schema_del_file_xml_FatturaPA_versione_1.2.2.xsd"


# --------------------------------------------------------------- Sanitizers

# Caratteri di controllo Unicode (LTR, RTL, BOM, ZWSP, ZWJ, etc.) che spesso
# vengono incollati da PDF/Word e che lo SDI rifiuta nei campi anagrafici.
_INVISIBLE_CHARS = (
    "\u200b\u200c\u200d\u200e\u200f"  # zero-width + LTR/RTL marks
    "\u202a\u202b\u202c\u202d\u202e"  # directional embedding/override
    "\u2060\u2061\u2062\u2063\u2064"  # word joiners
    "\ufeff\u00a0"                       # BOM + nbsp
)


def _clean(s: Any) -> str:
    """Remove invisible/control unicode chars and normalize whitespace.
    Applied to every XML text value to avoid SDI rejection of pasted strings.
    """
    if s is None:
        return ""
    txt = str(s)
    # Remove invisible/directional chars
    for ch in _INVISIBLE_CHARS:
        txt = txt.replace(ch, "")
    # Remove other Unicode control category (Cf, Cc) except TAB/LF/CR
    txt = "".join(
        c for c in txt
        if unicodedata.category(c)[0] != "C" or c in "\t\n\r"
    )
    # Normalize whitespace (LF/CR → space, collapse multiple spaces)
    txt = re.sub(r"[\r\n]+", " ", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def _clean_alnum(s: Any, max_len: int = 0) -> str:
    """Keep only [A-Z0-9] (uppercase). Used for SDI codes (P.IVA, CF persona giuridica, codice SDI)."""
    txt = _clean(s).upper()
    txt = re.sub(r"[^A-Z0-9]", "", txt)
    return txt[:max_len] if max_len else txt


def _clean_cf(s: Any) -> str:
    """Codice Fiscale italiano: 16 alfanumerici (persona fisica) o 11 cifre (persona giuridica)."""
    cf = _clean_alnum(s)
    if len(cf) == 11:
        return cf  # P.IVA used as CF
    if len(cf) == 16:
        return cf
    return cf[:16]  # accept partial, will be rejected by SDI if invalid


# --------------------------------------------------------------- Address parser

PROVINCIA_RE = re.compile(r"\b([A-Z]{2})\b")
CAP_RE = re.compile(r"\b(\d{5})\b")


def parse_address(indirizzo: str, cap_field: str = "") -> Dict[str, str]:
    """Best-effort parse of a free-form Italian address string.

    Examples handled:
      "Via Roma, 12, 20100 Milano (MI)"            → split by comma
      "00054 Via Torre Clementina, 80, Fiumicino, RM, Italia"
      "03100 Via degli Etruschi, 7, Frosinone, FR, Italia"
      "Sede Legale: Via della Foce 12 — 00054 Fiumicino RM"

    Strategy:
      1. Clean preambles ('Sede Legale:', etc).
      2. Split by comma and strip the trailing "Italia".
      3. The CAP (5 digits) is extracted and removed from any token.
      4. Provincia = last 2-letter uppercase token (not IT).
      5. Comune = the non-numeric token that does NOT contain street keywords
         ("via", "viale", "piazza", "corso", "vicolo", "largo", "str.", etc).
      6. Indirizzo = the street tokens (those containing street keywords or numbers).
    """
    raw = _clean(indirizzo)
    # Rimuovi preamboli tipo "Sede Legale:", "Sede Operativa:"
    raw = re.sub(r"(?i)\b(sede\s+legale|sede\s+operativa|sede)\s*:?\s*", "", raw)
    # Se l'utente ha incollato ragione sociale prima dell'indirizzo, tronchiamo
    # alla prima street keyword. Esempio: "WATERWELL FCO Cleaning Tech SRL Via della Foce"
    # → tronca a "Via della Foce ...".
    STREET_KW_RE = re.compile(
        r"\b(via|viale|v\.le|piazza|p\.zza|piazzale|corso|c\.so|vicolo|"
        r"largo|strada|str\.|lungomare|lungotevere|salita|discesa|"
        r"circonvallazione|borgo|contrada|loc\.|località)\b",
        re.IGNORECASE,
    )
    m = STREET_KW_RE.search(raw)
    if m and m.start() > 0:
        raw = raw[m.start():].strip()
    cap = _clean(cap_field)
    provincia = ""
    nazione = "IT"

    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if parts and parts[-1].upper() in {"ITALIA", "ITALY", "IT"}:
        parts = parts[:-1]
        nazione = "IT"

    # CAP detection (field first, then any part — and strip it from the part)
    if not cap:
        for i, p in enumerate(parts):
            m = CAP_RE.search(p)
            if m:
                cap = m.group(1)
                parts[i] = CAP_RE.sub("", p).strip(" ,-")
                break
    else:
        # CAP è già nel campo: rimuoviamolo dalle parti se compare
        for i, p in enumerate(parts):
            if cap in p:
                parts[i] = p.replace(cap, "").strip(" ,-")

    # Provincia detection (from the end)
    for i in range(len(parts) - 1, -1, -1):
        m = PROVINCIA_RE.search(parts[i])
        if m and m.group(1) not in {"IT", "ITALIA"}:
            provincia = m.group(1)
            # rimuovi la sigla dalla parte (se è da sola la parte sparisce)
            parts[i] = re.sub(rf"\b{provincia}\b", "", parts[i]).strip(" ,-")
            if not parts[i]:
                parts.pop(i)
            break

    # Rimuovi parti vuote
    parts = [p for p in parts if p]

    # Classifica le parti rimanenti in "street" vs "comune"
    STREET_KW = (
        "via", "viale", "v.le", "piazza", "p.zza", "piazzale", "corso", "c.so",
        "vicolo", "largo", "strada", "str.", "lungomare", "lungotevere",
        "salita", "discesa", "circonvallazione", "borgo", "contrada"
    )

    def looks_like_street(p: str) -> bool:
        low = p.lower()
        if any(low.startswith(kw + " ") or low == kw or (" " + kw + " ") in (" " + low + " ") for kw in STREET_KW):
            return True
        # parts che contengono cifre (numero civico) → street
        if re.search(r"\d", p):
            return True
        return False

    street_parts = [p for p in parts if looks_like_street(p)]
    comune_parts = [p for p in parts if not looks_like_street(p)]

    indirizzo_out = ", ".join(street_parts).strip(" ,-")
    comune_out = (comune_parts[0] if comune_parts else "")

    # Se non abbiamo capito niente, prendi la prima parte come indirizzo e
    # l'ultima come comune.
    if not indirizzo_out and parts:
        indirizzo_out = parts[0]
    if not comune_out and len(parts) > 1:
        comune_out = parts[-1]

    return {
        "indirizzo": (indirizzo_out or "—")[:60],
        "cap":       cap or "00000",
        "comune":    (comune_out or "Sconosciuto")[:60],
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
    """Estrae la P.IVA italiana (11 cifre). Rimuove prefisso 'IT' eventualmente
    presente quando l'utente la inserisce in formato VAT EU (es. 'IT17400491001').
    """
    raw = _clean(piva).upper()
    # Rimuovi prefisso IT seguito da cifre
    m = re.match(r"^IT\s*(\d.*)$", raw)
    if m:
        raw = m.group(1)
    # Tieni solo cifre, max 11
    digits = re.sub(r"\D+", "", raw)
    return digits[:11]


def safe_numero(num: str) -> str:
    """Sanitize document number: keep alphanumeric, '/', '-', '.'. Strip invisible chars."""
    s = _clean(num).upper()
    return re.sub(r"[^A-Z0-9/\-.]", "", s)[:20]


def _e(v: Any) -> str:
    """Sanitize + XML-escape a text value."""
    return escape(_clean(v))


def _tag(name: str, value: Any) -> str:
    """Render a leaf element only if value is non-empty."""
    s = "" if value is None else str(value).strip()
    if not s:
        return ""
    return f"<{name}>{_e(s)}</{name}>"


# --------------------------------------------------------------- Main builder

def build_fattura_elettronica_xml(
    fattura: Dict[str, Any],
    company: Dict[str, Any],
    cliente: Dict[str, Any],
    ddts: List[Dict[str, Any]],
) -> Tuple[bytes, str]:
    """Generate the full Fattura Elettronica XML (FPR12 — privati) for a fattura.

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
    cliente_cf = _clean_cf(cliente.get("codice_fiscale"))
    if not cliente_piva and not cliente_cf:
        raise ValueError("Cliente senza P.IVA né Codice Fiscale: impossibile generare XML PA")

    # ----- Header components
    progressivo = progressivo_invio(fattura.get("numero", ""))
    numero_doc = safe_numero(fattura.get("numero", ""))
    codice_dest = _clean_alnum(cliente.get("codice_sdi"), max_len=7) or "0000000"
    if len(codice_dest) != 7:
        codice_dest = "0000000"
    pec_dest = _clean(cliente.get("pec"))

    # ----- Addresses
    # Se sono valorizzati i campi separati (cap/comune/provincia), li usiamo
    # come fonte primaria. Altrimenti facciamo fallback al parser dell'indirizzo libero.
    def resolve_addr(entity: Dict[str, Any]) -> Dict[str, str]:
        cap_v = _clean(entity.get("cap"))
        comune_v = _clean(entity.get("comune"))
        prov_v = _clean(entity.get("provincia")).upper()[:2]
        if comune_v and cap_v:
            # campi separati valorizzati: usali (con sanitization indirizzo)
            indir_raw = _clean(entity.get("indirizzo") or "")
            # Rimuovi preamboli e ragione sociale dall'indirizzo
            indir_raw = re.sub(r"(?i)\b(sede\s+legale|sede\s+operativa|sede)\s*:?\s*", "", indir_raw)
            STREET_KW = re.compile(
                r"\b(via|viale|v\.le|piazza|p\.zza|piazzale|corso|c\.so|vicolo|"
                r"largo|strada|str\.|lungomare|lungotevere|salita|discesa|"
                r"circonvallazione|borgo|contrada|loc\.|località)\b",
                re.IGNORECASE,
            )
            m = STREET_KW.search(indir_raw)
            if m and m.start() > 0:
                indir_raw = indir_raw[m.start():].strip()
            # se l'indirizzo libero conteneva CAP/comune/provincia, rimuovili
            indir_raw = re.sub(rf"\b{re.escape(cap_v)}\b", "", indir_raw)
            indir_raw = re.sub(rf"\b{re.escape(comune_v)}\b", "", indir_raw, flags=re.IGNORECASE)
            if prov_v:
                indir_raw = re.sub(rf"\b{prov_v}\b", "", indir_raw)
            indir_raw = re.sub(r"\s*,\s*,\s*", ", ", indir_raw)
            indir_raw = indir_raw.strip(" ,-").strip()
            return {
                "indirizzo": (indir_raw or "—")[:60],
                "cap": cap_v[:5],
                "comune": comune_v[:60],
                "provincia": prov_v,
                "nazione": (_clean(entity.get("nazione")) or "IT")[:2].upper(),
            }
        # fallback parser
        return parse_address(entity.get("indirizzo", ""), entity.get("cap", ""))

    cedente_addr = resolve_addr(company)
    cessionario_addr = resolve_addr(cliente)

    regime_fiscale = _clean_alnum(company.get("regime_fiscale") or "RF01")[:4] or "RF01"
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
    # IMPORTANT: dichiariamo il namespace SDI sia con prefisso `p:` sul root
    # SIA come default namespace (`xmlns="..."`) così TUTTI i figli ricadono
    # automaticamente nel namespace SDI come richiesto dallo schema XSD
    # (elementFormDefault="qualified"). Senza il default namespace gli
    # elementi senza prefisso risulterebbero in "no-namespace" e lo SDI
    # rifiuterebbe il file.
    fname = f"IT{company_piva}_{progressivo}.xml"
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<p:FatturaElettronica versione="FPR12" '
        f'xmlns="{NS}" '
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
        + _tag("CodiceFiscale", _clean_cf(company.get("codice_fiscale")))
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
        f"<Numero>{_e(numero_doc)}</Numero>"
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
            + (f"<IBAN>{_e(_clean_alnum(company.get('iban')))}</IBAN>" if company.get("iban") else "")
            + "</DettaglioPagamento>"
            "</DatiPagamento>"
        )
        + "</FatturaElettronicaBody>"
        "</p:FatturaElettronica>"
    )

    return xml.encode("utf-8"), fname
