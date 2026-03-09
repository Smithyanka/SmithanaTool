from __future__ import annotations
import os, re, sys, subprocess


def open_in_explorer(path: str) -> None:
    """Открыть папку/файл в системном проводнике (Windows/macOS/Linux)."""
    try:
        if sys.platform.startswith('win'):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform.startswith('darwin'):
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])
    except Exception:
        pass

def unique_path(path: str) -> str:
    """Если файл существует — добавляет суффикс ' (2)', ' (3)', ..."""
    root, ext = os.path.splitext(path)
    cand = path
    k = 2
    while os.path.exists(cand):
        cand = f"{root} ({k}){ext}"
        k += 1
    return cand

