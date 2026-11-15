"""Dialog unlock vault (input master password)."""

from pathlib import Path

from cryptography.exceptions import InvalidTag
from PySide6.QtWidgets import QDialog, QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from vault.manager import VaultManager

MIN_PASSWORD_LEN = 8


class UnlockDialog(QDialog):
    """Buka vault yang sudah ada, atau buat vault baru kalau `vault_path` belum ada.

    Sukses -> self.manager (VaultManager) sudah unlocked dan siap dipakai caller.
    """

    def __init__(self, vault_path: Path, parent=None) -> None:
        super().__init__(parent)
        self.vault_path = Path(vault_path)
        self.manager = VaultManager()
        self._is_new = not self.vault_path.exists()

        self.setWindowTitle("Buat Vault Baru" if self._is_new else "Buka Vault")
        self.setModal(True)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.returnPressed.connect(self._on_submit)

        form = QFormLayout()
        form.addRow("Master Password:", self.password_input)

        self.confirm_input = None
        if self._is_new:
            self.confirm_input = QLineEdit()
            self.confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.confirm_input.returnPressed.connect(self._on_submit)
            form.addRow("Konfirmasi:", self.confirm_input)

        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: #D9534F;")
        self.error_label.setWordWrap(True)

        self.submit_button = QPushButton("Buat Vault" if self._is_new else "Buka")
        self.submit_button.clicked.connect(self._on_submit)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addWidget(self.submit_button)

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
            return
        except ValueError as e:
            self.error_label.setText(f"Vault rusak atau tidak valid: {e}")
            return

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
        dlg.password_input.setText("correct horse battery staple")
        dlg.confirm_input.setText("beda")
        dlg._on_submit()
        assert not dlg.manager.is_unlocked
        assert "cocok" in dlg.error_label.text()

        dlg.confirm_input.setText("correct horse battery staple")
        dlg._on_submit()
        assert dlg.manager.is_unlocked
        assert vault_path.exists()

        # Skenario 2: vault sudah ada -> mode unlock, password salah harus ditolak.
        dlg2 = UnlockDialog(vault_path)
        assert not dlg2._is_new
        assert dlg2.confirm_input is None
        dlg2.password_input.setText("password salah")
        dlg2._on_submit()
        assert not dlg2.manager.is_unlocked
        assert "salah" in dlg2.error_label.text()

        # Skenario 3: password benar -> unlock sukses.
        dlg3 = UnlockDialog(vault_path)
        dlg3.password_input.setText("correct horse battery staple")
        dlg3._on_submit()
        assert dlg3.manager.is_unlocked

    print("unlock_dialog.py self-check OK")
