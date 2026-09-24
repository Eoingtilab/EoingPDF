"""Embed a font that contains the generated Korean, English and Japanese text."""
import pymupdf as pdf
from .distribution import resource_root


def text_font(*texts):
    font = pdf.Font(fontfile=str(resource_root() / 'assets/fonts/Pretendard-Regular.ttf'))
    characters = {char for text in texts for char in text if not char.isspace()}
    if any(not font.has_glyph(ord(char)) for char in characters):
        # Qt's UI fallback is not applied by Page.insert_text. MuPDF bundles this
        # CJK font, so document generation remains independent of installed fonts.
        return pdf.Font('cjk')
    return font
