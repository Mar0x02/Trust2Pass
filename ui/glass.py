"""Kartu rounded-rect solid (TANPA blur) - background translucent + border tipis.

Sempat dicoba versi blur beneran (QGraphicsBlurEffect + render ulang radial-glow + mask biner
custom buat motong pojok ke bentuk rounded), tapi mask custom itu gak pernah pas 100% sama path
ber-antialiasing yang dipakai buat gambar kartunya - selalu nyisain siku tajam kecil di pojok tiap
kali parameter-nya diubah. QSS `border-radius` bawaan Qt jauh lebih simpel dan gak punya masalah
itu karena Qt sendiri yang nge-handle clipping background-nya.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QListWidget, QWidget


def _rgba(color: QColor) -> str:
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"


class GlassPanel(QWidget):
    """Kontainer kartu kaca generik (dipakai buat detail_panel, radius=0 - kotak, sama kayak
    sidebar). Konten ditaruh lewat layout biasa seperti QWidget lain."""

    def __init__(self, tint: QColor, border: QColor, radius: int = 14, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("glassPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"#glassPanel {{ background-color: {_rgba(tint)}; "
            f"border: 1px solid {_rgba(border)}; border-radius: {radius}px; }}"
        )


class GlassListWidget(QListWidget):
    """QListWidget tint biru, bisa nampung satu floating dock (`attach_floating`) yang nempel
    di bawah-tengah, nutupin sebagian item saat di-scroll.

    Sengaja TANPA border-radius (sudut kotak, bukan rounded seperti GlassPanel) - QSS
    border-radius cuma ngebulat FRAME-nya, gak nge-clip `viewport()` (area isi list) yang tetep
    kotak tajam di baliknya. Udah dicoba ditutup pakai `setMask` rounded-region, tapi di window
    asli (bukan offscreen test) kombinasinya sama resize berulang dari QSplitter malah bikin
    artefak lingkaran ganda yang lebih jelek daripada sudut kotak biasa. Sudut kotak di sini lebih
    aman daripada dipaksain bulat tapi rusak.
    """

    def __init__(self, tint: QColor, border: QColor, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("glassList")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"#glassList {{ background-color: {_rgba(tint)}; border: 1px solid {_rgba(border)}; }}"
        )
        self.setFrameShape(QListWidget.Shape.NoFrame)
        self.viewport().setAutoFillBackground(False)
        # viewport() itu QWidget polos juga - kena rule global "QWidget { background-color }" app-
        # wide dan nutup TOTAL background #glassList di atas dengan warna solid (autoFillBackground
        # cuma matiin auto-fill lewat PALETTE, bukan lewat stylesheet). Sama kayak bug
        # `detailContent` sebelumnya: HARUS pakai selector ber-objectName, bukan deklarasi tanpa
        # selector (lihat catatan di main_window.py).
        self.viewport().setObjectName("glassListViewport")
        self.viewport().setStyleSheet("#glassListViewport { background: transparent; }")
        # Scroll tetap jalan lewat wheel/trackpad/keyboard, cuma gambar scrollbar-nya dimatiin.
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Kalau window di-resize sempit banget, jangan munculin scrollbar horizontal bawaan Qt -
        # biarin teks item kepotong (elide) daripada nongolin scrollbar jelek di bawah list.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._floating: QWidget | None = None
        self._floating_margin = 12

    def attach_floating(self, widget: QWidget, margin: int = 12) -> None:
        """Taruh `widget` sebagai overlay yang ngambang nempel di bawah-tengah widget ini,
        bukan item layout biasa - supaya konten di baliknya (list yang di-scroll) tetap kebaca
        di belakangnya lewat backdrop translucent-nya sendiri."""
        widget.setParent(self)
        widget.raise_()
        self._floating = widget
        self._floating_margin = margin
        self._reposition_floating()

    def bottom_reserved_height(self) -> int:
        """Tinggi yang ketutup floating overlay di bawah (+ margin-nya) - dipakai caller buat kasih
        ruang kosong ekstra di akhir konten yang discroll, biar item terakhir bisa discroll sampai
        bener-bener lewat dari belakang overlay."""
        if self._floating is None:
            return 0
        return self._floating.sizeHint().height() + self._floating_margin * 2

    def _reposition_floating(self) -> None:
        if self._floating is None:
            return
        size = self._floating.sizeHint()
        x = (self.width() - size.width()) // 2
        y = self.height() - size.height() - self._floating_margin
        self._floating.setGeometry(max(0, x), max(0, y), size.width(), size.height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reposition_floating()
