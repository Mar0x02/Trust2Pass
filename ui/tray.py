"""Tray/menu bar icon - UI mandiri, terpisah dari dashboard (QSystemTrayIcon)."""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "icon-rounded.png"


class TrayIcon(QSystemTrayIcon):
    """Klik kiri/trigger -> buka dashboard. Menu kanan: Buka Dashboard, Lock Vault, Keluar."""

    show_dashboard_requested = Signal()
    lock_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(QIcon(str(ICON_PATH)), parent)
        self.setToolTip("Trust2Pass")

        menu = QMenu()
        self.show_action = menu.addAction("Buka Dashboard")
        self.show_action.triggered.connect(self.show_dashboard_requested.emit)
        self.lock_action = menu.addAction("Lock Vault")
        self.lock_action.triggered.connect(self.lock_requested.emit)
        menu.addSeparator()
        self.quit_action = menu.addAction("Keluar")
        self.quit_action.triggered.connect(self.quit_requested.emit)
        self.setContextMenu(menu)

        self.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_dashboard_requested.emit()

    def set_locked(self, locked: bool) -> None:
        """Update tooltip & nonaktifkan 'Lock Vault' kalau sudah locked, biar status kebaca dari tray."""
        self.setToolTip("Trust2Pass (locked)" if locked else "Trust2Pass")
        self.lock_action.setEnabled(not locked)


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    tray = TrayIcon()
    assert ICON_PATH.exists()
    assert not tray.icon().isNull()

    events = []
    tray.show_dashboard_requested.connect(lambda: events.append("show"))
    tray.lock_requested.connect(lambda: events.append("lock"))
    tray.quit_requested.connect(lambda: events.append("quit"))

    tray.show_action.trigger()
    tray.lock_action.trigger()
    tray.quit_action.trigger()
    assert events == ["show", "lock", "quit"]

    # Klik kiri (Trigger) di icon tray juga harus buka dashboard.
    events.clear()
    tray._on_activated(QSystemTrayIcon.ActivationReason.Trigger)
    assert events == ["show"]

    # Klik kanan (Context menu) TIDAK boleh ikut buka dashboard.
    events.clear()
    tray._on_activated(QSystemTrayIcon.ActivationReason.Context)
    assert events == []

    tray.set_locked(True)
    assert not tray.lock_action.isEnabled()
    tray.set_locked(False)
    assert tray.lock_action.isEnabled()

    print("tray.py self-check OK")
