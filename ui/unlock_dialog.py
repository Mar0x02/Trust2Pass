"""Dialog unlock vault (input master password)."""

from pathlib import Path

from cryptography.exceptions import InvalidTag
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ui.i18n import tr
from ui.theme import (
    DARK,
    LIGHT,
    clear_field_error,
    glow_background_css,
    is_dark_mode,
    mark_field_error,
    make_hint_label,
    tinted_icon,
)
from vault import storage
from vault.manager import VaultManager

MIN_PASSWORD_LEN = 8
ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "icon-rounded.png"


class UnlockDialog(QDialog):
    """Buka vault yang sudah ada, atau buat vault baru kalau `vault_path` belum ada.

    Sukses -> self.manager (VaultManager) sudah unlocked dan siap dipakai caller.
    """

    def __init__(
        self, vault_path: Path, parent=None, force_new: bool = False, is_export: bool = False,
        is_import: bool = False,
    ) -> None:
        super().__init__(parent)
        self.vault_path = Path(vault_path)
        self.manager = VaultManager()
        self._is_export = is_export
        self._is_import = is_import
        # force_new/is_export dipake Export (main_window.py) - target path-nya bisa aja
        # kebetulan udah ada (user milih nama file yang udah dipakai lewat save-dialog, yang
        # native-nya sendiri udah nanya "mau overwrite?"), tapi maksudnya tetep BUAT vault baru
        # (password baru), bukan unlock file lama pakai password lama.
        self._is_new = force_new or is_export or not self.vault_path.exists()

        # Semua QPushButton di app ini punya background accent (lihat theme.py), jadi
        # ikon tombol disamakan warnanya dengan label tombol (selection_text), bukan teks halaman.
        self._button_icon_color = (DARK if is_dark_mode() else LIGHT)["selection_text"]

        if is_export:
            dialog_title, subtitle_text = tr("export_dialog_title"), tr("export_dialog_subtitle")
        elif is_import:
            # Dialog ini minta password VAULT LAIN (sumber import), bukan punya kita sendiri -
            # judul/subtitle HARUS beda dari "Buka Vault" biasa, biar gak kesan lagi login ke
            # vault sendiri (lihat ui/main_window.py _on_import).
            dialog_title, subtitle_text = tr("import_unlock_title"), tr("import_unlock_subtitle")
        elif self._is_new:
            dialog_title, subtitle_text = tr("unlock_title_new"), tr("subtitle_new")
        else:
            dialog_title, subtitle_text = tr("unlock_title_existing"), tr("subtitle_existing")
        self.setWindowTitle(dialog_title)
        self.setModal(True)
        self.setMinimumWidth(360)
        self.setObjectName("unlockDialog")
        tokens = DARK if is_dark_mode() else LIGHT
        self.setStyleSheet(glow_background_css(tokens, "QDialog#unlockDialog"))

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

        subtitle_label = QLabel(subtitle_text)
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle_label.setStyleSheet("color: #6B7280;")

        password_label = QLabel(tr("label_master_password"))

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

        # Field required nunjukin error-nya sendiri (border merah + hint italic di bawahnya),
        # bukan satu pesan gabungan - sama kayak EntryDialog (lihat theme.make_hint_label dkk).
        self.password_hint = make_hint_label()
        self.password_input.textChanged.connect(lambda: clear_field_error(self.password_input, self.password_hint))
        password_field = QVBoxLayout()
        password_field.setContentsMargins(0, 0, 0, 0)
        password_field.setSpacing(2)
        password_field.addLayout(password_row)
        password_field.addWidget(self.password_hint)

        self.confirm_input = None
        self.confirm_hint = None
        confirm_label = None
        confirm_field = None
        # Export SENGAJA gak ada confirm - beda risiko sama bikin vault utama: typo di sini cuma
        # bikin file export gagal dibuka (tinggal export ulang), bukan kehilangan vault utama yang
        # zero-knowledge/no-recovery. Dialog jadi kelihatan beda juga dari "Buat Vault Baru",
        # sesuai yang diminta.
        if self._is_new and not is_export:
            confirm_label = QLabel(tr("label_confirm_password"))
            self.confirm_input = QLineEdit()
            self.confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.confirm_input.returnPressed.connect(self._on_submit)
            self.confirm_hint = make_hint_label()
            self.confirm_input.textChanged.connect(
                lambda: clear_field_error(self.confirm_input, self.confirm_hint)
            )
            confirm_field = QVBoxLayout()
            confirm_field.setContentsMargins(0, 0, 0, 0)
            confirm_field.setSpacing(2)
            confirm_field.addWidget(self.confirm_input)
            confirm_field.addWidget(self.confirm_hint)

        # Error vault-level (bukan punya satu field tertentu, mis. file vault korup) tetap pakai
        # satu label gabungan ini.
        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: #D9534F;")
        self.error_label.setWordWrap(True)

        if is_export:
            self._submit_label = tr("export_dialog_submit")
        elif is_import:
            self._submit_label = tr("import_unlock_submit")
        elif self._is_new:
            self._submit_label = tr("submit_label_new")
        else:
            self._submit_label = tr("submit_label_existing")
        self.submit_button = QPushButton(self._submit_label)
        self.submit_button.clicked.connect(self._on_submit)

        if is_export:
            initial_status = tr("export_status_initial")
        elif is_import:
            initial_status = tr("import_unlock_status_initial")
        elif self._is_new:
            initial_status = tr("status_belum_ada_vault")
        else:
            initial_status = tr("status_locked")
        self.status_label = QLabel(initial_status)
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
        layout.addLayout(password_field)
        if confirm_label is not None:
            layout.addWidget(confirm_label)
            layout.addLayout(confirm_field)
        layout.addWidget(self.error_label)
        layout.addWidget(self.submit_button)
        layout.addSpacing(8)
        layout.addWidget(self.status_label)

    def _toggle_password_visibility(self, checked: bool) -> None:
        self.password_input.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)
        self.password_toggle.setIcon(tinted_icon("🙈" if checked else "👁", self._button_icon_color))

    def _set_loading(self, loading: bool) -> None:
        self.submit_button.setEnabled(not loading)
        if loading:
            self.submit_button.setText(tr("loading_text"))
            self.submit_button.setIcon(tinted_icon("⏳", self._button_icon_color))
            self.submit_button.setIconSize(QSize(16, 16))
        else:
            self.submit_button.setText(self._submit_label)
            self.submit_button.setIcon(QIcon())

    def _on_submit(self) -> None:
        password_str = self.password_input.text()
        if not password_str:
            mark_field_error(self.password_input, self.password_hint, tr("hint_isi_master_password"))
            return

        if self._is_new:
            if self.confirm_input is not None and password_str != self.confirm_input.text():
                mark_field_error(self.confirm_input, self.confirm_hint, tr("hint_konfirmasi_tidak_cocok"))
                return
            if len(password_str) < MIN_PASSWORD_LEN:
                mark_field_error(
                    self.password_input, self.password_hint,
                    tr("hint_master_password_min", n=MIN_PASSWORD_LEN),
                )
                return

        password_bytes = password_str.encode("utf-8")
        # Best-effort: hapus dari widget sesegera mungkin. str Python di atas tetap
        # immutable di memori (lihat crypto/memory.py) - keterbatasan yang didokumentasikan.
        self.password_input.clear()
        if self.confirm_input is not None:
            self.confirm_input.clear()

        self._set_loading(True)
        # Argon2id (derive_key) sengaja lambat (~0,5-1 detik, lihat CLAUDE.md) - paksa repaint
        # dulu biar tombol beneran kelihatan "Memproses..." sebelum thread utama ke-block KDF-nya.
        QApplication.processEvents()
        try:
            if self._is_new:
                kind = storage.KIND_EXPORT if self._is_export else storage.KIND_VAULT
                self.manager.create(self.vault_path, password_bytes, kind=kind)
            else:
                self.manager.unlock(self.vault_path, password_bytes)
        except InvalidTag:
            self._set_loading(False)
            mark_field_error(self.password_input, self.password_hint, tr("hint_password_salah"))
            self.status_label.setText(tr("status_locked"))
            return
        except ValueError as e:
            self._set_loading(False)
            self.error_label.setText(tr("error_vault_corrupt", detail=e))
            return

        if self._is_export:
            done_status = tr("export_status_done")
        elif self._is_import:
            done_status = tr("import_unlock_status_done")
        else:
            done_status = tr("status_unlocked")
        self.status_label.setText(done_status)
        self.accept()


