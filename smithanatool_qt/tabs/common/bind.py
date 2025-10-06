from PySide6.QtWidgets import QLineEdit, QSpinBox, QCheckBox, QComboBox
from smithanatool_qt.settings_bind import group
from smithanatool_qt.tabs.common.defaults import DEFAULTS

def _to_bool(s: str) -> bool:
    return str(s).lower() in ("1", "true", "yes", "on")

def _from_bool(b: bool) -> str:
    return "1" if b else "0"

def bind_widget(self, widget, key: str, default, section: str):
    """Привязать widget <-> INI[section/key] с автозагрузкой и автосохранением."""
    # загрузка
    val = self._ini_load_str(key, str(default))

    if isinstance(widget, QLineEdit):
        widget.setText(val)
        widget.textChanged.connect(lambda v: self._save_str_ini(key, v))
        return

    if isinstance(widget, QSpinBox):
        try:
            widget.setValue(int(val))
        except ValueError:
            widget.setValue(int(default))
        widget.valueChanged.connect(lambda v: self._save_str_ini(key, str(int(v))))
        return

    if isinstance(widget, QCheckBox):
        widget.setChecked(_to_bool(val))
        widget.toggled.connect(lambda v: self._save_str_ini(key, _from_bool(v)))
        return

    if isinstance(widget, QComboBox):
        try:
            widget.setCurrentIndex(int(val))
        except ValueError:
            widget.setCurrentIndex(int(default))
        widget.currentIndexChanged.connect(lambda i: self._save_str_ini(key, str(int(i))))
        return

    raise TypeError(f"bind_widget: неподдерживаемый виджет {type(widget).__name__}")

def apply_bindings(self, section: str, table: list[tuple]):
    for widget, key, default in table:
        bind_widget(self, widget, key, DEFAULTS.get(key, default), section)