"""Tema aplikasi: palette Midnight Obsidian, ngikutin dark/light mode sistem."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QImage, QPainter, QPixmap

DARK = {
    "bg": "#0C0F14",
    "surface": "#151B23",
    "border": "#232B36",
    "text": "#F2F5F9",
    "muted_text": "#6B7280",
    "accent": "#3662E3",
    "accent_hover": "#4A76F0",
    "accent_pressed": "#2A4FC0",
    "cyan": "#65D0EA",
    "cyan_text": "#0C0F14",
    "selection_text": "#F2F5F9",
    "disabled_bg": "#232B36",
    "disabled_text": "#6B7280",
    "alt_row": "#11151C",
    "glow": "#2B3F6E",
}

LIGHT = {
    "bg": "#F7F9FC",
    "surface": "#FFFFFF",
    "border": "#D7DEE8",
    "text": "#11151C",
    "muted_text": "#6B7280",
    "accent": "#3662E3",
    "accent_hover": "#2A4FC0",
    "accent_pressed": "#1F3C99",
    "cyan": "#1C8FB0",
    "cyan_text": "#FFFFFF",
    "selection_text": "#FFFFFF",
    "disabled_bg": "#E3E8F0",
    "disabled_text": "#9AA3B2",
    "alt_row": "#F2F5F9",
    "glow": "#E7EEFF",
}

STYLESHEET_TEMPLATE = """
QWidget {{
    background-color: {bg};
    color: {text};
    font-size: 13px;
}}
QDialog {{
    background-color: {bg};
}}
QLineEdit, QTextEdit {{
    background-color: {surface};
    color: {text};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: {accent};
    selection-color: {selection_text};
}}
QLineEdit:focus, QTextEdit:focus {{
    border: 1px solid {cyan};
}}
QPushButton {{
    background-color: {accent};
    color: {selection_text};
    border: none;
    border-radius: 6px;
    padding: 7px 14px;
}}
QPushButton:hover {{
    background-color: {accent_hover};
}}
QPushButton:pressed {{
    background-color: {accent_pressed};
}}
QPushButton:disabled {{
    background-color: {disabled_bg};
    color: {disabled_text};
}}
QPushButton:checkable:checked {{
    background-color: {cyan};
    color: {cyan_text};
}}
QTableWidget {{
    background-color: {bg};
    alternate-background-color: {alt_row};
    gridline-color: {border};
    border: 1px solid {border};
    border-radius: 6px;
    selection-background-color: {accent};
    selection-color: {selection_text};
}}
QHeaderView::section {{
    background-color: {surface};
    color: {text};
    padding: 6px;
    border: none;
    border-bottom: 1px solid {border};
}}
QLabel {{
    background: transparent;
}}
"""


def build_stylesheet(tokens: dict) -> str:
    return STYLESHEET_TEMPLATE.format(**tokens)


def tinted_icon(symbol: str, color: str, size: int = 28, boost: float = 1.0) -> QIcon:
    """Render glyph/emoji `symbol` jadi ikon monokrom warna `color` (ngikutin tema), bukan emoji warna asli.

    Emoji warna (mis. 👁 🎲 📋) membedakan detail pakai warna, bukan transparansi - kalau cuma
    dipotong pakai alpha-nya, detail itu hilang jadi blob. Jadi bagian gelap glyph dipakai sebagai
    "tinta" (makin gelap = makin solid), bagian terang jadi makin transparan, ala line-icon.

    `boost` (>1.0) ngangkat opacity tiap piksel biar makin solid/putih - buat glyph yang warna
    aslinya medium-terang (mis. 🌐) dan jadinya keabu-abuan kalau boost=1.0 (default, gak diubah).
    """
    scale = 2
    px = size * scale
    glyph = QPixmap(px, px)
    glyph.fill(Qt.GlobalColor.transparent)

    painter = QPainter(glyph)
    font = painter.font()
    font.setPixelSize(int(px * 0.82))
    painter.setFont(font)
    painter.drawText(glyph.rect(), Qt.AlignmentFlag.AlignCenter, symbol)
    painter.end()

    image = glyph.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    out = QImage(image.size(), QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    base = QColor(color)
    for y in range(image.height()):
        for x in range(image.width()):
            src_alpha = image.pixelColor(x, y).alpha()
            if src_alpha == 0:
                continue
            luminance = image.pixelColor(x, y).lightnessF() * 255
            ink_alpha = min(src_alpha, 255 - int(luminance))
            ink_alpha = min(255, int(ink_alpha * boost))
            if ink_alpha > 0:
                out.setPixelColor(x, y, QColor(base.red(), base.green(), base.blue(), ink_alpha))

    result = QPixmap.fromImage(out).scaled(
        size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )
    return QIcon(result)


def glow_background_css(tokens: dict, selector: str) -> str:
    """CSS radial-glow (sama kayak VaultPickerDialog) buat dipasang di window/dialog lain lewat `selector`.

    `selector` harus spesifik ke 1 widget pakai object name, mis. "QDialog#entryDialog", supaya
    gak ketimpa/nimpa background widget lain yang kebetulan sama-sama QWidget/QDialog.
    """
    return (
        f"{selector} {{ background: qradialgradient("
        "cx:0.5, cy:0.22, radius:1.1, fx:0.5, fy:0.22, "
        f"stop:0 {tokens['glow']}, stop:1 {tokens['bg']}); }}"
    )


def is_dark_mode() -> bool:
    scheme = QGuiApplication.styleHints().colorScheme()
    if scheme == Qt.ColorScheme.Unknown:
        return QGuiApplication.palette().color(QGuiApplication.palette().ColorRole.Window).lightness() < 128
    return scheme == Qt.ColorScheme.Dark


def apply_theme(app) -> None:
    """Set stylesheet sesuai tema sistem saat ini, dan auto re-apply kalau user ganti tema saat app jalan."""
    app.setStyleSheet(build_stylesheet(DARK if is_dark_mode() else LIGHT))
    app.styleHints().colorSchemeChanged.connect(lambda _: apply_theme(app))


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    dark_css = build_stylesheet(DARK)
    light_css = build_stylesheet(LIGHT)
    assert "#0C0F14" in dark_css
    assert "#F7F9FC" in light_css
    assert dark_css != light_css
    assert isinstance(is_dark_mode(), bool)

    apply_theme(app)
    assert app.styleSheet() in (dark_css, light_css)

    print("theme.py self-check OK")
