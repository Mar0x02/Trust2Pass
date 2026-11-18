"""Tray/menu bar icon - UI mandiri, terpisah dari dashboard (QSystemTrayIcon)."""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QActionGroup, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ui.i18n import LANGUAGE_NAMES, SUPPORTED_LANGUAGES, tr

ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "icon-rounded.png"


class TrayIcon(QSystemTrayIcon):
    """Klik kiri/trigger -> buka dashboard. Menu kanan: Buka Dashboard, Lock Vault, submenu
    Bahasa, Keluar."""

    show_dashboard_requested = Signal()
    lock_requested = Signal()
    quit_requested = Signal()
    language_selected = Signal(str)  # "" = Otomatis (ikuti sistem), selainnya kode bahasa

    def __init__(self, current_language_override: str = "", parent=None) -> None:
        super().__init__(QIcon(str(ICON_PATH)), parent)
        self.setToolTip("Trust2Pass")

        menu = QMenu()
        self.show_action = menu.addAction(tr("tray_menu_open"))
        self.show_action.triggered.connect(self.show_dashboard_requested.emit)
        self.lock_action = menu.addAction(tr("tray_menu_lock"))
        self.lock_action.triggered.connect(self.lock_requested.emit)
        menu.addSeparator()

        # Live language switching butuh retranslate semua widget yang udah dibangun - di luar
        # scope sekarang (lihat ui/i18n.py), jadi milih di sini cuma nyimpen preferensi + minta
        # restart (ditangani caller lewat sinyal `language_selected`).
        language_menu = menu.addMenu(tr("tray_menu_language"))
        language_group = QActionGroup(self)
        language_group.setExclusive(True)

        auto_action = language_menu.addAction(tr("menu_language_auto"))
        auto_action.setCheckable(True)
        auto_action.setChecked(current_language_override == "")
        auto_action.triggered.connect(lambda: self.language_selected.emit(""))
        language_group.addAction(auto_action)

        for code in SUPPORTED_LANGUAGES:
            action = language_menu.addAction(LANGUAGE_NAMES[code])
            action.setCheckable(True)
            action.setChecked(current_language_override == code)
            action.triggered.connect(lambda checked, c=code: self.language_selected.emit(c))
            language_group.addAction(action)

        menu.addSeparator()
        self.quit_action = menu.addAction(tr("tray_menu_quit"))
        self.quit_action.triggered.connect(self.quit_requested.emit)
        self.setContextMenu(menu)

        self.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_dashboard_requested.emit()

    def set_locked(self, locked: bool) -> None:
        """Update tooltip & nonaktifkan 'Lock Vault' kalau sudah locked, biar status kebaca dari tray."""
        self.setToolTip(tr("tray_tooltip_locked") if locked else "Trust2Pass")
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

    # Submenu bahasa: pilihan tersimpan ter-checked di awal, milih yang lain emit kode-nya.
    tray2 = TrayIcon(current_language_override="ja")
    language_actions = {a.text(): a for a in tray2.contextMenu().actions() if a.menu()}
    ja_action = next(a for a in list(language_actions.values())[0].menu().actions() if a.text() == "日本語")
    assert ja_action.isChecked()

    selected = []
    tray2.language_selected.connect(selected.append)
    en_action = next(a for a in list(language_actions.values())[0].menu().actions() if a.text() == "English")
    en_action.trigger()
    assert selected == ["en"]

    print("tray.py self-check OK")
