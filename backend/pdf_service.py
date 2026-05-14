"""PDF generation service for DDT and Fatture (ReportLab)."""
import io
from datetime import datetime
from typing import Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage,
)

from storage import get_object


INDACO = colors.HexColor("#4F46E5")
SLATE_800 = colors.HexColor("#1E293B")
SLATE_500 = colors.HexColor("#64748B")
SLATE_200 = colors.HexColor("#E2E8F0")


def _styles():
    ss = getSampleStyleSheet()
    st = {
        "h1": ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=18, textColor=SLATE_800, leading=22, spaceAfter=4),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=12, textColor=INDACO, leading=14, spaceAfter=2),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=8.5, textColor=SLATE_500, leading=11),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=10, textColor=SLATE_800, leading=13),
        "mono": ParagraphStyle("mono", fontName="Helvetica", fontSize=9, textColor=SLATE_800, leading=12),
        "right": ParagraphStyle("right", fontName="Helvetica", fontSize=10, textColor=SLATE_800, leading=13, alignment=2),
        "cortesia": ParagraphStyle("cortesia", fontName="Helvetica-Oblique", fontSize=9, textColor=INDACO, leading=11, spaceAfter=4),
    }
    return st


def _logo_flowable(logo_path: Optional[str], max_w_mm: float = 35, max_h_mm: float = 18):
    if not logo_path:
        return None
    try:
        data, _ = get_object(logo_path)
        img = RLImage(io.BytesIO(data))
        img.drawWidth = max_w_mm * mm
        img.drawHeight = max_h_mm * mm
        img._restrictSize(max_w_mm * mm, max_h_mm * mm)
        return img
    except Exception:
        return None


def _company_block(company: Dict, st: Dict) -> List:
    lines = []
    if company.get("nome"):
        lines.append(f"<b>{company['nome']}</b>")
    if company.get("ragione_sociale"):
        lines.append(company["ragione_sociale"])
    if company.get("indirizzo"):
        lines.append(company["indirizzo"])
    piva = company.get("partita_iva", "")
    cf = company.get("codice_fiscale", "")
    if piva or cf:
        bits = []
        if piva: bits.append(f"P.IVA {piva}")
        if cf and cf != piva: bits.append(f"CF {cf}")
        lines.append(" · ".join(bits))
    contacts = []
    if company.get("telefono"): contacts.append(f"Tel {company['telefono']}")
    if company.get("email"): contacts.append(company["email"])
    if contacts:
        lines.append(" · ".join(contacts))
    if company.get("pec"): lines.append(f"PEC: {company['pec']}")
    if company.get("iban"): lines.append(f"IBAN: {company['iban']}")
    if company.get("sito_web"): lines.append(company["sito_web"])
    return [Paragraph(l, st["small"]) for l in lines]


def _cliente_block(cliente: Dict, st: Dict) -> List:
    lines = []
    primary = (cliente.get("denominazione_struttura") or cliente.get("ragione_sociale") or "").strip()
    secondary = cliente.get("ragione_sociale", "")
    if primary:
        lines.append(f"<b>{primary}</b>")
    if secondary and secondary.strip() and secondary.strip() != primary:
        lines.append(f"<font size=8>{secondary}</font>")
    if cliente.get("indirizzo"):
        lines.append(cliente["indirizzo"])
    piva = cliente.get("partita_iva", "")
    cf = cliente.get("codice_fiscale", "")
    if piva: lines.append(f"P.IVA {piva}")
    if cf and cf != piva: lines.append(f"CF {cf}")
    if cliente.get("email"): lines.append(cliente["email"])
    if cliente.get("telefono"): lines.append(f"Tel {cliente['telefono']}")
    return [Paragraph(l, st["right"]) for l in lines]


