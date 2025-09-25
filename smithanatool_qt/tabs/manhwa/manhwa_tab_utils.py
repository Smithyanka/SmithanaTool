import os, sys, subprocess
from PySide6.QtCore import QStandardPaths

def open_in_explorer(path: str):
    try:
        if sys.platform.startswith('win'):
            os.startfile(path)  # type: ignore
        elif sys.platform.startswith('darwin'):
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])
    except Exception:
        pass

def choose_start_dir(prefer: str) -> str:
    p = (prefer or "").strip()
    if p and os.path.isdir(p):
        return p
    docs = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or ""
    return docs or os.path.expanduser("~")
