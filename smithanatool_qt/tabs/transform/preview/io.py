from __future__ import annotations

import os

from PySide6.QtGui import QImage

from .utils import force_dpi72, _qimage_from_pil


def is_psd_path(path: str | None) -> bool:
    ext = os.path.splitext(path or "")[1].lower()
    return ext in (".psd", ".psb")


def load_qimage(path: str) -> QImage | None:
    """Load an image from disk (supports common formats + PSD/PSB via psd-tools).

    Returns None on failure.
    """
    if not path:
        return None

    if is_psd_path(path):
        try:
            # Heavy imports kept inside
            from psd_tools import PSDImage

            psd = PSDImage.open(path)
            pil = psd.composite()
            qimg = _qimage_from_pil(pil)
            if qimg is not None and not qimg.isNull():
                force_dpi72(qimg)
                if qimg.format() != QImage.Format_RGBA8888:
                    qimg = qimg.convertToFormat(QImage.Format_RGBA8888)
            return qimg
        except Exception:
            return None

    qimg = QImage(path)
    if qimg.isNull():
        return None

    # normalize format
    if qimg.format() == QImage.Format_Indexed8:
        qimg = qimg.convertToFormat(QImage.Format_RGB32)

    force_dpi72(qimg)
    return qimg
