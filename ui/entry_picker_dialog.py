"""Dialog checklist pilih entri - dipakai bareng buat Import & Export (lihat main_window.py).
Satu dialog generik: caller yang nentuin entri mana yang ditampilin (entri vault lain buat
Import, entri vault sendiri buat Export)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout

from ui.i18n import tr
from ui.theme import DARK, LIGHT, glow_background_css, is_dark_mode
from vault.models import Entry


class EntryPickerDialog(QDialog):
    """Sukses -> self.selected_entries terisi entri yang di-checklist (subset dari `entries`)."""

    def __init__(self, entries: list[Entry], title: str, parent=None) -> None:
        super().__init__(parent)
        self._entries = entries
        self.selected_entries: list[Entry] = []

        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumSize(360, 420)
        self.setObjectName("entryPickerDialog")
        tokens = DARK if is_dark_mode() else LIGHT
        self.setStyleSheet(glow_background_css(tokens, "QDialog#entryPickerDialog"))

        self.list_widget = QListWidget()
        for entry in entries:
            item = QListWidgetItem(f"{entry.site} ({entry.username})")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.list_widget.addItem(item)

        select_all_button = QPushButton(tr("btn_select_all"))
        select_all_button.setProperty("variant", "secondary")
        select_all_button.clicked.connect(lambda: self._set_all_checked(True))
        select_none_button = QPushButton(tr("btn_select_none"))
        select_none_button.setProperty("variant", "secondary")
        select_none_button.clicked.connect(lambda: self._set_all_checked(False))

        select_row = QHBoxLayout()
        select_row.addWidget(select_all_button)
        select_row.addWidget(select_none_button)
        select_row.addStretch()

        cancel_button = QPushButton(tr("btn_batal"))
        cancel_button.setProperty("variant", "secondary")
        cancel_button.clicked.connect(self.reject)
        confirm_button = QPushButton(tr("btn_continue"))
        confirm_button.clicked.connect(self._on_confirm)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(confirm_button)

        layout = QVBoxLayout(self)
        layout.addLayout(select_row)
        layout.addWidget(self.list_widget)
        layout.addLayout(button_row)

    def _set_all_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(state)

    def _on_confirm(self) -> None:
        self.selected_entries = [
            entry
            for i, entry in enumerate(self._entries)
            if self.list_widget.item(i).checkState() == Qt.CheckState.Checked
        ]
        self.accept()


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    entries = [
        Entry(site="github.com", username="a", password="pa"),
        Entry(site="google.com", username="b", password="pb"),
        Entry(site="example.com", username="c", password="pc"),
    ]

    dlg = EntryPickerDialog(entries, "Pilih Entri buat Diimport")
    assert dlg.list_widget.count() == 3
    # Default-nya semua ke-checklist.
    dlg._on_confirm()
    assert len(dlg.selected_entries) == 3

    dlg2 = EntryPickerDialog(entries, "Pilih Entri buat Diexport")
    dlg2._set_all_checked(False)
    dlg2.list_widget.item(1).setCheckState(Qt.CheckState.Checked)
    dlg2._on_confirm()
    assert [e.site for e in dlg2.selected_entries] == ["google.com"]

    print("entry_picker_dialog.py self-check OK")
