from typing import Optional, Tuple

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import (
    QImage, QPainter
)
from PySide6.QtWidgets import (
    QApplication
)
import  math

from .utils import force_dpi72

class SelectionMixin:


        def _clear_selection(self):
            self._sel_active = False
            self._sel_y1 = None
            self._sel_y2 = None
            self._resizing_edge = None
            self.label.setCursor(Qt.ArrowCursor)
            self.label.update()
            self._update_actions_enabled()
            self._update_info_label()
    
        def _has_selection(self) -> bool:
            return (
                (self._current_path in self._images) if self._current_path else False
            ) and (
                    self._sel_y1 is not None and self._sel_y2 is not None and abs(self._sel_y2 - self._sel_y1) > 0
            )
    
        def _label_to_image_y_edge(self, y_label: int, *, as_top: bool) -> int:
            pm = self.label.pixmap()
            if not pm or not (self._current_path and self._current_path in self._images):
                return 0
            img = self._images[self._current_path]
            y0 = self._v_offset_on_label()
            y_rel = y_label - y0
            if y_rel <= 0:
                return 0
            if y_rel >= pm.height():
                return img.height()
            ratio = img.height() / pm.height()
            if as_top:
                return int(y_rel * ratio)  # floor
            else:
                return min(img.height(), int(math.ceil(y_rel * ratio)))  # ceil
    
        def _begin_selection(self, pos_label: QPoint):
            if not (self._current_path and self._current_path in self._images):
                return
            self._sel_active = True
            y_top = self._label_to_image_y_edge(pos_label.y(), as_top=True)
            h = self._images[self._current_path].height()
            self._sel_y1 = max(0, min(h, y_top))
            self._sel_y2 = self._sel_y1
            self.label.update()
            self._update_actions_enabled()
            self._update_info_label()
    
    
        def _update_selection(self, pos_label: QPoint):
            if not self._sel_active or not (self._current_path and self._current_path in self._images):
                return
            y = self._label_to_image_y(pos_label.y())
            h = self._images[self._current_path].height()
            self._sel_y2 = max(1, min(h, self._label_to_image_y_edge(pos_label.y(), as_top=False)))
            self.label.update()
            self._update_actions_enabled()
            self._update_info_label()
    
    
        def _end_selection(self, pos_label: QPoint):
            if not self._sel_active or not (self._current_path and self._current_path in self._images):
                return
            y = self._label_to_image_y(pos_label.y())
            h = self._images[self._current_path].height()
            self._sel_y2 = max(1, min(h, self._label_to_image_y_edge(pos_label.y(), as_top=False)))
            self._sel_active = False
            # Нулевая высота — сброс
            if self._sel_y1 is None or self._sel_y2 is None or abs(self._sel_y2 - self._sel_y1) < 1:
                self._clear_selection()
                return
            if self._sel_y1 > self._sel_y2:
                self._sel_y1, self._sel_y2 = self._sel_y2, self._sel_y1
            h = self._images[self._current_path].height()
            y1 = int(self._sel_y1)
            y2 = int(self._sel_y2)
            self._sel_y1, self._sel_y2 = self._snap_selection_to_edges(h, y1, y2)
            self.label.update()
            self._update_actions_enabled()
            self._update_info_label()
    
        # --- редактирование выделения (resize) ---
        def _selection_on_label(self) -> Tuple[Optional[int], Optional[int]]:
            if not self._has_selection():
                return None, None
            img = self._images[self._current_path]
            pm = self.label.pixmap()
            scaled_h = pm.height()
            y1 = int(self._sel_y1 * scaled_h / max(1, img.height()))
            y2 = int(math.ceil(self._sel_y2 * scaled_h / max(1, img.height())))
            y1 = max(0, min(scaled_h, y1))
            y2 = max(0, min(scaled_h, y2))
            if y1 > y2:
                y1, y2 = y2, y1
            return y1, y2
    
        def _v_offset_on_label(self) -> int:
            """Вернёт вертикальный отступ (y0) pixmap внутри QLabel."""
            pm = self.label.pixmap()
            if not pm:
                return 0
            # QLabel по-прежнему с AlignCenter, поэтому центровка по вертикали работает
            return max(0, (self.label.height() - pm.height()) // 2) if (self.label.alignment() & Qt.AlignVCenter) else 0
    
        def _label_to_image_y(self, y_label: int) -> int:
            pm = self.label.pixmap()
            if not pm or not (self._current_path and self._current_path in self._images):
                return 0
            img = self._images[self._current_path]
    
            y0 = self._v_offset_on_label()
            y_rel = y_label - y0  # координата относительно ВЕРХА pixmap
    
            if y_rel <= 0:
                return 0
            if y_rel >= pm.height():
                return img.height()  # позволяем нижней границе быть ровно h
    
            # floor-мэппинг внутрь [0..h)
            return int(y_rel * img.height() / pm.height())
    
        def _edge_under_cursor(self, pos_label: QPoint, thresh: int = 6) -> Optional[str]:
            if not self._has_selection():
                return None
            y1, y2 = self._selection_on_label()  # координаты в системе ПИКСМАПА
            if y1 is None:
                return None
            y0 = self._v_offset_on_label()
            if abs(pos_label.y() - (y0 + y1)) <= thresh:
                return 'top'
            if abs(pos_label.y() - (y0 + y2)) <= thresh:
                return 'bottom'
            return None
    
        def _update_hover_cursor(self, pos_label: QPoint) -> bool:
            edge = self._edge_under_cursor(pos_label)
            if edge:
                self.label.setCursor(Qt.SizeVerCursor)
                return True
            else:
                self.label.setCursor(Qt.ArrowCursor)
                return False
    
        def _press_selection(self, pos_label: QPoint) -> bool:
            edge = self._edge_under_cursor(pos_label)
            if edge:
                self._resizing_edge = edge
                self.label.setCursor(Qt.SizeVerCursor)
                return True
    
            # клик вне области — сброс
            if self._has_selection():
                y1, y2 = self._selection_on_label()
                if y1 is not None:
                    y0 = self._v_offset_on_label()
                    if not (y0 + y1 <= pos_label.y() <= y0 + y2):
                        self._clear_selection()
    
            # начать новое выделение
            self._begin_selection(pos_label)
            return True
    
    
        def _resize_selection(self, pos_label: QPoint):
            if not self._resizing_edge or not (self._current_path and self._current_path in self._images):
                return
            y = self._label_to_image_y(pos_label.y())
            h = self._images[self._current_path].height()
            y = max(1, min(h, y))
            if self._resizing_edge == 'bottom':
                self._sel_y2 = max(1, min(h, self._label_to_image_y_edge(pos_label.y(), as_top=False)))
            elif self._resizing_edge == 'top':
                self._sel_y1 = max(0, min(h, self._label_to_image_y_edge(pos_label.y(), as_top=True)))
            self.label.update()
            self._update_actions_enabled()
            self._update_info_label()
    
    
        def _copy_selection(self):
            # есть ли изображение и выделение
            if not (self._current_path and self._current_path in self._images and self._has_selection()):
                return
    
            img: QImage = self._images[self._current_path]
            h, w = img.height(), img.width()
    
            # нормализуем и «прибиваем» к краям, как в cut
            y1 = int(self._sel_y1)
            y2 = int(self._sel_y2)
            y1, y2 = self._snap_selection_to_edges(h, y1, y2)
            if y2 <= y1:
                return
    
            cut_h = y2 - y1
            frag = img.copy(0, y1, w, cut_h)
    
            # во внутренний буфер приложения (для "Вставить в начало/конец")
            self._clip.append(frag)
    
            # в системный буфер обмена — как изображение (для вставки в другие программы)
            try:
                QApplication.clipboard().setImage(frag)
            except Exception:
                pass
    
            # UI-обратная связь + обновление доступности вставки
            self.show_toast(f"Скопировано: {w}×{cut_h}px", 1500)
            self._update_actions_enabled()
    
    
        def _cut_selection(self):
            if not self._has_selection():
                return
            img = self._images[self._current_path]
            h, w = img.height(), img.width()
    
            # НОРМАЛИЗУЕМ И ПРИБИВАЕМ К КРАЯМ
            y1 = int(self._sel_y1)
            y2 = int(self._sel_y2)
            y1, y2 = self._snap_selection_to_edges(h, y1, y2)
            if y2 <= y1:
                return
    
            cut_h = y2 - y1
            frag = img.copy(0, y1, w, cut_h)
            self._clip.append(frag)
    
            self._push_undo()
            new_img = QImage(w, h - cut_h,
                             img.format() if img.format() != QImage.Format_Indexed8 else QImage.Format_RGB32)
            force_dpi72(new_img)
            new_img.fill(Qt.transparent if new_img.hasAlphaChannel() else Qt.white)
            p = QPainter(new_img)
            if y1 > 0:
                p.drawImage(0, 0, img, 0, 0, w, y1)
            if y2 < h:
                p.drawImage(0, y1, img, 0, y2, w, h - y2)
            p.end()
    
            self._images[self._current_path] = new_img
            self._recalc_dirty_vs_disk()
            self._clear_selection()
            self._update_preview_pixmap()
            self._update_actions_enabled()
    
    
        def _paste_fragment(self, at_top: bool):
            if not (self._current_path and self._current_path in self._images):
                return
            if not self._clip:
                return
            base = self._images[self._current_path]
            frag = self._clip[-1]
            if frag.width() != base.width():
                frag = frag.scaled(base.width(), int(frag.height() * (base.width() / frag.width())),
                                   Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                force_dpi72(frag)
    
            self._push_undo()
            w = base.width()
            new_h = base.height() + frag.height()
            new_img = QImage(w, new_h, base.format() if base.format() != QImage.Format_Indexed8 else QImage.Format_RGB32)
            force_dpi72(new_img)
            new_img.fill(Qt.transparent if new_img.hasAlphaChannel() else Qt.white)
    
            p = QPainter(new_img)
            if at_top:
                p.drawImage(0, 0, frag)
                p.drawImage(0, frag.height(), base)
            else:
                p.drawImage(0, 0, base)
                p.drawImage(0, base.height(), frag)
            p.end()
    
            self._images[self._current_path] = new_img
            self._set_dirty(self._current_path, True)
            self._update_preview_pixmap()
            self._update_actions_enabled()
    
    
