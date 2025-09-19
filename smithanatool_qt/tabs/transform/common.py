from __future__ import annotations
import os, re

SUPPORTED_EXT = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'}

def natural_key(path: str):
    """Естественная сортировка по имени файла (учитывает числа)."""
    name = os.path.basename(path)
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', name)]

def mtime_key(path: str) -> float:
    """Ключ сортировки по времени модификации файла."""
    try:
        return os.path.getmtime(path)
    except Exception:
        return 0.0

def is_image(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SUPPORTED_EXT and os.path.isfile(path)

def dedup_keep_order(items):
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

def open_in_explorer(folder: str):
    import sys, subprocess
    if os.name == 'nt':
        os.startfile(folder)
    elif sys.platform == 'darwin':
        subprocess.run(['open', folder])
    else:
        subprocess.run(['xdg-open', folder])
