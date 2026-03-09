from __future__ import annotations
import os, re
from PySide6.QtGui import QImageReader

_DEFAULT_EXT = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.psd', '.psb'}

def _runtime_supported_ext() -> set[str]:
    """Расширения, которые реально умеет читать Qt на этой машине."""
    try:
        fmts = QImageReader.supportedImageFormats()  # [QByteArray, ...]
        qt_exts = {"." + bytes(f).decode("ascii").lower() for f in fmts}
        return qt_exts | _DEFAULT_EXT
    except Exception:
        return _DEFAULT_EXT

SUPPORTED_EXT = _runtime_supported_ext()


def is_image(path: str) -> bool:
    if isinstance(path, str) and path.startswith("mem://"):
        return True

    if not os.path.isfile(path):
        return False
    try:
        reader = QImageReader(path)
        if reader.canRead():
            return True
    except Exception:
        pass

    ext = os.path.splitext(path)[1].lower()
    return ext in SUPPORTED_EXT

def dedup_keep_order(items):
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

