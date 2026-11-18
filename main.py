"""Entry point aplikasi Trust2Pass."""

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QSettings, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from ui import theme
from ui.i18n import get_language, set_language, tr
from ui.main_window import MainWindow
from ui.theme import DARK, LIGHT, glow_background_css, is_dark_mode
from ui.tray import TrayIcon
from ui.unlock_dialog import UnlockDialog
from ui.vault_picker_dialog import VaultPickerDialog
from vault.manager import VaultManager

IDLE_LOCK_SECONDS = 10 * 60  # auto-lock setelah idle (CLAUDE.md: 5-15 menit, bisa diatur)
ORG_NAME = "Trust2Pass"
APP_NAME = "Trust2Pass"
SETTINGS_KEY_LAST_VAULT = "last_vault_path"
SETTINGS_KEY_LANGUAGE = "language_override"
ICON_PATH = Path(__file__).resolve().parent / "assets" / "icon-rounded.png"


def choose_vault_path() -> Path | None:
    """Vault terakhir (kalau masih ada) -> dialog branded pilih/buat vault."""
    last_path = QSettings(ORG_NAME, APP_NAME).value(SETTINGS_KEY_LAST_VAULT, "")
    if last_path and Path(last_path).exists():
        return Path(last_path)

    picker = VaultPickerDialog()
    if picker.exec() == QDialog.DialogCode.Accepted:
        return picker.vault_path
    return None


def remember_vault_path(path: Path) -> None:
    QSettings(ORG_NAME, APP_NAME).setValue(SETTINGS_KEY_LAST_VAULT, str(path))


def run_unlock_flow(vault_path: Path) -> VaultManager | None:
    """Tampilkan UnlockDialog. Return VaultManager yang sudah unlocked, atau None kalau user cancel."""
    dialog = UnlockDialog(vault_path)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.manager
    return None


class IdleWatcher(QObject):
    """Reset idle timer tiap ada mouse/keyboard event di seluruh app; panggil on_timeout kalau idle kelamaan."""

    def __init__(self, timeout_seconds: int, on_timeout, parent=None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(on_timeout)
        self._timeout_ms = timeout_seconds * 1000
        self.reset()

    def reset(self) -> None:
        self._timer.start(self._timeout_ms)

    def stop(self) -> None:
        self._timer.stop()

    def eventFilter(self, watched, event) -> bool:
        if event.type() in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress, QEvent.Type.KeyPress):
            self.reset()
        return False


