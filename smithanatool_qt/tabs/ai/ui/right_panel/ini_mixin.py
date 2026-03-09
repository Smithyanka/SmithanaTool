# ini_mixin.py (Right panel: Extra only)
from __future__ import annotations

from smithanatool_qt.settings_bind import group, get_value, set_value


class RightPanelIniMixin:
    """INI-персист ТОЛЬКО для extra-настроек правой панели (thumbs/zoom и т.п.).

    Настройки движков/моделей/ключей теперь живут в ui/settings/ini_mixin.py (AiSettingsIniMixin)
    и сохраняются в группе INI_GROUP="AiSettings".
    """

    INI_GROUP = "AiRightPanel"

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
    # INI helpers
    # -------------------------

    def _save_ini(self, key: str, val):
        try:
            with group(self.INI_GROUP):
                set_value(key, val)
        except Exception:
            pass

    def _get_ini_bool(self, key: str, default: bool = False) -> bool:
        try:
            with group(self.INI_GROUP):
                return bool(get_value(key, default, typ=bool))
        except Exception:
            return default

    def _get_ini(self, key: str, default=None, typ=str):
        try:
            with group(self.INI_GROUP):
                return get_value(key, default, typ=typ)
        except Exception:
            return default
