"""Export anagrafica clienti in Excel (.xlsx) e PDF (landscape multi-pagina)."""
import io
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from core import db, get_current_user, tenant_scope

router = APIRouter(tags=["clienti-export"])


# Colonne esportabili — chiave DB → intestazione italiana (nell'ordine desiderato)
EXPORT_COLUMNS = [
    ("codice", "Codice"),
    ("ragione_sociale", "Ragione sociale"),
    ("denominazione_struttura", "Denominazione struttura"),
    ("partita_iva", "Partita IVA"),
    ("codice_fiscale", "Codice fiscale"),
    ("codice_sdi", "Codice SDI"),
    ("pec", "PEC"),
    ("indirizzo", "Indirizzo"),
    ("cap", "CAP"),
    ("comune", "Comune"),
    ("provincia", "Provincia"),
    ("nazione", "Nazione"),
    ("telefono", "Telefono"),
    ("email", "E-mail"),
    ("referente", "Referente"),
    ("condizioni_pagamento", "Condizioni di pagamento"),
    ("attivo", "Attivo"),
    ("note", "Note"),
]

# Campi che devono restare TESTO in Excel per non perdere zeri iniziali
TEXT_FIELDS = {"partita_iva", "codice_fiscale", "cap", "codice_sdi", "telefono"}


async def _fetch_clienti(user: Dict, q: Optional[str]) -> List[Dict[str, Any]]:
    """Recupera clienti applicando lo stesso filtro `q` della griglia e ordinamento alfabetico."""
    query: Dict[str, Any] = dict(tenant_scope(user))
    if q:
        query["$or"] = [
            {"ragione_sociale": {"$regex": q, "$options": "i"}},
            {"denominazione_struttura": {"$regex": q, "$options": "i"}},
            {"codice": {"$regex": q, "$options": "i"}},
        ]
    cursor = db.clienti.find(query, {"_id": 0}).collation({"locale": "it", "strength": 1}).sort("ragione_sociale", 1)
    return await cursor.to_list(100000)


def _row_value(c: Dict[str, Any], key: str):
    v = c.get(key)
    if v is None or v == "":
        return ""
    if key == "attivo":
        return "Sì" if v else "No"
    return v


@router.get("/clienti/export/excel")
async def export_clienti_excel(
    q: Optional[str] = Query(None),
    user: Dict = Depends(get_current_user),
):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    clienti = await _fetch_clienti(user, q)

    wb = Workbook()
    ws = wb.active
    ws.title = "Anagrafica clienti"

    headers = [h for _, h in EXPORT_COLUMNS]
    ws.append(headers)
    # Stile intestazione
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="4338CA")
    for col_idx, _ in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    # Righe
    for c in clienti:
        row = []
        for key, _ in EXPORT_COLUMNS:
            val = _row_value(c, key)
            if key in TEXT_FIELDS:
                val = str(val) if val != "" else ""
            row.append(val)
        ws.append(row)

    # Colonne testo → forzatura formato
    text_col_idx = [i + 1 for i, (k, _) in enumerate(EXPORT_COLUMNS) if k in TEXT_FIELDS]
    for col in text_col_idx:
        letter = get_column_letter(col)
        for cell in ws[letter][1:]:
            cell.number_format = "@"

    # Autofilter + freeze pane + larghezze auto
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for col_idx, (_, header) in enumerate(EXPORT_COLUMNS, start=1):
        letter = get_column_letter(col_idx)
        max_len = len(header)
        for row in ws.iter_rows(min_row=2, min_col=col_idx, max_col=col_idx):
            val = row[0].value
            if val is not None:
                max_len = max(max_len, min(60, len(str(val))))
        ws.column_dimensions[letter].width = max_len + 2

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"Anagrafica_Clienti_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/clienti/export/pdf")
async def export_clienti_pdf(
    q: Optional[str] = Query(None),
    user: Dict = Depends(get_current_user),
):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    clienti = await _fetch_clienti(user, q)

    # Colonne compatte per PDF (subset delle più significative)
    pdf_cols = [
        ("codice", "Cod."),
        ("ragione_sociale", "Ragione sociale"),
        ("partita_iva", "P.IVA"),
        ("codice_fiscale", "Cod. fiscale"),
        ("comune", "Comune"),
        ("provincia", "PR"),
        ("telefono", "Telefono"),
        ("email", "E-mail"),
        ("condizioni_pagamento", "Pagamento"),
        ("attivo", "Attivo"),
    ]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=10 * mm, rightMargin=10 * mm,
        topMargin=12 * mm, bottomMargin=10 * mm,
        title="Anagrafica clienti",
    )
    styles = getSampleStyleSheet()
    title_st = ParagraphStyle("t", parent=styles["Title"], fontSize=14, textColor=colors.HexColor("#4338CA"))
    small_st = ParagraphStyle("s", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#64748B"))
    cell_st = ParagraphStyle("c", parent=styles["Normal"], fontSize=7, leading=8)

    elements: List = [
        Paragraph("Anagrafica clienti", title_st),
        Paragraph(
            f"Generato il {datetime.now().strftime('%d/%m/%Y %H:%M')} · Totale clienti esportati: <b>{len(clienti)}</b>",
            small_st,
        ),
        Spacer(1, 4 * mm),
    ]

    header = [Paragraph(f"<b>{h}</b>", cell_st) for _, h in pdf_cols]
    data = [header]
    for c in clienti:
        row = [Paragraph(str(_row_value(c, k)), cell_st) for k, _ in pdf_cols]
        data.append(row)

    # Larghezze bilanciate su A4 landscape (~277mm utili)
    col_widths = [18 * mm, 55 * mm, 26 * mm, 30 * mm, 30 * mm, 10 * mm, 28 * mm, 45 * mm, 25 * mm, 15 * mm]
    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4338CA")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    elements.append(tbl)

    doc.build(elements)
    buf.seek(0)
    filename = f"Anagrafica_Clienti_{datetime.now().strftime('%Y-%m-%d')}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
