# ini_mixin.py (AiSettings)
from __future__ import annotations

from pathlib import Path

from smithanatool_qt.settings_bind import group, get_value, set_value, ini_path

from smithanatool_qt.tabs.ai.core.storage.engines_store import (
    custom_engines_path,
    read_custom_engines_file,
    write_custom_engines_file,
    parse_custom_engines_ini_raw,
    normalize_custom_engines,
)


class AiSettingsIniMixin:
    """
    INI-персист для блока "Настройки" (движки/модель/язык/API keys и т.д.).

    По умолчанию хранит значения в группе INI_GROUP="AiSettings".
    Поддерживает миграцию со старой группы LEGACY_INI_GROUP="AiRightPanel".
    """

    INI_GROUP = "AiSettings"
    LEGACY_INI_GROUP = "AiRightPanel"

    KEY_CUSTOM_ENGINES = "custom_engines"  # legacy (huge json string) — keep for migration
    CUSTOM_ENGINES_FILENAME = "custom_engines.json"

    KEY_ENGINE_ID = "engine_id"
    KEY_ENGINE_IDX = "engine_idx"
    KEY_MODEL_ID = "model_id"
    KEY_MODEL_IDX = "model_idx"
    KEY_LANG_CODE = "lang_code"
    KEY_LANG_IDX = "lang_idx"
    KEY_BATCH_SIZE = "batch_size"
    LEGACY_KEY_BATCH_SIZE = "gemini_batch_size"
    KEY_YC_API_KEY = "yc_api_key"
    KEY_YC_FOLDER_ID = "yc_folder_id"

    _MIGRATE_KEYS = {
        KEY_ENGINE_ID,
        KEY_ENGINE_IDX,
        KEY_MODEL_ID,
        KEY_MODEL_IDX,
        KEY_LANG_CODE,
        KEY_LANG_IDX,
        KEY_BATCH_SIZE,
        KEY_YC_API_KEY,
        KEY_YC_FOLDER_ID,
        KEY_CUSTOM_ENGINES,
    }

    def _set_combo_by_data(self, combo, data_value: str) -> bool:
        """Выбрать элемент QComboBox по itemData(). Возвращает True если найдено."""
        if data_value is None:
            return False
        target = str(data_value).strip()
        for i in range(combo.count()):
            if str(combo.itemData(i) or "") == target:
                combo.setCurrentIndex(i)
                return True
        return False

    # -------------------------
    # Custom engines (JSON file)
    # -------------------------

    def _custom_engines_path(self) -> Path:
        """Файл custom_engines.json рядом с settings.ini."""
        try:
            return custom_engines_path(ini_path().resolve(), filename=self.CUSTOM_ENGINES_FILENAME)
        except Exception:
            return Path(self.CUSTOM_ENGINES_FILENAME)

    def _load_custom_engines(self) -> list[dict]:
        """Загрузить кастомные движки из custom_engines.json (рядом с settings.ini).

        Поддерживает миграцию со старого INI-ключа (огромная JSON-строка).
        Также гарантирует наличие поля `id` у каждого движка.

        NOTE: метод синхронный (GUI-поток). Для старта приложения лучше
        использовать асинхронную инициализацию в AiSettingsWidget.
        """
        p = self._custom_engines_path()

        data = read_custom_engines_file(p)
        if data:
            try:
                cleaned = normalize_custom_engines(data)
                write_custom_engines_file(p, cleaned)
                return cleaned
            except Exception:
                return data

        raw = ""
        try:
            raw = str(self._get_ini(self.KEY_CUSTOM_ENGINES, "", typ=str) or "")
        except Exception:
            raw = ""

        if raw.strip():
            try:
                parsed = parse_custom_engines_ini_raw(raw)
                cleaned = normalize_custom_engines(parsed)
                write_custom_engines_file(p, cleaned)

                try:
                    with group(self.INI_GROUP):
                        set_value(self.KEY_CUSTOM_ENGINES, "")
                except Exception:
                    pass

                return cleaned
            except Exception:
                pass

        return []

    def _save_custom_engines(self, payload: list[dict]) -> None:
        """Сохранить кастомные движки в custom_engines.json (рядом с settings.ini)."""
        p = self._custom_engines_path()
        cleaned = normalize_custom_engines(payload or [])
        write_custom_engines_file(p, cleaned)

    # -------------------------
    # INI: Settings only
    # -------------------------

    def _restore_ini_settings(self) -> None:
        """Восстановить INI только для блока "Настройки"."""
        model_id = self._get_ini(self.KEY_MODEL_ID, "", typ=str)
        model_idx = self._get_ini(self.KEY_MODEL_IDX, 0, typ=int)
        lang_idx = self._get_ini(self.KEY_LANG_IDX, 0, typ=int)
        batch_size = self._read_batch_size(default=8)
        yc_api_key = self._get_ini(self.KEY_YC_API_KEY, "", typ=str)
        yc_folder_id = self._get_ini(self.KEY_YC_FOLDER_ID, "", typ=str)
        lang_code = self._normalize_lang_code(self._get_ini(self.KEY_LANG_CODE, "", typ=str))

        self._restore_model_selection(model_id=model_id, model_idx=model_idx)
        self._restore_language_selection(lang_code=lang_code, lang_idx=lang_idx)
        self._restore_batch_and_yandex(batch_size=batch_size, yc_api_key=yc_api_key, yc_folder_id=yc_folder_id)

    def _restore_model_selection(self, *, model_id, model_idx) -> None:
        combo = getattr(self, "cmb_model", None)
        if combo is None:
            return

        mid = (str(model_id) if model_id is not None else "").strip()
        if mid:
            try:
                self._set_combo_by_data(combo, mid)
            except Exception:
                pass
            return

        self._set_combo_index_safe(combo, model_idx, default=0)

    def _restore_language_selection(self, *, lang_code: str, lang_idx) -> None:
        combo = getattr(self, "cmb_lang", None)
        if combo is None:
            return

        if lang_code:
            ok = self._set_combo_by_data(combo, lang_code)
            if not ok:
                combo.setCurrentIndex(0)
            return

        self._set_combo_index_safe(combo, lang_idx, default=0)

        try:
            migrated = str(combo.currentData() or "").strip()
            with group(self.INI_GROUP):
                set_value(self.KEY_LANG_CODE, migrated)
        except Exception:
            pass

    def _restore_batch_and_yandex(self, *, batch_size, yc_api_key, yc_folder_id) -> None:
        try:
            if getattr(self, "spn_batch", None) is not None:
                self.spn_batch.setValue(self._coerce_int(batch_size, default=8))
        except Exception:
            pass

        try:
            if getattr(self, "ed_yc_api_key", None) is not None:
                self.ed_yc_api_key.setText(str(yc_api_key or ""))
            if getattr(self, "ed_yc_folder_id", None) is not None:
                self.ed_yc_folder_id.setText(str(yc_folder_id or ""))
        except Exception:
            pass

    def _wire_persistence_settings(self) -> None:
        """Подключить сохранение INI только для блока "Настройки"."""
        if getattr(self, "cmb_model", None) is not None:
            try:
                self.cmb_model.currentIndexChanged.connect(
                    lambda *_: self._save_ini(self.KEY_MODEL_ID, str(self.cmb_model.currentData() or ""))
                )
            except Exception:
                pass

        if getattr(self, "cmb_lang", None) is not None:
            try:
                self.cmb_lang.currentIndexChanged.connect(
                    lambda *_: self._save_ini(self.KEY_LANG_CODE, str(self.cmb_lang.currentData() or ""))
                )
            except Exception:
                pass

        if getattr(self, "spn_batch", None) is not None:
            try:
                self.spn_batch.valueChanged.connect(
                    lambda *_: self._save_ini(self.KEY_BATCH_SIZE, int(self.spn_batch.value()))
                )
            except Exception:
                pass

        if getattr(self, "ed_yc_api_key", None) is not None:
            try:
                self.ed_yc_api_key.textChanged.connect(
                    lambda *_: self._save_ini(self.KEY_YC_API_KEY, str(self.ed_yc_api_key.text() or ""))
                )
            except Exception:
                pass
        if getattr(self, "ed_yc_folder_id", None) is not None:
            try:
                self.ed_yc_folder_id.textChanged.connect(
                    lambda *_: self._save_ini(self.KEY_YC_FOLDER_ID, str(self.ed_yc_folder_id.text() or ""))
                )
            except Exception:
                pass

    def _read_batch_size(self, default: int = 8) -> int:
        batch_size = self._get_ini(self.KEY_BATCH_SIZE, default, typ=int)
        if self._is_meaningful_value(batch_size, default):
            return self._coerce_int(batch_size, default=default)

        legacy = self._read_ini_from_group(self.INI_GROUP, self.LEGACY_KEY_BATCH_SIZE, default, typ=int)
        if not self._is_meaningful_value(legacy, default):
            legacy = self._read_ini_from_group(self.LEGACY_INI_GROUP, self.LEGACY_KEY_BATCH_SIZE, default, typ=int)

        if self._is_meaningful_value(legacy, default):
            normalized = self._coerce_int(legacy, default=default)
            self._save_ini(self.KEY_BATCH_SIZE, normalized)
            return normalized

        return self._coerce_int(batch_size, default=default)

    # -------------------------
    # Shared helpers
    # -------------------------

    @staticmethod
    def _coerce_int(value, default: int) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

    @staticmethod
    def _normalize_lang_code(value) -> str:
        lang_code = (str(value) if value is not None else "").strip().lower()

        if lang_code in ("english", "eng"):
            return "en"
        if lang_code in ("russian", "rus"):
            return "ru"
        if lang_code in ("korean",):
            return "ko"
        if lang_code in ("japan", "jp", "jpn"):
            return "ja"
        if lang_code in ("chinese", "china", "cn", "zho", "chi", "zh-cn", "zh-tw", "zh-hans", "zh-hant"):
            return "zh"
        if lang_code == "auto":
            return ""

        return lang_code

    @staticmethod
    def _is_meaningful_value(value, default) -> bool:
        try:
            return value != default and str(value) != str(default)
        except Exception:
            return False

    @staticmethod
    def _set_combo_index_safe(combo, index_value, *, default: int = 0) -> None:
        try:
            index = int(index_value)
        except Exception:
            index = int(default)

        if index < 0 or index >= combo.count():
            index = int(default)
        combo.setCurrentIndex(index)

    def _save_ini(self, key: str, value) -> None:
        try:
            with group(self.INI_GROUP):
                set_value(key, value)
        except Exception:
            pass

    def _get_ini_bool(self, key: str, default: bool = False) -> bool:
        v = self._get_ini(key, default, typ=bool)
        try:
            return bool(v)
        except Exception:
            return bool(default)

    def _read_ini_from_group(self, group_name: str, key: str, default, typ):
        try:
            with group(group_name):
                return get_value(key, default, typ=typ)
        except Exception:
            return default

    def _get_ini(self, key: str, default, typ):
        """Прочитать значение из INI (AiSettings) с fallback на legacy группу (AiRightPanel)."""
        v = self._read_ini_from_group(self.INI_GROUP, key, default, typ)

        if key in getattr(self, "_MIGRATE_KEYS", set()):
            is_default = not self._is_meaningful_value(v, default)
            if is_default:
                legacy = self._read_ini_from_group(self.LEGACY_INI_GROUP, key, default, typ)
                if self._is_meaningful_value(legacy, default):
                    try:
                        with group(self.INI_GROUP):
                            set_value(key, legacy)
                    except Exception:
                        pass
                    v = legacy

        return v
