"""Hapus bagian PySide6 yang gak dipakai Trust2Pass dari app bundle hasil `briefcase build`.

Trust2Pass cuma import QtCore/QtGui/QtWidgets (lihat grep di kode: gak ada QML, Network, Sql,
OpenGL, Svg, dll). PySide6-Essentials tetap bundle SEMUA modul itu + dev tools (Designer,
Assistant, Linguist, lupdate) karena pip install gak tahu subset mana yang kepake - jadi dipotong
manual di sini, setelah build, sebelum package. Verifikasi otool -L sebelum nulis skrip ini: Qt
Widgets/Gui/Core cuma depend satu sama lain, gak ada modul lain yang di-dlopen diam-diam (lihat
diskusi commit ini).

Jalankan: python scripts/trim_pyside6.py <path ke Something.app>
"""

import shutil
import sys
from pathlib import Path

KEEP_FRAMEWORKS = {
    "QtCore.framework", "QtGui.framework", "QtWidgets.framework",
    # Bukan dipakai langsung dari Python, tapi dibutuhkan native oleh QtGui.framework
    # (QtDBus) atau plugin iconengines/imageformats bawaan (QtSvg) - verifikasi via
    # `otool -L` tiap .framework/plugin, JANGAN hapus tanpa cek ulang (lihat histori commit).
    "QtDBus.framework", "QtSvg.framework",
}
KEEP_MODULES = {"QtCore", "QtGui", "QtWidgets"}
REMOVE_TOP_LEVEL_TOOLS = [
    "Assistant.app", "Designer.app", "Linguist.app",
    "lupdate", "qmlformat", "qmllint", "qmlls",
    "include", "typesystems",
]
REMOVE_QT_DIRS = ["qml", "libexec", "translations", "metatypes"]
REMOVE_PLUGIN_DIRS = ["qmltooling", "designer", "sqldrivers", "tls", "networkinformation"]


def rm(path: Path) -> None:
    if not path.exists():
        return
    size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.is_dir() else path.stat().st_size
    print(f"  - {path.name} ({size / 1_000_000:.1f} MB)")
    shutil.rmtree(path) if path.is_dir() else path.unlink()


REMOVE_STDLIB_DIRS = ["test", "ensurepip", "lib2to3", "pydoc_data"]


def trim_stdlib(app_path: Path) -> None:
    """Hapus bagian stdlib CPython yang murni test-suite/dev-tool (.py/data doang, bukan
    binary - gak ada risiko native-link kayak Qt frameworks di atas)."""
    candidates = list((Path(app_path) / "Contents/Frameworks").glob("Python.framework/Versions/*/lib/python*"))
    if not candidates:
        return
    stdlib_dir = candidates[0]
    print("Removing unused CPython stdlib test/dev-tool dirs:")
    for name in REMOVE_STDLIB_DIRS:
        rm(stdlib_dir / name)


def main(app_path: str) -> None:
    pyside_dir = Path(app_path) / "Contents/Resources/app_packages/PySide6"
    if not pyside_dir.is_dir():
        sys.exit(f"Gak nemu {pyside_dir} - jalanin ini SETELAH `briefcase build`, SEBELUM `briefcase package`.")

    print("Removing unused PySide6 dev tools / build-time artifacts:")
    for name in REMOVE_TOP_LEVEL_TOOLS:
        rm(pyside_dir / name)

    print("Removing unused Qt module bindings (.abi3.so + .pyi):")
    for so in pyside_dir.glob("Qt*.abi3.so"):
        module = so.name.removesuffix(".abi3.so")
        if module not in KEEP_MODULES:
            rm(so)
            rm(pyside_dir / f"{module}.pyi")

    qt_dir = pyside_dir / "Qt"
    print("Removing unused Qt native frameworks:")
    for fw in (qt_dir / "lib").glob("*.framework"):
        if fw.name not in KEEP_FRAMEWORKS:
            rm(fw)

    print("Removing unused Qt support dirs:")
    for name in REMOVE_QT_DIRS:
        rm(qt_dir / name)

    print("Removing unused Qt plugins:")
    for name in REMOVE_PLUGIN_DIRS:
        rm(qt_dir / "plugins" / name)

    trim_stdlib(Path(app_path))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(f"Usage: python {sys.argv[0]} <path to Something.app>")
    main(sys.argv[1])
