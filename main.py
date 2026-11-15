"""Entry point aplikasi Trust2Pass."""

import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QSettings, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog

from ui.main_window import MainWindow
from ui.tray import TrayIcon
from ui.unlock_dialog import UnlockDialog
from vault.manager import VaultManager

IDLE_LOCK_SECONDS = 10 * 60  # auto-lock setelah idle (CLAUDE.md: 5-15 menit, bisa diatur)
ORG_NAME = "Trust2Pass"
APP_NAME = "Trust2Pass"
SETTINGS_KEY_LAST_VAULT = "last_vault_path"


def choose_vault_path() -> Path | None:
    """Vault terakhir (kalau masih ada) -> dialog buka vault -> dialog buat vault baru."""
    last_path = QSettings(ORG_NAME, APP_NAME).value(SETTINGS_KEY_LAST_VAULT, "")
    if last_path and Path(last_path).exists():
        return Path(last_path)

    existing, _ = QFileDialog.getOpenFileName(None, "Buka Vault Trust2Pass", "", "Trust2Pass Vault (*.t2p)")
    if existing:
        return Path(existing)

    new_path, _ = QFileDialog.getSaveFileName(None, "Buat Vault Baru", "trust2pass.t2p", "Trust2Pass Vault (*.t2p)")
    return Path(new_path) if new_path else None


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

    window.locked.connect(handle_locked)
    tray.show_dashboard_requested.connect(window.show)
    tray.show_dashboard_requested.connect(window.raise_)
    tray.show_dashboard_requested.connect(window.activateWindow)
    tray.lock_requested.connect(do_lock)
    tray.quit_requested.connect(handle_quit)
    app.aboutToQuit.connect(lambda: window.manager.lock() if window.manager.is_unlocked else None)

    idle_watcher = IdleWatcher(idle_seconds, do_lock)
    app.installEventFilter(idle_watcher)
    return idle_watcher


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # tetap hidup di tray walau dashboard ditutup

    vault_path = choose_vault_path()
    if vault_path is None:
        sys.exit(0)

    manager = run_unlock_flow(vault_path)
    if manager is None:
        sys.exit(0)
    remember_vault_path(vault_path)

    window = MainWindow(manager)
    tray = TrayIcon()
    tray.show()

    wire_app(window, tray, vault_path, app)

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
