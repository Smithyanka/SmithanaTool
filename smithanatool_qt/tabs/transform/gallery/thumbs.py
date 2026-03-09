from __future__ import annotations

import os
import zlib
from typing import Dict, Tuple, Optional

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QPixmapCache, QImageReader

from ..preview.utils import memory_image_for, _qimage_from_pil


def _safe_icon_size(size: Optional[QSize]) -> QSize:
    if size is None or size.isNull() or size.width() <= 0 or size.height() <= 0:
        return QSize(64, 64)
    return QSize(max(1, size.width()), max(1, size.height()))


def _norm_fs_path(p: str) -> str:
    # нормализация снижает шанс дублей из-за разных форм пути (case/relative)
    try:
        return os.path.normcase(os.path.abspath(p))
    except Exception:
        return p


class ThumbnailProvider:
    """Ленивая генерация и кэширование иконок/миниатюр для элементов списка."""

    def __init__(self) -> None:
        # +sig (CRC32) в ключ
        self._cache: Dict[Tuple[str, int, int, int, int, int, int, int], QIcon] = {}
        self._sig_cache: Dict[Tuple[str, int, int], int] = {}  # (path, mtime_ns, size) -> sig

    def clear(self) -> None:
        self._cache.clear()
        self._sig_cache.clear()
        try:
            QPixmapCache.clear()
        except Exception:
            pass

    def _content_sig(self, path: str, mtime_ns: int, fsize: int) -> int:
        k = (path, mtime_ns, fsize)
        sig = self._sig_cache.get(k)
        if sig is not None:
            return sig

        # CRC32(head + tail)
        try:
            with open(path, "rb") as f:
                head = f.read(65536)
                if fsize > 65536:
                    f.seek(max(0, fsize - 65536))
                    tail = f.read(65536)
                else:
                    tail = b""
            crc = zlib.crc32(head)
            crc = zlib.crc32(tail, crc)
            sig = int(crc & 0xFFFFFFFF)
        except Exception:
            sig = 0

        self._sig_cache[k] = sig
        return sig

    def icon_for(self, path: str, icon_size: Optional[QSize]) -> QIcon:
        size = _safe_icon_size(icon_size)
        w, h = size.width(), size.height()

        # mem:// оставляем как есть
        real_path = path
        if isinstance(path, str) and not path.startswith("mem://"):
            real_path = _norm_fs_path(path)

        mtime_ns = 0
        fsize = 0
        ctime_ns = 0
        ino = 0
        sig = 0

        if isinstance(real_path, str) and not real_path.startswith("mem://"):
            try:
                st = os.stat(real_path)
                mtime_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)))
                fsize = int(st.st_size)
                ctime_ns = int(getattr(st, "st_ctime_ns", int(st.st_ctime * 1e9)))
                ino = int(getattr(st, "st_ino", 0))
                sig = self._content_sig(real_path, mtime_ns, fsize)
            except Exception:
                pass

        key = (real_path, w, h, mtime_ns, fsize, ctime_ns, ino, sig)

        cached = self._cache.get(key)
        if cached is not None:
            return cached

        pm = self._load_pixmap(real_path, size)
        ic = QIcon() if (pm is None or pm.isNull()) else QIcon(
            pm.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        self._cache[key] = ic
        return ic

    # ---------- internals ----------
    def _load_pixmap(self, path: str, size: QSize) -> Optional[QPixmap]:
        if isinstance(path, str) and path.startswith("mem://"):
            try:
                img = memory_image_for(path)
                if img is not None and not img.isNull():
                    return QPixmap.fromImage(img)
            except Exception:
                return None
            return None

        ext = os.path.splitext(path)[1].lower()
        if ext in (".psd", ".psb"):
            return self._load_psd_pixmap(path, size)

        # обычный файл
        try:
            r = QImageReader(path)
            img = r.read()
            if img.isNull():
                return None
            return QPixmap.fromImage(img)
        except Exception:
            return None

    def _load_psd_pixmap(self, path: str, size: QSize) -> Optional[QPixmap]:
        # Ленивая загрузка зависимостей, чтобы не утяжелять старт панели.
        try:
            from psd_tools import PSDImage  # type: ignore
            from PIL import Image as PILImage  # type: ignore
        except Exception:
            return None

        try:
            psd = PSDImage.open(path)
            pil = psd.composite()

            # Чтобы при масштабировании до icon_size картинка выглядела лучше,
            # сначала ужмём до ~2x размера иконки.
            tw = max(64, int(size.width()) * 2)
            th = max(64, int(size.height()) * 2)

            try:
                Resampling = getattr(PILImage, "Resampling", PILImage)
                pil.thumbnail((tw, th), Resampling.LANCZOS)
            except Exception:
                try:
                    pil.thumbnail((tw, th), PILImage.LANCZOS)
                except Exception:
                    pil.thumbnail((tw, th))

            qimg = _qimage_from_pil(pil)
            return QPixmap.fromImage(qimg)
        except Exception:
            return None