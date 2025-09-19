
from __future__ import annotations
from typing import Iterable, List, Tuple
import os
from PIL import Image

def is_png(path: str) -> bool:
    return os.path.splitext(path)[1].lower() == '.png'

def filter_png(paths: Iterable[str]) -> List[str]:
    return [p for p in paths if is_png(p)]

def _web_palette_256() -> list[int]:
    pal: list[int] = []
    # 6x6x6 web palette (216 colors)
    for r in (0x00,0x33,0x66,0x99,0xCC,0xFF):
        for g in (0x00,0x33,0x66,0x99,0xCC,0xFF):
            for b in (0x00,0x33,0x66,0x99,0xCC,0xFF):
                pal.extend([r, g, b])
    # +40 grays to get exact 256
    for i in range(40):
        v = int(round(i * 255/39))
        pal.extend([v, v, v])
    return pal

def _quantize_to_web256(im: Image.Image, dither: bool) -> Image.Image:
    # Flatten to RGB on white background if RGBA, ensure mode suitable for quantization
    if im.mode == "RGBA":
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(bg, im).convert("RGB")
    elif im.mode == "P":
        try:
            im = im.convert("RGB")
        except Exception:
            pass
    elif im.mode not in ("RGB", "L"):
        im = im.convert("RGB")

    try:
        dither_flag = Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE  # Pillow>=9.1
    except Exception:
        dither_flag = Image.FLOYDSTEINBERG if dither else Image.NONE

    pal_img = Image.new("P", (16, 16))
    pal_img.putpalette(_web_palette_256())

    # Prefer palette-driven quantization to Web-256
    try:
        return im.convert("RGB").quantize(palette=pal_img, dither=dither_flag)
    except Exception:
        # Fallback to adaptive 256 colors
        try:
            return im.convert("RGB").convert("P", palette=Image.ADAPTIVE, colors=256)
        except Exception:
            return im.convert("P")

def convert_png_to_gif(src_path: str, dst_path: str, dither: bool = True) -> Tuple[bool, str]:
    """Конвертация PNG → GIF с палитрой Web-256 и рабочим дизерингом.
    Максимально возможное качество для одиночного GIF-кадра: палитра 256 + Floyd–Steinberg.
    """
    try:
        with Image.open(src_path) as _im:
            _im.load()
            im = _im.copy()
        pal = _quantize_to_web256(im, dither)
        # optimize=True уменьшает размер, не ухудшая одиночный кадр
        try:
            pal.save(dst_path, format="GIF", save_all=False, optimize=True)
        except TypeError:
            pal.save(dst_path, format="GIF")
        return True, dst_path
    except Exception as e:
        return False, str(e)
