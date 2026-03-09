from __future__ import annotations

import os
import pathlib
import subprocess
import sys
from functools import lru_cache
from typing import Optional

from PySide6.QtCore import QStandardPaths


def _is_writable_dir(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, '.write_test')
        with open(probe, 'w', encoding='utf-8') as fh:
            fh.write('')
        os.remove(probe)
        return True
    except Exception:
        return False


def _first_existing_settings_parent(anchor: Optional[str] = None) -> Optional[str]:
    candidates: list[pathlib.Path] = []
    cwd = pathlib.Path.cwd()
    candidates.append(cwd)
    if anchor:
        try:
            p = pathlib.Path(anchor).resolve()
            candidates.extend([p.parent, *p.parents])
        except Exception:
            pass

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if (candidate / 'settings.ini').exists():
            return key
    return None


@lru_cache(maxsize=16)
def get_settings_dir(anchor: Optional[str] = None) -> str:
    try:
        if getattr(sys, 'frozen', False):
            base = os.path.dirname(sys.executable)
        else:
            base = _first_existing_settings_parent(anchor) or os.getcwd()

        if _is_writable_dir(base):
            return base

        app_data = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or ''
        if app_data and _is_writable_dir(app_data):
            return app_data

        home = os.path.expanduser('~')
        if _is_writable_dir(home):
            return home
    except Exception:
        pass

    fallback = os.getcwd()
    os.makedirs(fallback, exist_ok=True)
    return fallback


def choose_start_dir(prefer: str) -> str:
    path = (prefer or '').strip()
    if path and os.path.isdir(path):
        return path
    docs = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or ''
    return docs or os.path.expanduser('~') or os.getcwd()


def open_in_explorer(path: str) -> None:
    path = (path or '').strip()
    if not path:
        return
    try:
        if os.name == 'nt':
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == 'darwin':
            subprocess.check_call(['open', path])
        else:
            subprocess.check_call(['xdg-open', path])
    except Exception:
        pass
