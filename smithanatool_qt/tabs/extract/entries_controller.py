from __future__ import annotations
import traceback
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QPoint, QRect, QThreadPool, QRunnable, QObject, QThread, Signal, Slot, QEvent

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget, QLabel, QVBoxLayout, QProgressBar

from .handwriting_input import HandwritingInputDialog

from .ocr.ocr_yandex import yandex_ocr_full, yandex_ocr_map_rois


class _BusyOverlay(QWidget):
    """Полупрозрачный оверлей поверх выбранной области (dim + блокировка ввода)."""
    def __init__(self, parent: QWidget, cover_widgets: Optional[List[QWidget]] = None):
        super().__init__(parent)
        self.setObjectName("busyOverlay")
        self.setVisible(False)

        # Чтобы фон из QSS гарантированно рисовался
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)

        # Блокируем клики/скролл, пока идёт OCR
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.NoFocus)

        # Какие виджеты должны быть "прикрыты" оверлеем (например Preview + Right)
        self._cover_widgets: List[QWidget] = list(cover_widgets or [])

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._label = QLabel("Распознавание...", self)
        self._label.setAlignment(Qt.AlignCenter)

        self._bar = QProgressBar(self)
        self._bar.setRange(0, 0)  # бесконечная анимация
        self._bar.setTextVisible(False)
        self._bar.setFixedWidth(260)

        # Центрируем текст
        lay.addStretch(1)
        lay.addWidget(self._label, 0, Qt.AlignCenter)
        lay.addWidget(self._bar, 0, Qt.AlignCenter)
        lay.addStretch(1)

        # Стили
        self.setStyleSheet("""
        QWidget#busyOverlay { background-color: rgba(0,0,0,200); }

        QWidget#busyOverlay QLabel {
          color: white;
          font-size: 20px;
          font-weight: 600;
          padding: 14px 22px;
          border-radius: 10px;
        }

        QProgressBar {
          border: 1px solid rgba(255,255,255,60);
          border-radius: 6px;
          background: rgba(255,255,255,25);
          height: 12px;
        }

        QProgressBar::chunk {
          border-radius: 6px;
          background: rgba(35,135,213,200);
        }
        """)

        # Следим за ресайзом/движением родителя и прикрываемых виджетов
        parent.installEventFilter(self)
        for w in self._cover_widgets:
            try:
                w.installEventFilter(self)
            except Exception:
                pass

        self._update_geometry()

    def set_text(self, text: str):
        self._label.setText(text or "Распознавание...")

    def _update_geometry(self):
        """Подгоняем геометрию оверлея под cover_widgets (или под весь parent)."""
        parent = self.parentWidget()
        if parent is None:
            return

        if not self._cover_widgets:
            self.setGeometry(parent.rect())
            return

        rect: Optional[QRect] = None
        for w in self._cover_widgets:
            if w is None:
                continue
            try:
                tl = w.mapTo(parent, QPoint(0, 0))
                r = QRect(tl, w.size())
            except Exception:
                continue
            rect = r if rect is None else rect.united(r)

        if rect is None:
            rect = parent.rect()

        self.setGeometry(rect)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Resize, QEvent.Move, QEvent.Show, QEvent.LayoutRequest):
            self._update_geometry()
        return super().eventFilter(watched, event)


class _OcrSignals(QObject):
    done = Signal(list, str)   # texts: List[str], first_error: str
    error = Signal(str)        # traceback


class _OcrTask(QRunnable):
    def __init__(self, work_fn, signals: _OcrSignals):
        super().__init__()
        self._work_fn = work_fn
        self.signals = signals

    def run(self):
        try:
            texts, first_error = self._work_fn()
            self.signals.done.emit(texts, first_error or "")
        except Exception:
            self.signals.error.emit(traceback.format_exc())



