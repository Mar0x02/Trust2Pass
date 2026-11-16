"""Window utama: daftar entri (sidebar + panel detail), CRUD, auto-lock."""

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFormLayout,
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
from ui.glass import GlassListWidget, GlassPanel
from ui.theme import DARK, LIGHT, glow_background_css, is_dark_mode, tinted_icon
from vault.manager import VaultManager
from vault.models import Entry

CLIPBOARD_CLEAR_SECONDS = 20
PASSWORD_MASK = "••••••••"
ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "icon-rounded.png"


class EntryDialog(QDialog):
    """Form tambah/edit satu entri. Sukses -> self.result_entry (Entry) siap dipakai caller."""

    def __init__(self, entry: Entry | None = None, parent=None) -> None:
        super().__init__(parent)
        self._entry_id = entry.id if entry else None
        self.result_entry: Entry | None = None
        tokens = DARK if is_dark_mode() else LIGHT
        self._button_icon_color = tokens["selection_text"]

        self.setWindowTitle("Edit Entri" if entry else "Tambah Entri")
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
        self.generate_button.setIcon(tinted_icon("🎲", self._button_icon_color))
        self.generate_button.setIconSize(QSize(18, 18))
        self.generate_button.setFixedWidth(36)
        self.generate_button.clicked.connect(self._on_generate)

        password_row = QHBoxLayout()
        password_row.addWidget(self.password_input)
        password_row.addWidget(self.toggle_button)
        password_row.addWidget(self.generate_button)

        form = QFormLayout()
        form.addRow("Nama:", self.site_input)
        form.addRow("Username:", self.username_input)
        form.addRow("Password:", password_row)
        form.addRow("URL:", self.url_input)
        form.addRow("Catatan:", self.notes_input)

        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: #D9534F;")

        cancel_button = QPushButton("Batal")
        cancel_button.clicked.connect(self.reject)
        save_button = QPushButton("Simpan")
        save_button.clicked.connect(self._on_save)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(save_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error_label)
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
        if not site or not username or not password:
            self.error_label.setText("Situs, username, dan password wajib diisi.")
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
        self.search_input.setPlaceholderText("Cari...")
        self.search_input.addAction(
            tinted_icon("🔍", self._muted_icon_color), QLineEdit.ActionPosition.LeadingPosition
        )
        self.search_input.textChanged.connect(self._refresh_list)

        lock_button = QPushButton(" Lock")
        lock_button.setIcon(tinted_icon("🔒", self._button_icon_color))
        lock_button.setIconSize(QSize(16, 16))
        lock_button.clicked.connect(self._on_lock)

        top_bar = QHBoxLayout()
        top_bar.addWidget(icon_label)
        top_bar.addWidget(title_label)
        top_bar.addWidget(self.search_input, stretch=1)
        top_bar.addWidget(lock_button)

        # --- sidebar (daftar entri) ---
        # List diisi full-height (bukan dipotong layout) - tombol tambah NEMPEL ngambang langsung
        # di atasnya (tanpa panel/backdrop di belakangnya - cuma tombolnya doang yang melayang),
        # supaya item yang di-scroll tetap kebaca sampai ke batas bawah list.
        self.entry_list = GlassListWidget(
            tokens["glow"], tokens["bg"], glass_tint, glass_border, radius=14, blur_radius=30
        )
        self.entry_list.setObjectName("entryList")
        self.entry_list.currentItemChanged.connect(self._on_selection_changed)

        add_button = QPushButton(" Tambah Entri")
        add_button.setIcon(tinted_icon("➕", self._button_icon_color))
        add_button.setIconSize(QSize(14, 14))
        add_button.clicked.connect(self._on_add)
        self.entry_list.attach_floating(add_button, margin=10)

        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.addWidget(self.entry_list)

        # --- panel detail ---
        detail_header = QLabel("DETAIL ENTRI")
        detail_header.setStyleSheet("font-weight: bold; color: #6B7280;")
        self.edit_button = QPushButton()
        self.edit_button.setIcon(tinted_icon("✏️", self._button_icon_color))
        self.edit_button.setIconSize(QSize(18, 18))
        self.edit_button.setFixedWidth(36)
        self.edit_button.clicked.connect(self._on_edit)
        self.delete_button = QPushButton()
        self.delete_button.setIcon(tinted_icon("🗑️", self._button_icon_color))
        self.delete_button.setIconSize(QSize(18, 18))
        self.delete_button.setFixedWidth(36)
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
        self.detail_notes.setWordWrap(True)
        self.detail_created = QLabel("-")
        self.detail_updated = QLabel("-")

        self.show_password_button = QPushButton()
        self.show_password_button.setIcon(tinted_icon("👁", self._button_icon_color))
        self.show_password_button.setIconSize(QSize(18, 18))
        self.show_password_button.setFixedWidth(36)
        self.show_password_button.setCheckable(True)
        self.show_password_button.toggled.connect(self._toggle_detail_password)
        copy_password_button = QPushButton()
        copy_password_button.setIcon(tinted_icon("📋", self._button_icon_color))
        copy_password_button.setIconSize(QSize(18, 18))
        copy_password_button.setFixedWidth(36)
        copy_password_button.clicked.connect(self._on_copy_password)

        password_row = QHBoxLayout()
        password_row.addWidget(self.detail_password, stretch=1)
        password_row.addWidget(self.show_password_button)
        password_row.addWidget(copy_password_button)

        detail_form = QFormLayout()
        detail_form.addRow("Nama:", self.detail_site)
        detail_form.addRow("Username:", self.detail_username)
        detail_form.addRow("Password:", password_row)
        detail_form.addRow("URL:", self.detail_url)
        detail_form.addRow("Catatan:", self.detail_notes)
        detail_form.addRow("Dibuat:", self.detail_created)
        detail_form.addRow("Diubah:", self.detail_updated)

        detail_panel = GlassPanel(tokens["glow"], tokens["bg"], glass_tint, glass_border, radius=14, blur_radius=30)
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(16, 16, 16, 16)
        detail_layout.addLayout(detail_header_row)
        detail_layout.addLayout(detail_form)
        detail_layout.addStretch()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(16)
        splitter.addWidget(sidebar)
        splitter.addWidget(detail_panel)
        splitter.setSizes([220, 480])

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

    def refresh(self) -> None:
        self._refresh_list()

    def _refresh_list(self) -> None:
        self.entry_list.blockSignals(True)
        self.entry_list.clear()
        for entry in self._visible_entries():
            item = QListWidgetItem(tinted_icon("🌐", self._page_icon_color, boost=2.4), entry.site)
            item.setData(Qt.ItemDataRole.UserRole, entry.id)
            self.entry_list.addItem(item)
            if entry.id == self._selected_id:
                self.entry_list.setCurrentItem(item)
        # Baris kosong non-selectable di akhir, setinggi dock tombol tambah - tanpa ini, scroll
        # mentok begitu item terakhir baru nyentuh tepi atas dock, padahal dock masih nutupin
        # separuh baris itu (susah diklik). Dengan baris kosong ini, item terakhir bisa discroll
        # sampai bener-bener lewat dari belakang dock.
        spacer = QListWidgetItem()
        spacer.setFlags(Qt.ItemFlag.NoItemFlags)
        spacer.setSizeHint(QSize(1, self.entry_list.bottom_reserved_height()))
        self.entry_list.addItem(spacer)
        self.entry_list.blockSignals(False)
        if self.entry_list.currentItem() is None:
            self._selected_id = None
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
        self.edit_button.setEnabled(has_entry)
        self.delete_button.setEnabled(has_entry)
        self.show_password_button.setEnabled(has_entry)

        if entry is None:
            self.detail_site.setText("-")
            self.detail_username.setText("-")
            self.detail_password.setText(PASSWORD_MASK)
            self.detail_url.setText("-")
            self.detail_notes.setText("-")
            self.detail_created.setText("-")
            self.detail_updated.setText("-")
            return

        self.detail_site.setText(entry.site)
        self.detail_username.setText(entry.username)
        self.detail_password.setText(entry.password if self._password_visible else PASSWORD_MASK)
        self.detail_url.setText(entry.url or "-")
        self.detail_notes.setText(entry.notes or "-")
        self.detail_created.setText(entry.created_at)
        self.detail_updated.setText(entry.updated_at)

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
        confirm = QMessageBox.question(self, "Hapus Entri", f"Hapus entri '{entry.site}'?")
        if confirm == QMessageBox.StandardButton.Yes:
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

        # Belum ada seleksi -> panel detail kosong, edit/delete/show disabled.
        assert window.detail_site.text() == "-"
        assert not window.edit_button.isEnabled()

        # Pilih entri pertama -> panel detail keisi, password tetap ter-mask.
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

        # EntryDialog: validasi field wajib.
        dialog = EntryDialog(parent=window)
        dialog._on_save()
        assert dialog.result_entry is None
        assert "wajib" in dialog.error_label.text()

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

    print("main_window.py self-check OK")
