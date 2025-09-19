
from __future__ import annotations
import os
from typing import Optional

from PySide6.QtGui import QPixmap

try:
    from PIL import Image
    from PIL.ImageQt import ImageQt
except Exception:
    Image = None
    ImageQt = None

try:
    from psd_tools import PSDImage  # type: ignore
except Exception:
    PSDImage = None

def _pil_to_qpixmap(pil_img) -> Optional[QPixmap]:
    if ImageQt is None or pil_img is None:
        return None
    try:
        if pil_img.mode not in ("RGB", "RGBA"):
            pil_img = pil_img.convert("RGBA")
        qimg = ImageQt(pil_img)
        return QPixmap.fromImage(qimg)
    except Exception:
        return None

def load_qpixmap(path: str) -> Optional[QPixmap]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".psd":
        if PSDImage is not None:
            try:
                psd = PSDImage.open(path)
                pil = psd.composite()
                pm = _pil_to_qpixmap(pil)
                if pm is not None and not pm.isNull():
                    return pm
            except Exception:
                pass
        if Image is not None:
            try:
                pil = Image.open(path)
                pil.load()
                pm = _pil_to_qpixmap(pil)
                if pm is not None and not pm.isNull():
                    return pm
            except Exception:
                pass
        return None

    pm = QPixmap(path)
    if not pm.isNull():
        return pm

    if Image is not None:
        try:
            pil = Image.open(path)
            pil.load()
            pm = _pil_to_qpixmap(pil)
            if pm is not None and not pm.isNull():
                return pm
        except Exception:
            pass

    return None
