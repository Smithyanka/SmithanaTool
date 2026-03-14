from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple
import uuid

from PySide6.QtCore import QRect


@dataclass
class Entry:
    text: str = ""
    rect: Optional[QRect] = None
    uid: str = field(default_factory=lambda: uuid.uuid4().hex)


class EntriesStore:
    """Хранилище фрагментов (текст + опциональный QRect) по пути изображения.

    Основной идентификатор entry — ``uid``. Rect/index-based методы сохранены
    как совместимый слой для постепенной миграции существующего кода.
    """

    def __init__(self):
        self._by_path: Dict[str, List[Entry]] = {}

    # ---- internals ----
    def _norm_path(self, path: str) -> str:
        return path or ""

    def _clone_rect(self, rect: Optional[QRect]) -> Optional[QRect]:
        if rect is None or rect.isNull():
            return None
        return QRect(rect)

    def _clone_entry(self, entry: Entry) -> Entry:
        return Entry(
            text=(entry.text or ""),
            rect=self._clone_rect(entry.rect),
            uid=str(getattr(entry, "uid", "")) or uuid.uuid4().hex,
        )

    # ---- basics ----
    def ensure_path(self, path: str) -> None:
        p = self._norm_path(path)
        if p not in self._by_path:
            self._by_path[p] = []

    def entries(self, path: str) -> List[Entry]:
        """Возвращает внутренний mutating-список entries для path.

        Для безопасного чтения без доступа к внутреннему состоянию используй
        ``entries_snapshot()``.
        """
        p = self._norm_path(path)
        self.ensure_path(p)
        return self._by_path[p]

    def entries_snapshot(self, path: str) -> List[Entry]:
        return [self._clone_entry(e) for e in self.entries(path)]

    def texts(self, path: str) -> List[str]:
        return [e.text or "" for e in self.entries(path)]

    def rects(self, path: str) -> List[QRect]:
        return [QRect(e.rect) for e in self.entries(path) if e.rect is not None and not e.rect.isNull()]

    def paths(self) -> List[str]:
        return list(self._by_path.keys())

    def clear(self, path: str) -> None:
        self._by_path[self._norm_path(path)] = []

    def clear_all(self) -> None:
        self._by_path.clear()

    # ---- uid-based access ----
    def get_entry(self, path: str, uid: str) -> Optional[Entry]:
        for entry in self.entries(path):
            if entry.uid == uid:
                return entry
        return None

    def has_entry(self, path: str, uid: str) -> bool:
        return self.get_entry(path, uid) is not None

    def index_by_uid(self, path: str, uid: str) -> int:
        for i, entry in enumerate(self.entries(path)):
            if entry.uid == uid:
                return i
        return -1

    def set_text_by_uid(self, path: str, uid: str, text: str) -> bool:
        entry = self.get_entry(path, uid)
        if entry is None:
            return False
        entry.text = text or ""
        return True

    def set_rect_by_uid(self, path: str, uid: str, rect: Optional[QRect]) -> bool:
        entry = self.get_entry(path, uid)
        if entry is None:
            return False
        entry.rect = self._clone_rect(rect)
        return True

    def delete_by_uid(self, path: str, uid: str) -> bool:
        idx = self.index_by_uid(path, uid)
        if idx < 0:
            return False
        del self.entries(path)[idx]
        return True

    def reorder_entries_by_uids(self, path: str, uids_in_order: Sequence[str]) -> None:
        es = list(self.entries(path))
        if not es:
            return

        by_uid = {entry.uid: entry for entry in es}
        ordered: List[Entry] = []
        used: set[str] = set()

        for uid in uids_in_order or []:
            entry = by_uid.get(uid)
            if entry is None or uid in used:
                continue
            ordered.append(entry)
            used.add(uid)

        rest = [entry for entry in es if entry.uid not in used]
        self._by_path[self._norm_path(path)] = ordered + rest

    # ---- CRUD from right panel (legacy/index-based) ----

    def add_entry(
        self,
        path: str,
        text: str = "",
        rect: Optional[QRect] = None,
        uid: Optional[str] = None,
    ) -> Entry:
        entry = Entry(
            text=(text or ""),
            rect=self._clone_rect(rect),
            uid=str(uid or "") or uuid.uuid4().hex,
        )
        self.entries(path).append(entry)
        return entry

    # ---- overlay-driven updates (legacy/rect-based) ----
    def mark_rect_deleted(self, path: str, rect_img: QRect) -> None:
        idx = self.index_by_rect(path, rect_img)
        if idx < 0:
            return
        self.set_rect_by_uid(path, self.entries(path)[idx].uid, None)

    def update_rect(self, path: str, old_rect: QRect, new_rect: QRect) -> None:
        idx = self.index_by_rect(path, old_rect)
        if idx < 0:
            return
        self.set_rect_by_uid(path, self.entries(path)[idx].uid, new_rect)

    def clear_rectangles(self, path: str, overlay_rects: List[QRect]) -> None:
        if not overlay_rects:
            return
        rect_keys = {(r.x(), r.y(), r.width(), r.height()) for r in overlay_rects}
        for entry in self.entries(path):
            rect = entry.rect
            if rect is None:
                continue
            if (rect.x(), rect.y(), rect.width(), rect.height()) in rect_keys:
                entry.rect = None

    def restore_rectangles(self, path: str, records: Sequence[Tuple[Optional[int], QRect]]) -> None:
        if not records:
            return

        es = self.entries(path)
        for idx, rect in records:
            if idx is None or not (0 <= idx < len(es)):
                continue
            if rect is None or rect.isNull():
                continue
            self.set_rect_by_uid(path, es[idx].uid, rect)

    def reorder_entries_by_rects(self, path: str, rects_in_order: Sequence[QRect]) -> None:
        if not rects_in_order:
            return

        uids_in_order: List[str] = []
        used_uids: set[str] = set()
        for rect in rects_in_order:
            idx = self.index_by_rect(path, rect)
            if idx < 0:
                continue
            uid = self.entries(path)[idx].uid
            if uid in used_uids:
                continue
            used_uids.add(uid)
            uids_in_order.append(uid)

        self.reorder_entries_by_uids(path, uids_in_order)

    def replace_entries(self, path: str, entries: Sequence[Entry]) -> None:
        p = self._norm_path(path)
        self._by_path[p] = [self._clone_entry(e) for e in entries]

    # ---- mapping / labels (legacy/presentation helper) ----
    def index_by_rect(self, path: str, rect: QRect) -> int:
        """Возвращает индекс entry (0-based), у которого rect совпадает, иначе -1."""
        for i, entry in enumerate(self.entries(path)):
            if entry.rect is not None and entry.rect == rect:
                return i
        return -1

    def labels_for_rects(self, path: str, rects: List[QRect], mode: str) -> List[str]:
        """mode: 'visual' (1..N на оверлее) или любой другой — по индексу entry."""
        if mode == "visual":
            return [str(i + 1) for i in range(len(rects))]

        labels: List[str] = []
        for rect in rects:
            idx = self.index_by_rect(path, rect)
            labels.append(str(idx + 1) if idx >= 0 else "•")
        return labels

    # ---- applying OCR results (legacy/domain helper) ----
    def apply_ocr_results(self, path: str, rects_fixed: List[QRect], texts: List[str]) -> None:
        """Обновляет/добавляет entries по результатам OCR."""
        es = self.entries(path)

        def norm(text: str) -> str:
            text = (text or "").strip()
            return " ".join(text.split())

        for rect, raw_text in zip(rects_fixed, texts):
            text = norm(raw_text)
            updated = False
            for entry in es:
                if entry.rect is not None and entry.rect == rect:
                    # если OCR пустой — не затираем существующий текст
                    if text:
                        entry.text = text
                    updated = True
                    break

            if not updated:
                self.add_entry(
                    path,
                    text=text or f"Фрагмент {len(es) + 1}",
                    rect=rect,
                )
