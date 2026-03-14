from __future__ import annotations

import os

from PySide6.QtCore import QTimer
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import QWidget, QHBoxLayout, QMessageBox, QSizePolicy

from smithanatool_qt.utils import dialogs
from smithanatool_qt.settings_bind import group, bind_attr_string, save_attr_string

from smithanatool_qt.tabs.gallery_preview_host import GalleryPreviewHost
from smithanatool_qt.tabs.transform.gallery import GalleryPanel
from smithanatool_qt.tabs.transform.preview import PreviewPanel

from .right_panel import WorkshopRightPanel

LEFT_MIN_W = 280
RIGHT_MIN_W = 480


class WorkshopTab(QWidget):
    """Одна вкладка ("Мастерская") с общей Галереей и Превью.

    Справа переключаемые панели:
      - Преобразования (SectionsPanel)
      - Распознавание текста (OCR Right Panel)

    Галерея/превью остаются теми же (инстансы не меняются),
    меняется только правая панель.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._save_dir = ""

        self._ocr_ready = False
        self._ocr_visible = False
        self._mode = "transform"
        self._ocr_rect_sort_mode = "webtoon"

        self.host = GalleryPreviewHost(
            self,
            gallery_factory=GalleryPanel,
            preview_factory=PreviewPanel,
            right_factory=self._build_right,
            persist_key="WorkshopTab/splitter",
            sizes=[LEFT_MIN_W, 1000, RIGHT_MIN_W],
        )

        self.gallery = self.host.gallery
        self.preview = self.host.preview
        self.right = self.host.right  # WorkshopRightPanel
        self.splitter = self.host.splitter

        # ------------ скрывать панели  ------------
        self.splitter.setChildrenCollapsible(True)

        self.splitter.setCollapsible(0, True)
        self.splitter.setCollapsible(1, False)
        self.splitter.setCollapsible(2, True)

        self.gallery.setMinimumWidth(LEFT_MIN_W)
        self.right.setMinimumWidth(RIGHT_MIN_W)
        self.preview.setMinimumWidth(0)

        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)

        self.gallery.setSizePolicy(QSizePolicy.Preferred, self.gallery.sizePolicy().verticalPolicy())
        self.right.setSizePolicy(QSizePolicy.Preferred, self.right.sizePolicy().verticalPolicy())
        # ---------------------------------------------------------

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 8)
        lay.setSpacing(0)
        lay.addWidget(self.host)

        # Базовый просмотр: выбор файла в галерее -> показать в превью
        self.gallery.currentPathChanged.connect(self._on_gallery_path_changed)

        # Сохранение (как в TransformTab)
        self.preview.action_btn_save.clicked.connect(self._save)
        self.preview.action_btn_save_as.clicked.connect(self._save_as)
        self.preview.ocrSortRectsRequested.connect(self._on_preview_ocr_sort_requested)
        self.preview.ocrDeleteRectsRequested.connect(self._on_preview_ocr_delete_requested)
        self.preview.ocrUndoRequested.connect(self._on_preview_ocr_undo_requested)
        self.preview.ocrRedoRequested.connect(self._on_preview_ocr_redo_requested)

        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._save)
        QShortcut(QKeySequence("Ctrl+Shift+S"), self, activated=self._save_as)

        self._apply_settings_from_ini()

        # Реакция на переключение режимов справа
        self.right.modeChanged.connect(self._on_mode_changed)

        self._initial_mode_applied = False

    def _build_right(self, gallery, preview, parent):
        return WorkshopRightPanel(gallery=gallery, preview=preview, parent=parent)

    def showEvent(self, e):
        super().showEvent(e)
        if getattr(self, "_initial_mode_applied", False):
            return
        self._initial_mode_applied = True
        # Применить стартовый режим после того, как вкладка реально показана
        QTimer.singleShot(0, lambda: self.right.set_mode(self._mode, emit=True))

    # ---------------- settings ----------------
    def _apply_settings_from_ini(self):
        try:
            with group("TransformTab"):
                bind_attr_string(self, "_save_dir", "save_dir", "")
        except Exception:
            pass

        try:
            with group("WorkshopTab"):
                bind_attr_string(self, "_mode", "mode", "transform")
                bind_attr_string(self, "_ocr_rect_sort_mode", "ocr_rect_sort_mode", "webtoon")
        except Exception:
            pass

        try:
            from smithanatool_qt.tabs.ai.utils.rect_utils import normalize_rect_sort_mode
            self._ocr_rect_sort_mode = normalize_rect_sort_mode(self._ocr_rect_sort_mode)
        except Exception:
            self._ocr_rect_sort_mode = "webtoon"

    def _save_ocr_sort_mode_to_ini(self) -> None:
        try:
            with group("WorkshopTab"):
                save_attr_string(self, "_ocr_rect_sort_mode", "ocr_rect_sort_mode")
        except Exception:
            pass

    def _sync_ocr_sort_mode_from_entries(self, *, save: bool = True) -> None:
        if not self._ocr_ready:
            return

        try:
            from smithanatool_qt.tabs.ai.utils.rect_utils import normalize_rect_sort_mode
            self._ocr_rect_sort_mode = normalize_rect_sort_mode(
                getattr(self.entries, "_rect_sort_mode", self._ocr_rect_sort_mode)
            )
        except Exception:
            return

        if save:
            self._save_ocr_sort_mode_to_ini()

    # ---------------- save / save as (from TransformTab) ----------------
    def _save(self):
        # Запрет для PSD/PSB
        if getattr(self.preview, "_is_current_psd", None) and self.preview._is_current_psd():
            QMessageBox.information(self, "Сохранение недоступно", "PSD/PSB нельзя сохранять в этом режиме.")
            return

        path = getattr(self.preview, "_current_path", None)
        if getattr(self.preview, "_is_memory_path", None) and self.preview._is_memory_path(path):
            self._save_as()
            return
        if getattr(self.preview, "_is_pasted_temp_path", None) and self.preview._is_pasted_temp_path(path):
            self._save_as()
            return

        if self.preview.save_current_overwrite():
            self.preview.show_toast("Сохранено!", 3000)
        else:
            QMessageBox.warning(self, "Ошибка", "Не удалось сохранить изображение.")

    def _save_as(self):
        cur = getattr(self.preview, "_current_path", None)
        old = cur

        # 1) Имя и расширение по исходному файлу
        base = "image"
        ext = ".png"
        if cur:
            base = os.path.splitext(os.path.basename(cur))[0] or base
            orig_ext = os.path.splitext(cur)[1].lower()
            if orig_ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"):
                ext = orig_ext
        suggested_name = base + ext

        # 2) Стартовый путь: из INI, иначе только имя (чтобы ОС взяла "последнюю папку")
        initial = suggested_name
        save_dir = getattr(self, "_save_dir", "") or ""
        if save_dir and os.path.isdir(save_dir):
            initial = os.path.join(save_dir, suggested_name)

        # 3) Диалог "Сохранить как"
        path, selected_filter = dialogs.ask_save_file(
            self,
            "Сохранить изображение как",
            "PNG (*.png);;JPEG (*.jpg *.jpeg);;Все файлы (*.*)",
            initial_path=initial,
        )
        if not path:
            return

        # 4) Если расширение не указано — добавим по выбранному фильтру
        if not os.path.splitext(path)[1]:
            if selected_filter and "JPEG" in selected_filter:
                path += ".jpg"
            else:
                path += ".png"

        # 5) Сохранение и обновление INI-папки
        if self.preview.save_current_as(path):
            if old and (
                (getattr(self.preview, "_is_memory_path", None) and self.preview._is_memory_path(old))
                or (getattr(self.preview, "_is_pasted_temp_path", None) and self.preview._is_pasted_temp_path(old))
            ):
                self.preview.relink_current_to(path)
                self.gallery.apply_path_mapping({old: path}, call_forget_cb=False)

            new_dir = os.path.dirname(path)
            if new_dir and os.path.isdir(new_dir):
                self._save_dir = new_dir
                # сохраняем папку в INI (тот же namespace, что и раньше)
                with group("TransformTab"):
                    save_attr_string(self, "_save_dir", "save_dir")

            QMessageBox.information(self, "Сохранено", f"Сохранено: {path}")
        else:
            QMessageBox.warning(self, "Ошибка", "Не удалось сохранить изображение.")

    # ---------------- OCR wiring ----------------
    def _on_gallery_path_changed(self, path) -> None:
        """Единая точка реакции на смену выбранного файла в галерее."""
        if self._mode == "ocr":
            # В AI-режиме источником правды является entries/viewer
            if self._ocr_ready:
                try:
                    self.entries.on_path_changed(path)
                    return
                except Exception:
                    pass
            # fallback
            self.preview.show_path(path)
            return

        # transform
        self.preview.show_path(path)

    def _on_mode_changed(self, mode: str) -> None:
        """mode: 'transform' | 'ocr'"""
        self._mode = mode
        self._apply_mode_profile(mode)

        try:
            with group("WorkshopTab"):
                save_attr_string(self, "_mode", "mode")
        except Exception:
            pass

        if mode == "ocr":
            self._ensure_ocr_ready()
            self._set_ocr_visible(True)

            # Обновить OCR UI под текущий файл
            try:
                cur = getattr(self.preview, "_current_path", None)
                self.entries.on_path_changed(cur)
            except Exception:
                pass
            return

        # transform
        self._set_ocr_visible(False)

    def _ensure_ocr_ready(self) -> None:
        from smithanatool_qt.tabs.ai.controllers.viewer_controller import AiViewerController
        from smithanatool_qt.tabs.ai.controllers.entries_controller import AiEntriesController
        from smithanatool_qt.tabs.ai.services.ai_service import AiService

        if self._ocr_ready:
            return

        ocr_right = self.right.ensure_ocr_panel()

        # сервисы/контроллеры и подключение сигналов
        self.ai = AiService()
        self.viewer = AiViewerController(tab=self, gallery=self.gallery, preview=self.preview, right=ocr_right)
        self.entries = AiEntriesController(tab=self, viewer=self.viewer, right=ocr_right, ai=self.ai)

        try:
            from smithanatool_qt.tabs.ai.utils.rect_utils import normalize_rect_sort_mode
            self.entries._rect_sort_mode = normalize_rect_sort_mode(self._ocr_rect_sort_mode)
        except Exception:
            pass

        # right -> actions
        ocr_right.aiRequested.connect(self.entries.ai_all)
        ocr_right.saveRequested.connect(self.entries.save_to_file)
        ocr_right.saveAllRequested.connect(self.entries.save_all_to_file)
        ocr_right.handwritingRequested.connect(self.entries.open_handwriting_dialog)

        # overlay -> store
        self.viewer.overlay.rectAdded.connect(self.entries.on_rect_added)
        self.viewer.overlay.rectDeleted.connect(self.entries.on_rect_deleted)
        self.viewer.overlay.rectChanged.connect(self.entries.on_rect_changed)

        self._ocr_ready = True
        self._apply_mode_profile(self._mode)

        # стартуем отложенную инициализацию настроек (если есть)
        try:
            ocr_right._install_settings_widget_late()
        except Exception:
            pass

        # по умолчанию в режиме преобразований оверлей должен быть скрыт
        self._set_ocr_visible(False)

    def _set_ocr_visible(self, visible: bool) -> None:
        self._ocr_visible = bool(visible)
        if not self._ocr_ready:
            return

        try:
            self.viewer.overlay.setVisible(self._ocr_visible)
        except Exception:
            pass

        # Когда OCR скрыт, лучше не показывать busy overlay
        if not self._ocr_visible:
            try:
                self.entries._busy_overlay.hide()
            except Exception:
                pass

    # ---------------- misc ----------------
    def reset_layout_to_defaults(self):
        self.splitter.setSizes([LEFT_MIN_W, 1000, RIGHT_MIN_W])

    def _apply_mode_profile(self, mode: str) -> None:
        mode = (mode or "transform").strip().lower()
        is_transform = (mode == "transform")

        if hasattr(self.preview, "set_actions_ui_enabled"):
            self.preview.set_actions_ui_enabled(True)

        if hasattr(self.preview, "set_actions_profile"):
            self.preview.set_actions_profile("transform" if is_transform else "ocr")

        if hasattr(self.preview, "set_selection_enabled"):
            self.preview.set_selection_enabled(is_transform)

        if not is_transform:
            if hasattr(self.preview, "set_frame_enabled"):
                try:
                    self.preview.set_frame_enabled(False)
                except Exception:
                    pass

            if hasattr(self.preview, "_clear_selection"):
                try:
                    self.preview._clear_selection()
                except Exception:
                    pass

        # OCR overlay: создание новой области ЛКМ только в OCR
        if self._ocr_ready:
            from PySide6.QtCore import Qt
            self.viewer.overlay.set_create_button(
                Qt.MouseButton.LeftButton if mode == "ocr" else Qt.MouseButton.RightButton
            )
            try:
                self.entries._update_preview_ocr_menu_state()
            except Exception:
                pass

    def _on_preview_ocr_sort_requested(self) -> None:
        if self._mode != "ocr":
            return
        self._ensure_ocr_ready()
        try:
            title = self.entries.cycle_rect_sort_mode()
            self._sync_ocr_sort_mode_from_entries(save=True)
        except Exception:
            return
        self.preview.show_toast(f"Порядок рамок: {title}", 2500)

    def _on_preview_ocr_delete_requested(self) -> None:
        if self._mode != "ocr":
            return
        self._ensure_ocr_ready()
        try:
            self.entries.clear_rectangles()
        except Exception:
            pass

    def _on_preview_ocr_undo_requested(self) -> None:
        if self._mode != "ocr":
            return
        self._ensure_ocr_ready()
        try:
            self.entries.undo_last_action()
            self._sync_ocr_sort_mode_from_entries(save=True)
        except Exception:
            pass

    def _on_preview_ocr_redo_requested(self) -> None:
        if self._mode != "ocr":
            return
        self._ensure_ocr_ready()
        try:
            self.entries.redo_last_action()
            self._sync_ocr_sort_mode_from_entries(save=True)
        except Exception:
            pass