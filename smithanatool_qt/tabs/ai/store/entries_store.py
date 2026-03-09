from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from PySide6.QtCore import QRect


@dataclass
class Entry:
    text: str
    rect: Optional[QRect] = None


class EntriesStore:
    """Хранилище фрагментов (текст + опциональный QRect) по пути изображения."""

    def __init__(self):
        self._by_path: Dict[str, List[Entry]] = {}

    # ---- basics ----
    def ensure_path(self, path: str) -> None:
        p = path or ""
        if p not in self._by_path:
            self._by_path[p] = []

    def entries(self, path: str) -> List[Entry]:
        self.ensure_path(path)
        return self._by_path[path or ""]

    def texts(self, path: str) -> List[str]:
        return [e.text or "" for e in self.entries(path)]

    def rects(self, path: str) -> List[QRect]:
        return [e.rect for e in self.entries(path) if e.rect is not None]

    # ---- CRUD from right panel ----
    def set_text(self, path: str, index: int, text: str) -> None:
        es = self.entries(path)
        if 0 <= index < len(es):
            es[index].text = text

    def delete_entry(self, path: str, index: int) -> None:
        es = self.entries(path)
        if 0 <= index < len(es):
            del es[index]

    def add_entry(self, path: str, text: str, rect: Optional[QRect]) -> None:
        self.entries(path).append(Entry(text=text, rect=rect))

    # ---- overlay-driven updates ----
    def mark_rect_deleted(self, path: str, rect_img: QRect) -> None:
        for e in self.entries(path):
            if e.rect is not None and e.rect == rect_img:
                e.rect = None
                return

    def update_rect(self, path: str, old_rect: QRect, new_rect: QRect) -> None:
        for e in self.entries(path):
            if e.rect is not None and e.rect == old_rect:
                e.rect = new_rect
                return

    def clear_rectangles(self, path: str, overlay_rects: List[QRect]) -> None:
        if not overlay_rects:
            return
        rect_keys = {(r.x(), r.y(), r.width(), r.height()) for r in overlay_rects}
        for e in self.entries(path):
            r = e.rect
            if r is None:
                continue
            if (r.x(), r.y(), r.width(), r.height()) in rect_keys:
                e.rect = None

    # ---- mapping / labels ----
    def index_by_rect(self, path: str, rect: QRect) -> int:
        """Возвращает индекс entry (0-based) у которого rect совпадает, иначе -1."""
        for i, e in enumerate(self.entries(path)):
            if e.rect is not None and e.rect == rect:
                return i
        return -1

    def labels_for_rects(self, path: str, rects: List[QRect], mode: str) -> List[str]:
        """mode: 'visual' (1..N на оверлее) или любой другой — по индексу entry."""
        if mode == "visual":
            return [str(i + 1) for i in range(len(rects))]

        labels: List[str] = []
        for r in rects:
            idx = self.index_by_rect(path, r)
            labels.append(str(idx + 1) if idx >= 0 else "•")
        return labels

    # ---- applying OCR results ----
    def apply_ocr_results(self, path: str, rects_fixed: List[QRect], texts: List[str]) -> None:
        """Обновляет/добавляет entries по результатам OCR."""
        es = self.entries(path)

        def norm(t: str) -> str:
            t = (t or "").strip()
            return " ".join(t.split())

        for r, t in zip(rects_fixed, texts):
            text = norm(t)
            updated = False
            for e in es:
                if e.rect is not None and e.rect == r:
                    # если OCR пустой — не затираем существующий текст
                    if text:
                        e.text = text
                    updated = True
                    break

            if not updated:
                es.append(
                    Entry(
                        text=text or f"Фрагмент {len(es) + 1}",
                        rect=r,
                    )
                )
