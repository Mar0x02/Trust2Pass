"""Dialog MFA: verifikasi kode TOTP (gerbang reveal/copy & aksi pelemahan proteksi) + pengaturan
aktif/nonaktif/scope. Lihat vault/manager.py buat alasan desainnya (kenapa TOTP cuma gerbang,
bukan bahan kunci dekripsi)."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from crypto import totp
from ui.i18n import tr
from ui.theme import (
    DARK,
    LIGHT,
    clear_field_error,
    glow_background_css,
    is_dark_mode,
    mark_field_error,
    make_hint_label,
)
from vault.manager import InvalidMfaCode, MfaLockedOut, VaultManager


class MfaPromptDialog(QDialog):
    """Dialog kecil minta 1 kode TOTP 6 digit. Sukses -> self.code siap dipakai caller
    (reveal_password/disable_mfa/set_mfa_scope - caller yang verifikasi ke VaultManager)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.code = ""
        tokens = DARK if is_dark_mode() else LIGHT
        self.setWindowTitle(tr("mfa_prompt_title"))
        self.setModal(True)
        self.setMinimumWidth(320)
        self.setObjectName("mfaPromptDialog")
        self.setStyleSheet(glow_background_css(tokens, "QDialog#mfaPromptDialog"))

        label = QLabel(tr("mfa_prompt_label"))
        self.code_input = QLineEdit()
        self.code_input.setMaxLength(6)
        self.code_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code_input.setPlaceholderText("000000")
        self.code_input.returnPressed.connect(self._on_submit)

        self.hint = make_hint_label()
        self.code_input.textChanged.connect(lambda: clear_field_error(self.code_input, self.hint))

        cancel_button = QPushButton(tr("btn_batal"))
        cancel_button.setProperty("variant", "secondary")
        cancel_button.clicked.connect(self.reject)
        submit_button = QPushButton(tr("btn_verify"))
        submit_button.clicked.connect(self._on_submit)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(submit_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.addWidget(label)
        layout.addWidget(self.code_input)
        layout.addWidget(self.hint)
        layout.addLayout(button_row)

    def _on_submit(self) -> None:
        code = self.code_input.text().strip()
        if not code:
            mark_field_error(self.code_input, self.hint, tr("hint_isi_kode_mfa"))
            return
        self.code = code
        self.accept()


class MfaSettingsDialog(QDialog):
    """Status MFA saat ini + aksi aktif/matiin/ganti scope. Dibuka dari tombol "MFA" di top bar
    MainWindow (lihat ui/main_window.py)."""

    def __init__(self, manager: VaultManager, parent=None) -> None:
        super().__init__(parent)
        self.manager = manager
        tokens = DARK if is_dark_mode() else LIGHT
        self.setWindowTitle(tr("mfa_settings_title"))
        self.setModal(True)
        self.setMinimumWidth(380)
        self.setObjectName("mfaSettingsDialog")
        self.setStyleSheet(glow_background_css(tokens, "QDialog#mfaSettingsDialog"))

        self.status_label = QLabel()
        self.status_label.setStyleSheet("font-weight: bold;")
        explain_label = QLabel(tr("mfa_explain_text"))
        explain_label.setWordWrap(True)
        explain_label.setStyleSheet(f"color: {tokens['muted_text']}; font-size: 12px;")

        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(24, 20, 24, 20)
        self.layout_.setSpacing(10)
        self.layout_.addWidget(self.status_label)
        self.layout_.addWidget(explain_label)

        self._body = QVBoxLayout()
        self.layout_.addLayout(self._body)

        close_button = QPushButton(tr("btn_continue"))
        close_button.clicked.connect(self.accept)
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_row.addWidget(close_button)
        self.layout_.addLayout(close_row)

        self._rebuild_body()

    def _clear_body(self) -> None:
        while self._body.count():
            item = self._body.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _rebuild_body(self) -> None:
        self._clear_body()
        if self.manager.mfa_enabled:
            scope_label = tr("mfa_scope_all") if self.manager.mfa_scope == "all" else tr("mfa_scope_selected")
            self.status_label.setText(tr("mfa_status_enabled", scope=scope_label))
            self._build_enabled_body()
        else:
            self.status_label.setText(tr("mfa_status_disabled"))
            self._build_disabled_body()

    def _build_disabled_body(self) -> None:
        enable_button = QPushButton(tr("btn_mfa_enable"))
        enable_button.clicked.connect(self._on_start_enroll)
        self._body.addWidget(enable_button)

    def _build_enabled_body(self) -> None:
        self.scope_group = QButtonGroup(self)
        self.scope_all_radio = QRadioButton(tr("mfa_scope_all"))
        self.scope_selected_radio = QRadioButton(tr("mfa_scope_selected"))
        self.scope_group.addButton(self.scope_all_radio)
        self.scope_group.addButton(self.scope_selected_radio)
        if self.manager.mfa_scope == "all":
            self.scope_all_radio.setChecked(True)
        else:
            self.scope_selected_radio.setChecked(True)
        self._body.addWidget(self.scope_all_radio)
        self._body.addWidget(self.scope_selected_radio)

        apply_button = QPushButton(tr("btn_mfa_apply_scope"))
        apply_button.setProperty("variant", "secondary")
        apply_button.clicked.connect(self._on_apply_scope)
        disable_button = QPushButton(tr("btn_mfa_disable"))
        disable_button.setProperty("variant", "danger")
        disable_button.clicked.connect(self._on_disable)

        action_row = QHBoxLayout()
        action_row.addWidget(apply_button)
        action_row.addWidget(disable_button)
        self._body.addLayout(action_row)

    def _prompt_code(self) -> str | None:
        dialog = MfaPromptDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.code

    def _on_apply_scope(self) -> None:
        new_scope = "all" if self.scope_all_radio.isChecked() else "selected"
        if new_scope == self.manager.mfa_scope:
            return
        code = self._prompt_code()
        if code is None:
            return
        try:
            self.manager.set_mfa_scope(new_scope, code)
        except InvalidMfaCode:
            self._show_error(tr("mfa_invalid_code_title"), tr("mfa_invalid_code_text"))
            return
        except MfaLockedOut as e:
            self._show_error(tr("mfa_locked_title"), tr("mfa_locked_text", seconds=int(e.retry_after) + 1))
            return
        self._rebuild_body()

    def _on_disable(self) -> None:
        code = self._prompt_code()
        if code is None:
            return
        try:
            self.manager.disable_mfa(code)
        except InvalidMfaCode:
            self._show_error(tr("mfa_invalid_code_title"), tr("mfa_invalid_code_text"))
            return
        except MfaLockedOut as e:
            self._show_error(tr("mfa_locked_title"), tr("mfa_locked_text", seconds=int(e.retry_after) + 1))
            return
        self._rebuild_body()

    def _on_start_enroll(self) -> None:
        dialog = MfaEnrollDialog(self.manager, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._rebuild_body()

    def _show_error(self, title: str, text: str) -> None:
        tokens = DARK if is_dark_mode() else LIGHT
        box = QMessageBox(self)
        box.setObjectName("confirmDialog")
        box.setStyleSheet(glow_background_css(tokens, "QMessageBox#confirmDialog"))
        box.setIcon(QMessageBox.Icon.NoIcon)
        box.setWindowTitle(title)
        box.setText(text)
        box.addButton(tr("btn_continue"), QMessageBox.ButtonRole.AcceptRole)
        box.exec()


class MfaEnrollDialog(QDialog):
    """Enrollment pertama kali: generate secret baru, tampilkan QR + secret buat discan/diketik
    manual ke app Authenticator, minta 1 kode konfirmasi sebelum beneran disimpan ke vault."""

    def __init__(self, manager: VaultManager, parent=None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.secret = totp.generate_secret()
        tokens = DARK if is_dark_mode() else LIGHT
        self.setWindowTitle(tr("btn_mfa_enable"))
        self.setModal(True)
        self.setMinimumWidth(340)
        self.setObjectName("mfaEnrollDialog")
        self.setStyleSheet(glow_background_css(tokens, "QDialog#mfaEnrollDialog"))

        account_name = self.manager.path.name if self.manager.path else "Trust2Pass Vault"
        uri = totp.provisioning_uri(self.secret, account_name)
        png = totp.qr_png_bytes(uri)
        qr_pixmap = QPixmap()
        qr_pixmap.loadFromData(png, "PNG")
        qr_label = QLabel()
        qr_label.setPixmap(
            qr_pixmap.scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        )
        qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        instruction_label = QLabel(tr("mfa_enroll_instruction"))
        instruction_label.setWordWrap(True)

        secret_row = QHBoxLayout()
        secret_row.addWidget(QLabel(tr("mfa_enroll_secret_label")))
        secret_field = QLineEdit(self.secret)
        secret_field.setReadOnly(True)
        secret_row.addWidget(secret_field)

        self.scope_group = QButtonGroup(self)
        self.scope_all_radio = QRadioButton(tr("mfa_scope_all"))
        self.scope_selected_radio = QRadioButton(tr("mfa_scope_selected"))
        self.scope_all_radio.setChecked(True)
        self.scope_group.addButton(self.scope_all_radio)
        self.scope_group.addButton(self.scope_selected_radio)

        code_label = QLabel(tr("mfa_prompt_label"))
        self.code_input = QLineEdit()
        self.code_input.setMaxLength(6)
        self.code_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code_input.setPlaceholderText("000000")
        self.code_input.returnPressed.connect(self._on_confirm)
        self.hint = make_hint_label()
        self.code_input.textChanged.connect(lambda: clear_field_error(self.code_input, self.hint))

        cancel_button = QPushButton(tr("btn_batal"))
        cancel_button.setProperty("variant", "secondary")
        cancel_button.clicked.connect(self.reject)
        confirm_button = QPushButton(tr("btn_mfa_confirm_enable"))
        confirm_button.clicked.connect(self._on_confirm)
        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(confirm_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        layout.addWidget(qr_label)
        layout.addWidget(instruction_label)
        layout.addLayout(secret_row)
        layout.addWidget(self.scope_all_radio)
        layout.addWidget(self.scope_selected_radio)
        layout.addWidget(code_label)
        layout.addWidget(self.code_input)
        layout.addWidget(self.hint)
        layout.addLayout(button_row)

    def _on_confirm(self) -> None:
        code = self.code_input.text().strip()
        if not code:
            mark_field_error(self.code_input, self.hint, tr("hint_isi_kode_mfa"))
            return
        scope = "all" if self.scope_all_radio.isChecked() else "selected"
        try:
            self.manager.enable_mfa(self.secret, scope, code)
        except InvalidMfaCode:
            mark_field_error(self.code_input, self.hint, tr("mfa_invalid_code_text"))
            return
        self.accept()


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from crypto.kdf import MIN_MEMORY_KIB, MIN_PARALLELISM, MIN_TIME_COST
    from ui.i18n import set_language

    set_language("id")
    app = QApplication(sys.argv)

    with tempfile.TemporaryDirectory() as tmp:
        vault_path = Path(tmp) / "mfa_dialog_test.t2p"
        manager = VaultManager()
        manager.create(vault_path, b"correct horse battery staple", MIN_MEMORY_KIB, MIN_TIME_COST, MIN_PARALLELISM)

        # MfaPromptDialog: kosong -> hint, isi -> accept dengan .code terisi.
        prompt = MfaPromptDialog()
        prompt._on_submit()
        assert prompt.hint.isVisibleTo(prompt)
        prompt.code_input.setText("123456")
        prompt._on_submit()
        assert prompt.code == "123456"

        # Settings dialog, MFA belum aktif -> cuma ada tombol enable.
        settings = MfaSettingsDialog(manager)
        assert tr("btn_mfa_enable") in [
            settings._body.itemAt(i).widget().text()
            for i in range(settings._body.count())
            if settings._body.itemAt(i).widget() is not None
        ]

        # Enroll dialog: generate secret baru, confirm_code SALAH -> ditolak, manager tetap nonaktif.
        enroll = MfaEnrollDialog(manager)
        enroll.code_input.setText("000000" if enroll.secret else "000000")
        enroll._on_confirm()
        assert not manager.mfa_enabled
        assert enroll.hint.isVisibleTo(enroll)

        # confirm_code BENAR (hitung dari secret yang sama) -> enroll sukses.
        import pyotp

        enroll.code_input.setText(pyotp.TOTP(enroll.secret).now())
        enroll._on_confirm()
        assert manager.mfa_enabled
        assert manager.mfa_scope == "all"

        # Settings dialog sekarang nunjukin status aktif + opsi scope/disable.
        settings2 = MfaSettingsDialog(manager)
        assert tr("mfa_status_enabled", scope=tr("mfa_scope_all")) in settings2.status_label.text()

    print("mfa_dialog.py self-check OK")
