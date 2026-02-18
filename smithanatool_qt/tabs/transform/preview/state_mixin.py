from typing import Optional, List
import os
from PySide6.QtGui import QImage
from concurrent.futures import ThreadPoolExecutor, as_completed
from PySide6.QtCore import QPoint

class StateMixin:
        def _sync_slice_count_and_emit(self):
            """Синхронизирует _slice_count с текущими границами и эмитит сигнал при изменении."""
            n = max(1, len(self._slice_bounds) - 1) if self._slice_bounds else 0
            if n != getattr(self, "_slice_count", n):
                self._slice_count = n
                try:
                    self.sliceCountChanged.emit(n)
                except Exception:
                    pass
    
    
        def _store_slice_state(self, path: Optional[str]):
            """Снимок состояния нарезки для указанного пути (обычно текущего)."""
            if not path:
                return
            st = {
                "enabled": bool(getattr(self, "_slice_enabled", False)),
                "by": str(getattr(self, "_slice_by", "count")),
                "count": int(getattr(self, "_slice_count", 2)),
                "height_px": int(getattr(self, "_slice_height_px", 2000)),
                "bounds": list(getattr(self, "_slice_bounds", []) or []),
            }
            self._slice_state[path] = st
    
    
        def _restore_slice_state(self, path: Optional[str]):
            """Применить сохранённое состояние для пути (если есть). Безопасно к отсутствию."""
            if not path:
                return
            st = self._slice_state.get(path)
            img = self._images.get(path)
            if st is None or img is None:
                # по умолчанию — нарезка выключена
                self._slice_enabled = False
                self._slice_bounds = []
                self._sync_slice_count_and_emit()
                self._update_preview_pixmap()
                return
    
            # применяем режим/параметры
            self._slice_enabled = bool(st.get("enabled", False))
            self._slice_by = "height" if st.get("by") == "height" else "count"
            self._slice_count = max(2, int(st.get("count", 2)))
            self._slice_height_px = max(1, int(st.get("height_px", 2000)))
    
            bounds = list(st.get("bounds") or [])
            # подстраховка: корректируем под текущую высоту изображения
            H = int(img.height())
            bounds = sorted(set(max(0, min(H, int(y))) for y in bounds))
            if not bounds or bounds[0] != 0:
                bounds = [0] + bounds
            if bounds[-1] != H:
                bounds.append(H)
            # Если границы есть — используем их; иначе пересобираем по режиму
            if len(bounds) >= 3 and any(bounds[i + 1] > bounds[i] for i in range(len(bounds) - 1)):
                self._slice_bounds = bounds
                # Синхронизируем self._slice_count и, если есть, уведомим UI
                self._slice_count = max(2, len(self._slice_bounds) - 1)
                try:
                    if hasattr(self, "sliceCountChanged"):
                        self.sliceCountChanged.emit(int(self._slice_count))
                except Exception:
                    pass
            else:
                # как и раньше — пересобираем по активному режиму
                if self._slice_by == "height":
                    try:
                        self._init_slice_bounds()
                    except Exception:
                        self._slice_bounds = [0, H]
                else:
                    self._rebuild_slice_bounds()
    
            self._update_preview_pixmap()
    
        def get_slice_state(self, path: Optional[str] = None) -> dict:
            """Вернуть слепок текущего состояния (для отладки/логов)."""
            p = path or self._current_path
            if not p:
                return {}
            cur = {
                "enabled": bool(getattr(self, "_slice_enabled", False)),
                "by": str(getattr(self, "_slice_by", "count")),
                "count": int(getattr(self, "_slice_count", 2)),
                "height_px": int(getattr(self, "_slice_height_px", 2000)),
                "bounds": list(getattr(self, "_slice_bounds", []) or []),
            }
            # если есть сохранённая версия — вернём её (реальное пер-файловое состояние)
            return self._slice_state.get(p, cur)
    
    
        def _recalc_dirty_vs_disk(self, path: str | None = None):
            p = path or self._current_path
            if not p:
                return
            base = self._loaded_from_disk.get(p)
            cur = self._images.get(p)
            if base is None or cur is None:
                return
            # QImage == сравнивает содержимое, размеры и формат
            self._set_dirty(p, not (cur == base))
    
        def forget_paths(self, paths: list[str]) -> None:
            """Полностью убрать пути из внутренних кэшей превью."""
            if not paths:
                return
            if getattr(self, "_current_path", None) in paths:
                self._current_path = None
                try:
                    self.label.setText("Нет изображения")
                except Exception:
                    pass
    
            # Чистим все связанные структуры
            for p in paths:
                # снять звёздочку, если была
                try:
                    if getattr(self, "_dirty", {}).get(p, False):
                        self.dirtyChanged.emit(p, False)
                except Exception:
                    pass
                if hasattr(self, "_images"):            self._images.pop(p, None)
                if hasattr(self, "_undo"):              self._undo.pop(p, None)
                if hasattr(self, "_redo"):              self._redo.pop(p, None)
                if hasattr(self, "_loaded_from_disk"):  self._loaded_from_disk.pop(p, None)
                if hasattr(self, "_dirty"):             self._dirty.pop(p, None)
                if hasattr(self, "_scroll_pos"):         self._scroll_pos.pop(p, None)
    
            # Обновить кнопки/инфо
            try:
                self._update_actions_enabled()
                self._update_info_label()
                self.label.update()
            except Exception:
                pass
    
    
        def set_slice_mode(self, on: bool, count: Optional[int] = None):
            self._slice_enabled = bool(on)
            if count is not None:
                self._slice_count = max(2, int(count))
            self._rebuild_slice_bounds()
            self._update_preview_pixmap()
    
    
        def set_slice_count(self, count: int):
            self._slice_count = max(2, int(count))
            self._rebuild_slice_bounds()
            self._update_preview_pixmap()
    
        def save_slices(self, out_dir: str, threads: int = 4, auto_threads: bool = True) -> int:
            """Режет текущее изображение по _slice_bounds и сохраняет фрагменты параллельно.
            Возвращает число успешно сохранённых фрагментов.
            """
            if not (self._current_path and self._current_path in self._images):
                return 0
            if not self._slice_enabled or not self._slice_bounds or len(self._slice_bounds) < 2:
                return 0
    
            img: QImage = self._images[self._current_path]
            h, w = img.height(), img.width()
            bounds = list(self._slice_bounds)
            # подстрахуемся, что 0 и h на краях
            if bounds[0] != 0: bounds[0] = 0
            if bounds[-1] != h: bounds[-1] = h
    
            # авто-потоки
            if auto_threads:
                cpu = os.cpu_count() or 4
                threads = max(2, min(8, cpu))  # не перегружаем диск
    
            tasks = []
    
            def _save_one(i: int, y1: int, y2: int) -> bool:
                cut_h = max(1, y2 - y1)
                frag = img.copy(0, y1, w, cut_h)  # локальная копия для потока
                # имена вида: <basename>_s01.png
                base = os.path.splitext(os.path.basename(self._current_path))[0]
                dst = os.path.join(out_dir, f"{base}_{str(i + 1).zfill(2)}.png")
                return bool(frag.save(dst))
    
            with ThreadPoolExecutor(max_workers=int(threads)) as ex:
                for i in range(len(bounds) - 1):
                    y1, y2 = bounds[i], bounds[i + 1]
                    if y2 <= y1:  # пропуск нулевой высоты
                        continue
                    tasks.append(ex.submit(_save_one, i, int(y1), int(y2)))
    
                done_ok = 0
                for fut in as_completed(tasks):
                    try:
                        if fut.result():
                            done_ok += 1
                    except Exception:
                        pass
    
            return done_ok
    
        # ---------- Геометрия + перетаскивание ----------
    
        def _rebuild_slice_bounds(self):
            """Равномерное разбиение по высоте текущего изображения."""
            if not (self._current_path and self._current_path in self._images):
                self._slice_bounds = []
                return
            img: QImage = self._images[self._current_path]
            H = img.height()
            n = max(2, int(self._slice_count))
            step = H / n
            ys = [0]
            acc = 0.0
            for _ in range(1, n):
                acc += step
                ys.append(int(round(acc)))
            ys.append(H)
            # устраняем возможные дубликаты из-за округления
            ys2 = [ys[0]]
            for y in ys[1:]:
                if y <= ys2[-1]:
                    y = ys2[-1] + 1
                ys2.append(min(y, H))
            ys2[-1] = H
            self._slice_bounds = ys2
            self._sync_slice_count_and_emit()
    
        def _slice_bounds_on_label(self) -> List[int]:
            """Пересчёт границ из координат изображения в координаты pixmap/label."""
            pm = self.label.pixmap()
            if not pm or not (self._current_path and self._current_path in self._images):
                return []
            img = self._images[self._current_path]
            scaled_h = pm.height()
            ys = []
            for y in self._slice_bounds:
                ys.append(int(y * scaled_h / max(1, img.height())))
            # монотонность/границы
            ys2 = [max(0, min(scaled_h, ys[0]))] if ys else []
            for y in ys[1:]:
                y = max(ys2[-1], min(scaled_h, y))
                ys2.append(y)
            return ys2
    
        def _boundary_under_cursor(self, pos_label: QPoint, thresh: int = 6) -> Optional[int]:
            ys = self._slice_bounds_on_label()
            if not ys:
                return None
            y0 = self._v_offset_on_label()
            for i, y in enumerate(ys[1:-1], start=1):  # только внутренние границы
                if abs(pos_label.y() - (y0 + y)) <= thresh:
                    return i
            return None
    
    
