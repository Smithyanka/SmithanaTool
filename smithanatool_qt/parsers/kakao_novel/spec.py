# -*- coding: utf-8 -*-
"""Спецификации выбора номеров глав/томов: парсинг диапазонов."""

from __future__ import annotations
from typing import List

import re

def parse_num_spec(spec: str) -> List[int]:
    """'1,2,5-7 10' → [1,2,5,6,7,10] (без дублей, порядок сохраняем)."""
    nums: List[int] = []
    spec = (spec or "").strip()
    if not spec:
        return nums
    tokens = re.split(r"[,\s]+", spec)
    for t in tokens:
        if not t:
            continue
        m = re.match(r"^(\d+)-(\d+)$", t)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            step = 1 if a <= b else -1
            nums.extend(range(a, b + step, step))
        elif t.isdigit():
            nums.append(int(t))
    # de-dupe, keep order
    seen = set()
    out: List[int] = []
    for n in nums:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


