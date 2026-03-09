from __future__ import annotations

from typing import Optional, Callable, List, Tuple

from PySide6.QtCore import Qt, QRect, QThreadPool
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QMessageBox

from smithanatool_qt.tabs.ai.ui.widgets.busy_overlay import BusyOverlay
from smithanatool_qt.tabs.ai.jobs.entries_ocr_jobs import OcrConfigError, prepare_ocr_work
from smithanatool_qt.tabs.ai.services.selection_provider import build_ocr_runtime_config
from smithanatool_qt.tabs.ai.store.entries_store import EntriesStore
from smithanatool_qt.tabs.ai.ui.widgets.handwriting_input import HandwritingInputDialog
from smithanatool_qt.tabs.ai.workers.qt_runnable import OcrSignals, OcrTask
from smithanatool_qt.tabs.ai.utils.rect_utils import sort_rects_top_down


class AiEntriesController:
    """Оркестратор: viewer/right + OCR + оверлей.

    - EntriesStore хранит фрагменты (текст + QRect)
    - entries_ocr_jobs готовит функцию OCR для фона (Yandex/RouterAI)

    Синхронизация выбора (рамка <-> строка):
    - НЕЛЬЗЯ полагаться на "row == index рамки" (пользователь может менять порядок текста).
    - Поэтому мы храним rect каждой строки в QListWidgetItem.setData(Qt.UserRole, QRect).
      При drag&drop данные переезжают вместе со строкой.
    """

    def __init__(self, tab, viewer, right, ai):
        self._label_mode = "visual"
        self.tab = tab
        self.viewer = viewer
        self.right = right
        self.ai = ai

        self._store = EntriesStore()

        self._pool = QThreadPool.globalInstance()
        self._ocr_running = False

        self._ocr_signals = None
        self._ocr_task = None

        # Синхронизация выделений
        self._syncing_selection = False
        self._selected_rect_img: Optional[QRect] = None

        # Оверлей поверх области просмотра (галереи)
        parent_for_overlay = getattr(self.tab, "host", None) or self.tab
        self._busy_overlay = BusyOverlay(
            parent_for_overlay,
            cover_widgets=[getattr(self.viewer, "preview", None)],
        )

        self._install_selection_sync()

    # -------- selection sync --------
    def _install_selection_sync(self) -> None:
        # overlay -> list
        try:
            self.viewer.overlay.rectSelected.connect(self._on_overlay_rect_selected)
            self.viewer.overlay.selectionCleared.connect(self._on_overlay_selection_cleared)
        except Exception:
            pass

        # list -> overlay
        try:
            self.right.list.itemSelectionChanged.connect(self._on_list_selection_changed)
        except Exception:
            pass

        # перестановки строк (drag&drop) -> обновить подписи на рамках
        try:
            m = self.right.list.model()
            m.rowsMoved.connect(lambda *args: self._on_list_structure_changed())
            m.layoutChanged.connect(lambda *args: self._on_list_structure_changed())
            m.modelReset.connect(lambda *args: self._on_list_structure_changed())
        except Exception:
            pass

    def _on_list_structure_changed(self) -> None:
        # НЕ трогаем store, только подписи/визуал.
        try:
            self._sync_overlay_labels(self._current_path())
        except Exception:
            pass

    def _clear_list_selection(self) -> None:
        try:
            self.right.list.clearSelection()
        except Exception:
            pass
        try:
            self.right.list.setCurrentRow(-1)
        except Exception:
            pass

    def _clear_both_selection(self) -> None:
        if self._syncing_selection:
            return
        self._syncing_selection = True
        try:
            try:
                self.viewer.overlay.clear_selection()
            except Exception:
                pass
            self._clear_list_selection()
        finally:
            self._syncing_selection = False

    def _set_list_selected_row(self, row: int) -> None:
        if row is None or row < 0 or row >= self.right.list.count():
            self._clear_list_selection()
            return

        try:
            from PySide6.QtCore import QItemSelectionModel

            self.right.list.setCurrentRow(int(row), QItemSelectionModel.ClearAndSelect)
        except Exception:
            # fallback
            try:
                self._clear_list_selection()
                self.right.list.setCurrentRow(int(row))
                it = self.right.list.item(int(row))
                if it is not None:
                    it.setSelected(True)
            except Exception:
                pass

        try:
            it = self.right.list.item(int(row))
            if it is not None:
                self.right.list.scrollToItem(it)
        except Exception:
            pass

    def _ensure_list_item_rect_data(self, path: str) -> None:
        """Инициализировать Qt.UserRole -> QRect после right.set_items(...).

        Важно: не перезаписываем уже установленную привязку, иначе после reorder она начнёт "плавать".
        """
        n = self.right.list.count()
        if n <= 0:
            return

        # Если хотя бы у одного item уже есть rect — считаем, что привязка настроена (не трогаем).
        for row in range(n):
            it = self.right.list.item(row)
            if it is None:
                continue
            v = it.data(Qt.UserRole)
            if isinstance(v, QRect) and not v.isNull():
                return

        try:
            entries = self._store.entries(path)
        except Exception:
            entries = []

        for row in range(n):
            it = self.right.list.item(row)
            if it is None:
                continue
            rect = None
            if 0 <= row < len(entries):
                rect = entries[row].rect
            it.setData(Qt.UserRole, rect)

    def _replace_rect_in_list_items(self, old_rect: Optional[QRect], new_rect: Optional[QRect]) -> None:
        """Обновить привязку item->rect без разрушения порядка строк."""
        if old_rect is None or old_rect.isNull():
            return
        n = self.right.list.count()
        for row in range(n):
            it = self.right.list.item(row)
            if it is None:
                continue
            if it.data(Qt.UserRole) == old_rect:
                it.setData(Qt.UserRole, new_rect)

    def _clear_all_list_item_rect_data(self) -> None:
        n = self.right.list.count()
        for row in range(n):
            it = self.right.list.item(row)
            if it is None:
                continue
            v = it.data(Qt.UserRole)
            if isinstance(v, QRect):
                it.setData(Qt.UserRole, None)

    def _find_row_in_list_by_rect(self, rect_img: QRect) -> int:
        if rect_img is None or rect_img.isNull():
            return -1
        n = self.right.list.count()
        for row in range(n):
            it = self.right.list.item(row)
            if it is None:
                continue
            if it.data(Qt.UserRole) == rect_img:
                return row
        return -1

    def _set_overlay_selected_rect(self, rect_img: Optional[QRect]) -> None:
        try:
            if rect_img is None or rect_img.isNull():
                self.viewer.overlay.clear_selection()
                return

            rects = self.viewer.rects_img()
            for i, r in enumerate(rects):
                if r == rect_img:
                    self.viewer.overlay.set_selected_index(i)  # без эмита
                    return
            self.viewer.overlay.clear_selection()
        except Exception:
            pass

    def _on_overlay_rect_selected(self, overlay_index: int, rect_img: QRect) -> None:
        if self._syncing_selection:
            return

        self._selected_rect_img = rect_img

        # ищем строку по rect, а не по индексу
        row = self._find_row_in_list_by_rect(rect_img)

        self._syncing_selection = True
        try:
            if row >= 0:
                self._set_list_selected_row(row)
            else:
                self._clear_list_selection()
        finally:
            self._syncing_selection = False

    def _on_overlay_selection_cleared(self) -> None:
        if self._syncing_selection:
            return
        self._selected_rect_img = None

        self._syncing_selection = True
        try:
            self._clear_list_selection()
        finally:
            self._syncing_selection = False

    def _on_list_selection_changed(self) -> None:
        if self._syncing_selection:
            return

        try:
            rows = sorted({mi.row() for mi in self.right.list.selectedIndexes()})
        except Exception:
            rows = []

        if len(rows) != 1:
            self._selected_rect_img = None
            self._syncing_selection = True
            try:
                self._set_overlay_selected_rect(None)
            finally:
                self._syncing_selection = False
            return

        row = rows[0]
        it = self.right.list.item(row)
        rect = it.data(Qt.UserRole) if it is not None else None

        self._selected_rect_img = rect

        self._syncing_selection = True
        try:
            self._set_overlay_selected_rect(rect)
        finally:
            self._syncing_selection = False

    # -------- utilities --------
    def _current_path(self) -> str:
        return getattr(self.viewer.preview, "_current_path", "") or ""

    def _resort_overlay_rects(self):
        rects = self.viewer.rects_img()
        if not rects:
            return
        self.viewer.set_rects_img(sort_rects_top_down(rects))

        # после сортировки индексы могут поменяться — пересинхронизируем подсветку
        if self._selected_rect_img is not None:
            self._set_overlay_selected_rect(self._selected_rect_img)

        self._sync_overlay_labels(self._current_path())

    # -------- events --------
    def on_path_changed(self, path: Optional[str]):
        self.viewer.show_path(path)
        p = path or ""
        self._store.ensure_path(p)

        # рамки
        self.viewer.set_rects_img(self._store.rects(p))

        # список
        self.right.set_items(self._store.texts(p))
        self._ensure_list_item_rect_data(p)

        # подписи
        self._sync_overlay_labels(p)

        # новый файл — сбросить выделение
        self._selected_rect_img = None
        self._clear_both_selection()

    def on_rect_added(self, rect_img: QRect):
        self._resort_overlay_rects()

    def on_rect_deleted(self, idx: int, rect_img: QRect):
        p = self._current_path()
        self._store.mark_rect_deleted(p, rect_img)

        # поддержать привязку item->rect (не ломая reorder)
        self._ensure_list_item_rect_data(p)
        self._replace_rect_in_list_items(rect_img, None)

        # если удалили выбранную рамку — сбросить выбор
        if self._selected_rect_img is not None and rect_img == self._selected_rect_img:
            self._selected_rect_img = None
            self._clear_both_selection()

        self._resort_overlay_rects()

    def on_rect_changed(self, idx: int, old_rect: QRect, new_rect: QRect):
        p = self._current_path()
        self._store.update_rect(p, old_rect, new_rect)

        if self._selected_rect_img is not None and old_rect == self._selected_rect_img:
            self._selected_rect_img = new_rect

        # поддержать привязку item->rect (не ломая reorder)
        self._ensure_list_item_rect_data(p)
        self._replace_rect_in_list_items(old_rect, new_rect)

        self._resort_overlay_rects()

    # -------- overlay labels / clearing --------
    def _sync_overlay_labels(self, path: str):
        rects = self.viewer.rects_img()

        if self._label_mode == "visual":
            labels: List[str] = []
            for i, r in enumerate(rects):
                row = self._find_row_in_list_by_rect(r)
                labels.append(str(row + 1) if row >= 0 else str(i + 1))
            self.viewer.set_labels(labels)
            return

        labels = self._store.labels_for_rects(path, rects, mode=self._label_mode)
        self.viewer.set_labels(labels)

    def clear_rectangles(self):
        """Удаляет все рамки на оверлее, но тексты справа не удаляет."""
        p = self._current_path()
        rects = self.viewer.rects_img()
        if not rects:
            return
        self._store.clear_rectangles(p, rects)
        self.viewer.clear_overlay()

        self._clear_all_list_item_rect_data()
        self._sync_overlay_labels(p)

        self._selected_rect_img = None
        self._clear_both_selection()

    # -------- CRUD from right panel --------
    def on_item_edited(self, index: int, text: str):
        p = self._current_path()
        self._store.set_text(p, index, text)
        self._sync_overlay_labels(p)

    def on_item_deleted(self, index: int):
        p = self._current_path()
        self._store.delete_entry(p, index)
        self.right.set_items(self._store.texts(p))
        self._ensure_list_item_rect_data(p)
        self._sync_overlay_labels(p)

        self._selected_rect_img = None
        self._clear_both_selection()

    # -------- extract --------
    def _set_ocr_busy(self, busy: bool, text: str = "Распознавание..."):
        self._ocr_running = bool(busy)

        try:
            self.right.btn_extract.setEnabled(not busy)
        except Exception:
            pass
        try:
            self.right.btn_handwriting.setEnabled(not busy)
        except Exception:
            pass

        try:
            if busy:
                self._busy_overlay.set_text(text)
                self._busy_overlay.raise_()
                self._busy_overlay.show()
            else:
                self._busy_overlay.hide()
        except Exception:
            pass

    def _run_ocr_background(
        self,
        *,
        path: str,
        rects_fixed: List[QRect],
        work_fn: Callable[[], Tuple[List[str], str]],
    ) -> None:
        """Запускает OCR в QThreadPool и применяет результат в UI-потоке."""
        self._set_ocr_busy(True, "Распознавание...")

        signals = OcrSignals()
        self._ocr_signals = signals

        def on_done(texts, first_error):
            from shiboken6 import isValid

            if not isValid(self.tab):
                self._ocr_task = None
                self._ocr_signals = None
                self._set_ocr_busy(False)
                return

            try:
                self._store.apply_ocr_results(path, rects_fixed, texts)

                if first_error:
                    QMessageBox.warning(self.tab, "Ошибка распознавания текста", first_error)

                self.right.set_items(self._store.texts(path))
                self._ensure_list_item_rect_data(path)
                self._sync_overlay_labels(path)
            finally:
                self._ocr_task = None
                self._ocr_signals = None
                self._set_ocr_busy(False)

        def on_error(tb):
            from shiboken6 import isValid

            if not isValid(self.tab):
                self._ocr_task = None
                self._ocr_signals = None
                self._set_ocr_busy(False)
                return

            try:
                QMessageBox.warning(self.tab, "Ошибка распознавания текста", tb)
            finally:
                self._ocr_task = None
                self._ocr_signals = None
                self._set_ocr_busy(False)

        signals.done.connect(on_done)
        signals.error.connect(on_error)

        task = OcrTask(work_fn, signals)
        self._ocr_task = task
        self._pool.start(task)

    def ai_all(self):
        if getattr(self, "_ocr_running", False):
            return

        p = self._current_path()
        self._store.ensure_path(p)

        rects = self.viewer.rects_img()
        if not rects:
            QMessageBox.information(self.tab, "Распознать текст", "Нет выделенных областей.")
            return
        cfg = build_ocr_runtime_config(self.right)

        try:
            rects_fixed, work = prepare_ocr_work(
                viewer=self.viewer,
                ai=self.ai,
                rects=list(rects),
                cfg=cfg,
            )
        except OcrConfigError as e:
            QMessageBox.warning(self.tab, "Ошибка", str(e))
            return

        self._run_ocr_background(path=p, rects_fixed=rects_fixed, work_fn=work)

    # -------- handwriting --------
    def open_handwriting_dialog(self):
        dlg = HandwritingInputDialog(self.tab)
        dlg.setWindowModality(Qt.NonModal)
        dlg.setAttribute(Qt.WA_DeleteOnClose, True)
        dlg.aiRequested.connect(self._run_handwriting_ocr)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _run_handwriting_ocr(self, img: QImage):
        if img is None or img.isNull():
            return
        cfg = build_ocr_runtime_config(self.right)
        try:
            png_bytes = self.viewer.qimage_to_png_bytes(img)
            out = self.ai.ocr_images([png_bytes], cfg)
            text = (out[0] if out else "")
        except Exception as e:
            QMessageBox.warning(self.tab, "Ошибка", f"Не удалось распознать рукописный ввод:\n{e}")
            return
        self._add_handwriting_fragment(text)

    def _add_handwriting_fragment(self, raw_text: str):
        p = self._current_path()
        self._store.ensure_path(p)

        text = (raw_text or "").strip()
        if not text:
            return
        text = " ".join(text.split())

        self._store.add_entry(p, text=text, rect=None)
        self.right.set_items(self._store.texts(p))
        self._ensure_list_item_rect_data(p)
        self._sync_overlay_labels(p)

    # -------- save --------
    def save_to_file(self, path: str):
        p = self._current_path()
        lines = self._store.texts(p)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except Exception as e:
            QMessageBox.warning(self.tab, "Сохранение", f"Не удалось сохранить файл:\n{e}")
