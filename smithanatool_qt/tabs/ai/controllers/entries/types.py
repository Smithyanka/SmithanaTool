from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from PySide6.QtCore import QRect

from smithanatool_qt.tabs.ai.store.entries_store import Entry


RectKey = Tuple[int, int, int, int]


@dataclass
class RectActionSnapshot:
    overlay_rects: List[QRect]
    entries: List[Entry]
    manual_orders: Dict[RectKey, int]
    manual_next: int
    sort_mode: str
