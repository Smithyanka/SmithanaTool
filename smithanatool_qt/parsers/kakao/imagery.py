# -*- coding: utf-8 -*-
import re
from urllib.parse import urlparse
from typing import Optional

def sanitize_ext(url: str, content_type: Optional[str] = None, default: str = ".img") -> str:
    """
    Возвращает расширение файла по content-type или по URL.
    Если определить нельзя — возвращает default.
    """
    import mimetypes
    if content_type:
        ext = mimetypes.guess_extension((content_type or "").split(";")[0].strip())
        if ext:
            return ext
    path = urlparse(url).path
    m = re.search(r"\.(jpg|jpeg|png|webp|gif|bmp|avif)(?:$|\?)", path, re.I)
    if m:
        return "." + m.group(1).lower()
    return default

def pick_best_from_srcset(srcset_value: str) -> Optional[str]:
    """
    Из srcset выбирает самый «широкий» источник (по w).
    """
    try:
        parts = [p.strip() for p in srcset_value.split(",")]
        candidates = []
        for p in parts:
            bits = p.split()
            if not bits:
                continue
            u = bits[0]
            w = 0
            if len(bits) > 1 and bits[1].endswith("w"):
                try:
                    w = int(bits[1][:-1])
                except Exception:
                    w = 0
            candidates.append((w, u))
        if candidates:
            candidates.sort(key=lambda x: x[0])
            return candidates[-1][1]
    except Exception:
        pass
    return None
