from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QSplitter, QMessageBox, QFileDialog
from smithanatool_qt.utils import dialogs

from .gallery_panel import GalleryPanel
from .preview_panel import PreviewPanel
from .sections_panel import SectionsPanel

from PySide6.QtGui import QShortcut, QKeySequence
import os
from smithanatool_qt.settings_bind import group, bind_attr_string, save_attr_string


class TransformTab(QWidget):
    """Собирает три панели в QSplitter и связывает их сигналами."""
    def __init__(self, parent=None):
        super().__init__(parent)

        splitter = QSplitter(Qt.Horizontal, self)
        self.gallery = GalleryPanel()
        self.preview = PreviewPanel()
        self.preview.gallery_panel = self.gallery
        self.sections = SectionsPanel(self.gallery, self.preview)

        self.gallery.set_unsaved_checker(self.preview.has_unsaved_changes)

        self.gallery.set_dirty_checker(self.preview.is_dirty)
        self.preview.dirtyChanged.connect(self.gallery.mark_dirty)
        self.gallery.set_forget_callback(self.preview.forget_paths)

        splitter.addWidget(self.gallery)
        splitter.addWidget(self.preview)
        splitter.addWidget(self.sections)
        splitter.setSizes([100, 900, 700])  # дефолт

        splitter.setProperty("persist_key", "TransformTab/splitter")
        self.splitter = splitter

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 15, 0, 10)
        lay.setSpacing(0)
        lay.addWidget(splitter)

        # Сигналы: выбор файла -> предпросмотр
        self.gallery.currentPathChanged.connect(self.preview.show_path)

        # Сохранение
        self.preview.btn_save.clicked.connect(self._save)
        self.preview.btn_save_as.clicked.connect(self._save_as)
        self.preview.saveAsRequested.connect(self._save_as)

        # --- Хоткеи
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._save)
        QShortcut(QKeySequence("Ctrl+Shift+S"), self, activated=self._save_as)

        self._save_dir = ""



        self._apply_settings_from_ini()

    def _apply_settings_from_ini(self):
        try:
            with group("TransformTab"):
                bind_attr_string(self, "_save_dir", "save_dir", "")
        except Exception:
            pass
    def _save_str_ini(self, key: str, value: str):
        try:
            shadow_attr = f"__{key}__shadow"
            setattr(self, shadow_attr, value)
            with group("TransformTab"):
                save_attr_string(self, shadow_attr, key)
        except Exception:
            pass
    def _save(self):
        # Запрет для PSD/PSB
        if self.preview._is_current_psd():
            QMessageBox.information(self, "Сохранение недоступно",
                                    "PSD/PSB нельзя сохранять в этом режиме.")
            return
        path = getattr(self.preview, "_current_path", None)
        if self.preview._is_memory_path(path) or self.preview._is_pasted_temp_path(path):
            self._save_as(); return
        if self.preview.save_current_overwrite():
            self.preview.show_toast("Сохранено!", 3000)
        else:
            QMessageBox.warning(self, "Ошибка", "Не удалось сохранить изображение.")

    def _save_as(self):
        # (нужно: import os; dialogs и QMessageBox уже импортированы выше)
        cur = getattr(self.preview, "_current_path", None)

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
            initial_path=initial
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
            new_dir = os.path.dirname(path)
            if new_dir and os.path.isdir(new_dir):
                self._save_dir = new_dir
                # метод из шага с INI: сохраняет строку в группу TransformTab
                if hasattr(self, "_save_str_ini"):
                    self._save_str_ini("save_dir", self._save_dir)
            QMessageBox.information(self, "Сохранено", f"Сохранено: {path}")
        else:
            QMessageBox.warning(self, "Ошибка", "Не удалось сохранить изображение.")

    def reset_layout_to_defaults(self):
        self.splitter.setSizes([100, 900, 700])

