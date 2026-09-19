import io
import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.config import FONTS_DIR

VN_FONT = "DejaVuSans"
VN_FONT_BOLD = "DejaVuSans-Bold"

_fonts_registered = False


def ensure_vn_fonts():
    global _fonts_registered
    if _fonts_registered:
        return
    pdfmetrics.registerFont(TTFont(VN_FONT, os.path.join(FONTS_DIR, "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(VN_FONT_BOLD, os.path.join(FONTS_DIR, "DejaVuSans-Bold.ttf")))
    _fonts_registered = True


def group_errors(errors: list):
    grouped = {}
    for err in errors:
        grouped.setdefault(err["token"], []).append(err["location"])
    return sorted(grouped.items(), key=lambda item: len(item[1]), reverse=True)


def build_spellcheck_pdf(job: dict) -> io.BytesIO:
    ensure_vn_fonts()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("VNTitle", parent=styles["Title"], fontName=VN_FONT_BOLD)
    header_style = ParagraphStyle("VNHeader", fontName=VN_FONT_BOLD, fontSize=9, textColor=colors.white, alignment=TA_LEFT)
    cell_style = ParagraphStyle("VNCell", fontName=VN_FONT, fontSize=9, leading=12, alignment=TA_LEFT)

    data = [[Paragraph("Từ lỗi", header_style), Paragraph("Tần suất", header_style), Paragraph("Vị trí", header_style)]]
    for token, locations in group_errors(job["errors"]):
        data.append([Paragraph(token, cell_style), Paragraph(str(len(locations)), cell_style), Paragraph(", ".join(locations), cell_style)])

    table = Table(data, colWidths=[110, 60, 330], repeatRows=1)
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
    doc.build([Paragraph("Báo cáo lỗi chính tả", title_style), Spacer(1, 12), table])
    buffer.seek(0)
    return buffer
