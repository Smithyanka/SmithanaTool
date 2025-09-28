from smithanatool_qt.settings_bind import group, save_attr_string, bind_attr_string

class IniStringsMixin:
    """Small mixin to save/load strings to INI with a per-class group."""
    INI_GROUP: str | None = None

    def _ini_group(self) -> str:
        return self.INI_GROUP or self.__class__.__name__

    def _ini_save_str(self, key: str, value: str):
        shadow_attr = f"__{key}__shadow"
        setattr(self, shadow_attr, value)
        with group(self._ini_group()):
            save_attr_string(self, shadow_attr, key)

    def _ini_load_str(self, key: str, default: str = "") -> str:
        shadow_attr = f"__{key}__shadow"
        setattr(self, shadow_attr, default)
        with group(self._ini_group()):
            bind_attr_string(self, shadow_attr, key, default)
        return getattr(self, shadow_attr, default)
