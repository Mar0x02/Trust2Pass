"""Format timestamp vault ("%Y-%m-%d %H:%M" UTC) jadi tanggal lokal + waktu relatif, ikut bahasa
UI aktif (ui/i18n.py) - nama bulan dari QLocale (ngikut Qt, bukan tulis tangan per bahasa).

shortcut: pluralisasi disederhanakan - selalu pakai bentuk yang sama ("{n} minutes ago" baik n=1
maupun n=5). Aturan plural per-bahasa yang bener (apalagi Arab, yang punya >2 bentuk) di luar
scope; upgrade kalau user minta tampilan waktu yang lebih presisi secara gramatikal.
"""

from datetime import datetime, timezone

from PySide6.QtCore import QLocale

from ui.i18n import get_language, tr

STORED_FORMAT = "%Y-%m-%d %H:%M"


def _month_name(dt_local: datetime) -> str:
    return QLocale(get_language()).monthName(dt_local.month, QLocale.FormatType.LongFormat)


def _format_absolute(dt_local: datetime) -> str:
    return f"{dt_local.day} {_month_name(dt_local)} {dt_local.year} {dt_local.strftime('%H:%M')}"


def _format_relative(dt_local: datetime, now_local: datetime) -> str:
    seconds = (now_local - dt_local).total_seconds()
    if seconds < 60:
        return tr("time_just_now")
    if seconds < 3600:
        return tr("time_minutes_ago", n=int(seconds // 60))
    if seconds < 86400:
        return tr("time_hours_ago", n=int(seconds // 3600))
    days = int(seconds // 86400)
    if days < 30:
        return tr("time_days_ago", n=days)
    return ""  # lebih dari ~sebulan - tanggal absolut aja udah cukup jelas


def format_timestamp(raw: str) -> str:
    """`raw` -> "18 November 2026 18:00 (3 jam yang lalu)". `raw` kosong/invalid -> dikembalikan apa adanya."""
    try:
        dt_utc = datetime.strptime(raw, STORED_FORMAT).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return raw
    dt_local = dt_utc.astimezone()
    now_local = datetime.now().astimezone()
    absolute = _format_absolute(dt_local)
    relative = _format_relative(dt_local, now_local)
    return f"{absolute} ({relative})" if relative else absolute


if __name__ == "__main__":
    import sys
    from datetime import timedelta

    from PySide6.QtWidgets import QApplication

    from ui.i18n import set_language

    app = QApplication(sys.argv)

    now_raw = datetime.now(timezone.utc).strftime(STORED_FORMAT)
    set_language("id")
    assert "Baru saja" in format_timestamp(now_raw) or "menit" in format_timestamp(now_raw)

    five_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime(STORED_FORMAT)
    assert "5 menit yang lalu" in format_timestamp(five_min_ago)

    set_language("en")
    assert "5 minutes ago" in format_timestamp(five_min_ago)

    old = "2026-01-01 00:00"
    old_formatted = format_timestamp(old)
    assert "(" not in old_formatted  # lebih dari sebulan -> gak ada embel-embel relatif

    assert format_timestamp("bukan tanggal valid") == "bukan tanggal valid"

    print("datetime_fmt.py self-check OK")