def _rows_table(righe: List[Dict], st: Dict) -> Table:
    header = [
        Paragraph("<b>Codice</b>", st["body"]),
        Paragraph("<b>Descrizione</b>", st["body"]),
        Paragraph("<b>U.M.</b>", st["body"]),
        Paragraph("<b>Q.tà</b>", st["right"]),
        Paragraph("<b>P.U.</b>", st["right"]),
        Paragraph("<b>Totale</b>", st["right"]),
    ]
    data = [header]
    for r in righe:
        data.append([
            Paragraph(r.get("codice", ""), st["mono"]),
            Paragraph(r.get("descrizione", ""), st["body"]),
            Paragraph(r.get("unita_misura", "pz"), st["body"]),
            Paragraph(f"{r.get('quantita', 0):g}", st["right"]),
            Paragraph(f"€ {float(r.get('prezzo_unitario', 0)):.2f}", st["right"]),
            Paragraph(f"€ {float(r.get('totale', 0)):.2f}", st["right"]),
        ])
    t = Table(data, colWidths=[25*mm, 70*mm, 15*mm, 18*mm, 22*mm, 25*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, INDACO),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, SLATE_200),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _fmt_date(dt) -> str:
    if isinstance(dt, datetime):
        return dt.strftime("%d/%m/%Y")
    if isinstance(dt, str):
        try:
            return datetime.fromisoformat(dt.replace("Z", "+00:00")).strftime("%d/%m/%Y")
        except Exception:
            return dt
    return ""


def _build(elements: List) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm, topMargin=15*mm, bottomMargin=15*mm,
        title="CleanTec Document",
    )
    doc.build(elements)
    return buf.getvalue()


def _header_table(company: Dict, cliente: Dict, st: Dict) -> Table:
    logo = _logo_flowable(company.get("logo_path"))
    left_stack = ([logo] if logo else []) + _company_block(company, st)
    right_stack = _cliente_block(cliente, st)
    return Table(
        [[left_stack or [Paragraph(" ", st["body"])], right_stack or [Paragraph(" ", st["right"])]]],
        colWidths=[95*mm, 80*mm],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]),
    )


def generate_ddt_pdf(ddt: Dict, cliente: Dict, company: Dict) -> bytes:
    st = _styles()
    el: List = []
    el.append(_header_table(company, cliente, st))
    el.append(Spacer(1, 8*mm))
    el.append(Paragraph(f"<b>D.D.T. {ddt.get('numero', '')}</b>", st["h1"]))
    el.append(Paragraph(f"Data: {_fmt_date(ddt.get('data'))}", st["small"]))
    el.append(Spacer(1, 6*mm))
    el.append(_rows_table(ddt.get("righe", []), st))
    el.append(Spacer(1, 4*mm))
    el.append(Paragraph(
        f"<b>Imponibile: € {float(ddt.get('imponibile', 0)):.2f}</b>",
        ParagraphStyle("tot", parent=st["right"], fontName="Helvetica-Bold", fontSize=11),
    ))
    if ddt.get("note"):
        el.append(Spacer(1, 4*mm))
        el.append(Paragraph("<b>Note:</b>", st["body"]))
        el.append(Paragraph(ddt["note"], st["small"]))
    el.append(Spacer(1, 10*mm))
    el.append(Paragraph("Documento di trasporto — non valido ai fini fiscali.", st["small"]))
    return _build(el)


def generate_fattura_pdf(fattura: Dict, cliente: Dict, company: Dict, ddt_list: List[Dict]) -> bytes:
    st = _styles()
    el: List = []
    el.append(_header_table(company, cliente, st))
    el.append(Spacer(1, 2*mm))
    el.append(Paragraph("Fattura di cortesia", st["cortesia"]))
    el.append(Spacer(1, 4*mm))
    el.append(Paragraph(f"<b>Fattura {fattura.get('numero', '')}</b>", st["h1"]))
    el.append(Paragraph(f"Data: {_fmt_date(fattura.get('data'))}", st["small"]))
    el.append(Spacer(1, 6*mm))

    # Aggregate all rows from all DDT
    aggregated_rows: List[Dict] = []
    for d in ddt_list:
        for r in d.get("righe", []):
            aggregated_rows.append(r)
    el.append(_rows_table(aggregated_rows, st))
    el.append(Spacer(1, 4*mm))
    el.append(Paragraph(
        f"<b>Imponibile: € {float(fattura.get('imponibile', fattura.get('totale', 0))):.2f}</b>",
        ParagraphStyle("tot", parent=st["right"], fontName="Helvetica-Bold", fontSize=11),
    ))
    el.append(Paragraph(
        f"<b>Totale: € {float(fattura.get('totale', 0)):.2f}</b>",
        ParagraphStyle("tot2", parent=st["right"], fontName="Helvetica-Bold", fontSize=12, textColor=INDACO),
    ))
    el.append(Spacer(1, 6*mm))
    refs = ", ".join(d.get("numero", "") for d in ddt_list)
    if refs:
        el.append(Paragraph(f"<b>D.D.T. inclusi:</b> {refs}", st["small"]))
    if company.get("iban"):
        el.append(Spacer(1, 4*mm))
        el.append(Paragraph(f"<b>Bonifico su IBAN:</b> {company['iban']}", st["body"]))
    el.append(Spacer(1, 10*mm))
    el.append(Paragraph("Fattura di cortesia — non sostituisce la fattura elettronica SDI.", st["small"]))
    return _build(el)