class ExtractEntriesController:
    """Хранение фрагментов и синхронизация правой панели/оверлея."""

    def __init__(self, tab, viewer, right, ocr):
        self._label_mode = "visual"
        self.tab = tab
        self.viewer = viewer
        self.right = right
        self.ocr = ocr
        self._entries: Dict[str, List[Dict]] = {}  # path -> [{text, rect}]

        self._pool = QThreadPool.globalInstance()
        self._ocr_running = False

        self._ocr_signals = None
        self._ocr_task = None

        # Оверлей поверх области просмотра (галереи)
        parent_for_overlay = getattr(self.tab, "host", None) or self.tab
        self._busy_overlay = _BusyOverlay(
            parent_for_overlay,
            cover_widgets=[getattr(self.viewer, "preview", None)],
        )

    def _resort_overlay_rects(self):
        rects = self.viewer.rects_img()
        if not rects:
            return
        rects_sorted = self._sort_rects_top_down(rects)
        self.viewer.set_rects_img(rects_sorted)


    def _sort_rects_top_down(self, rects: list[QRect]) -> list[QRect]:
        if not rects:
            return rects

        # медианная высота — база для допуска по строке
        hs = sorted(r.height() for r in rects)
        h_med = hs[len(hs) // 2]
        line_tol = int(h_med * 0.6)  # допуск по Y

        # сортируем сначала по Y
        rects_sorted = sorted(rects, key=lambda r: r.y())

        lines: list[list[QRect]] = []
        for r in rects_sorted:
            placed = False
            for line in lines:
                if abs(line[0].y() - r.y()) <= line_tol:
                    line.append(r)
                    placed = True
                    break
            if not placed:
                lines.append([r])

        # внутри строки — слева направо
        for line in lines:
            line.sort(key=lambda r: r.x())

        # склеиваем строки
        out: list[QRect] = []
        for line in lines:
            out.extend(line)

        return out

    # -------- utilities --------
    def _current_path(self) -> str:
        return getattr(self.viewer.preview, "_current_path", "") or ""


    # -------- events --------
    def on_path_changed(self, path: Optional[str]):
        self.viewer.show_path(path)
        p = path or ""
        if p not in self._entries:
            self._entries[p] = []
        rects = [e["rect"] for e in self._entries[p] if e.get("rect") is not None]
        self.viewer.set_rects_img(rects)
        self._sync_overlay_labels(p)
        self.right.set_items([e.get("text", "") for e in self._entries[p]])

    def on_rect_added(self, rect_img: QRect):
        self._resort_overlay_rects()
        self._sync_overlay_labels(self._current_path())

    def on_rect_deleted(self, idx: int, rect_img: QRect):
        p = self._current_path()
        if p in self._entries:
            for e in self._entries[p]:
                if e.get("rect") == rect_img:
                    e["rect"] = None
                    break

        self._resort_overlay_rects()
        self._sync_overlay_labels(p)

    def on_rect_changed(self, idx: int, old_rect: QRect, new_rect: QRect):
        p = self._current_path()
        if p in self._entries:
            for e in self._entries[p]:
                if e.get("rect") == old_rect:
                    e["rect"] = new_rect
                    break

        self._resort_overlay_rects()
        self._sync_overlay_labels(p)

    # -------- overlay labels / clearing --------
    def _sync_overlay_labels(self, path: str):
        rects = self.viewer.rects_img()
        if self._label_mode == "visual":
            self.viewer.set_labels([str(i + 1) for i in range(len(rects))])
            return

        labels: List[str] = []
        for r in rects:
            found_idx = -1
            for i, e in enumerate(self._entries.get(path, [])):
                if e.get("rect") is not None and e["rect"] == r:
                    found_idx = i
                    break
            labels.append(str(found_idx + 1) if found_idx >= 0 else "•")
        self.viewer.set_labels(labels)

    def clear_rectangles(self):
        """Удаляет все рамки на оверлее, но тексты справа не удаляет."""
        p = self._current_path()
        rects = self.viewer.rects_img()
        if not rects:
            return
        rect_keys = {(r.x(), r.y(), r.width(), r.height()) for r in rects}
        for e in self._entries.get(p, []):
            r = e.get("rect")
            if r is None:
                continue
            if (r.x(), r.y(), r.width(), r.height()) in rect_keys:
                e["rect"] = None
        self.viewer.clear_overlay()
        self._sync_overlay_labels(p)

    # -------- CRUD from right panel --------
    def on_item_edited(self, index: int, text: str):
        p = self._current_path()
        if p in self._entries and 0 <= index < len(self._entries[p]):
            self._entries[p][index]["text"] = text
            self._sync_overlay_labels(p)

    def on_item_deleted(self, index: int):
        p = self._current_path()
        if p in self._entries and 0 <= index < len(self._entries[p]):
            del self._entries[p][index]
            self.right.set_items([e.get("text", "") for e in self._entries[p]])
            self._sync_overlay_labels(p)

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

        # Затемнение галереи
        try:
            if busy:
                self._busy_overlay.set_text(text)
                self._busy_overlay.raise_()
                self._busy_overlay.show()
            else:
                self._busy_overlay.hide()
        except Exception:
            pass

    def extract_all(self):
        if getattr(self, "_ocr_running", False):
            return

        p = self._current_path()
        if p not in self._entries:
            self._entries[p] = []

        rects = self.viewer.rects_img()
        if not rects:
            QMessageBox.information(self.tab, "Извлечь текст", "Нет выделенных областей.")
            return

        model, lang = self.ocr.selected_model_lang()
        engine = self.ocr.selected_engine()

        # --- СНИМАЕМ ВСЁ НУЖНОЕ В GUI-ПОТОКЕ (никаких UI-обращений в фоне) ---
        # Прямоугольники зафиксируем как plain-данные + сами QRect (для сравнения/апдейта)
        rects_fixed = list(rects)

        # Общая функция сравнения
        def same(a: QRect, b: QRect) -> bool:
            return (a is not None) and (b is not None) and (a == b)

        # Подготовка данных для OCR
        first_error_init = ""

        if engine == "yandex":
            # Снимем ключи/папку в GUI потоке (ocr_service читает UI-поля)
            api_key, folder_id = self.ocr._yc_api_key_folder()
            if not api_key or not folder_id:
                QMessageBox.warning(self.tab, "Ошибка", "Не задан YC_OCR_API_KEY и/или YC_FOLDER_ID.")
                return

            page = self.viewer.get_current_qimage()
            if page is None or page.isNull():
                # нечего распознавать
                page_bytes = b""
            else:
                try:
                    page_bytes = self.viewer.qimage_to_png_bytes(page)
                except Exception as e:
                    page_bytes = b""
                    first_error_init = str(e)

            rois_xywh = [(r.x(), r.y(), r.width(), r.height()) for r in rects_fixed]

            def work():
                first_error = first_error_init
                if not page_bytes:
                    return (["" for _ in rects_fixed], first_error)

                try:
                    resp = yandex_ocr_full(
                        image_bytes=page_bytes,
                        api_key=api_key,
                        folder_id=folder_id,
                        lang_code=(lang or ""),
                        model="page",
                        # кэш ты хотел убрать — значит не передаём use_cache/cache_ttl_days
                    )
                    texts = yandex_ocr_map_rois(ocr_resp=resp, rois=rois_xywh, mode="intersect")
                    return (texts, first_error)
                except Exception as e:
                    if not first_error:
                        first_error = str(e)
                    return (["" for _ in rects_fixed], first_error)

        else:
            # gemini (RouterAI) — подготовка crop PNG в GUI потоке (Qt-объекты безопаснее трогать тут)
            valid_idx = []
            valid_bytes = []
            texts_init = ["" for _ in rects_fixed]

            for i, r in enumerate(rects_fixed):
                crop = self.viewer.crop_qimage(r)
                if crop is None:
                    continue
                try:
                    png_bytes = self.viewer.qimage_to_png_bytes(crop)
                except Exception:
                    png_bytes = b""
                if png_bytes:
                    valid_idx.append(i)
                    valid_bytes.append(png_bytes)

            batch_size = self.ocr.selected_batch_size()

            # Снимем RouterAI ключ/URL в GUI потоке
            api_key = self.ocr._routerai_api_key()
            if not api_key:
                QMessageBox.warning(self.tab, "Ошибка", "Не задан ROUTERAI_API_KEY (ключ RouterAI).")
                return
            base_url = self.ocr._routerai_base_url()

            # Подстраховка по модели (как в ocr_service)
            if not model or "/" not in (model or ""):
                model = model or "google/gemini-2.5-flash"

            def work():
                first_error = ""
                texts = list(texts_init)
                if not valid_bytes:
                    return (texts, first_error)

                try:
                    # используем уже существующий движок внутри сервиса (он stateless)
                    # и повторяем логику chunking как в ExtractOcrService.ocr_batch() :contentReference[oaicite:5]{index=5}
                    bs = max(1, int(batch_size or 1))
                    out_all = []
                    for j in range(0, len(valid_bytes), bs):
                        chunk = valid_bytes[j:j + bs]
                        out_all.extend(
                            self.ocr._gemini.ocr_batch(
                                images_bytes=list(chunk),
                                api_key=api_key,
                                model=model or "google/gemini-2.5-flash",
                                base_url=base_url,
                                lang_hint=(lang or ""),
                            )
                        )

                    for k, t in enumerate(out_all):
                        if k < len(valid_idx):
                            texts[valid_idx[k]] = t or ""
                except Exception as e:
                    first_error = str(e)

                return (texts, first_error)

        # --- СТАРТ ФОНА ---
        self._set_ocr_busy(True, "Распознавание...")

        signals = _OcrSignals()
        self._ocr_signals = signals  # keep alive

        def on_done(texts, first_error):
            from shiboken6 import isValid

            # если вкладка уже убита — просто аккуратно завершаем
            if not isValid(self.tab):
                self._ocr_task = None
                self._ocr_signals = None
                self._set_ocr_busy(False)
                return

            # применяем результат в GUI-потоке
            try:
                for r, text in zip(rects_fixed, texts):
                    if text:
                        text = " ".join(text.split())

                    updated = False
                    for e in self._entries[p]:
                        if same(r, e.get("rect")):
                            e["text"] = text or e.get("text", "")
                            updated = True
                            break

                    if not updated:
                        self._entries[p].append({
                            "text": text or f"Фрагмент {len(self._entries[p]) + 1}",
                            "rect": r,
                        })

                if first_error:
                    QMessageBox.warning(self.tab, "Ошибка извлечения текста", first_error)

                self.right.set_items([e.get("text", "") for e in self._entries[p]])
                self._sync_overlay_labels(p)
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
                QMessageBox.warning(self.tab, "Ошибка извлечения текста", tb)
            finally:
                self._ocr_task = None
                self._ocr_signals = None
                self._set_ocr_busy(False)

        signals.done.connect(on_done)
        signals.error.connect(on_error)

        task = _OcrTask(work, signals)
        self._ocr_task = task  # keep alive
        self._pool.start(task)

    # -------- handwriting --------
    def open_handwriting_dialog(self):
        dlg = HandwritingInputDialog(self.tab)
        dlg.setWindowModality(Qt.NonModal)
        dlg.setAttribute(Qt.WA_DeleteOnClose, True)
        dlg.extractRequested.connect(self._run_handwriting_ocr)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _run_handwriting_ocr(self, img: QImage):
        if img is None or img.isNull():
            return
        model, lang = self.ocr.selected_model_lang()
        try:
            png_bytes = self.viewer.qimage_to_png_bytes(img)
            text = self.ocr.ocr(png_bytes, model=model, lang=lang)
        except Exception as e:
            QMessageBox.warning(self.tab, "Ошибка", f"Не удалось распознать рукописный ввод:\n{e}")
            return
        self._add_handwriting_fragment(text)

    def _add_handwriting_fragment(self, raw_text: str):
        p = self._current_path()
        if p not in self._entries:
            self._entries[p] = []

        text = (raw_text or "").strip()
        if not text:
            return
        text = " ".join(text.split())

        self._entries[p].append({"text": text, "rect": None})
        self.right.set_items([e.get("text", "") for e in self._entries[p]])
        self._sync_overlay_labels(p)

    # -------- save --------
    def save_to_file(self, path: str):
        p = self._current_path()
        lines = [e.get("text", "") for e in self._entries.get(p, [])]
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except Exception as e:
            QMessageBox.warning(self.tab, "Сохранение", f"Не удалось сохранить файл:\n{e}")
