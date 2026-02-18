from pathlib import Path
import sys

def asset_path(*parts: str) -> Path:
    """
    Возвращает корректный путь к файлам из папки assets:
    - DEV: рядом с модулем graphic/...
    - EXE (PyInstaller): <_MEIPASS>/assets/... или рядом с exe, если так упаковали
    """
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    else:
        base = Path(__file__).resolve().parents[2]  # корень пакета SmithanaTool_Qt
    return base / "assets" / Path(*parts)