def _offerta_rows_table(righe: List[Dict], st: Dict) -> Table:
    header = [
        Paragraph("<b>Codice</b>", st["body"]),
        Paragraph("<b>Descrizione</b>", st["body"]),
        Paragraph("<b>Q.tà</b>", st["right"]),
        Paragraph("<b>Listino</b>", st["right"]),
        Paragraph("<b>Sconto</b>", st["right"]),
        Paragraph("<b>Unit.</b>", st["right"]),
        Paragraph("<b>Totale</b>", st["right"]),
    ]
    data = [header]
    for r in righe:
        sc_perc = float(r.get("sconto_perc", 0) or 0)
        sc_eur = float(r.get("sconto_eur", 0) or 0)
        sconto_txt = ""
        if sc_perc:
            sconto_txt += f"-{sc_perc:g}%"
        if sc_eur:
            sconto_txt += f" -€{sc_eur:.2f}" if sconto_txt else f"-€{sc_eur:.2f}"
        data.append([
            Paragraph(r.get("codice", ""), st["mono"]),
            Paragraph(r.get("descrizione", ""), st["body"]),
            Paragraph(f"{r.get('quantita', 0):g} {r.get('unita_misura', 'pz')}", st["right"]),
            Paragraph(f"€ {float(r.get('prezzo_unitario', 0)):.2f}", st["right"]),
            Paragraph(sconto_txt or "—", st["right"]),
            Paragraph(f"€ {float(r.get('prezzo_finale', 0)):.2f}", st["right"]),
            Paragraph(f"<b>€ {float(r.get('totale', 0)):.2f}</b>", st["right"]),
        ])
    t = Table(data, colWidths=[22*mm, 50*mm, 20*mm, 22*mm, 18*mm, 20*mm, 23*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, INDACO),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, SLATE_200),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def generate_offerta_pdf(offerta: Dict, cliente: Dict, company: Dict, as_contratto: bool = False) -> bytes:
    st = _styles()
    el: List = []
    el.append(_header_table(company, cliente, st))
    el.append(Spacer(1, 6*mm))

    if as_contratto:
        numero = offerta.get("contratto_numero", "")
        title = f"<b>CONTRATTO DI SERVIZIO N. {numero}</b>"
        data_emissione = offerta.get("contratto_data") or offerta.get("data_creazione")
        subtitle = f"Origine: Offerta {offerta.get('numero','')} · Data attivazione: {_fmt_date(data_emissione)}"
    else:
        numero = offerta.get("numero", "")
        title = f"<b>OFFERTA COMMERCIALE {numero}</b>"
        subtitle = f"Data: {_fmt_date(offerta.get('data_creazione'))}"
        if offerta.get("data_scadenza"):
            subtitle += f" · Validità fino al {_fmt_date(offerta['data_scadenza'])}"

    el.append(Paragraph(title, ParagraphStyle("tit", parent=st["h1"], fontSize=16, textColor=INDACO)))
    el.append(Paragraph(subtitle, st["small"]))
    el.append(Spacer(1, 4*mm))

    # Meta block
    meta_data = [
        [Paragraph("<b>Durata contratto</b>", st["body"]),
         Paragraph(f"{offerta.get('durata_mesi', 12)} mesi", st["body"])],
    ]
    if offerta.get("listino_id"):
        meta_data.append([Paragraph("<b>Listino applicato</b>", st["body"]),
                          Paragraph("Riferimento interno", st["body"])])
    mt = Table(meta_data, colWidths=[45*mm, 130*mm], style=TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    el.append(mt)
    el.append(Spacer(1, 4*mm))

    # Items
    el.append(_offerta_rows_table(offerta.get("righe", []), st))
    el.append(Spacer(1, 3*mm))

    # Totals
    sconto_tot = float(offerta.get("sconto_totale", 0) or 0)
    if sconto_tot > 0:
        el.append(Paragraph(
            f"<b>Risparmio totale sconto: € {sconto_tot:.2f}</b>",
            ParagraphStyle("sc", parent=st["right"], fontName="Helvetica-Bold", fontSize=10, textColor=colors.HexColor("#059669")),
        ))
    el.append(Paragraph(
        f"<b>Imponibile: € {float(offerta.get('imponibile', 0)):.2f}</b>",
        ParagraphStyle("tot2", parent=st["right"], fontName="Helvetica-Bold", fontSize=12, textColor=INDACO),
    ))
    el.append(Spacer(1, 6*mm))

    # Termini & Condizioni
    termini = offerta.get("termini_condizioni", [])
    if termini:
        el.append(Paragraph("<b>Termini e Condizioni</b>", st["h2"]))
        el.append(Spacer(1, 2*mm))
        for t in termini:
            titolo = (t.get("titolo") or "").strip()
            testo = (t.get("testo") or "").strip()
            if titolo:
                el.append(Paragraph(f"<b>{titolo}</b>", st["body"]))
            if testo:
                el.append(Paragraph(testo.replace("\n", "<br/>"), st["small"]))
            el.append(Spacer(1, 2*mm))

    if offerta.get("note"):
        el.append(Spacer(1, 2*mm))
        el.append(Paragraph("<b>Note</b>", st["body"]))
        el.append(Paragraph(offerta["note"], st["small"]))

    el.append(Spacer(1, 10*mm))
    if as_contratto:
        # Signature boxes
        sig = Table([[
            Paragraph("<b>Per il Fornitore</b><br/><br/><br/>____________________<br/><font size=8>Timbro e firma</font>", st["body"]),
            Paragraph("<b>Per il Cliente</b><br/><br/><br/>____________________<br/><font size=8>Timbro e firma</font>", st["body"]),
        ]], colWidths=[85*mm, 85*mm])
        el.append(sig)
    else:
        el.append(Paragraph(
            "La presente offerta commerciale ha valore di proposta contrattuale. L'accettazione avviene con sottoscrizione o comunicazione scritta.",
            st["small"],
        ))
    return _build(el)



# ============== PDF REPORT (FASE 5 export) ==============

def _report_header(title: str, subtitle: str, company: Dict, st: Dict) -> List:
    logo = _logo_flowable(company.get("logo_url"))
    left = []
    if logo:
        left.append(logo)
    left.append(Paragraph(f"<b>{company.get('nome') or company.get('ragione_sociale') or 'Azienda'}</b>", st["body"]))
    if company.get("partita_iva"):
        left.append(Paragraph(f"P.IVA {company['partita_iva']}", st["small"]))
    tbl = Table([[left, [
        Paragraph(f"<b>{title}</b>", st["h1"]),
        Paragraph(subtitle, st["small"]),
        Paragraph(f"Generato il {datetime.now().strftime('%d/%m/%Y %H:%M')}", st["small"]),
    ]]], colWidths=[80*mm, 100*mm])
    tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, -1), "RIGHT")]))
    return [tbl, Spacer(1, 6*mm)]


