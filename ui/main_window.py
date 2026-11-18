"""Window utama: daftar entri (sidebar + panel detail), CRUD, auto-lock."""

import uuid
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from generator import generate_password
from ui.datetime_fmt import format_timestamp
from ui.entry_picker_dialog import EntryPickerDialog
from ui.import_report_dialog import ImportReportDialog
from ui.glass import GlassListWidget, GlassPanel
from ui.i18n import tr
from ui.unlock_dialog import UnlockDialog
from ui.theme import (
    DARK,
    LIGHT,
    clear_field_error,
    glow_background_css,
    is_dark_mode,
    make_hint_label,
    mark_field_error,
    tinted_icon,
)
from vault import storage
from vault.manager import VaultManager
from vault.models import Entry

CLIPBOARD_CLEAR_SECONDS = 20
PASSWORD_MASK = "••••••••"
ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "icon-rounded.png"
NOTES_PREVIEW_WIDTH_PX = 380


def _section_header(title: str, tokens: dict) -> QVBoxLayout:
    """Judul kecil + garis tipis di bawahnya - ngelompokin field detail panel jadi beberapa
    section ("Information"/"Credential"/"Time"), bukan satu form panjang rata."""
    label = QLabel(title)
    label.setStyleSheet(f"color: {tokens['muted_text']}; font-weight: bold; font-size: 12px;")
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(f"background-color: {tokens['border']}; max-height: 1px; border: none;")
    layout = QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    layout.addWidget(label)
    layout.addWidget(line)
    return layout


class EntryDialog(QDialog):
    """Form tambah/edit satu entri. Sukses -> self.result_entry (Entry) siap dipakai caller."""

    def __init__(self, entry: Entry | None = None, parent=None) -> None:
        super().__init__(parent)
        self._entry_id = entry.id if entry else None
        self.result_entry: Entry | None = None
        tokens = DARK if is_dark_mode() else LIGHT
        self._button_icon_color = tokens["selection_text"]  # ikon di atas tombol primary (biru)
        self._secondary_icon_color = tokens["text"]  # ikon di atas tombol secondary (netral)

        self.setWindowTitle(tr("entry_dialog_title_edit") if entry else tr("entry_dialog_title_add"))
        self.setModal(True)
        self.setObjectName("entryDialog")
        self.setStyleSheet(glow_background_css(tokens, "QDialog#entryDialog"))

        self.site_input = QLineEdit(entry.site if entry else "")
        self.username_input = QLineEdit(entry.username if entry else "")
        self.url_input = QLineEdit(entry.url if entry else "")
        self.notes_input = QTextEdit(entry.notes if entry else "")

        self.password_input = QLineEdit(entry.password if entry else "")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.toggle_button = QPushButton()
        self.toggle_button.setIcon(tinted_icon("👁", self._button_icon_color))
        self.toggle_button.setIconSize(QSize(18, 18))
        self.toggle_button.setCheckable(True)
        self.toggle_button.setFixedWidth(36)
        self.toggle_button.toggled.connect(self._toggle_password_visibility)
        self.generate_button = QPushButton()
        self.generate_button.setIcon(tinted_icon("🎲", self._secondary_icon_color))
        self.generate_button.setIconSize(QSize(18, 18))
        self.generate_button.setFixedWidth(36)
        self.generate_button.setProperty("variant", "secondary")
        self.generate_button.clicked.connect(self._on_generate)

        password_row = QHBoxLayout()
        password_row.addWidget(self.password_input)
        password_row.addWidget(self.toggle_button)
        password_row.addWidget(self.generate_button)

        # Field wajib (Nama/Username/Password) nunjukin error-nya sendiri-sendiri (border merah +
        # hint italic persis di bawahnya), bukan satu pesan gabungan di bawah form - biar jelas
        # LANGSUNG field mana yang masih kosong, gak perlu nebak-nebak dari teks gabungan.
        self.site_hint = make_hint_label()
        self.username_hint = make_hint_label()
        self.password_hint = make_hint_label()

        site_field = QVBoxLayout()
        site_field.setContentsMargins(0, 0, 0, 0)
        site_field.setSpacing(2)
        site_field.addWidget(self.site_input)
        site_field.addWidget(self.site_hint)

        username_field = QVBoxLayout()
        username_field.setContentsMargins(0, 0, 0, 0)
        username_field.setSpacing(2)
        username_field.addWidget(self.username_input)
        username_field.addWidget(self.username_hint)

        password_field = QVBoxLayout()
        password_field.setContentsMargins(0, 0, 0, 0)
        password_field.setSpacing(2)
        password_field.addLayout(password_row)
        password_field.addWidget(self.password_hint)

        form = QFormLayout()
        form.addRow(tr("form_label_nama"), site_field)
        form.addRow(tr("form_label_username"), username_field)
        form.addRow(tr("form_label_password"), password_field)
        form.addRow(tr("form_label_url"), self.url_input)
        form.addRow(tr("form_label_catatan"), self.notes_input)

        self.site_input.textChanged.connect(lambda: clear_field_error(self.site_input, self.site_hint))
        self.username_input.textChanged.connect(
            lambda: clear_field_error(self.username_input, self.username_hint)
        )
        self.password_input.textChanged.connect(
            lambda: clear_field_error(self.password_input, self.password_hint)
        )

        cancel_button = QPushButton(tr("btn_batal"))
        cancel_button.setProperty("variant", "secondary")
        cancel_button.clicked.connect(self.reject)
        save_button = QPushButton(tr("btn_simpan"))
        save_button.clicked.connect(self._on_save)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(save_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(button_row)

    def _toggle_password_visibility(self, checked: bool) -> None:
        self.password_input.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)
        self.toggle_button.setIcon(tinted_icon("🙈" if checked else "👁", self._button_icon_color))

    def _on_generate(self) -> None:
        self.toggle_button.setChecked(True)
        self.password_input.setText(generate_password())

    def _on_save(self) -> None:
        site = self.site_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text()

        valid = True
        if not site:
            mark_field_error(self.site_input, self.site_hint, tr("hint_isi_nama"))
            valid = False
        if not username:
            mark_field_error(self.username_input, self.username_hint, tr("hint_isi_username"))
            valid = False
        if not password:
            mark_field_error(self.password_input, self.password_hint, tr("hint_isi_password"))
            valid = False
        if not valid:
            return

        if self._entry_id:
            self.result_entry = Entry(
                id=self._entry_id, site=site, username=username, password=password,
                url=self.url_input.text().strip(), notes=self.notes_input.toPlainText(),
            )
        else:
            self.result_entry = Entry(
                site=site, username=username, password=password,
                url=self.url_input.text().strip(), notes=self.notes_input.toPlainText(),
            )
        self.accept()


