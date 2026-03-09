from __future__ import annotations

import json
import re
from typing import Any, List


def parse_json_string_array(text: str, expected_len: int) -> List[str]:
    """Парсит JSON-массив строк из ответа модели.

    Fallback:
      - если в ответе есть лишний текст/markdown, вытаскиваем первый "[ ... ]" блок.
      - если парсинг не удался: кладём исходный текст в 1-й элемент.
    """

    n = int(expected_len or 0)
    if n <= 0:
        return []

    t = (text or "").strip()
    arr: Any = None

    try:
        arr = json.loads(t)
    except Exception:
        m = re.search(r"\[[\s\S]*?\]", t)
        if m:
            try:
                arr = json.loads(m.group(0))
            except Exception:
                arr = None

    if not isinstance(arr, list):
        out = [""] * n
        out[0] = t
        return out

    out: List[str] = []
    for i in range(n):
        v = arr[i] if i < len(arr) else ""
        if v is None:
            v = ""
        out.append(str(v).strip())
    return out
