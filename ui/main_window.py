"""Window utama: daftar entri, CRUD, auto-lock."""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from generator import generate_password
from vault.manager import VaultManager
from vault.models import Entry

CLIPBOARD_CLEAR_SECONDS = 20
PASSWORD_MASK = "••••••••"
COLUMNS = ("Situs", "Username", "Password", "URL")


class EntryDialog(QDialog):
    """Form tambah/edit satu entri. Sukses -> self.result_entry (Entry) siap dipakai caller."""

    def __init__(self, entry: Entry | None = None, parent=None) -> None:
        super().__init__(parent)
        self._entry_id = entry.id if entry else None
        self.result_entry: Entry | None = None

        self.setWindowTitle("Edit Entri" if entry else "Tambah Entri")
        self.setModal(True)

        self.site_input = QLineEdit(entry.site if entry else "")
        self.username_input = QLineEdit(entry.username if entry else "")
        self.url_input = QLineEdit(entry.url if entry else "")
        self.notes_input = QTextEdit(entry.notes if entry else "")

        self.password_input = QLineEdit(entry.password if entry else "")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.toggle_button = QPushButton("Show")
        self.toggle_button.setCheckable(True)
        self.toggle_button.toggled.connect(self._toggle_password_visibility)
        self.generate_button = QPushButton("Generate")
        self.generate_button.clicked.connect(self._on_generate)

        password_row = QHBoxLayout()
        password_row.addWidget(self.password_input)
        password_row.addWidget(self.toggle_button)
        password_row.addWidget(self.generate_button)

        form = QFormLayout()
        form.addRow("Situs:", self.site_input)
        form.addRow("Username:", self.username_input)
        form.addRow("Password:", password_row)
        form.addRow("URL:", self.url_input)
        form.addRow("Catatan:", self.notes_input)

        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: #D9534F;")

        save_button = QPushButton("Simpan")
        save_button.clicked.connect(self._on_save)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addWidget(save_button)

    def _toggle_password_visibility(self, checked: bool) -> None:
        self.password_input.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)
        self.toggle_button.setText("Hide" if checked else "Show")

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
    """Dashboard vault. Hanya dibuat setelah VaultManager unlocked (Confidentiality gate)."""

    locked = Signal()

    def __init__(self, manager: VaultManager, parent=None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle(f"Trust2Pass - {manager.path.name}")

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._on_edit)

        add_button = QPushButton("Tambah")
        add_button.clicked.connect(self._on_add)
        edit_button = QPushButton("Edit")
        edit_button.clicked.connect(self._on_edit)
        delete_button = QPushButton("Hapus")
        delete_button.clicked.connect(self._on_delete)
        copy_button = QPushButton("Copy Password")
        copy_button.clicked.connect(self._on_copy_password)
        lock_button = QPushButton("Lock")
        lock_button.clicked.connect(self._on_lock)

        toolbar = QHBoxLayout()
        for button in (add_button, edit_button, delete_button, copy_button, lock_button):
            toolbar.addWidget(button)

        layout = QVBoxLayout(self)
        layout.addLayout(toolbar)
        layout.addWidget(self.table)

        self.refresh()

    def refresh(self) -> None:
        self.table.setRowCount(len(self.manager.entries))
        for row, entry in enumerate(self.manager.entries):
            self.table.setItem(row, 0, QTableWidgetItem(entry.site))
            self.table.setItem(row, 1, QTableWidgetItem(entry.username))
            self.table.setItem(row, 2, QTableWidgetItem(PASSWORD_MASK))
            self.table.setItem(row, 3, QTableWidgetItem(entry.url))

    def _selected_entry(self) -> Entry | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.manager.entries):
            return None
        return self.manager.entries[row]

    def _on_add(self) -> None:
        dialog = EntryDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.manager.add_entry(dialog.result_entry)
            self.refresh()

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
            self.refresh()

    def _on_delete(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        confirm = QMessageBox.question(self, "Hapus Entri", f"Hapus entri '{entry.site}'?")
        if confirm == QMessageBox.StandardButton.Yes:
            self.manager.delete_entry(entry.id)
            self.refresh()

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
        assert window.table.rowCount() == 2
        assert window.table.item(0, 0).text() == "github.com"
        assert window.table.item(0, 2).text() == PASSWORD_MASK  # password harus ter-mask di tabel

        # Copy password -> clipboard keisi, lalu "timeout" logic harus clear kalau belum diubah.
        window.table.setCurrentCell(0, 0)
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

        # Edit lewat manager langsung (tanpa modal) lalu refresh harus kebawa ke tabel.
        target_id = manager.entries[1].id
        manager.update_entry(target_id, site="updated.com")
        window.refresh()
        assert window.table.item(1, 0).text() == "updated.com"

        # Lock -> manager locked, signal "locked" harus ke-emit.
        got_signal = []
        window.locked.connect(lambda: got_signal.append(True))
        window._on_lock()
        assert not manager.is_unlocked
        assert got_signal == [True]
        assert window.table.rowCount() == 0  # entries udah di-clear manager.lock()

    print("main_window.py self-check OK")
