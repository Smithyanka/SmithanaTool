from __future__ import annotations
from typing import Iterable, List, Tuple
import os

from PIL import Image

def is_psd(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in (".psd", ".psb")

def filter_psd(paths: Iterable[str]) -> List[str]:
    return [p for p in paths if is_psd(p)]

def _load_psd_flatten(path: str) -> Image.Image | None:
    """
    Пытаемся получить композит PSD максимально «безопасно».
    1) psd_tools.PSDImage.composite(apply_icc=False)
    2) Если не вышло — вручную пробегаем по видимым пиксельным слоям и альфа-композитим.
    3) Фолбэк: Pillow.open(path) как есть.
    Во всех случаях выкидываем icc_profile и приводим в sRGB.
    """
    try:
        from psd_tools import PSDImage  # type: ignore
    except Exception:
        PSDImage = None

    im = None
    if PSDImage is not None:
        try:
            psd = PSDImage.open(path)
            try:
                try:
                    im = psd.composite(apply_icc=True)
                except Exception:
                    im = psd.composite(apply_icc=False)
            except Exception:
                im = None

            if im is None:
                # Ручной сбор видимых пиксельных слоёв
                try:
                    visible = [
                        l for l in psd.descendants()
                        if getattr(l, "visible", True)
                        and not getattr(l, "is_group", lambda: False)()
                        and getattr(l, "has_pixels", lambda: True)()
                    ]
                    canvas = None
                    for l in visible:
                        li = None
                        for fn in (
                                lambda: l.composite(apply_icc=True),
                                lambda: l.composite(apply_icc=False),
                                lambda: l.topil(apply_icc=True),
                                lambda: l.topil(apply_icc=False),
                        ):
                            try:
                                li = fn()
                                if li is not None:
                                    break
                            except Exception:
                                pass
                        if li is None:
                            continue

                        li = _to_srgb_safe(li).convert("RGBA")

                        if canvas is None:
                            canvas = li
                        else:
                            canvas.alpha_composite(li)
                    if canvas is not None:
                        im = canvas
                except Exception:
                    im = None
        except Exception:
            im = None

    if im is None:
        # Фолбэк: Pillow открытие (для простых PSD)
        try:
            im = Image.open(path)
        except Exception:
            return None


    if im.mode not in ("RGB", "RGBA", "L", "LA"):
        im = im.convert("RGBA" if "A" in im.getbands() else "RGB")

    return _to_srgb_safe(im)

def _to_srgb_safe(im: Image.Image) -> Image.Image:
    """Очень безопасное приведение к sRGB, без падений на странных профилях."""
    try:
        # Если есть встроенный профиль, Pillow/psd_tools уже могли применить;
        # здесь достаточно убедиться, что im пригодна для PNG
        if im.mode in ("P", "PA"):
            # палитра → RGB (или RGBA)
            im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
    except Exception:
        pass
    return im

def convert_psd_to_png(
    src_path: str,
    dst_path: str,
    png_compress_level: int,
    optimize: bool = False,
    strip_metadata: bool = True
) -> Tuple[bool, str]:
    """
    Конвертирует PSD → PNG.
    Важно: 'png_compress_level' — 0..9. Чем выше, тем меньше/медленнее.
    Рекомендации:
      - Если хочешь ярче видеть разницу от уровней — держи optimize=False.
      - Если нужна максимальная «выморозка» размера — включай optimize=True (но тогда различия уровней часто сглаживаются).
    """
    try:
        im = _load_psd_flatten(src_path)
        if im is None:
            return False, "Не удалось собрать изображение из PSD"

        # Строим параметры сохранения PNG
        lvl = int(max(0, min(9, png_compress_level)))
        params = {
            "optimize": bool(optimize),
            "compress_level": lvl,
        }

        if strip_metadata and hasattr(im, "info"):
            try:
                # вычищаем мусор, который png всё равно не использует
                info = dict(im.info or {})
                for k in list(info.keys()):
                    if k.lower() in ("exif", "comment", "dpi", "chunks", "transparency"):
                        info.pop(k, None)
                im.info.clear()
                im.info.update(info)
            except Exception:
                pass

        os.makedirs(os.path.dirname(dst_path) or ".", exist_ok=True)

        # Финальная страховка по режиму
        if im.mode not in ("RGB", "RGBA", "L", "LA"):
            im = im.convert("RGBA" if "A" in im.getbands() else "RGB")

        icc = im.info.get("icc_profile")
        if icc:
            params["icc_profile"] = icc
        im.save(dst_path, format="PNG", **params)
        return True, dst_path
    except Exception as e:
        return False, str(e)
