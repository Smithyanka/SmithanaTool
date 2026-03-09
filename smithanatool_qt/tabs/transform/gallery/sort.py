from __future__ import annotations

import os
import re
from typing import Any

_SPLIT_RE = re.compile(r"(\d+)")


def apply_sort(files: list[str], field_text: str, order_text: str, added_order: dict[str, int]) -> list[str]:
    reverse = (order_text == "По убыванию")

    if field_text == "По названию":
        return sorted(files, key=natural_key, reverse=reverse)

    if field_text == "По добавлению":
        return sorted(files, key=lambda p: added_order.get(p, float("inf")), reverse=reverse)

    # По дате изменения: добавим natural_key вторым ключом для стабильности
    return sorted(files, key=lambda p: (mtime_key(p), natural_key(p)), reverse=reverse)


def natural_key(path: str) -> list[Any]:
    """Ключ для «естественной» сортировки: file2 < file10."""
    name = os.path.basename(path)
    parts = _SPLIT_RE.split(name)
    return [int(t) if t.isdigit() else t.casefold() for t in parts]


def mtime_key(path: str) -> float:
    """Ключ сортировки по времени модификации файла."""
    try:
        return os.path.getmtime(path)
    except Exception:
        return 0.0