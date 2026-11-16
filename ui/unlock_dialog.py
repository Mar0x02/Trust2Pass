"""Dialog unlock vault (input master password)."""

from pathlib import Path

from cryptography.exceptions import InvalidTag
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ui.theme import DARK, LIGHT, is_dark_mode, tinted_icon
from vault.manager import VaultManager

MIN_PASSWORD_LEN = 8
ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "icon-rounded.png"


class UnlockDialog(QDialog):
    """Buka vault yang sudah ada, atau buat vault baru kalau `vault_path` belum ada.

    Sukses -> self.manager (VaultManager) sudah unlocked dan siap dipakai caller.
    """

    def __init__(self, vault_path: Path, parent=None) -> None:
        super().__init__(parent)
        self.vault_path = Path(vault_path)
        self.manager = VaultManager()
        self._is_new = not self.vault_path.exists()
        # Semua QPushButton di app ini punya background accent (lihat theme.py), jadi
        # ikon tombol disamakan warnanya dengan label tombol (selection_text), bukan teks halaman.
        self._button_icon_color = (DARK if is_dark_mode() else LIGHT)["selection_text"]

        self.setWindowTitle("Buat Vault Baru" if self._is_new else "Buka Vault")
        self.setModal(True)
        self.setMinimumWidth(360)

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

        subtitle_label = QLabel("Buat Master Password Baru" if self._is_new else "Credential Manager")
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle_label.setStyleSheet("color: #6B7280;")

        password_label = QLabel("Master Password")

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.returnPressed.connect(self._on_submit)

        self.password_toggle = QPushButton()
        self.password_toggle.setIcon(tinted_icon("👁", self._button_icon_color))
        self.password_toggle.setIconSize(QSize(18, 18))
        self.password_toggle.setCheckable(True)
        self.password_toggle.setFixedWidth(36)
        self.password_toggle.toggled.connect(self._toggle_password_visibility)

        password_row = QHBoxLayout()
        password_row.addWidget(self.password_input)
        password_row.addWidget(self.password_toggle)

        self.confirm_input = None
        confirm_label = None
        if self._is_new:
            confirm_label = QLabel("Konfirmasi Master Password")
            self.confirm_input = QLineEdit()
            self.confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.confirm_input.returnPressed.connect(self._on_submit)

        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: #D9534F;")
        self.error_label.setWordWrap(True)

        self.submit_button = QPushButton("Buat Vault" if self._is_new else "Unlock")
        self.submit_button.clicked.connect(self._on_submit)

        self.status_label = QLabel("Status: Belum ada vault" if self._is_new else "Status: Vault locked")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #6B7280; font-size: 11px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(10)
        layout.addWidget(icon_label)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addSpacing(12)
        layout.addWidget(password_label)
        layout.addLayout(password_row)
        if confirm_label is not None:
            layout.addWidget(confirm_label)
            layout.addWidget(self.confirm_input)
        layout.addWidget(self.error_label)
        layout.addWidget(self.submit_button)
        layout.addSpacing(8)
        layout.addWidget(self.status_label)

    def _toggle_password_visibility(self, checked: bool) -> None:
        self.password_input.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)
        self.password_toggle.setIcon(tinted_icon("🙈" if checked else "👁", self._button_icon_color))

    def _on_submit(self) -> None:
        password_str = self.password_input.text()
        if not password_str:
            self.error_label.setText("Password tidak boleh kosong.")
            return

        if self._is_new:
            if password_str != self.confirm_input.text():
                self.error_label.setText("Konfirmasi password tidak cocok.")
                return
            if len(password_str) < MIN_PASSWORD_LEN:
                self.error_label.setText(f"Master password minimal {MIN_PASSWORD_LEN} karakter.")
                return

        password_bytes = password_str.encode("utf-8")
        # Best-effort: hapus dari widget sesegera mungkin. str Python di atas tetap
        # immutable di memori (lihat crypto/memory.py) - keterbatasan yang didokumentasikan.
        self.password_input.clear()
        if self.confirm_input is not None:
            self.confirm_input.clear()

        try:
            if self._is_new:
                self.manager.create(self.vault_path, password_bytes)
            else:
                self.manager.unlock(self.vault_path, password_bytes)
        except InvalidTag:
            self.error_label.setText("Password salah.")
            self.status_label.setText("Status: Vault locked")
            return
        except ValueError as e:
            self.error_label.setText(f"Vault rusak atau tidak valid: {e}")
            return

        self.status_label.setText("Status: Vault unlocked")
        self.accept()


if __name__ == "__main__":
    import sys
    import tempfile

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    with tempfile.TemporaryDirectory() as tmp:
        vault_path = Path(tmp) / "ui_test.t2p"

        # Skenario 1: vault belum ada -> mode create, password mismatch harus ditolak dulu.
        dlg = UnlockDialog(vault_path)
        assert dlg._is_new
        assert dlg.status_label.text() == "Status: Belum ada vault"
        dlg.password_input.setText("correct horse battery staple")
        dlg.confirm_input.setText("beda")
        dlg._on_submit()
        assert not dlg.manager.is_unlocked
        assert "cocok" in dlg.error_label.text()

        dlg.confirm_input.setText("correct horse battery staple")
        dlg._on_submit()
        assert dlg.manager.is_unlocked
        assert vault_path.exists()
        assert dlg.status_label.text() == "Status: Vault unlocked"

        # Toggle show/hide password.
        dlg.password_toggle.setChecked(True)
        assert dlg.password_input.echoMode() == QLineEdit.EchoMode.Normal
        assert not dlg.password_toggle.icon().isNull()
        dlg.password_toggle.setChecked(False)
        assert dlg.password_input.echoMode() == QLineEdit.EchoMode.Password

        # Skenario 2: vault sudah ada -> mode unlock (tanpa konfirmasi), password salah ditolak.
        dlg2 = UnlockDialog(vault_path)
        assert not dlg2._is_new
        assert dlg2.confirm_input is None
        assert dlg2.status_label.text() == "Status: Vault locked"
        dlg2.password_input.setText("password salah")
        dlg2._on_submit()
        assert not dlg2.manager.is_unlocked
        assert "salah" in dlg2.error_label.text()
        assert dlg2.status_label.text() == "Status: Vault locked"

        # Skenario 3: password benar -> unlock sukses.
        dlg3 = UnlockDialog(vault_path)
        dlg3.password_input.setText("correct horse battery staple")
        dlg3._on_submit()
        assert dlg3.manager.is_unlocked
        assert dlg3.status_label.text() == "Status: Vault unlocked"

    print("unlock_dialog.py self-check OK")