if __name__ == "__main__":
    import sys
    import tempfile

    from ui.i18n import set_language

    set_language("id")  # deterministik - gak ikut locale mesin yang jalanin self-check
    app = QApplication(sys.argv)

    with tempfile.TemporaryDirectory() as tmp:
        vault_path = Path(tmp) / "ui_test.t2p"

        # Password kosong -> hint per-field (bukan error_label gabungan), tombol gak jadi loading.
        dlg = UnlockDialog(vault_path)
        dlg._on_submit()
        assert dlg.password_hint.isVisibleTo(dlg) and "master password" in dlg.password_hint.text()
        assert dlg.submit_button.isEnabled()
        dlg.password_input.setText("x")
        assert not dlg.password_hint.isVisibleTo(dlg)  # hint ilang begitu mulai ngetik

        # Skenario 1: vault belum ada -> mode create, password mismatch harus ditolak dulu.
        assert dlg._is_new
        assert dlg.status_label.text() == "Status: Belum ada vault"
        dlg.password_input.setText("correct horse battery staple")
        dlg.confirm_input.setText("beda")
        dlg._on_submit()
        assert not dlg.manager.is_unlocked
        assert dlg.confirm_hint.isVisibleTo(dlg) and "cocok" in dlg.confirm_hint.text()

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
        assert dlg2.password_hint.isVisibleTo(dlg2) and "salah" in dlg2.password_hint.text()
        assert dlg2.status_label.text() == "Status: Vault locked"
        assert dlg2.submit_button.isEnabled()  # loading state dibalikin lagi abis gagal

        # Skenario 3: password benar -> unlock sukses.
        dlg3 = UnlockDialog(vault_path)
        dlg3.password_input.setText("correct horse battery staple")
        dlg3._on_submit()
        assert dlg3.manager.is_unlocked
        assert dlg3.status_label.text() == "Status: Vault unlocked"

        # force_new (dipake Export) - path udah ADA, tapi tetep mode "buat baru" (minta
        # konfirmasi password, bukan unlock pakai password lama).
        dlg4 = UnlockDialog(vault_path, force_new=True)
        assert dlg4._is_new
        assert dlg4.confirm_input is not None
        dlg4.password_input.setText("password export yang beda")
        dlg4.confirm_input.setText("password export yang beda")
        dlg4._on_submit()
        assert dlg4.manager.is_unlocked
        # overwrite -> entri lama ilang, bukan ke-reuse
        assert dlg4.manager.entries == []
        dlg4.manager.lock()

        # is_export - dialog KETARA beda dari "Buat Vault Baru": judul/subtitle beda, TANPA
        # confirm password, dan kind ke-tandain KIND_EXPORT di header file-nya.
        export_path = Path(tmp) / "export_ui_test.t2p"
        dlg5 = UnlockDialog(export_path, is_export=True)
        assert dlg5._is_new
        assert dlg5.confirm_input is None  # gak ada confirm
        assert dlg5.windowTitle() == tr("export_dialog_title")
        assert dlg5.windowTitle() != tr("unlock_title_new")
        dlg5.password_input.setText("password export laen lagi")
        dlg5._on_submit()
        assert dlg5.manager.is_unlocked
        assert dlg5.manager.kind == storage.KIND_EXPORT
        assert dlg5.status_label.text() == tr("export_status_done")
        dlg5.manager.lock()

        # is_import - dialog KETARA beda dari "Buka Vault" biasa (judulnya minta password file
        # SUMBER import, bukan vault sendiri).
        dlg6 = UnlockDialog(export_path, is_import=True)
        assert not dlg6._is_new  # unlock file yang udah ada, bukan bikin baru
        assert dlg6.confirm_input is None
        assert dlg6.windowTitle() == tr("import_unlock_title")
        assert dlg6.windowTitle() != tr("unlock_title_existing")
        dlg6.password_input.setText("password export laen lagi")
        dlg6._on_submit()
        assert dlg6.manager.is_unlocked
        assert dlg6.status_label.text() == tr("import_unlock_status_done")
        dlg6.manager.lock()

    print("unlock_dialog.py self-check OK")
