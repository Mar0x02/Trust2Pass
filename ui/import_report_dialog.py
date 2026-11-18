"""Laporan hasil Import per-entri: ✓ (aman, langsung masuk) / ✗ (duplikat persis - site,
username, password & URL sama kayak entri yang udah ada; notes/created_at/updated_at TIDAK
dihitung), dengan tombol "Coba Lagi" buat tetap maksa masukin walau duplikat.

Dipakai dari ui/main_window.py _on_import, SEBELUM entri beneran ditulis ke vault aktif - caller
yang nulis `self.entries_to_insert` ke VaultManager.add_entries() setelah dialog ini di-accept.
"""

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ui.i18n import tr
from ui.theme import DARK, LIGHT, glow_background_css, is_dark_mode
from vault.models import Entry

SUCCESS_COLOR = "#4CAF50"
FORCED_COLOR = "#E6A23C"


def _is_duplicate_of(existing: Entry, candidate: Entry) -> bool:
    """Sama persis di luar notes/created_at/updated_at - itu kriteria yang diminta, BUKAN
    perbandingan id (id baru selalu digenerate ulang pas import, lihat main_window.py)."""
    return (existing.site, existing.username, existing.password, existing.url) == (
        candidate.site, candidate.username, candidate.password, candidate.url
    )


class ImportReportDialog(QDialog):
    """Sukses -> self.entries_to_insert isinya entri yang harus ditulis ke vault aktif (yang gak
    duplikat + yang di-"Coba Lagi" paksa)."""

    def __init__(self, existing_entries: list[Entry], candidates: list[Entry], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("import_report_title"))
        self.setModal(True)
        self.setMinimumSize(440, 420)
        self.setObjectName("importReportDialog")
        tokens = DARK if is_dark_mode() else LIGHT
        self._danger_color = tokens["danger"]
        self.setStyleSheet(glow_background_css(tokens, "QDialog#importReportDialog"))

        self._candidates = candidates
        self._force = [False] * len(candidates)
        self._is_duplicate = [
            any(_is_duplicate_of(e, candidate) for e in existing_entries) for candidate in candidates
        ]
        self.entries_to_insert: list[Entry] = []

        self._icon_labels: list[QLabel] = []
        self._reason_labels: list[QLabel] = []
        self._retry_buttons: list[QPushButton] = []

        rows_container = QWidget()
        rows_layout = QVBoxLayout(rows_container)
        for i, candidate in enumerate(candidates):
            icon_label = QLabel()
            icon_label.setFixedWidth(20)
            text_label = QLabel(f"{candidate.site} ({candidate.username})")

            retry_button = QPushButton(tr("btn_try_again"))
            retry_button.setProperty("variant", "secondary")
            retry_button.clicked.connect(lambda checked, idx=i: self._on_retry(idx))

            top_row = QHBoxLayout()
            top_row.addWidget(icon_label)
            top_row.addWidget(text_label, 1)
            top_row.addWidget(retry_button)

            reason_label = QLabel()
            reason_label.setWordWrap(True)
            reason_label.setContentsMargins(26, 0, 0, 0)

            self._icon_labels.append(icon_label)
            self._reason_labels.append(reason_label)
            self._retry_buttons.append(retry_button)

            rows_layout.addLayout(top_row)
            rows_layout.addWidget(reason_label)
            self._refresh_row(i)
        rows_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(rows_container)

        done_button = QPushButton(tr("btn_done"))
        done_button.clicked.connect(self._on_done)
        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(done_button)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll)
        layout.addLayout(button_row)

    def _refresh_row(self, index: int) -> None:
        duplicate = self._is_duplicate[index]
        forced = self._force[index]
        icon_label = self._icon_labels[index]
        reason_label = self._reason_labels[index]
        retry_button = self._retry_buttons[index]

        if not duplicate:
            icon_label.setStyleSheet(f"color: {SUCCESS_COLOR}; font-weight: bold; font-size: 14px;")
            icon_label.setText("✓")
            reason_label.setVisible(False)
            retry_button.setVisible(False)
        elif forced:
            icon_label.setStyleSheet(f"color: {FORCED_COLOR}; font-weight: bold; font-size: 14px;")
            icon_label.setText("✓")
            reason_label.setText(tr("import_forced_reason"))
            reason_label.setStyleSheet(f"color: {FORCED_COLOR}; font-size: 11px;")
            reason_label.setVisible(True)
            retry_button.setVisible(False)
        else:
            icon_label.setStyleSheet(f"color: {self._danger_color}; font-weight: bold; font-size: 14px;")
            icon_label.setText("✗")
            reason_label.setText(tr("import_duplicate_reason"))
            reason_label.setStyleSheet(f"color: {self._danger_color}; font-size: 11px;")
            reason_label.setVisible(True)
            retry_button.setVisible(True)

    def _on_retry(self, index: int) -> None:
        self._force[index] = True
        self._refresh_row(index)

    def _on_done(self) -> None:
        self.entries_to_insert = [
            candidate for i, candidate in enumerate(self._candidates)
            if not self._is_duplicate[i] or self._force[i]
        ]
        self.accept()


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    from ui.i18n import set_language

    set_language("id")
    app = QApplication(sys.argv)

    existing = [Entry(site="github.com", username="me", password="p1", url="github.com")]
    candidates = [
        Entry(site="new.com", username="me", password="pnew", url=""),  # aman, beda
        Entry(site="github.com", username="me", password="p1", url="github.com", notes="beda notes gapapa"),  # duplikat persis
    ]

    dlg = ImportReportDialog(existing, candidates)
    assert dlg._is_duplicate == [False, True]
    assert dlg._icon_labels[0].text() == "✓"
    assert dlg._icon_labels[1].text() == "✗"
    # isVisibleTo (bukan isVisible) karena dialog ini gak di-show() beneran di self-check.
    assert dlg._retry_buttons[1].isVisibleTo(dlg)
    assert not dlg._retry_buttons[0].isVisibleTo(dlg)

    # Belum di-"Coba Lagi" -> yang duplikat GAK ikut ke-insert.
    dlg._on_done()
    assert [e.site for e in dlg.entries_to_insert] == ["new.com"]

    # Coba Lagi -> dipaksa masukin juga.
    dlg2 = ImportReportDialog(existing, candidates)
    dlg2._on_retry(1)
    assert dlg2._icon_labels[1].text() == "✓"
    dlg2._on_done()
    assert sorted(e.site for e in dlg2.entries_to_insert) == ["github.com", "new.com"]

    print("import_report_dialog.py self-check OK")