def wire_app(window: MainWindow, tray: TrayIcon, vault_path: Path, app: QApplication,
             idle_seconds: int = IDLE_LOCK_SECONDS) -> IdleWatcher:
    """Sambungkan tray, idle timer, dan alur lock/re-unlock ke `window`.

    Selalu baca/tulis lewat `window.manager` (bukan variabel lokal terpisah) - setelah
    re-unlock, `window.manager` diganti ke instance baru, jadi referensi lama jadi basi
    kalau disimpan di tempat lain.
    """

    def do_lock() -> None:
        if window.manager.is_unlocked:
            window._on_lock()

    def handle_locked() -> None:
        idle_watcher.stop()
        window.hide()
        tray.set_locked(True)
        new_manager = run_unlock_flow(vault_path)
        if new_manager is None:
            app.quit()
            return
        window.manager = new_manager
        window.refresh()
        tray.set_locked(False)
        window.show()
        idle_watcher.reset()

    def handle_quit() -> None:
        if window.manager.is_unlocked:
            window.manager.lock()
        app.quit()

    def handle_language_selected(code: str) -> None:
        QSettings(ORG_NAME, APP_NAME).setValue(SETTINGS_KEY_LANGUAGE, code)
        # Live-retranslate semua widget yang udah dibangun itu kerjaan besar (di luar scope -
        # lihat ui/i18n.py), jadi preferensi disimpan dulu lalu minta restart buat nerapinnya.
        tokens = DARK if is_dark_mode() else LIGHT
        box = QMessageBox(window)
        box.setObjectName("confirmDialog")
        box.setStyleSheet(glow_background_css(tokens, "QMessageBox#confirmDialog"))
        box.setIcon(QMessageBox.Icon.NoIcon)
        box.setWindowTitle(tr("restart_required_title"))
        box.setText(tr("restart_required_text"))
        restart_button = box.addButton(tr("btn_restart_now"), QMessageBox.ButtonRole.YesRole)
        later_button = box.addButton(tr("btn_later"), QMessageBox.ButtonRole.NoRole)
        later_button.setProperty("variant", "secondary")
        box.exec()
        if box.clickedButton() is restart_button:
            if window.manager.is_unlocked:
                window.manager.lock()
            # Spawn proses BARU yang benar-benar terpisah, baru quit proses ini - `os.execv`
            # (ganti image proses yang sama) ninggalin koneksi lama ke WindowServer macOS dalam
            # keadaan ambigu, bikin tray icon ilang/nyangkut karena NSStatusItem punya proses
            # lama gak ke-cleanup bersih sebelum proses baru coba bikin punya sendiri.
            subprocess.Popen([sys.executable] + sys.argv)
            app.quit()

    window.locked.connect(handle_locked)
    tray.show_dashboard_requested.connect(window.show)
    tray.show_dashboard_requested.connect(window.raise_)
    tray.show_dashboard_requested.connect(window.activateWindow)
    tray.lock_requested.connect(do_lock)
    tray.quit_requested.connect(handle_quit)
    tray.language_selected.connect(handle_language_selected)
    app.aboutToQuit.connect(lambda: window.manager.lock() if window.manager.is_unlocked else None)

    idle_watcher = IdleWatcher(idle_seconds, do_lock)
    app.installEventFilter(idle_watcher)
    return idle_watcher


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # tetap hidup di tray walau dashboard ditutup
    app.setWindowIcon(QIcon(str(ICON_PATH)))
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)

    # Preferensi bahasa manual (lewat tray menu) nimpa auto-detect sistem - HARUS sebelum
    # dialog/window apa pun dibangun, karena semuanya resolve teks lewat tr() pas __init__.
    language_override = QSettings(ORG_NAME, APP_NAME).value(SETTINGS_KEY_LANGUAGE, "")
    if language_override:
        set_language(language_override)

    theme.apply_theme(app)
    # Bahasa Arab (ui/i18n.py) butuh layout kanan-ke-kiri - Qt bisa mirror layout BAWAAN-nya
    # otomatis, tapi elemen yang digambar manual (radial-glow, posisi floating button di
    # GlassListWidget) gak ikut ke-mirror karena koordinatnya di-hardcode kiri-ke-kanan.
    if get_language() == "ar":
        app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    vault_path = choose_vault_path()
    if vault_path is None:
        sys.exit(0)

    manager = run_unlock_flow(vault_path)
    if manager is None:
        sys.exit(0)
    remember_vault_path(vault_path)

    window = MainWindow(manager)
    tray = TrayIcon(current_language_override=language_override)
    tray.show()

    wire_app(window, tray, vault_path, app)

    window.show()
    exit_code = app.exec()
    # QSystemTrayIcon (NSStatusItem di macOS) yang dibiarkan ke-cleanup otomatis pas interpreter
    # Python finalize (atexit) bisa segfault - urutan destroy Shiboken/Qt bentrok sama urutan GC
    # Python di titik itu (lihat crash log ~/Library/Logs/DiagnosticReports/Python-*.ips:
    # SIGSEGV di QSystemTrayIconWrapper::~QSystemTrayIconWrapper lewat Py_Finalize). Hapus
    # eksplisit DI SINI (app masih hidup, urutannya predictable) biar gak nyampe ke titik itu.
    tray.hide()
    del tray
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
