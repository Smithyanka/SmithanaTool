
from __future__ import annotations
from typing import Iterable, List, Optional
from PIL import Image

def _load_image(path: str) -> Image.Image:
    im = Image.open(path)
    im.load()
    return im

def load_images(paths: Iterable[str]) -> List[Image.Image]:
    out = []
    for p in paths:
        try:
            im = _load_image(p)
            out.append(im)
        except Exception:
            pass
    return out

def merge_vertical(images: List[Image.Image], target_width: Optional[int] = None) -> Image.Image:
    """Склейка по вертикали. При target_width все изображения приводятся к этой ширине с сохранением пропорций."""
    proc = []
    for im in images:
        if im is None:
            continue
        if im.mode in ("RGBA", "LA"):
            im = im.convert("RGB")
        elif im.mode == "P":
            im = im.convert("RGB")
        if target_width and im.width != target_width:
            h = max(1, int(round(im.height * (target_width / float(im.width)))))
            im = im.resize((target_width, h), Image.LANCZOS)
        proc.append(im)
    if not proc:
        raise ValueError("Нет изображений для склейки.")
    total_w = max(im.width for im in proc)
    total_h = sum(im.height for im in proc)
    canvas = Image.new("RGB", (total_w, total_h), (255, 255, 255))
    y = 0
    for im in proc:
        canvas.paste(im, (0, y))
        y += im.height
    return canvas

def merge_horizontal(images: List[Image.Image], target_height: Optional[int] = None) -> Image.Image:
    """Склейка по горизонтали. При target_height приводим все к этой высоте с сохранением пропорций."""
    imgs = []
    for im in images:
        if im is None:
            continue
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA")
        if target_height and im.height != target_height:
            ratio = target_height / float(im.height)
            new_w = max(1, int(round(im.width * ratio)))
            im = im.resize((new_w, target_height), Image.LANCZOS)
        imgs.append(im)
    if not imgs:
        raise ValueError("Нет изображений для склейки.")
    total_w = sum(im.width for im in imgs)
    max_h = max(im.height for im in imgs)
    canvas = Image.new("RGBA", (total_w, max_h), (255, 255, 255, 0))
    x = 0
    for im in imgs:
        y = (max_h - im.height) // 2
        mask = im.split()[3] if im.mode == 'RGBA' else None
        canvas.paste(im.convert('RGBA') if im.mode != 'RGBA' else im, (x, y), mask)
        x += im.width
    # если ни у одного нет альфы — можно привести к RGB
    if all((im.mode == 'RGB') for im in imgs):
        canvas = canvas.convert('RGB')
    return canvas

def save_png(img: Image.Image, path: str, optimize: bool = True, compress_level: int = 6, strip_metadata: bool = False) -> None:
    im = img
    try:
        if strip_metadata:
            im = im.copy()
            im.info.pop("exif", None)
            im.info.pop("icc_profile", None)
            # очистка PNG-текста/метаданных
            for k in list(im.info.keys()):
                if isinstance(im.info.get(k), (bytes, bytearray, str)):
                    try:
                        im.info.pop(k, None)
                    except Exception:
                        pass
    except Exception:
        pass
    params = {
        "optimize": bool(optimize),
        "compress_level": int(max(0, min(9, compress_level))),
    }
    try:
        im.save(path, format="PNG", **params)
    except Exception:
        # Последняя попытка без optimize
        params["optimize"] = False
        im.save(path, format="PNG", **params)
