import io
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.common_pdf import VN_FONT, VN_FONT_BOLD, ensure_vn_fonts

ensure_vn_fonts()


def build_qc_pdf(mismatches: list, sheets: Optional[list] = None, file_name: Optional[str] = None) -> io.BytesIO:
    sheets = sheets or []

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=28,
        rightMargin=28,
        topMargin=32,
        bottomMargin=28,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("VNTitle", parent=styles["Title"], fontName=VN_FONT_BOLD)
    meta_style = ParagraphStyle("VNMeta", fontName=VN_FONT, fontSize=9, textColor=colors.grey)
    header_style = ParagraphStyle("VNHeader", fontName=VN_FONT_BOLD, fontSize=9, textColor=colors.white, alignment=TA_LEFT)
    cell_style = ParagraphStyle("VNCell", fontName=VN_FONT, fontSize=8.5, leading=11, alignment=TA_LEFT)

    elements = [Paragraph("Báo cáo QC đối chiếu sản phẩm", title_style), Spacer(1, 4)]
    if file_name:
        elements.append(Paragraph(f"File: {file_name}", meta_style))
    elements.append(Paragraph(f"Sheet đã chạy: {', '.join(sheets) if sheets else '-'}", meta_style))
    elements.append(Paragraph(f"Số điểm chưa khớp: {len(mismatches)}", meta_style))
    elements.append(Spacer(1, 12))

    if not mismatches:
        elements.append(Paragraph("Không phát hiện điểm chưa khớp.", cell_style))
    else:
        headers = ["Sheet", "Sản phẩm", "Thuộc tính", "Dòng", "Giá trị trong sheet", "Giá trị chuẩn", "Diễn giải"]
        data = [[Paragraph(h, header_style) for h in headers]]
        for m in mismatches:
            row_range = m.get("row_range") or []
            row_text = f"{row_range[0]}-{row_range[1]}" if len(row_range) == 2 else "-"
            expected = m.get("expected_value")
            data.append([
                Paragraph(str(m.get("sheet_name") or "-"), cell_style),
                Paragraph(str(m.get("product_ref") or "Không rõ sản phẩm"), cell_style),
                Paragraph(str(m.get("attribute") or "-"), cell_style),
                Paragraph(row_text, cell_style),
                Paragraph(str(m.get("claimed_value") or "-"), cell_style),
                Paragraph(str(expected) if expected not in (None, "") else "Không tìm thấy", cell_style),
                Paragraph(str(m.get("reasoning") or "-"), cell_style),
            ])
        table = Table(data, colWidths=[55, 100, 75, 40, 115, 115, 260], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d3748")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return buffer
