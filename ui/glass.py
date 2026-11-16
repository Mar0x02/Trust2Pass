"""Widget kaca (frosted glass): blur BENERAN lewat QGraphicsBlurEffect, bukan sekadar alpha-blend.

Background-nya adalah radial-glow statis punya MainWindow (gak pernah berubah setelah render
pertama), jadi di-render ULANG manual (bukan di-grab dari window-nya) supaya gak recursive -
kalau grab() dipanggil dari dalam paintEvent widget yang posisinya jadi anak dari window yang
di-grab, Qt bakal render ulang window itu termasuk widget ini sendiri (paintEvent terpicu lagi
di tengah proses render -> infinite recursion).
"""

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (
    QBitmap,
    QBrush,
    QColor,
    QGradient,
    QPainter,
    QPainterPath,
    QPixmap,
    QRadialGradient,
    QRegion,
)
from PySide6.QtWidgets import (
    QGraphicsBlurEffect,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QListWidget,
    QScrollBar,
    QWidget,
)


def blurred(pixmap: QPixmap, radius: float) -> QPixmap:
    """Blur `pixmap` beneran (gaussian-ish) pakai QGraphicsBlurEffect."""
    if pixmap.isNull():
        return pixmap
    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(pixmap)
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(radius)
    item.setGraphicsEffect(effect)
    scene.addItem(item)
    result = QPixmap(pixmap.size())
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    scene.render(painter, QRectF(result.rect()), QRectF(pixmap.rect()))
    painter.end()
    return result


def radial_glow_pixmap(size, glow_hex: str, bg_hex: str) -> QPixmap:
    """Render ulang radial-glow yang SAMA persis kayak `theme.glow_background_css` tapi sebagai
    QPixmap asli, supaya bisa di-crop per-widget lalu di-blur jadi backdrop kartu kaca."""
    pixmap = QPixmap(size)
    painter = QPainter(pixmap)
    gradient = QRadialGradient(QPointF(0.5, 0.22), 1.1, QPointF(0.5, 0.22))
    gradient.setCoordinateMode(QGradient.CoordinateMode.ObjectBoundingMode)
    gradient.setColorAt(0.0, QColor(glow_hex))
    gradient.setColorAt(1.0, QColor(bg_hex))
    painter.fillRect(QRect(QPoint(0, 0), size), QBrush(gradient))
    painter.end()
    return pixmap


