from typing import Dict, Optional
from PIL import Image
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

# In-memory QImage cache keyed by path or arbitrary string keys
_MEM_IMAGES: Dict[str, QImage] = {}

DPM_72 = 2835

def force_dpi72(img: QImage) -> None:
    if img and not img.isNull():
        img.setDotsPerMeterX(DPM_72)
        img.setDotsPerMeterY(DPM_72)

def register_memory_image(key: str, img: QImage) -> None:
    if img is None:
        return
    _MEM_IMAGES[key] = img.copy()

def unregister_memory_images(paths: list[str]) -> None:
    for p in paths:
        _MEM_IMAGES.pop(p, None)

def memory_image_for(key: str) -> Optional[QImage]:
    return _MEM_IMAGES.get(key)

def clear_memory_registry() -> None:
    _MEM_IMAGES.clear()

_app = QApplication.instance()
if _app and not getattr(QApplication, "_mem_cleanup_connected", False):
    _app.aboutToQuit.connect(clear_memory_registry)  # type: ignore[attr-defined]
    QApplication._mem_cleanup_connected = True      # type: ignore[attr-defined]

def _set_dpm_from_dpi(qimg: QImage, xdpi: float, ydpi: float | None = None):
    ydpi = xdpi if ydpi is None else ydpi
    inch_to_meter = 39.37007874  # dpm = dpi * 39.37
    qimg.setDotsPerMeterX(int(round(xdpi * inch_to_meter)))
    qimg.setDotsPerMeterY(int(round(ydpi * inch_to_meter)))

def _ensure_dpm(qimg: QImage, fallback_dpi: float = 72):
    if qimg.dotsPerMeterX() <= 0 or qimg.dotsPerMeterY() <= 0:
        _set_dpm_from_dpi(qimg, fallback_dpi, fallback_dpi)

def _qimage_from_pil(pil_img: Image.Image) -> QImage:
    """Convert PIL.Image to a detached QImage (RGBA8888)."""
    if pil_img.mode not in ("RGBA", "RGB", "LA", "L"):
        pil_img = pil_img.convert("RGBA")
    else:
        if pil_img.mode in ("RGB", "L", "LA"):
            pil_img = pil_img.convert("RGBA")
    w, h = pil_img.size
    buf = pil_img.tobytes("raw", "RGBA")
    qimg = QImage(buf, w, h, 4 * w, QImage.Format_RGBA8888).copy()
    from .utils import force_dpi72
    force_dpi72(qimg)
    return qimg
