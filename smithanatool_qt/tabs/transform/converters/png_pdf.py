
from __future__ import annotations
from typing import Iterable, List, Tuple
import os
from PIL import Image

def is_png(path: str) -> bool:
    return os.path.splitext(path)[1].lower() == '.png'

def filter_png(paths: Iterable[str]) -> List[str]:
    return [p for p in paths if is_png(p)]

def convert_png_to_pdf(src_path: str, dst_path: str, jpeg_quality: int = 92, dpi: int = 100) -> Tuple[bool, str]:
    """PNG → одностраничный PDF."""
    try:
        im = Image.open(src_path).convert('RGB')
        im.save(dst_path, format='PDF', resolution=int(dpi), quality=int(jpeg_quality))
        return True, dst_path
    except Exception as e:
        try:
            im = Image.open(src_path).convert('RGB')
            im.save(dst_path, format='PDF', resolution=int(dpi))
            return True, dst_path
        except Exception as e2:
            return False, f"{e}; {e2}"

def merge_pngs_to_pdf(paths: List[str], dst_pdf: str, jpeg_quality: int = 92, dpi: int = 100) -> Tuple[bool, str]:
    """Собирает несколько PNG в ОДИН многостраничный PDF."""
    try:
        images = [Image.open(p).convert('RGB') for p in paths]
        if not images:
            return False, "Нет изображений"
        first, rest = images[0], images[1:]
        first.save(dst_pdf, format='PDF', save_all=True, append_images=rest, resolution=int(dpi), quality=int(jpeg_quality))
        # Закрыть файлы (в некоторых окружениях важно)
        for im in images:
            try:
                im.close()
            except Exception:
                pass
        return True, dst_pdf
    except Exception as e:
        return False, str(e)