class MainWindow(QWidget):
    """Dashboard vault: sidebar daftar entri + panel detail. Hanya dibuat setelah
    VaultManager unlocked (Confidentiality gate)."""

    locked = Signal()

    def __init__(self, manager: VaultManager, parent=None) -> None:
        super().__init__(parent)
        self.manager = manager
        self._selected_id: str | None = None
        self._password_visible = False
        self.setWindowTitle(f"Trust2Pass - {manager.path.name}")
        self.setObjectName("mainWindow")
        # Tanpa ini, ukuran awal window ngikutin sizeHint layout yang kekecilan - sidebar jadi
        # sempit dan munculin scrollbar horizontal bawaan Qt yang jelek.
        self.resize(760, 560)

        tokens = DARK if is_dark_mode() else LIGHT
        # QSplitter & handle-nya kena rule global "QWidget { background-color }" juga (dari
        # app.setStyleSheet di theme.apply_theme), jadi perlu ditimpa eksplisit jadi transparent -
        # kalau enggak, celah antara dua kartu kaca keisi warna bg solid, bukan nerusin glow di baliknya.
        self.setStyleSheet(
            glow_background_css(tokens, "QWidget#mainWindow") + "QSplitter, QSplitter::handle { background: transparent; }"
        )
        self._button_icon_color = tokens["selection_text"]  # semua QPushButton pakai background accent
        self._page_icon_color = tokens["text"]  # ikon di atas background halaman (bukan tombol)
        self._muted_icon_color = tokens["muted_text"]

        # Frosted glass klasik: kartu kaca HARUS lebih terang dari background di belakangnya biar
        # kebaca sebagai "kaca" (bukan makin gelap kayak nimpa warna surface gelap di atas bg gelap -
        # kontrasnya ilang). Makanya tint-nya putih, bukan warna token surface/border.
        glass_tint = QColor(255, 255, 255, 34)
        glass_border = QColor(255, 255, 255, 75)

        # Sidebar nempel di tepi kiri window - di luar jangkauan radial-glow yang nyala di
        # tengah-atas (lihat glow_background_css), jadi kalau tint-nya putih polos kayak
        # detail_panel, dia numpuk di atas bg yang udah gelap di situ dan keliatan mati/item,
        # bukan kaca. Dikasih dasar warna dari token glow sendiri biar tetep keliatan "kaca biru"
        # independen dari backdrop window di belakangnya.
        sidebar_tint = QColor(tokens["glow"]).lighter(200)
        sidebar_tint.setAlpha(160)

        # --- top bar ---
        icon_label = QLabel()
        pixmap = QPixmap(str(ICON_PATH))
        if not pixmap.isNull():
            icon_label.setPixmap(
                pixmap.scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )
        title_label = QLabel("Trust2Pass")
        title_label.setStyleSheet("font-weight: bold; font-size: 15px;")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(tr("search_placeholder"))
        self.search_input.addAction(
            tinted_icon("🔍", self._page_icon_color), QLineEdit.ActionPosition.LeadingPosition
        )
        # shortcut: filtering `_visible_entries` itu sinkron & instan (cuma nyaring list in-memory
        # yang udah ke-decrypt), jadi gak ada proses beneran buat ditunggu - spinner ini cuma
        # nyala sebentar (durasi tetap) buat ngasih feedback visual "lagi nyari", bukan nunggu
        # async beneran. Kalau nanti pencarian jadi berat/pindah ke thread lain, ganti jadi
        # show/hide di awal/akhir kerjaan asli, bukan timer tetap.
        self._search_spinner_action = self.search_input.addAction(
            tinted_icon("⏳", self._page_icon_color), QLineEdit.ActionPosition.TrailingPosition
        )
        self._search_spinner_action.setVisible(False)
        self.search_input.textChanged.connect(self._on_search_changed)

        import_button = QPushButton(tr("btn_import"))
        import_button.setIcon(tinted_icon("📥", self._page_icon_color))
        import_button.setIconSize(QSize(16, 16))
        import_button.setProperty("variant", "secondary")
        import_button.clicked.connect(self._on_import)
        export_button = QPushButton(tr("btn_export"))
        export_button.setIcon(tinted_icon("📤", self._page_icon_color))
        export_button.setIconSize(QSize(16, 16))
        export_button.setProperty("variant", "secondary")
        export_button.clicked.connect(self._on_export)

        lock_button = QPushButton(tr("btn_lock"))
        lock_button.setIcon(tinted_icon("🔒", self._button_icon_color))
        lock_button.setIconSize(QSize(16, 16))
        lock_button.clicked.connect(self._on_lock)

        top_bar = QHBoxLayout()
        top_bar.addWidget(icon_label)
        top_bar.addWidget(title_label)
        top_bar.addWidget(self.search_input, stretch=1)
        top_bar.addWidget(import_button)
        top_bar.addWidget(export_button)
        top_bar.addWidget(lock_button)

        # --- sidebar (daftar entri) ---
        # List diisi full-height (bukan dipotong layout) - tombol tambah NEMPEL ngambang langsung
        # di atasnya (tanpa panel/backdrop di belakangnya - cuma tombolnya doang yang melayang),
        # supaya item yang di-scroll tetap kebaca sampai ke batas bawah list.
        self.entry_list = GlassListWidget(sidebar_tint, glass_border)
        self.entry_list.currentItemChanged.connect(self._on_selection_changed)

        add_button = QPushButton(tr("btn_tambah_entri"))
        add_button.setIcon(tinted_icon("➕", self._button_icon_color))
        add_button.setIconSize(QSize(14, 14))
        add_button.clicked.connect(self._on_add)
        self.entry_list.attach_floating(add_button, margin=10)

        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.addWidget(self.entry_list)

        # --- panel detail ---
        detail_header = QLabel(tr("detail_entri_header"))
        detail_header.setStyleSheet(f"font-weight: bold; color: {tokens['text']};")
        self.edit_button = QPushButton()
        self.edit_button.setIcon(tinted_icon("✏️", self._page_icon_color))
        self.edit_button.setIconSize(QSize(18, 18))
        self.edit_button.setFixedWidth(36)
        self.edit_button.setProperty("variant", "secondary")
        self.edit_button.clicked.connect(self._on_edit)
        self.delete_button = QPushButton()
        self.delete_button.setIcon(tinted_icon("🗑️", self._button_icon_color))
        self.delete_button.setIconSize(QSize(18, 18))
        self.delete_button.setFixedWidth(36)
        self.delete_button.setProperty("variant", "danger")
        self.delete_button.clicked.connect(self._on_delete)

        detail_header_row = QHBoxLayout()
        detail_header_row.addWidget(detail_header)
        detail_header_row.addStretch()
        detail_header_row.addWidget(self.edit_button)
        detail_header_row.addWidget(self.delete_button)

        self.detail_site = QLabel("-")
        self.detail_username = QLabel("-")
        self.detail_password = QLabel(PASSWORD_MASK)
        self.detail_url = QLabel("-")
        self.detail_url.setOpenExternalLinks(True)
        self.detail_notes = QLabel("-")
        self.detail_notes.setWordWrap(False)
        # Tanpa batas lebar, teks yang gak di-elide (atau di-elide berdasar JUMLAH KARAKTER, yang
        # lebar pixel-nya tetep beda-beda tergantung isi hurufnya) bikin sizeHint label ini goyang
        # tiap ganti entri - ngerembet ke lebar form & sidebar lewat splitter. setMaximumWidth
        # bikin batasnya konsisten; teksnya sendiri di-elide pas-pixel ke lebar ini juga
        # (lihat _update_detail_panel), jadi gak cuma kepotong visual doang.
        self.detail_notes.setMaximumWidth(NOTES_PREVIEW_WIDTH_PX)
        self.detail_created = QLabel("-")
        self.detail_updated = QLabel("-")

        self.show_password_button = QPushButton()
        self.show_password_button.setIcon(tinted_icon("👁", self._button_icon_color))
        self.show_password_button.setIconSize(QSize(18, 18))
        self.show_password_button.setFixedWidth(36)
        self.show_password_button.setCheckable(True)
        self.show_password_button.toggled.connect(self._toggle_detail_password)
        copy_password_button = QPushButton()
        copy_password_button.setIcon(tinted_icon("📋", self._page_icon_color))
        copy_password_button.setIconSize(QSize(18, 18))
        copy_password_button.setFixedWidth(36)
        copy_password_button.setProperty("variant", "secondary")
        copy_password_button.clicked.connect(self._on_copy_password)

        password_row = QHBoxLayout()
        password_row.addWidget(self.detail_password, stretch=1)
        password_row.addWidget(self.show_password_button)
        password_row.addWidget(copy_password_button)

        def _mini_form() -> QFormLayout:
            """Form kecil per-section - rata kiri (bukan default platform yang bisa beda-beda),
            dan field gak dipaksa melar ngisi sisa lebar (biar gak kelihatan "ngambang" di tengah)."""
            form = QFormLayout()
            form.setContentsMargins(0, 0, 0, 0)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
            form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
            return form

        info_form = _mini_form()
        info_form.addRow(tr("form_label_nama"), self.detail_site)
        info_form.addRow(tr("form_label_url"), self.detail_url)

        cred_form = _mini_form()
        cred_form.addRow(tr("form_label_username"), self.detail_username)
        cred_form.addRow(tr("form_label_password"), password_row)

        notes_row = QHBoxLayout()
        notes_label = QLabel(tr("form_label_catatan"))
        notes_row.addWidget(notes_label)
        notes_row.addWidget(self.detail_notes)
        notes_row.addStretch()

        time_form = _mini_form()
        time_form.addRow(tr("form_label_dibuat"), self.detail_created)
        time_form.addRow(tr("form_label_diubah"), self.detail_updated)

        self.detail_content = QWidget()
        # QWidget polos kena rule global "QWidget { background-color: ... }" (solid, bukan
        # transparent kayak QLabel) - tanpa ini nutup backdrop kaca di belakangnya jadi kotak item.
        # HARUS pakai selector ber-objectName ("#detailContent"), BUKAN deklarasi tanpa selector -
        # style tanpa selector di widget yang punya anak bikin Qt berhenti nurunin stylesheet
        # app-wide (termasuk warna biru QPushButton) ke semua child-nya (tombol edit/delete/dst
        # jadi transparan tanpa background, cuma ikonnya doang yang keliatan).
        self.detail_content.setObjectName("detailContent")
        self.detail_content.setStyleSheet("#detailContent { background: transparent; }")
        detail_content_layout = QVBoxLayout(self.detail_content)
        detail_content_layout.setContentsMargins(0, 0, 0, 0)
        detail_content_layout.setSpacing(6)
        detail_content_layout.addLayout(detail_header_row)
        detail_content_layout.addSpacing(10)
        detail_content_layout.addLayout(_section_header(tr("section_information"), tokens))
        detail_content_layout.addLayout(info_form)
        detail_content_layout.addSpacing(10)
        detail_content_layout.addLayout(_section_header(tr("section_credential"), tokens))
        detail_content_layout.addLayout(cred_form)
        detail_content_layout.addSpacing(10)
        detail_content_layout.addLayout(notes_row)
        detail_content_layout.addSpacing(10)
        detail_content_layout.addLayout(_section_header(tr("section_time"), tokens))
        detail_content_layout.addLayout(time_form)

        self.detail_empty_label = QLabel(tr("detail_empty_text"))
        self.detail_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_empty_label.setStyleSheet(f"color: {tokens['text']}; font-size: 14px;")

        detail_panel = GlassPanel(glass_tint, glass_border, radius=0)
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(16, 16, 16, 16)
        detail_layout.addWidget(self.detail_content)
        detail_layout.addWidget(self.detail_empty_label)
        detail_layout.addStretch()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(16)
        splitter.addWidget(sidebar)
        splitter.addWidget(detail_panel)
        splitter.setSizes([220, 480])
        # Sidebar (index 0) JANGAN ikut nyerap/ngasih ruang pas konten berubah - semua
        # pertambahan/pengurangan lebar harus diserap detail_panel (index 1) aja, biar sidebar
        # tetep diem di tempat walau detail panel-nya minta lebar beda-beda.
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(12)
        layout.addLayout(top_bar)
        layout.addWidget(splitter)

        self.refresh()

    def _visible_entries(self) -> list[Entry]:
        query = self.search_input.text().strip().lower()
        if not query:
            return list(self.manager.entries)
        return [e for e in self.manager.entries if query in e.site.lower() or query in e.username.lower()]

    def _on_search_changed(self) -> None:
        self._refresh_list()
        self._search_spinner_action.setVisible(bool(self.search_input.text().strip()))
        QTimer.singleShot(300, lambda: self._search_spinner_action.setVisible(False))

    def refresh(self) -> None:
        self._refresh_list()

    def _refresh_list(self) -> None:
        self.entry_list.blockSignals(True)
        self.entry_list.clear()
        first_item = None
        selected_item = None
        for entry in self._visible_entries():
            item = QListWidgetItem(tinted_icon("🌐", self._page_icon_color, boost=2.4), entry.site)
            item.setData(Qt.ItemDataRole.UserRole, entry.id)
            self.entry_list.addItem(item)
            first_item = first_item or item
            if entry.id == self._selected_id:
                selected_item = item
        # Gak ada entri yang masih cocok sama seleksi sebelumnya (awal buka vault, atau entri yang
        # lagi dipilih abis dihapus) - jatuh ke entri pertama biar panel detail gak nganggur kosong.
        self.entry_list.setCurrentItem(selected_item or first_item)
        # Baris kosong non-selectable di akhir, setinggi dock tombol tambah - tanpa ini, scroll
        # mentok begitu item terakhir baru nyentuh tepi atas dock, padahal dock masih nutupin
        # separuh baris itu (susah diklik). Dengan baris kosong ini, item terakhir bisa discroll
        # sampai bener-bener lewat dari belakang dock.
        spacer = QListWidgetItem()
        spacer.setFlags(Qt.ItemFlag.NoItemFlags)
        spacer.setSizeHint(QSize(1, self.entry_list.bottom_reserved_height()))
        self.entry_list.addItem(spacer)
        self.entry_list.blockSignals(False)
        current = self.entry_list.currentItem()
        self._selected_id = current.data(Qt.ItemDataRole.UserRole) if current else None
        self._update_detail_panel()

    def _selected_entry(self) -> Entry | None:
        for entry in self.manager.entries:
            if entry.id == self._selected_id:
                return entry
        return None

    def _on_selection_changed(self, current: QListWidgetItem | None, _previous) -> None:
        self._selected_id = current.data(Qt.ItemDataRole.UserRole) if current else None
        self._password_visible = False
        self.show_password_button.setChecked(False)
        self._update_detail_panel()

    def _update_detail_panel(self) -> None:
        entry = self._selected_entry()
        has_entry = entry is not None
        self.detail_content.setVisible(has_entry)
        self.detail_empty_label.setVisible(not has_entry)
        self.edit_button.setEnabled(has_entry)
        self.delete_button.setEnabled(has_entry)
        self.show_password_button.setEnabled(has_entry)

        if entry is None:
            self.detail_site.setText("-")
            self.detail_username.setText("-")
            self.detail_password.setText(PASSWORD_MASK)
            self.detail_url.setText("-")
            self.detail_notes.setText("-")
            self.detail_notes.setToolTip("")
            self.detail_created.setText("-")
            self.detail_updated.setText("-")
            return

        self.detail_site.setText(entry.site)
        self.detail_username.setText(entry.username)
        self.detail_password.setText(entry.password if self._password_visible else PASSWORD_MASK)
        self.detail_url.setText(entry.url or "-")
        notes = entry.notes or "-"
        elided = self.detail_notes.fontMetrics().elidedText(
            notes, Qt.TextElideMode.ElideRight, NOTES_PREVIEW_WIDTH_PX
        )
        self.detail_notes.setText(elided)
        self.detail_notes.setToolTip(notes if notes != "-" else "")
        self.detail_created.setText(format_timestamp(entry.created_at))
        self.detail_updated.setText(format_timestamp(entry.updated_at))

    def _toggle_detail_password(self, checked: bool) -> None:
        self._password_visible = checked
        self.show_password_button.setIcon(tinted_icon("🙈" if checked else "👁", self._button_icon_color))
        self._update_detail_panel()

    def _on_add(self) -> None:
        dialog = EntryDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.manager.add_entry(dialog.result_entry)
            self._selected_id = dialog.result_entry.id
            self._refresh_list()

    def _on_edit(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        dialog = EntryDialog(entry, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            updated = dialog.result_entry
            self.manager.update_entry(
                entry.id, site=updated.site, username=updated.username,
                password=updated.password, url=updated.url, notes=updated.notes,
            )
            self._refresh_list()

    def _on_delete(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        box = QMessageBox(self)
        box.setObjectName("confirmDialog")
        tokens = DARK if is_dark_mode() else LIGHT
        box.setStyleSheet(glow_background_css(tokens, "QMessageBox#confirmDialog"))
        box.setIcon(QMessageBox.Icon.NoIcon)
        box.setWindowTitle(tr("confirm_delete_title"))
        box.setText(tr("confirm_delete_text", site=entry.site))
        cancel_button = box.addButton(tr("btn_batal"), QMessageBox.ButtonRole.NoRole)
        cancel_button.setProperty("variant", "secondary")
        delete_button = box.addButton(tr("btn_hapus"), QMessageBox.ButtonRole.YesRole)
        delete_button.setProperty("variant", "danger")
        box.setDefaultButton(cancel_button)
        box.exec()
        if box.clickedButton() is delete_button:
            self.manager.delete_entry(entry.id)
            self._selected_id = None
            self._refresh_list()

    def _on_copy_password(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        self._copy_to_clipboard(entry.password)

    def _copy_to_clipboard(self, password: str) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText(password)
        QTimer.singleShot(CLIPBOARD_CLEAR_SECONDS * 1000, lambda: self._clear_clipboard_if_unchanged(password))

    def _clear_clipboard_if_unchanged(self, password: str) -> None:
        # Jangan clear kalau user udah copy sesuatu yang lain di antara waktu itu.
        clipboard = QApplication.clipboard()
        if clipboard.text() == password:
            clipboard.clear()

    def _show_info(self, title: str, text: str) -> None:
        tokens = DARK if is_dark_mode() else LIGHT
        box = QMessageBox(self)
        box.setObjectName("confirmDialog")
        box.setStyleSheet(glow_background_css(tokens, "QMessageBox#confirmDialog"))
        box.setIcon(QMessageBox.Icon.NoIcon)
        box.setWindowTitle(title)
        box.setText(text)
        box.addButton(tr("btn_continue"), QMessageBox.ButtonRole.AcceptRole)
        box.exec()

    def _on_import(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, tr("import_file_dialog_title"), "", "Trust2Pass Vault (*.t2p)"
        )
        if not path_str:
            return
        import_path = Path(path_str)
        # `kind` dibaca dari header PLAINTEXT, gak butuh password - jadi dicek DULU sebelum
        # minta password sama sekali. Import cuma nerima file hasil fitur Export, BUKAN vault
        # biasa (walau sama-sama format .t2p dan sama-sama bisa di-unlock) - requirement eksplisit
        # biar Import gak kepake buat "nyomot" vault utama orang laen secara utuh.
        try:
            header = storage.read_header(import_path)
        except ValueError as e:
            self._show_info(tr("import_invalid_file_title"), tr("import_invalid_file_text", detail=e))
            return
        if header["kind"] != storage.KIND_EXPORT:
            self._show_info(tr("import_wrong_kind_title"), tr("import_wrong_kind_text"))
            return
        # UnlockDialog di sini minta password VAULT LAIN (bukan punya kita) - gak ada server,
        # cuma file + password, jadi ini memang satu-satunya cara "izin" buat baca isinya.
        dialog = UnlockDialog(import_path, parent=self, is_import=True)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        other_manager = dialog.manager
        try:
            picker = EntryPickerDialog(other_manager.entries, tr("import_picker_title"), parent=self)
            if picker.exec() != QDialog.DialogCode.Accepted or not picker.selected_entries:
                return
            # Laporan per-entri: duplikat PERSIS (site/username/password/url, notes/timestamp gak
            # dihitung) ditandain ✗ dan gak ikut masuk KECUALI user klik "Coba Lagi" buat maksa.
            report = ImportReportDialog(self.manager.entries, picker.selected_entries, parent=self)
            if report.exec() != QDialog.DialogCode.Accepted or not report.entries_to_insert:
                return
            # id baru per entri - entri yang diimport dianggap "salinan baru", bukan entri yang
            # sama persis (menghindari tabrakan id kalau vault sumbernya kebetulan hasil export
            # dari vault yang sama juga).
            imported = [replace(e, id=uuid.uuid4().hex) for e in report.entries_to_insert]
            self.manager.add_entries(imported)
            self._refresh_list()
        finally:
            # Zeroize vault LAIN itu sesegera mungkin, apapun hasilnya (termasuk kalau di-cancel
            # di entry picker) - gak boleh nongkrong lama-lama di memori.
            other_manager.lock()

    def _on_export(self) -> None:
        picker = EntryPickerDialog(self.manager.entries, tr("export_picker_title"), parent=self)
        if picker.exec() != QDialog.DialogCode.Accepted or not picker.selected_entries:
            return
        path_str, _ = QFileDialog.getSaveFileName(
            self, tr("export_file_dialog_title"), "export.t2p", "Trust2Pass Vault (*.t2p)"
        )
        if not path_str:
            return
        export_path = Path(path_str)
        # is_export=True - dialog KETARA beda dari "Buat Vault Baru" (judul/teks beda, tanpa
        # confirm password - lihat ui/unlock_dialog.py), dan file-nya ditandain KIND_EXPORT di
        # header biar fitur Import bisa bedain dari vault biasa.
        dialog = UnlockDialog(export_path, parent=self, is_export=True)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        export_manager = dialog.manager
        export_manager.add_entries(list(picker.selected_entries))
        export_manager.lock()
        self._show_info(
            tr("export_done_title"), tr("export_done_text", n=len(picker.selected_entries), path=str(export_path))
        )

    def _on_lock(self) -> None:
        self.manager.lock()
        self._selected_id = None
        self._password_visible = False
        self.refresh()
        self.locked.emit()


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from ui.i18n import set_language

    set_language("id")  # deterministik - gak ikut locale mesin yang jalanin self-check
    app = QApplication(sys.argv)

    with tempfile.TemporaryDirectory() as tmp:
        vault_path = Path(tmp) / "ui_test.t2p"
        manager = VaultManager()
        from crypto.kdf import MIN_MEMORY_KIB, MIN_PARALLELISM, MIN_TIME_COST
        manager.create(vault_path, b"correct horse battery staple", MIN_MEMORY_KIB, MIN_TIME_COST, MIN_PARALLELISM)
        manager.add_entry(Entry(site="github.com", username="Mar0x02", password="s3cr3t!"))
        manager.add_entry(Entry(site="example.com", username="neo", password="hunter2"))

        window = MainWindow(manager)
        assert window.entry_list.count() == 3  # 2 entri + 1 baris spacer non-selectable di akhir
        assert window.entry_list.item(0).text() == "github.com"
        assert not window.entry_list.item(0).icon().isNull()

        # Buka vault -> entri pertama auto-terpilih (panel detail gak nganggur kosong), password
        # tetap ter-mask.
        assert window._selected_entry().site == "github.com"
        assert window.detail_site.text() == "github.com"
        assert window.edit_button.isEnabled()

        window.entry_list.setCurrentRow(0)
        assert window._selected_entry().site == "github.com"
        assert window.detail_site.text() == "github.com"
        assert window.detail_password.text() == PASSWORD_MASK
        assert window.edit_button.isEnabled()

        # Toggle show password di detail panel.
        window.show_password_button.setChecked(True)
        assert window.detail_password.text() == "s3cr3t!"
        window.show_password_button.setChecked(False)
        assert window.detail_password.text() == PASSWORD_MASK

        # Ganti seleksi -> show-password harus reset ke hidden (jangan bocor ke entri lain).
        window.show_password_button.setChecked(True)
        window.entry_list.setCurrentRow(1)
        assert not window.show_password_button.isChecked()
        assert window.detail_password.text() == PASSWORD_MASK

        # Search filter: cuma cocok 1 entri.
        window.search_input.setText("github")
        assert window.entry_list.count() == 2  # 1 entri cocok + 1 spacer
        assert window.entry_list.item(0).text() == "github.com"
        window.search_input.setText("")
        assert window.entry_list.count() == 3

        # Copy password (dari detail panel) -> clipboard keisi, auto-clear logic jalan.
        window.entry_list.setCurrentRow(0)
        window._on_copy_password()
        assert QApplication.clipboard().text() == "s3cr3t!"
        window._clear_clipboard_if_unchanged("s3cr3t!")
        assert QApplication.clipboard().text() == ""

        # Tapi kalau clipboard udah diubah user, auto-clear TIDAK boleh nimpa yang baru.
        window._on_copy_password()
        QApplication.clipboard().setText("sesuatu yang lain")
        window._clear_clipboard_if_unchanged("s3cr3t!")
        assert QApplication.clipboard().text() == "sesuatu yang lain"

        # EntryDialog: validasi per-field wajib.
        dialog = EntryDialog(parent=window)
        dialog._on_save()
        assert dialog.result_entry is None
        # isVisibleTo (bukan isVisible) karena dialog ini gak di-show() beneran di self-check -
        # isVisible() selalu False buat widget yang top-level-nya belum tampil di layar.
        assert dialog.site_hint.isVisibleTo(dialog) and "username" not in dialog.site_hint.text()
        assert dialog.username_hint.isVisibleTo(dialog)
        assert dialog.password_hint.isVisibleTo(dialog)
        dialog.username_input.setText("u")
        assert not dialog.username_hint.isVisibleTo(dialog)  # hint ilang begitu mulai ngetik

        # EntryDialog: generate password harus isi field & toggle ke visible.
        dialog.site_input.setText("test.com")
        dialog.username_input.setText("u")
        dialog._on_generate()
        assert len(dialog.password_input.text()) == 16
        assert dialog.toggle_button.isChecked()
        dialog._on_save()
        assert dialog.result_entry is not None
        assert dialog.result_entry.site == "test.com"

        # Edit lewat manager langsung (tanpa modal) lalu refresh harus kebawa ke sidebar.
        target_id = manager.entries[1].id
        manager.update_entry(target_id, site="updated.com")
        window.refresh()
        assert any(e.site == "updated.com" for e in manager.entries)

        # Lock -> manager locked, signal "locked" harus ke-emit, panel/list ke-clear.
        got_signal = []
        window.locked.connect(lambda: got_signal.append(True))
        window._on_lock()
        assert not manager.is_unlocked
        assert got_signal == [True]
        assert window.entry_list.count() == 1  # 0 entri + 1 spacer
        assert window.detail_site.text() == "-"
        assert window.detail_empty_label.isVisibleTo(window) and not window.detail_content.isVisibleTo(window)

    print("main_window.py self-check OK")
