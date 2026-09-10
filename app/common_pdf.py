import os

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(BASE_DIR, "fonts")
VN_FONT = "DejaVuSans"
VN_FONT_BOLD = "DejaVuSans-Bold"

_fonts_registered = False


def ensure_vn_fonts():
    """Dang ky font ho tro tieng Viet cho reportlab, chi thuc hien 1 lan."""
    global _fonts_registered
    if _fonts_registered:
        return
    pdfmetrics.registerFont(TTFont(VN_FONT, os.path.join(FONT_DIR, "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(VN_FONT_BOLD, os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")))
    _fonts_registered = True