class _GlassPaintMixin:
    """Logic bareng buat GlassPanel & GlassListWidget: generate+cache backdrop blur dari radial-glow
    MainWindow, lalu gambar rounded-rect + tint translucent + border tipis di atasnya."""

    def _init_glass(self, glow_hex: str, bg_hex: str, tint: QColor, border: QColor, radius: int, blur_radius: float) -> None:
        self._glow_hex = glow_hex
        self._bg_hex = bg_hex
        self._tint = tint
        self._border = border
        self._radius = radius
        self._blur_radius = blur_radius
        self._cache: QPixmap | None = None
        self._cache_key = None
        self._floating: QWidget | None = None
        self._floating_margin = 12
        self._mask_size = None

    def _content_rect_in_window(self) -> QRect:
        origin = self.mapTo(self.window(), QPoint(0, 0))
        return QRect(origin, self.size())

    def _backdrop(self) -> QPixmap:
        window = self.window()
        local = self._content_rect_in_window()
        key = (window.width(), window.height(), local.x(), local.y(), local.width(), local.height())
        if self._cache is not None and self._cache_key == key:
            return self._cache
        full = radial_glow_pixmap(window.size(), self._glow_hex, self._bg_hex)
        crop = local.intersected(full.rect())
        cropped = full.copy(crop)
        self._cache = blurred(cropped, self._blur_radius)
        self._cache_key = key
        return self._cache

    def _paint_glass(self, painter: QPainter, rect) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), self._radius, self._radius)
        # "Undercoat" warna border, gak diclip, di-gambar DULUAN: mask biner (`_apply_rounded_mask`)
        # gak persis sama "lengkungannya" sama path ber-antialiasing ini (beda cara nge-resolve
        # pixel di tepi lengkungan), jadi ada celah sub-piksel di pojok. Tanpa undercoat ini,
        # celahnya nunjukin bg window mentah (item hitam); dengan undercoat, celahnya ketutup
        # warna border tipis - jauh lebih gak keliatan.
        painter.fillRect(rect, self._border)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, self._backdrop())
        painter.fillPath(path, self._tint)
        painter.setClipping(False)
        painter.setPen(self._border)
        painter.drawPath(path)

    def _ensure_rounded_mask(self, target: QWidget, rect) -> None:
        """Pasang ulang mask HANYA kalau ukurannya beneran berubah dari yang terakhir dipasang.

        Dipanggil dari `resizeEvent` DAN `paintEvent`: scrollbar yang muncul/ilang bikin Qt
        nge-resize viewport secara internal tanpa motong lewat resizeEvent widget luarnya, jadi
        mask yang cuma di-refresh di resizeEvent bisa basi (ukurannya gak ngikutin viewport yang
        udah menyempit/melebar gara-gara scrollbar) - celah sisa itu nunjukin bg mentah di
        belakangnya, bukan kartu kaca kita.
        """
        if rect.size() != self._mask_size:
            self._apply_rounded_mask(target, rect)
            self._mask_size = rect.size()

    def _apply_rounded_mask(self, target: QWidget, rect) -> None:
        """Clip SEMUA rendering `target` (termasuk item list yang digambar Qt sendiri, bukan cuma
        backdrop kita) ke bentuk rounded-rect - tanpa ini, konten item persegi nongol lewat
        lengkungan pojok dan keliatan nempel ke background window di baliknya, bukan di kartu kaca."""
        if rect.width() <= 0 or rect.height() <= 0:
            return
        bitmap = QBitmap(rect.size())
        bitmap.fill(Qt.GlobalColor.color0)
        painter = QPainter(bitmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.GlobalColor.color1)
        painter.setPen(Qt.PenStyle.NoPen)
        path = QPainterPath()
        # Mask biner (1-bit, gak ada antialiasing beneran) nge-resolve tepi lengkungan sedikit
        # lebih "ketat" daripada path ber-antialiasing yang dipakai buat gambar kartu kaca-nya di
        # `_paint_glass` - beda ini ketara banget di layar Retina (devicePixelRatio 2x). Tanpa
        # digedein, mask motong beberapa piksel KE DALAM konten yang udah digambar, nunjukkin bg
        # mentah window di pojoknya. Outset 2px cukup buat nutup selisihnya tanpa keliatan beda.
        path.addRoundedRect(QRectF(rect).adjusted(-4, -4, 4, 4), self._radius, self._radius)
        painter.drawPath(path)
        painter.end()
        target.setMask(QRegion(bitmap))

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
        bener-bener lewat dari belakang overlay (kalau enggak, scroll mentok pas item terakhir
        masih ketutup, susah diklik)."""
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


class GlassPanel(_GlassPaintMixin, QWidget):
    """Kontainer kartu kaca generik (dipakai buat detail_panel). Konten ditaruh lewat layout biasa
    seperti QWidget lain - anak-anaknya otomatis digambar Qt di atas backdrop ini."""

    def __init__(self, glow_hex: str, bg_hex: str, tint: QColor, border: QColor, radius: int = 14,
                 blur_radius: float = 28, parent=None) -> None:
        super().__init__(parent)
        self._init_glass(glow_hex, bg_hex, tint, border, radius, blur_radius)

    def paintEvent(self, event) -> None:
        self._ensure_rounded_mask(self, self.rect())
        painter = QPainter(self)
        self._paint_glass(painter, self.rect())
        painter.end()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._cache = None
        self._ensure_rounded_mask(self, self.rect())


class GlassListWidget(_GlassPaintMixin, QListWidget):
    """QListWidget dengan backdrop kartu kaca blur, dan bisa nampung satu floating dock
    (`attach_floating`) yang nempel di bawah-tengah, nutupin sebagian item saat di-scroll."""

    def __init__(self, glow_hex: str, bg_hex: str, tint: QColor, border: QColor, radius: int = 14,
                 blur_radius: float = 28, parent=None) -> None:
        super().__init__(parent)
        self._init_glass(glow_hex, bg_hex, tint, border, radius, blur_radius)
        self.setFrameShape(QListWidget.Shape.NoFrame)
        self.viewport().setAutoFillBackground(False)
        # Scrollbar NATIVE-nya makan "gutter" ruang di LUAR viewport (buat nyisain tempat buat
        # dirinya sendiri) - gutter itu gak pernah ke-cover backdrop kaca kita (cuma viewport yang
        # kita gambar+mask), jadi kalau dipakai langsung bakal nunjukkin bg mentah di belakangnya.
        # Solusinya: matiin reservasi gutter-nya (AlwaysOff - scroll via wheel/keyboard tetap
        # jalan, cuma gambarnya aja yang dimatiin), lalu bikin scrollbar SENDIRI yang jadi anak
        # viewport (biar ke-mask ikutan rounded, dan gak numpang ruang di luar viewport).
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        internal_vbar = self.verticalScrollBar()
        self._overlay_vbar = QScrollBar(Qt.Orientation.Vertical, self.viewport())
        self._overlay_vbar.setStyleSheet(
            """
            QScrollBar:vertical { background: transparent; width: 8px; margin: 6px 3px 6px 0px; border: none; }
            QScrollBar::handle:vertical { background: rgba(255, 255, 255, 80); border-radius: 4px; min-height: 24px; }
            QScrollBar::handle:vertical:hover { background: rgba(255, 255, 255, 120); }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; background: none; border: none; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; border: none; }
            """
        )

        def sync_range(lo: int, hi: int) -> None:
            self._overlay_vbar.setRange(lo, hi)
            self._overlay_vbar.setPageStep(internal_vbar.pageStep())
            self._overlay_vbar.setVisible(hi > lo)

        internal_vbar.rangeChanged.connect(sync_range)
        internal_vbar.valueChanged.connect(self._overlay_vbar.setValue)
        self._overlay_vbar.valueChanged.connect(internal_vbar.setValue)
        sync_range(internal_vbar.minimum(), internal_vbar.maximum())

    def paintEvent(self, event) -> None:
        self._ensure_rounded_mask(self.viewport(), self.viewport().rect())
        painter = QPainter(self.viewport())
        self._paint_glass(painter, self.viewport().rect())
        painter.end()
        super().paintEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._cache = None
        self._ensure_rounded_mask(self.viewport(), self.viewport().rect())
        self._reposition_floating()
        vp_rect = self.viewport().rect()
        width, side_margin, vert_margin = 8, 3, 6
        self._overlay_vbar.setGeometry(
            vp_rect.width() - width - side_margin, vert_margin, width, max(0, vp_rect.height() - 2 * vert_margin)
        )
