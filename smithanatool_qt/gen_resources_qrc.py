# python .\gen_resources_qrc.py
# pyside6-rcc smithanatool_qt/resources/resources.qrc -o smithanatool_qt/resources/resources_rc.py


from __future__ import annotations

from pathlib import Path
import os


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PKG_DIR = PROJECT_ROOT / "smithanatool_qt"
RES_DIR = PKG_DIR / "resources"
RES_DIR.mkdir(parents=True, exist_ok=True)

QRC_PATH = RES_DIR / "resources.qrc"

# Что включать
INCLUDE_DIRS = [
    PKG_DIR / "assets",
    PKG_DIR / "styles",
]

# какие расширения включать (можно расширять)
EXTS = {".svg", ".png", ".jpg", ".jpeg", ".ico", ".qss", ".ttf", ".otf"}


def rel_from_qrc(p: Path) -> str:
    # путь к файлу относительно папки resources/ (где лежит .qrc)
    return os.path.relpath(p, RES_DIR).replace("\\", "/")


def alias_from_pkg(p: Path) -> str:
    # алиас внутри ресурсов: 'assets/icons/x.svg' -> доступно как :/assets/icons/x.svg
    return p.relative_to(PKG_DIR).as_posix()


def main() -> None:
    files: list[Path] = []
    for d in INCLUDE_DIRS:
        if not d.exists():
            continue
        for p in d.rglob("*"):
            if p.is_file() and p.suffix.lower() in EXTS:
                files.append(p)

    files = sorted(set(files), key=lambda x: x.as_posix())

    lines = []
    lines.append('<!DOCTYPE RCC><RCC version="1.0">')
    lines.append('  <qresource prefix="/">')
    for p in files:
        alias = alias_from_pkg(p)
        ref = rel_from_qrc(p)
        lines.append(f'    <file alias="{alias}">{ref}</file>')
    lines.append('  </qresource>')
    lines.append('</RCC>')
    QRC_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote: {QRC_PATH} ({len(files)} files)")


if __name__ == "__main__":
    main()
