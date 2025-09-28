from __future__ import annotations
import os
from PySide6.QtWidgets import QFileDialog, QWidget
from PySide6.QtGui import QClipboard
from ..common import is_image

# Диалоги выбора
def pick_files(parent: QWidget, start_dir: str) -> list[str]:
    files, _ = QFileDialog.getOpenFileNames(
        parent,
        "Выберите файлы",
        start_dir,
        "Изображения (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.psd *.psb);;Все файлы (*.*)"
    )
    return [f for f in files if is_image(f)]

def pick_folder(parent: QWidget, start_dir: str) -> list[str]:
    folder = QFileDialog.getExistingDirectory(parent, "Выберите папку", start_dir)
    if not folder:
        return []
    try:
        entries = [os.path.join(folder, name) for name in os.listdir(folder)]
    except Exception:
        entries = []
    return [p for p in entries if is_image(p)]

# Буфер обмена / Drop
def paths_from_clipboard(parent: QWidget, cb: QClipboard) -> list[str]:
    md = cb.mimeData()
    new_paths: list[str] = []

    if md.hasUrls():
        for url in md.urls():
            p = url.toLocalFile()
            if not p:
                continue
            if os.path.isdir(p):
                try:
                    for name in os.listdir(p):
                        fp = os.path.join(p, name)
                        if is_image(fp):
                            new_paths.append(fp)
                except Exception:
                    pass
            elif is_image(p):
                new_paths.append(p)

    if not new_paths and md.hasImage():
        img = cb.image()  # QImage
        if not img.isNull():
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            mem_key = f"mem://pasted_{ts}.png"
            try:
                # относительный импорт на уровень вверх (panels.preview_panel)
                from ..preview_panel import register_memory_image
                register_memory_image(mem_key, img)
                new_paths.append(mem_key)
            except Exception:
                pass

    if not new_paths and md.hasText():
        text = md.text().strip().strip('"')
        parts = [s.strip() for s in text.replace("\r", "\n").split("\n") if s.strip()]
        for p in parts:
            if os.path.isfile(p) and is_image(p):
                new_paths.append(p)

    return new_paths

def paths_from_drop(urls) -> list[str]:
    paths: list[str] = []
    for url in urls:
        p = url.toLocalFile()
        if not p:
            continue
        if os.path.isdir(p):
            try:
                for name in os.listdir(p):
                    fp = os.path.join(p, name)
                    if is_image(fp):
                        paths.append(fp)
            except Exception:
                pass
        elif is_image(p):
            paths.append(p)
    return paths
