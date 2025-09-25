from __future__ import annotations
from typing import Optional, Callable, List
import os, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
from .utils import _compute_workers

def _list_chapter_images(chapter_dir: str) -> List[str]:
    files = []
    rx = re.compile(r"^(?:page_)?(\d{3,4})\.[A-Za-z0-9]+$")
    for name in os.listdir(chapter_dir):
        m = rx.match(name)
        if m: files.append((int(m.group(1)), name))
    files.sort(key=lambda t: t[0])
    return [os.path.join(chapter_dir, name) for _, name in files]

def _ensure_pillow(log=None):
    try:
        import PIL  # noqa
        from PIL import Image  # noqa
        return True
    except Exception:
        if log: log("[WARN] Pillow (PIL) не установлен — автосклейка отключена.")
        return False

def _stitch_group(img_paths: List[str], out_path: str, target_width: int,
                  optimize_png: bool, compress_level: int, strip_metadata: bool):
    imgs = []
    for p in img_paths:
        im = Image.open(p); im.load()
        if target_width and target_width > 0 and im.width != target_width:
            h = round(im.height * (target_width / im.width))
            im = im.resize((int(target_width), int(h)), Image.LANCZOS)
        if strip_metadata:
            if im.mode not in ("RGB","RGBA","L"):
                im = im.convert("RGB")
            im = Image.frombytes(im.mode, im.size, im.tobytes())
        imgs.append(im)

    total_w = max((im.width for im in imgs), default=0)
    total_h = sum((im.height for im in imgs), 0)
    if total_w <= 0 or total_h <= 0:
        return False
    canvas = Image.new("RGB", (total_w, total_h), (255, 255, 255))
    y = 0
    for im in imgs:
        if im.mode != "RGB": im = im.convert("RGB")
        canvas.paste(im, (0, y)); y += im.height

    canvas.save(out_path, format="PNG", optimize=bool(optimize_png), compress_level=max(0, min(9, int(compress_level))))
    return True

def _auto_stitch_chapter(chapter_dir: str, *, auto_cfg: dict, log=None, stop_flag: Optional[Callable[[], bool]] = None):
    if not (auto_cfg and auto_cfg.get("enable")): return
    if not _ensure_pillow(log): return

    per = max(1, int(auto_cfg.get("per") or 1))
    same_dir = bool(auto_cfg.get("same_dir"))
    target_width = int(auto_cfg.get("target_width") or 0)
    strip_metadata = bool(auto_cfg.get("strip_metadata"))
    optimize_png = bool(auto_cfg.get("optimize_png"))
    compress_level = int(auto_cfg.get("compress_level") or 6)
    delete_sources = bool(auto_cfg.get("delete_sources"))
    out_dir_pref = str(auto_cfg.get("out_dir") or "")
    auto_threads = bool(auto_cfg.get("auto_threads"))
    threads = int(auto_cfg.get("threads") or 4)

    out_dir = chapter_dir if (same_dir or not out_dir_pref) else out_dir_pref
    os.makedirs(out_dir, exist_ok=True)

    files = _list_chapter_images(chapter_dir)
    if not files:
        if log: log("[WARN] Автосклейка: нет файлов для склейки.")
        return

    groups = [files[i:i+per] for i in range(0, len(files), per)]
    def out_name(i: int) -> str: return f"{i:02d}.png"

    max_workers = _compute_workers(auto_threads, threads)

    def _stitch_one(i: int, group: List[str]):
        if stop_flag and stop_flag(): return (i, False, "")
        out_path = os.path.join(out_dir, out_name(i))
        ok = _stitch_group(group, out_path, target_width, optimize_png, compress_level, strip_metadata)
        return (i, ok, out_path)

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_stitch_one, i+1, g): i for i, g in enumerate(groups)}
        for fut in as_completed(futs):
            if stop_flag and stop_flag(): break
            i, ok, path = fut.result()
            if ok and log: log(f"[OK] Склейка {i:02d} → {path}")
            elif log: log(f"[WARN] Склейка {i:02d} не удалась.")

    if delete_sources and not (stop_flag and stop_flag()):
        try:
            for p in files:
                try: os.remove(p)
                except Exception: pass
            if log: log("[OK] Исходники удалены после склейки.")
        except Exception:
            if log: log("[WARN] Не удалось удалить исходники.")
