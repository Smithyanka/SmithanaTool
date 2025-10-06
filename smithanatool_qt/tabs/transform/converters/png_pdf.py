from __future__ import annotations
from typing import Iterable, List, Tuple
import os
from PIL import Image, ImageSequence, ImageFile

# Чтобы не падать на некоторых «битых» кадрах
ImageFile.LOAD_TRUNCATED_IMAGES = True

# Поддерживаем популярные форматы
IMG_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tif', '.tiff', '.gif'}

def is_image(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in IMG_EXTS

def filter_images(paths: Iterable[str]) -> List[str]:
    return [p for p in paths if is_image(p)]

# Совместимость со старым API (если где-то в коде ещё используются эти функции)
def is_png(path: str) -> bool:
    return os.path.splitext(path)[1].lower() == '.png'

def filter_png(paths: Iterable[str]) -> List[str]:
    return [p for p in paths if is_png(p)]

def _open_as_rgb_pages(path: str) -> List[Image.Image]:
    """Открыть файл как список RGB-страниц (учитываем мультикадровые GIF/TIFF)."""
    im = Image.open(path)
    try:
        if getattr(im, "is_animated", False):
            frames: List[Image.Image] = []
            for frame in ImageSequence.Iterator(im):
                frames.append(frame.convert("RGB"))
            return frames
        else:
            return [im.convert("RGB")]
    finally:
        # исходный дескриптор закроется позднее при закрытии сконвертированных изображений
        pass

def convert_image_to_pdf(src_path: str, dst_path: str, jpeg_quality: int | None = 92, dpi: int = 100) -> Tuple[bool, str]:
    """
    Как в старой логике: НЕ перекодируем заранее в JPEG.
    Просто открываем как RGB и сохраняем в PDF. Параметр quality передаём в save(),
    чтобы Pillow сам решил, как сжимать содержимое PDF.
    """
    try:
        pages = _open_as_rgb_pages(src_path)
        if not pages:
            return False, "Нет изображений"

        first, rest = pages[0], pages[1:]
        save_kwargs = dict(format="PDF", save_all=True, append_images=rest, resolution=int(dpi))
        if jpeg_quality is not None:
            save_kwargs["quality"] = int(jpeg_quality)

        first.save(dst_path, **save_kwargs)

        for im in pages:
            try:
                im.close()
            except Exception:
                pass
        return True, dst_path
    except Exception as e:
        return False, str(e)

def merge_images_to_pdf(paths: List[str], dst_pdf: str, jpeg_quality: int | None = 92, dpi: int = 100) -> Tuple[bool, str]:
    """
    Объединение нескольких файлов в один PDF — без предварительной перекодировки в JPEG,
    полностью как раньше.
    """
    try:
        paths = [p for p in paths if is_image(p)]
        if not paths:
            return False, "Нет изображений"

        # Собираем все страницы
        all_pages: List[Image.Image] = []
        for p in paths:
            all_pages.extend(_open_as_rgb_pages(p))

        if not all_pages:
            return False, "Нет изображений"

        first, rest = all_pages[0], all_pages[1:]
        save_kwargs = dict(format="PDF", save_all=True, append_images=rest, resolution=int(dpi))
        if jpeg_quality is not None:
            save_kwargs["quality"] = int(jpeg_quality)

        first.save(dst_pdf, **save_kwargs)

        for im in all_pages:
            try:
                im.close()
            except Exception:
                pass
        return True, dst_pdf
    except Exception as e:
        return False, str(e)

# ---- Совместимость с существующими вызовами из UI
def convert_png_to_pdf(src_path: str, dst_path: str, jpeg_quality: int = 92, dpi: int = 100) -> Tuple[bool, str]:
    return convert_image_to_pdf(src_path, dst_path, jpeg_quality=jpeg_quality, dpi=dpi)

def merge_pngs_to_pdf(paths: List[str], dst_pdf: str, jpeg_quality: int = 92, dpi: int = 100) -> Tuple[bool, str]:
    return merge_images_to_pdf(paths, dst_pdf, jpeg_quality=jpeg_quality, dpi=dpi)