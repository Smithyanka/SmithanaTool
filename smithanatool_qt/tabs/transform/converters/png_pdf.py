from __future__ import annotations
from typing import Iterable, List, Tuple
import os
from io import BytesIO
from PIL import Image, ImageSequence

# ---- Поддерживаем не только PNG
IMG_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tif', '.tiff', '.gif'}

def is_image(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in IMG_EXTS

def filter_images(paths: Iterable[str]) -> List[str]:
    return [p for p in paths if is_image(p)]

# ---- Обратная совместимость с прежним API
def is_png(path: str) -> bool:
    return os.path.splitext(path)[1].lower() == '.png'

def filter_png(paths: Iterable[str]) -> List[str]:
    # Теперь это универсальный фильтр
    return filter_images(paths)

# ---- Подготовка изображения к PDF (опционально «прожимаем» JPEG-ом в памяти)
def _to_pdf_ready_image(im: Image.Image, jpeg_quality: int | None) -> Image.Image:
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGB")
    elif im.mode not in ("RGB", "L"):
        im = im.convert("RGB")

    if jpeg_quality is None:
        return im if im.mode == "RGB" else im.convert("RGB")

    # Перекодируем в JPEG в памяти, затем обратно открываем как RGB —
    # так PDF получает уже сжатые данные.
    buf = BytesIO()
    im.convert("RGB").save(buf, format="JPEG", quality=int(jpeg_quality), optimize=True)
    buf.seek(0)
    return Image.open(buf).convert("RGB")

def _first_frame(im: Image.Image) -> Image.Image:
    # Для GIF/многокадровых — берём 1-й кадр (надёжный и предсказуемый вариант)
    if getattr(im, "is_animated", False):
        im.seek(0)
        return im.copy()
    return im

def convert_image_to_pdf(src_path: str, dst_path: str,
                         jpeg_quality: int = 92, dpi: int = 100) -> Tuple[bool, str]:
    """
    Любое изображение → одностраничный PDF.
    jpeg_quality: если указан, кадр предварительно сжимается JPEG-ом, что реально уменьшает размер PDF.
    """
    try:
        with Image.open(src_path) as _im:
            base = _first_frame(_im)
            page = _to_pdf_ready_image(base, jpeg_quality)
            page.save(dst_path, format="PDF", resolution=float(dpi))
            try:
                page.close()
            except Exception:
                pass
        return True, dst_path
    except Exception as e:
        return False, str(e)

def merge_images_to_pdf(paths: List[str], dst_pdf: str,
                        jpeg_quality: int = 92, dpi: int = 100) -> Tuple[bool, str]:
    """
    Собирает несколько изображений в ОДИН многостраничный PDF.
    Для анимированных GIF берётся первый кадр.
    """
    try:
        pages: List[Image.Image] = []
        for p in paths:
            with Image.open(p) as _im:
                base = _first_frame(_im)
                pages.append(_to_pdf_ready_image(base, jpeg_quality))

        if not pages:
            return False, "Нет изображений"

        first, rest = pages[0], pages[1:]
        first.save(dst_pdf, format="PDF", save_all=True, append_images=rest, resolution=float(dpi))
        # Закрываем временные объекты
        for im in pages:
            try:
                im.close()
            except Exception:
                pass
        return True, dst_pdf
    except Exception as e:
        return False, str(e)

# ---- Обратная совместимость с существующими вызовами
def convert_png_to_pdf(src_path: str, dst_path: str, jpeg_quality: int = 92, dpi: int = 100) -> Tuple[bool, str]:
    return convert_image_to_pdf(src_path, dst_path, jpeg_quality=jpeg_quality, dpi=dpi)

def merge_pngs_to_pdf(paths: List[str], dst_pdf: str, jpeg_quality: int = 92, dpi: int = 100) -> Tuple[bool, str]:
    return merge_images_to_pdf(paths, dst_pdf, jpeg_quality=jpeg_quality, dpi=dpi)
