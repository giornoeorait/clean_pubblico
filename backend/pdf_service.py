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
    if cliente.get("ragione_sociale"):
        lines.append(f"<b>{cliente['ragione_sociale']}</b>")
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
