"""Dialog pemilihan lokasi vault (branded), pengganti native file dialog telanjang."""

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QFileDialog, QLabel, QPushButton, QVBoxLayout

from ui.i18n import tr
from ui.theme import DARK, LIGHT, glow_background_css, is_dark_mode, tinted_icon

ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "icon-rounded.png"


class VaultPickerDialog(QDialog):
    """Tampilan pertama sebelum ada vault yang dikenal (belum ada `last_vault_path`).

    Sukses -> self.vault_path terisi (bisa vault lama yang mau dibuka, atau path baru
    yang belum ada file-nya untuk dibuat).
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.vault_path: Path | None = None

        self.setWindowTitle("Trust2Pass")
        self.setModal(True)
        self.setMinimumWidth(360)
        self.setObjectName("vaultPicker")

        tokens = DARK if is_dark_mode() else LIGHT
        self.setStyleSheet(glow_background_css(tokens, "QDialog#vaultPicker"))

        icon_label = QLabel()
        pixmap = QPixmap(str(ICON_PATH))
        if not pixmap.isNull():
            icon_label.setPixmap(
                pixmap.scaled(72, 72, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_label = QLabel("Trust2Pass")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 20px; font-weight: bold;")

        subtitle_label = QLabel(tr("vault_picker_subtitle"))
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle_label.setStyleSheet("color: #6B7280;")

        # Tombol ini punya background accent (biru) dari style global, jadi ikon disamakan
        # warnanya dengan label tombol (selection_text), bukan teks halaman.
        button_icon_color = tokens["selection_text"]

        self.open_button = QPushButton(tr("btn_open_existing"))
        self.open_button.setIcon(tinted_icon("📂", button_icon_color))
        self.open_button.setIconSize(QSize(18, 18))
        self.open_button.clicked.connect(self._on_open_existing)

        self.new_button = QPushButton(tr("btn_new_vault"))
        self.new_button.setIcon(tinted_icon("➕", button_icon_color))
        self.new_button.setIconSize(QSize(18, 18))
        self.new_button.clicked.connect(self._on_create_new)

        self.status_label = QLabel(tr("vault_picker_status_empty"))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #6B7280; font-size: 11px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(10)
        layout.addWidget(icon_label)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addSpacing(12)
        layout.addWidget(self.open_button)
        layout.addWidget(self.new_button)
        layout.addSpacing(8)
        layout.addWidget(self.status_label)

    def _on_open_existing(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, tr("file_dialog_open_title"), "", "Trust2Pass Vault (*.t2p)"
        )
        if not path_str:
            return
        self.vault_path = Path(path_str)
        self.accept()

    def _on_create_new(self) -> None:
        path_str, _ = QFileDialog.getSaveFileName(
            self, tr("file_dialog_save_title"), "trust2pass.t2p", "Trust2Pass Vault (*.t2p)"
        )
        if not path_str:
            return
        self.vault_path = Path(path_str)
        self.accept()


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    from ui.i18n import set_language

    set_language("id")  # deterministik - gak ikut locale mesin yang jalanin self-check
    app = QApplication(sys.argv)

    dlg = VaultPickerDialog()
    assert dlg.vault_path is None
    assert dlg.status_label.text() == "Status: Belum ada vault dipilih"
    assert dlg.open_button.text().endswith("Buka Vault yang Ada")
    assert dlg.new_button.text().endswith("Buat Vault Baru")

    print("vault_picker_dialog.py self-check OK")
