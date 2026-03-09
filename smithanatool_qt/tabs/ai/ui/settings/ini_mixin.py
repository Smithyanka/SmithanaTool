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

    _MIGRATE_KEYS = {
        # engine selection
        "engine_id",
        "engine_idx",
        # model/lang
        "model_id",
        "model_idx",
        "lang_code",
        "lang_idx",
        # service keys
        "batch_size",
        "yc_api_key",
        "yc_folder_id",
        # legacy payload
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

        # fallback + миграция со старого формата (INI)
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

                # очистим legacy, но уже в новой группе
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
        # читаем из новой группы (AiSettings), с fallback на legacy AiRightPanel
        def _read(key: str, default, typ):
            v = self._get_ini(key, default, typ=typ)
            return v

        # legacy idx fallbacks
        model_id = _read("model_id", "", str)
        m = _read("model_idx", 0, int)
        l = _read("lang_idx", 0, int)
        bs = _read("gemini_batch_size", 8, int)
        yk = _read("yc_api_key", "", str)
        yf = _read("yc_folder_id", "", str)
        lc = _read("lang_code", "", str)

        # model: prefer model_id (itemData), fallback model_idx
        mid = (str(model_id) if model_id is not None else "").strip()
        if mid and getattr(self, "cmb_model", None) is not None:
            try:
                self._set_combo_by_data(self.cmb_model, mid)
            except Exception:
                pass
        else:
            try:
                if getattr(self, "cmb_model", None) is not None:
                    self.cmb_model.setCurrentIndex(int(m) if isinstance(m, int) or str(m).isdigit() else 0)
            except Exception:
                pass

        # lang
        lang_code = (str(lc) if lc is not None else "").strip().lower()
        if lang_code in ("korean",):
            lang_code = "ko"
        elif lang_code in ("japan", "jp", "jpn"):
            lang_code = "ja"
        elif lang_code == "auto":
            lang_code = ""

        if getattr(self, "cmb_lang", None) is not None:
            if lang_code:
                ok = self._set_combo_by_data(self.cmb_lang, lang_code)
                if not ok:
                    self.cmb_lang.setCurrentIndex(0)
            else:
                # legacy index (миграция)
                try:
                    self.cmb_lang.setCurrentIndex(int(l) if isinstance(l, int) or str(l).isdigit() else 0)
                except Exception:
                    self.cmb_lang.setCurrentIndex(0)
                # миграция в lang_code
                try:
                    migrated = str(self.cmb_lang.currentData() or "").strip()
                    with group(self.INI_GROUP):
                        set_value("lang_code", migrated)
                except Exception:
                    pass

        # batch + yc
        try:
            if getattr(self, "spn_batch", None) is not None:
                self.spn_batch.setValue(int(bs) if isinstance(bs, int) or str(bs).isdigit() else 8)
        except Exception:
            pass
        try:
            if getattr(self, "ed_yc_api_key", None) is not None:
                self.ed_yc_api_key.setText(str(yk or ""))
            if getattr(self, "ed_yc_folder_id", None) is not None:
                self.ed_yc_folder_id.setText(str(yf or ""))
        except Exception:
            pass

    def _wire_persistence_settings(self) -> None:
        """Подключить сохранение INI только для блока "Настройки"."""
        # model (по itemData)
        if getattr(self, "cmb_model", None) is not None:
            try:
                self.cmb_model.currentIndexChanged.connect(
                    lambda *_: self._save_ini("model_id", str(self.cmb_model.currentData() or ""))
                )
            except Exception:
                pass

        # lang (по itemData)
        if getattr(self, "cmb_lang", None) is not None:
            try:
                self.cmb_lang.currentIndexChanged.connect(
                    lambda *_: self._save_ini("lang_code", str(self.cmb_lang.currentData() or ""))
                )
            except Exception:
                pass

        # batch
        if getattr(self, "spn_batch", None) is not None:
            try:
                self.spn_batch.valueChanged.connect(lambda *_: self._save_ini("batch_size", int(self.spn_batch.value())))
            except Exception:
                pass

        # yc
        if getattr(self, "ed_yc_api_key", None) is not None:
            try:
                self.ed_yc_api_key.textChanged.connect(lambda *_: self._save_ini("yc_api_key", str(self.ed_yc_api_key.text() or "")))
            except Exception:
                pass
        if getattr(self, "ed_yc_folder_id", None) is not None:
            try:
                self.ed_yc_folder_id.textChanged.connect(lambda *_: self._save_ini("yc_folder_id", str(self.ed_yc_folder_id.text() or "")))
            except Exception:
                pass

    # -------------------------
    # Shared helpers
    # -------------------------

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

    def _get_ini(self, key: str, default, typ):
        """Прочитать значение из INI (AiSettings) с fallback на legacy группу (AiRightPanel)."""
        try:
            with group(self.INI_GROUP):
                v = get_value(key, default, typ=typ)
        except Exception:
            v = default

        # миграция: если в новой группе значение дефолтное, попробуем legacy
        if key in getattr(self, "_MIGRATE_KEYS", set()):
            try:
                is_default = (v == default) or (str(v) == str(default) and typ in (str, int, bool))
            except Exception:
                is_default = True

            if is_default:
                try:
                    with group(self.LEGACY_INI_GROUP):
                        legacy = get_value(key, default, typ=typ)
                    # если в legacy есть не-дефолт — используем и пишем в новую группу
                    if legacy != default:
                        try:
                            with group(self.INI_GROUP):
                                set_value(key, legacy)
                        except Exception:
                            pass
                        v = legacy
                except Exception:
                    pass

        return v
