from __future__ import annotations

from typing import Optional, Tuple, Callable

from PySide6.QtCore import Qt, QEvent, QPoint, QRect, QSize, QObject
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QPushButton

from .selection_overlay import SelectionOverlay


class _ViewerEventFilter(QObject):
    def __init__(self, mid: QObject, label: QObject, on_mid_resize: Callable[[], None], on_label_resize: Callable[[], None]):
        super().__init__()
        self._mid = mid
        self._label = label
        self._on_mid_resize = on_mid_resize
        self._on_label_resize = on_label_resize

    def eventFilter(self, obj, ev):
        try:
            if ev.type() == QEvent.Resize:
                if obj is self._mid:
                    self._on_mid_resize()
                elif obj is self._label:
                    self._on_label_resize()
        except Exception:
            return False
        return False


class ExtractViewerController:
    """
    Управляет PreviewPanel и SelectionOverlay для вкладки Extract:
    - прячет лишние кнопки PreviewPanel
    - создаёт overlay для прямоугольников
    - создаёт кнопку "Удалить выделения" поверх preview (справа сверху)
    - даёт методы: rects/set_rects/labels, crop, QImage->bytes
    """

    def __init__(self, tab, gallery, preview, right):
        self.tab = tab
        self.gallery = gallery
        self.preview = preview
        self.right = right

        self._configure_preview()

        # Overlay attaches to label
        self.overlay = SelectionOverlay(
            parent=self.preview.label,
            get_img_size=self.get_img_size,
            map_img_to_widget=self.map_img_to_widget,
            map_widget_to_img=self.map_widget_to_img,
        )
        self.overlay.setGeometry(self.preview.label.rect())
        self.overlay.show()

        # Button anchored to preview widget (not image label)
        self.btn_clear_rects = QPushButton("Удалить фрагменты", self.preview)
        self.btn_clear_rects.setAutoDefault(False)
        self.btn_clear_rects.setToolTip("Удаляет рамки выделения. Тексты справа не удаляются.")
        self.btn_clear_rects.clicked.connect(self._on_clear_clicked)
        self.btn_clear_rects.show()
        self.btn_clear_rects.raise_()

        # Event filter: resize preview => reposition button; resize label => resize overlay
        self._filter = _ViewerEventFilter(
            mid=self.preview,
            label=self.preview.label,
            on_mid_resize=self._position_clear_button,
            on_label_resize=self._sync_overlay_geometry,
        )
        self.preview.installEventFilter(self._filter)
        self.preview.label.installEventFilter(self._filter)

        self._position_clear_button()
        self._sync_overlay_geometry()

    def _configure_preview(self):
        # Hide transform-specific controls if present
        for attr in [
            "btn_cut", "btn_paste_top", "btn_paste_bottom",
            "btn_undo", "btn_redo", "lbl_hint", "btn_save", "btn_save_as"
        ]:
            w = getattr(self.preview, attr, None)
            if w:
                try:
                    w.hide()
                except Exception:
                    pass

        if hasattr(self.preview, "lbl_info"):
            try:
                self.preview.lbl_info.hide()
            except Exception:
                pass

        # Disable slice mode if exists
        if hasattr(self.preview, "enable_slice_mode"):
            try:
                self.preview.enable_slice_mode(False)
            except Exception:
                pass

        if hasattr(self.preview, "_clear_selection"):
            try:
                self.preview._clear_selection()
            except Exception:
                pass

    def _sync_overlay_geometry(self):
        try:
            self.overlay.setGeometry(self.preview.label.rect())
            self.overlay.raise_()
        except Exception:
            pass
        try:
            self.btn_clear_rects.raise_()
        except Exception:
            pass

    def _position_clear_button(self):
        try:
            margin_top = 12
            margin_right = 32
            self.btn_clear_rects.adjustSize()
            x = self.preview.width() - self.btn_clear_rects.width() - margin_right
            y = margin_top
            if x < 0:
                x = 0
            self.btn_clear_rects.move(x, y)
        except Exception:
            pass

    def _on_clear_clicked(self):
        # Delegate to EntriesController via tab (it will detach rects without deleting texts)
        try:
            self.tab.entries.clear_rectangles()
        except Exception:
            # fallback: clear overlay only
            try:
                self.overlay.clear()
            except Exception:
                pass

    # ---- Public helpers ----
    def show_path(self, path: Optional[str]):
        show = getattr(self.preview, "show_path", None)
        if callable(show):
            show(path)

    def rects_img(self):
        return self.overlay.rects_img()

    def set_rects_img(self, rects):
        self.overlay.set_rects_img(rects)

    def set_labels(self, labels):
        self.overlay.set_labels(labels)

    def clear_overlay(self):
        self.overlay.clear()

    def get_current_qimage(self) -> Optional[QImage]:
        imgs = getattr(self.preview, "_images", None)
        cur = getattr(self.preview, "_current_path", None)
        if not imgs or not cur:
            return None
        return imgs.get(cur)

    def get_img_size(self) -> QSize:
        qimg = self.get_current_qimage()
        if qimg is None:
            return QSize(1, 1)
        return QSize(qimg.width(), qimg.height())

    def _label_pixmap_geom(self) -> Tuple[QSize, QPoint]:
        lbl = self.preview.label
        pm = lbl.pixmap()
        if pm is None:
            return QSize(1, 1), QPoint(0, 0)
        pm_size = pm.size()
        dx = (lbl.width() - pm_size.width()) // 2
        dy = (lbl.height() - pm_size.height()) // 2
        return pm_size, QPoint(dx, dy)

    def map_img_to_widget(self, r_img: QRect) -> QRect:
        qimg = self.get_current_qimage()
        if qimg is None or r_img.isNull():
            return QRect()
        pm_size, offset = self._label_pixmap_geom()
        sx = pm_size.width() / qimg.width()
        sy = pm_size.height() / qimg.height()
        x = int(r_img.x() * sx + offset.x())
        y = int(r_img.y() * sy + offset.y())
        w = int(r_img.width() * sx)
        h = int(r_img.height() * sy)
        return QRect(x, y, w, h)

    def map_widget_to_img(self, r_w: QRect) -> QRect:
        qimg = self.get_current_qimage()
        if qimg is None or r_w.isNull():
            return QRect()
        pm_size, offset = self._label_pixmap_geom()
        sx = qimg.width() / pm_size.width()
        sy = qimg.height() / pm_size.height()

        x = max(0, r_w.x() - offset.x())
        y = max(0, r_w.y() - offset.y())
        w = max(0, r_w.width())
        h = max(0, r_w.height())

        rx = int(x * sx)
        ry = int(y * sy)
        rw = int(w * sx)
        rh = int(h * sy)

        rx2 = min(qimg.width(), rx + rw)
        ry2 = min(qimg.height(), ry + rh)
        rx = max(0, rx)
        ry = max(0, ry)
        return QRect(rx, ry, max(0, rx2 - rx), max(0, ry2 - ry))

    def crop_qimage(self, rect_img: QRect) -> Optional[QImage]:
        qimg = self.get_current_qimage()
        if qimg is None or rect_img.isNull():
            return None
        r = rect_img.intersected(QRect(0, 0, qimg.width(), qimg.height()))
        if r.isNull():
            return None
        return qimg.copy(r)

    def qimage_to_png_bytes(self, qimg: QImage) -> bytes:
        from PySide6.QtCore import QBuffer, QIODevice
        if qimg is None or qimg.isNull():
            return b""
        buf = QBuffer()
        buf.open(QIODevice.ReadWrite)
        qimg.save(buf, "PNG")
        return bytes(buf.data())


    # --- UI helpers called from tab ---
    def apply_zoom_ui_mode(self, idx: int) -> None:
        """Применить режим UI масштаба (переключатель в правой панели)."""
        if hasattr(self.preview, "_apply_zoom_ui_mode"):
            try:
                self.preview._apply_zoom_ui_mode(int(idx))
            except Exception:
                pass
        # после смены режима может измениться геометрия -> обновим
        try:
            self._sync_overlay_geometry()
            self._position_clear_button()
        except Exception:
            pass

    def toggle_thumbs(self, enabled: bool) -> None:
        """Включить/выключить превью-миниатюры в галерее."""
        # Предпочтительно через API галереи/превью (если есть)
        try:
            gp = getattr(self.preview, "gallery_panel", None)
            if gp is not None and hasattr(gp, "set_show_thumbnails"):
                gp.set_show_thumbnails(bool(enabled))
                return
        except Exception:
            pass

        # fallback: напрямую менять iconSize у списка галереи
        try:
            if hasattr(self.gallery, "list"):
                from PySide6.QtCore import QSize
                self.gallery.list.setIconSize(QSize(128, 128) if enabled else QSize(1, 1))
        except Exception:
            pass

