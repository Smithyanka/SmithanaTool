from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from .ini_mixin import AiSettingsIniMixin
from .engine_mixin import AiSettingsEngineMixin
from .ai_settings_ui import build_settings_group


class _EnginesInitWorker(QObject):
    finished = Signal(object)  # dict payload
    failed = Signal(str)

    def __init__(self, engines_path: Path, legacy_raw: str, gemini_key: str, parent=None):
        super().__init__(parent)
        self._path = Path(engines_path)
        self._legacy_raw = legacy_raw or ""
        self._gemini_key = (gemini_key or "").strip()

    @Slot()
    def run(self):
        try:
            from smithanatool_qt.tabs.ai.core.storage.engines_store import (
                read_custom_engines_file,
                write_custom_engines_file,
                parse_custom_engines_ini_raw,
                normalize_custom_engines,
            )
            from smithanatool_qt.tabs.ai.core.engine_manager import EngineManager

            clear_legacy = False

            data = read_custom_engines_file(self._path)
            if data:
                cleaned = normalize_custom_engines(data)
                if cleaned != data:
                    try:
                        write_custom_engines_file(self._path, cleaned)
                    except Exception:
                        pass
                data = cleaned
            else:
                migrated = parse_custom_engines_ini_raw(self._legacy_raw)
                if migrated:
                    cleaned = normalize_custom_engines(migrated)
                    try:
                        write_custom_engines_file(self._path, cleaned)
                    except Exception:
                        pass
                    data = cleaned
                    clear_legacy = True
                else:
                    data = []

            mgr = EngineManager.from_sources(custom_engines=data, gemini_api_key=self._gemini_key)
            self.finished.emit({"engine_mgr": mgr, "clear_legacy": clear_legacy})
        except Exception as e:
            self.failed.emit(str(e))


class AiSettingsWidget(QWidget, AiSettingsIniMixin, AiSettingsEngineMixin):
    """Независимый блок "Настройки".

    Встраиваемый виджет: можно перемещать в другую вкладку/панель.

    - Сам строит UI (build_settings_group)
    - Сам восстанавливает/сохраняет INI (только settings-ключи)
    - Сам асинхронно поднимает EngineManager (QThread)

    """

    enginesReady = Signal()
    enginesFailed = Signal(str)

    def __init__(self, parent=None, *, ini_group: str | None = None):
        super().__init__(parent)

        if ini_group:
            self.INI_GROUP = str(ini_group)

        self._ui_built = False
        self._started = False

        self._engines_thread: QThread | None = None
        self._engines_worker: _EnginesInitWorker | None = None
        self._engines_inited = False

        self._persistence_wired = False
        self._engine_signals_wired = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._loading = QLabel("")
        root.addWidget(self._loading)

        self._settings_group = None

        # Не стартуем автоматически тяжёлые вещи, чтобы можно было вставить/показать UI.
        # Вызови start_async_init() после добавления в layout (right_panel делает это).

    def start_async_init(self) -> None:
        if self._started:
            return
        self._started = True

        if self._loading is not None:
            self._loading.setText("Загрузка настроек…")
            self._loading.repaint()

        QTimer.singleShot(0, lambda: QTimer.singleShot(0, self._late_build_ui_and_init))

    # ------------------------
    # UI build + engines init
    # ------------------------

    def _late_build_ui_and_init(self) -> None:
        if self._ui_built:
            return
        self._ui_built = True

        # 1) UI
        self.setUpdatesEnabled(False)
        try:
            self._settings_group = build_settings_group(self)
            self.layout().addWidget(self._settings_group)

            # CRUD по движкам
            self.btn_add_engine.clicked.connect(self._on_add_engine)
            try:
                self.btn_remove_engine.clicked.connect(self._on_remove_engine)
                self.btn_edit_engine.clicked.connect(self._on_edit_engine)
            except Exception:
                pass

            # restore settings (быстро)
            self._restore_ini_settings()

            # пока движки не готовы — блокируем engine-контролы
            self._set_engine_widgets_enabled(False)
        finally:
            self.setUpdatesEnabled(True)

        # 2) engines init
        self._start_engines_init_thread()

    def _set_engine_widgets_enabled(self, enabled: bool) -> None:
        for name in (
            "cmb_engine",
            "btn_add_engine",
            "btn_remove_engine",
            "btn_edit_engine",
            "ed_api_key",
            "cmb_model",
        ):
            w = getattr(self, name, None)
            if w is not None:
                try:
                    w.setEnabled(enabled)
                except Exception:
                    pass

    def _start_engines_init_thread(self) -> None:
        if self._engines_inited or self._engines_thread is not None:
            return

        # берём только данные (строки/путь) в GUI-потоке
        gemini_key = (self._get_ini("gemini_api_key", "", typ=str) or "").strip()
        legacy_raw = str(self._get_ini(self.KEY_CUSTOM_ENGINES, "", typ=str) or "")
        p = self._custom_engines_path()

        self._engines_thread = QThread(self)
        self._engines_worker = _EnginesInitWorker(p, legacy_raw, gemini_key)
        self._engines_worker.moveToThread(self._engines_thread)

        self._engines_thread.started.connect(self._engines_worker.run)
        self._engines_worker.finished.connect(self._on_engines_ready)
        self._engines_worker.failed.connect(self._on_engines_failed)

        # корректная уборка
        self._engines_worker.finished.connect(self._engines_thread.quit)
        self._engines_worker.failed.connect(self._engines_thread.quit)
        self._engines_worker.finished.connect(self._engines_worker.deleteLater)
        self._engines_worker.failed.connect(self._engines_worker.deleteLater)
        self._engines_thread.finished.connect(self._engines_thread.deleteLater)

        self._engines_thread.start()

    def _on_engines_ready(self, payload: dict) -> None:
        self._engines_inited = True

        # если мигрировали legacy INI -> файл, чистим legacy ключ в GUI-потоке
        if payload.get("clear_legacy"):
            self._save_ini(self.KEY_CUSTOM_ENGINES, "")

        mgr = payload.get("engine_mgr")
        if mgr is not None:
            self._apply_engine_manager(mgr)

        # теперь можно подключать сигналы сохранения и движков
        if not self._persistence_wired:
            self._wire_persistence_settings()
            self._persistence_wired = True

        if not self._engine_signals_wired:
            self._wire_engine_signals()
            self._engine_signals_wired = True

        # убрать "loading" лейбл
        if self._loading is not None:
            self._loading.setParent(None)
            self._loading.deleteLater()
            self._loading = None

        self._set_engine_widgets_enabled(True)

        # сброс ссылок
        self._engines_thread = None
        self._engines_worker = None

        self.enginesReady.emit()

    def _on_engines_failed(self, msg: str) -> None:
        if self._loading is not None:
            self._loading.setText(f"Не удалось загрузить движки: {msg}")

        self._set_engine_widgets_enabled(False)

        self._engines_thread = None
        self._engines_worker = None

        self.enginesFailed.emit(msg)