def _kpi_strip(kpis: List[tuple], st: Dict) -> Table:
    row = []
    for label, value in kpis:
        cell = [
            Paragraph(f"<font color='#64748B' size=8>{label}</font>", st["small"]),
            Paragraph(f"<b><font size=13 color='#4F46E5'>{value}</font></b>", st["body"]),
        ]
        row.append(cell)
    t = Table([row], colWidths=[(180 / len(kpis)) * mm] * len(kpis))
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.4, SLATE_200),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, SLATE_200),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _simple_table(headers: List[str], rows: List[List[str]], st: Dict, col_widths: Optional[List[float]] = None) -> Table:
    data = [[Paragraph(f"<b>{h}</b>", st["small"]) for h in headers]]
    for r in rows:
        data.append([Paragraph(str(c), st["small"]) for c in r])
    if not col_widths:
        col_widths = [(180 / len(headers)) * mm] * len(headers)
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INDACO),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, SLATE_200),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    return t


def _fmt_e(n) -> str:
    return f"€ {float(n or 0):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def generate_report_pdf(tipo: str, data: Dict, company: Dict, anno: Optional[int] = None) -> bytes:
    st = _styles()
    anno_txt = str(anno) if anno else "tutti gli anni"
    TITLES = {
        "fatturato": ("Report Fatturato", f"Anno {anno_txt}"),
        "produzione": ("Report Produzione (kg)", f"Anno {anno_txt}"),
        "costo_kg": ("Report Costo per kg", f"Anno {anno_txt}"),
        "marginalita": ("Report Marginalita", f"Anno {anno_txt}"),
        "aging": ("Report Aging Sospesi", "Fatture clienti non incassate"),
        "km": ("Report Km Automezzi", f"Anno {anno_txt}"),
    }
    title, sub = TITLES.get(tipo, ("Report", ""))
    el: List = _report_header(title, sub, company, st)

    if tipo == "fatturato":
        el.append(_kpi_strip([
            ("Totale fatturato", _fmt_e(data.get("totale"))),
            ("Incassato", _fmt_e(data.get("incassato"))),
            ("Sospeso", _fmt_e(data.get("sospeso"))),
        ], st))
        el.append(Spacer(1, 5*mm))
        el.append(Paragraph("<b>Andamento mensile</b>", st["h2"]))
        el.append(_simple_table(
            ["Mese", "Fatturato", "Incassato", "Sospeso", "N fatture"],
            [[r["mese"], _fmt_e(r["totale"]), _fmt_e(r["incassato"]), _fmt_e(r["sospeso"]), r["n"]] for r in data.get("per_mese", [])],
            st,
        ))
        el.append(Spacer(1, 5*mm))
        el.append(Paragraph("<b>Top 20 clienti</b>", st["h2"]))
        el.append(_simple_table(
            ["#", "Cliente", "Fatturato", "N fatture"],
            [[i + 1, r["cliente_nome"], _fmt_e(r["totale"]), r["n"]] for i, r in enumerate(data.get("per_cliente", []))],
            st, col_widths=[12*mm, 100*mm, 40*mm, 28*mm],
        ))

    elif tipo == "produzione":
        pz = data.get("totale_pezzi", 0)
        kg = data.get("totale_kg", 0)
        peso_m = (kg / pz) if pz else 0
        el.append(_kpi_strip([
            ("Kg prodotti", f"{kg:,.1f} kg".replace(",", ".")),
            ("Pezzi", f"{int(pz):,}".replace(",", ".")),
            ("Peso medio/pz", f"{peso_m:.2f} kg"),
        ], st))
        el.append(Spacer(1, 5*mm))
        el.append(Paragraph("<b>Andamento mensile</b>", st["h2"]))
        el.append(_simple_table(
            ["Mese", "Kg", "Pezzi"],
            [[r["mese"], f"{r['kg']:.1f}", f"{int(r['pezzi'])}"] for r in data.get("per_mese", [])],
            st,
        ))
        el.append(Spacer(1, 5*mm))
        el.append(Paragraph("<b>Top clienti per kg</b>", st["h2"]))
        el.append(_simple_table(
            ["Cliente", "Kg", "Pezzi"],
            [[r["cliente_nome"], f"{r['kg']:.1f}", f"{int(r['pezzi'])}"] for r in data.get("per_cliente", [])],
            st, col_widths=[120*mm, 30*mm, 30*mm],
        ))
        el.append(Spacer(1, 5*mm))
        el.append(Paragraph("<b>Top articoli per kg</b>", st["h2"]))
        el.append(_simple_table(
            ["Codice", "Descrizione", "Kg", "Pezzi"],
            [[r.get("codice", ""), r.get("descrizione", ""), f"{r['kg']:.1f}", f"{int(r['pezzi'])}"] for r in data.get("per_articolo", [])],
            st,
        ))

    elif tipo == "costo_kg":
        medio = data.get("costo_kg_medio")
        medio_s = f"EUR {medio:.4f}" if medio is not None else "-"
        el.append(_kpi_strip([
            ("Costi totali", _fmt_e(data.get("totale_costi"))),
            ("Kg prodotti", f"{data.get('totale_kg', 0):.1f} kg"),
            ("Costo medio/kg", medio_s),
        ], st))
        el.append(Spacer(1, 5*mm))
        el.append(Paragraph("<b>Ripartizione per categoria</b>", st["h2"]))
        el.append(_simple_table(
            ["Categoria", "Totale"],
            [[c, _fmt_e(t)] for c, t in (data.get("per_categoria") or {}).items()],
            st, col_widths=[90*mm, 90*mm],
        ))
        el.append(Spacer(1, 5*mm))
        el.append(Paragraph("<b>Dettaglio mensile</b>", st["h2"]))
        el.append(_simple_table(
            ["Mese", "Costi", "Kg prodotti", "EUR/kg"],
            [[r["mese"], _fmt_e(r["costi"]), f"{r['kg']:.1f}",
              (f"EUR {r['costo_kg']:.4f}" if r.get("costo_kg") is not None else "-")] for r in data.get("per_mese", [])],
            st,
        ))

    elif tipo == "marginalita":
        el.append(_kpi_strip([
            ("Fatturato", _fmt_e(data.get("totale_fatturato"))),
            ("Costi allocati", _fmt_e(data.get("totale_costi"))),
            ("Margine totale", _fmt_e(data.get("margine_totale"))),
            ("EUR/kg medio", f"EUR {data.get('costo_kg_medio', 0):.4f}"),
        ], st))
        el.append(Spacer(1, 5*mm))
        el.append(Paragraph("<b>Marginalita per cliente</b>", st["h2"]))
        el.append(_simple_table(
            ["#", "Cliente", "Fatturato", "Kg", "Costo alloc.", "Margine", "Margine %"],
            [[i + 1, r["cliente_nome"], _fmt_e(r["fatturato"]), f"{r['kg']:.1f}",
              _fmt_e(r["costo_allocato"]), _fmt_e(r["margine"]),
              (f"{r['margine_perc']:.1f}%" if r.get("margine_perc") is not None else "-")]
             for i, r in enumerate(data.get("per_cliente", []))],
            st, col_widths=[10*mm, 60*mm, 28*mm, 20*mm, 22*mm, 22*mm, 18*mm],
        ))

    elif tipo == "aging":
        el.append(_kpi_strip([
            ("Totale sospeso", _fmt_e(data.get("totale_sospeso"))),
            ("N fatture", str(data.get("numero_fatture", 0))),
            ("Rilevazione", data.get("oggi", "-")),
        ], st))
        el.append(Spacer(1, 5*mm))
        el.append(Paragraph("<b>Distribuzione per anzianita</b>", st["h2"]))
        el.append(_simple_table(
            ["Bucket (gg)", "Totale", "N fatture"],
            [[b["bucket"], _fmt_e(b["totale"]), b["n"]] for b in data.get("buckets", [])],
            st, col_widths=[60*mm, 60*mm, 60*mm],
        ))
        el.append(Spacer(1, 5*mm))
        el.append(Paragraph("<b>Dettaglio fatture in sospeso</b>", st["h2"]))
        el.append(_simple_table(
            ["Numero", "Cliente", "Data", "Giorni", "Totale", "Bucket"],
            [[f["numero"], f["cliente_nome"], (f.get("data") or "")[:10], f["giorni"], _fmt_e(f["totale"]), f["bucket"]]
             for f in data.get("dettagli", [])],
            st,
        ))

    elif tipo == "km":
        tot_km = data.get("totale_km", 0)
        tot_sp = data.get("totale_spesa", 0)
        cost_km_avg = (tot_sp / tot_km) if tot_km > 0 else 0
        el.append(_kpi_strip([
            ("Km totali", f"{int(tot_km):,}".replace(",", ".")),
            ("Spesa totale", _fmt_e(tot_sp)),
            ("EUR/km medio", f"EUR {cost_km_avg:.3f}"),
        ], st))
        el.append(Spacer(1, 5*mm))
        el.append(Paragraph("<b>Dettaglio per automezzo</b>", st["h2"]))
        el.append(_simple_table(
            ["Targa", "Km", "Spesa", "EUR/km"],
            [[t["targa"], f"{int(t['km_totali'])}", _fmt_e(t["spesa_totale"]),
              (f"EUR {t['costo_km']:.3f}" if t.get("costo_km") is not None else "-")]
             for t in data.get("per_targa", [])],
            st,
        ))
        el.append(Spacer(1, 5*mm))
        el.append(Paragraph("<b>Andamento mensile</b>", st["h2"]))
        el.append(_simple_table(
            ["Mese", "Km", "Spesa"],
            [[r["mese"], f"{int(r['km'])}", _fmt_e(r["spesa"])] for r in data.get("per_mese", [])],
            st,
        ))

    return _build(el)
