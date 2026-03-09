from __future__ import annotations

from PySide6.QtWidgets import QLineEdit, QSpinBox, QCheckBox, QComboBox
from smithanatool_qt.settings_bind import group, bind_attr_string, save_attr_string
from smithanatool_qt.tabs.common.defaults import DEFAULTS


_BINDINGS_ATTR = "__ini_bindings__"  # dict[str, list[tuple[widget, key, default]]]


def _to_bool(s: str) -> bool:
    return str(s).strip().lower() in ("1", "true", "yes", "on")


def _from_bool(b: bool) -> str:
    return "1" if bool(b) else "0"


class _IniStore:
    pass


_INI = _IniStore()


def _shadow_attr(section: str, key: str) -> str:
    # уникальный атрибут, чтобы не было конфликтов между секциями
    return f"__ini__{section}__{key}__shadow"


def ini_load_str(section: str, key: str, default: str = "") -> str:
    attr = _shadow_attr(section, key)
    setattr(_INI, attr, default)
    with group(section):
        bind_attr_string(_INI, attr, key, default)
    return getattr(_INI, attr, default)


def ini_save_str(section: str, key: str, value: str) -> None:
    attr = _shadow_attr(section, key)
    setattr(_INI, attr, value)
    with group(section):
        save_attr_string(_INI, attr, key)


def ini_load_int(section: str, key: str, default: int = 0) -> int:
    s = ini_load_str(section, key, str(int(default)))
    try:
        return int(str(s).strip())
    except Exception:
        return int(default)


def ini_save_int(section: str, key: str, value: int) -> None:
    ini_save_str(section, key, str(int(value)))


def ini_load_bool(section: str, key: str, default: bool = False) -> bool:
    s = ini_load_str(section, key, _from_bool(default))
    return _to_bool(s)


def ini_save_bool(section: str, key: str, value: bool) -> None:
    ini_save_str(section, key, _from_bool(value))


def _bindings_map(obj) -> dict:
    mp = getattr(obj, _BINDINGS_ATTR, None)
    if mp is None:
        mp = {}
        setattr(obj, _BINDINGS_ATTR, mp)
    return mp


def _set_widget_value(widget, value) -> None:
    if isinstance(widget, QLineEdit):
        widget.setText("" if value is None else str(value))
        return
    if isinstance(widget, QSpinBox):
        widget.setValue(int(value))
        return
    if isinstance(widget, QCheckBox):
        widget.setChecked(bool(value))
        return
    if isinstance(widget, QComboBox):
        widget.setCurrentIndex(int(value))
        return
    raise TypeError(f"reset_bindings: неподдерживаемый виджет {type(widget).__name__}")


def _save_widget_value(widget, key: str, section: str) -> None:
    if isinstance(widget, QLineEdit):
        val = widget.text()
    elif isinstance(widget, QSpinBox):
        val = str(int(widget.value()))
    elif isinstance(widget, QCheckBox):
        val = _from_bool(bool(widget.isChecked()))
    elif isinstance(widget, QComboBox):
        val = str(int(widget.currentIndex()))
    else:
        raise TypeError(f"reset_bindings: неподдерживаемый виджет {type(widget).__name__}")

    ini_save_str(section, key, val)


def bind_widget(self, widget, key: str, default, section: str):
    """Привязать widget <-> INI[section/key] с автозагрузкой и автосохранением."""
    # загрузка
    val = ini_load_str(section, key, str(default))

    if isinstance(widget, QLineEdit):
        widget.setText(val)
        widget.editingFinished.connect(lambda: ini_save_str(section, key, widget.text()))
        return

    if isinstance(widget, QSpinBox):
        try:
            widget.setValue(int(val))
        except ValueError:
            widget.setValue(int(default))
        widget.valueChanged.connect(lambda v: ini_save_str(section, key, str(int(v))))
        return

    if isinstance(widget, QCheckBox):
        widget.setChecked(_to_bool(val))
        widget.toggled.connect(lambda v: ini_save_str(section, key, _from_bool(v)))
        return

    if isinstance(widget, QComboBox):
        try:
            widget.setCurrentIndex(int(val))
        except ValueError:
            widget.setCurrentIndex(int(default))
        widget.currentIndexChanged.connect(lambda i: ini_save_str(section, key, str(int(i))))
        return

    raise TypeError(f"bind_widget: неподдерживаемый виджет {type(widget).__name__}")


def apply_bindings(self, section: str, table: list[tuple]):
    """Применить биндинги и зарегистрировать их для reset-to-defaults."""
    resolved = []
    for widget, key, default in table:
        d = DEFAULTS.get(key, default)
        resolved.append((widget, key, d))
        bind_widget(self, widget, key, d, section)

    _bindings_map(self)[section] = resolved
    return resolved


def reset_bindings(self, section: str, table: list[tuple] | None = None) -> None:
    """Сбросить значения (UI + INI) по таблице биндингов."""

    if table is None:
        table = _bindings_map(self).get(section)
    if not table:
        return

    for widget, key, default in table:
        _set_widget_value(widget, default)
        _save_widget_value(widget, key, section)
