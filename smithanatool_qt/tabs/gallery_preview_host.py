from __future__ import annotations

from typing import Callable, Optional, Sequence, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QSplitter


class GalleryPreviewHost(QWidget):
    """
    Общий каркас: GalleryPanel | PreviewPanel | (опционально) RightPanel в QSplitter.

    Идея: разные вкладки "надевают" свою логику поверх одного и того же host-а.

    Параметры:
      - gallery_factory: Callable[[], QWidget]
      - preview_factory: Callable[[], QWidget]
      - right_factory: Callable[[gallery, preview], QWidget] | None
      - persist_key: строка для сохранения размеров сплиттера (как было в TransformTab)
      - sizes: дефолтные размеры панелей
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        gallery_factory: Callable[[], QWidget],
        preview_factory: Callable[[], QWidget],
        right_factory: Optional[Callable[..., QWidget]] = None,
        persist_key: Optional[str] = None,
        sizes: Optional[Sequence[int]] = None,
    ):
        super().__init__(parent)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setChildrenCollapsible(False)

        if persist_key:
            splitter.setProperty("persist_key", str(persist_key))

        self.splitter = splitter

        # Panels
        self.gallery = gallery_factory()
        self.preview = preview_factory()

        # Common wiring (safe via hasattr)
        try:
            setattr(self.preview, "gallery_panel", self.gallery)
        except Exception:
            pass

        # "unsaved"/"dirty" glue (used by Transform gallery)
        try:
            if hasattr(self.gallery, "set_unsaved_checker") and hasattr(self.preview, "has_unsaved_changes"):
                self.gallery.set_unsaved_checker(self.preview.has_unsaved_changes)
        except Exception:
            pass

        try:
            if hasattr(self.gallery, "set_dirty_checker") and hasattr(self.preview, "is_dirty"):
                self.gallery.set_dirty_checker(self.preview.is_dirty)
        except Exception:
            pass

        try:
            if hasattr(self.preview, "dirtyChanged") and hasattr(self.gallery, "mark_dirty"):
                self.preview.dirtyChanged.connect(self.gallery.mark_dirty)
        except Exception:
            pass

        try:
            if hasattr(self.gallery, "set_forget_callback") and hasattr(self.preview, "forget_paths"):
                self.gallery.set_forget_callback(self.preview.forget_paths)
        except Exception:
            pass

        splitter.addWidget(self.gallery)
        splitter.addWidget(self.preview)

        self.right = None
        if right_factory is not None:
            # allow right_factory(gallery, preview) OR right_factory(gallery, preview, parent)
            try:
                right = right_factory(self.gallery, self.preview, self)
            except TypeError:
                right = right_factory(self.gallery, self.preview)
            self.set_right_widget(right)

        if sizes:
            try:
                splitter.setSizes(list(sizes))
            except Exception:
                pass

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(splitter)

    def set_right_widget(self, right: Optional[QWidget]) -> None:
        # Remove previous right if exists
        if self.right is not None:
            try:
                self.right.setParent(None)
            except Exception:
                pass
            self.right = None

        if right is None:
            return

        self.right = right
        self.splitter.addWidget(right)
