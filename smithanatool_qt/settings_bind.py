
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Any

from PySide6.QtCore import QSettings, QByteArray

_GROUP_STACK: list[str] = []

def _prefixed(key: str) -> str:
    if _GROUP_STACK:
        return "/".join(_GROUP_STACK + [key])
    return key

def _current_group_path() -> str:
    return "/".join(_GROUP_STACK)

def _prefixed_with(path: str, key: str) -> str:
    return f"{path}/{key}" if path else key

from PySide6.QtWidgets import QWidget, QLineEdit, QCheckBox, QSpinBox, QDoubleSpinBox, QComboBox, QRadioButton, QAbstractButton

# Single QSettings instance, INI format in app folder by default
import sys
# Place settings.ini next to the running binary (PyInstaller) or next to the entry script.
if getattr(sys, 'frozen', False):
    _base_dir = Path(sys.executable).resolve().parent  # folder with .exe
else:
    _base_dir = Path(sys.argv[0]).resolve().parent      # folder with main.py / entry script
_ini_path = _base_dir / "settings.ini"
_settings = QSettings(str(_ini_path), QSettings.IniFormat)

def ini_path() -> Path:
    return _ini_path

@contextmanager
def group(name: str):
    _GROUP_STACK.append(name)
    _settings.beginGroup(name)
    try:
        yield
    finally:
        _settings.endGroup()
        _GROUP_STACK.pop()

def set_value(key: str, value: Any):
    _settings.setValue(_prefixed(key), value)
    _settings.sync()
    _settings.sync()

def get_value(key: str, default: Any=None, typ: Optional[type]=None):
    key = _prefixed(key)

    # PySide6 compatibility: some builds don't accept 'typ='; prefer 'type='; fallback to manual cast.
    try:
        if typ is None:
            return _settings.value(key, default)
        return _settings.value(key, default, type=typ)  # type: ignore
    except TypeError:
        v = _settings.value(key, default)
        if typ is None or v is None:
            return v
        try:
            if typ is bool:
                if isinstance(v, str):
                    return v.lower() in ("1","true","yes","on")
                if isinstance(v, int):
                    return v != 0
                return bool(v)
            return typ(v)
        except Exception:
            return default

# ---------- Widget binders ----------

def bind_line_edit(widget: QLineEdit, key: str, default: str = ""):
    _path = _current_group_path()
    gkey = _prefixed_with(_path, key)
    v = _settings.value(gkey, None)
    migrated = False
    if v is None:
        v = _settings.value(key, None)
        if v is not None:
            _settings.setValue(gkey, v)  # migrate
            _settings.remove(key)        # cleanup duplicate
            migrated = True
    if v is None:
        v = default
    widget.setText(str(v))
    def _on(val):
        _settings.setValue(gkey, val)
    widget.textChanged.connect(_on)


def bind_checkbox(widget: QCheckBox, key: str, default: bool = False):
    _path = _current_group_path()
    gkey = _prefixed_with(_path, key)
    v = _settings.value(gkey, None)
    if v is None:
        v = _settings.value(key, None)
        if v is not None:
            _settings.setValue(gkey, v); _settings.remove(key)
    if isinstance(v, str):
        vv = v.lower() in ("1","true","yes","on")
    elif v is None:
        vv = bool(default)
    else:
        vv = bool(v)
    widget.setChecked(vv)
    def _on(_state):
        _settings.setValue(gkey, widget.isChecked())
    widget.stateChanged.connect(_on)


def bind_spinbox(widget: QSpinBox, key: str, default: int = 0):
    _path = _current_group_path()
    gkey = _prefixed_with(_path, key)
    v = _settings.value(gkey, None)
    if v is None:
        v = _settings.value(key, None)
        if v is not None:
            _settings.setValue(gkey, v); _settings.remove(key)
    try:
        vv = int(v if v is not None else default)
    except Exception:
        vv = int(default)
    widget.setValue(vv)
    def _on(val):
        _settings.setValue(gkey, int(val))
    widget.valueChanged.connect(_on)


def bind_dspinbox(widget: QDoubleSpinBox, key: str, default: float = 0.0):
    _path = _current_group_path()
    gkey = _prefixed_with(_path, key)
    v = _settings.value(gkey, None)
    if v is None:
        v = _settings.value(key, None)
        if v is not None:
            _settings.setValue(gkey, v); _settings.remove(key)
    try:
        vv = float(v if v is not None else default)
    except Exception:
        vv = float(default)
    widget.setValue(vv)
    def _on(val):
        _settings.setValue(gkey, float(val))
    widget.valueChanged.connect(_on)


def bind_combobox(widget: QComboBox, key: str, default_index: int = 0, by_text: bool = False):
    _path = _current_group_path()
    gkey = _prefixed_with(_path, key)
    if by_text:
        saved = _settings.value(gkey, None)
        if saved is None:
            saved = _settings.value(key, None)
            if saved is not None:
                _settings.setValue(gkey, saved); _settings.remove(key)
        if saved is not None:
            idx = widget.findText(str(saved))
            if idx >= 0:
                widget.setCurrentIndex(idx)
    else:
        idx = _settings.value(gkey, None)
        if idx is None:
            idx = _settings.value(key, None)
            if idx is not None:
                _settings.setValue(gkey, idx); _settings.remove(key)
        try:
            widget.setCurrentIndex(int(idx if idx is not None else default_index))
        except Exception:
            widget.setCurrentIndex(default_index)
    def _on(i):
        _settings.setValue(gkey, widget.currentText() if by_text else int(i))
    widget.currentIndexChanged.connect(_on)


def bind_radiobuttons(buttons: list[QRadioButton], key: str, default_index: int = 0):
    _path = _current_group_path()
    gkey = _prefixed_with(_path, key)
    saved = _settings.value(gkey, None)
    if saved is None:
        saved = _settings.value(key, None)
        if saved is not None:
            _settings.setValue(gkey, saved); _settings.remove(key)
    try:
        idx_saved = int(saved if saved is not None else default_index)
    except Exception:
        idx_saved = default_index
    if 0 <= idx_saved < len(buttons):
        buttons[idx_saved].setChecked(True)
    for idx, rb in enumerate(buttons):
        rb.toggled.connect(lambda checked, i=idx: checked and _settings.setValue(gkey, i))


def restore_window_geometry(window: QWidget, key: str = "MainWindow"):
    ba = get_value(f"{key}/geometry", None)
    if isinstance(ba, QByteArray):
        window.restoreGeometry(ba)

def save_window_geometry(window: QWidget, key: str = "MainWindow"):
    set_value(f"{key}/geometry", window.saveGeometry())


# ---------- Safe (optional) binders by attribute name ----------
def _getattr_widget(obj: object, name: str, typ=None):
    w = getattr(obj, name, None)
    if typ is None or isinstance(w, typ):
        return w
    return None

def try_bind_line_edit(owner: object, attr: str, key: str, default: str = ""):
    w = _getattr_widget(owner, attr, QLineEdit)
    if w is not None:
        bind_line_edit(w, key, default)

def try_bind_checkbox(owner: object, attr: str, key: str, default: bool = False):
    w = _getattr_widget(owner, attr, QCheckBox)
    if w is not None:
        bind_checkbox(w, key, default)

def try_bind_spinbox(owner: object, attr: str, key: str, default: int = 0):
    w = _getattr_widget(owner, attr, QSpinBox)
    if w is not None:
        bind_spinbox(w, key, default)


def _read_with_fallback_and_migrate(key: str, default):
    path = _current_group_path()
    gkey = _prefixed_with(path, key)
    val = _settings.value(gkey, None)
    if val is None:
        val = _settings.value(key, default)
        if val is not None:
            _settings.setValue(gkey, val)
    return default if val is None else val


# ---------- Bind plain string attributes (no widget) ----------
def bind_attr_string(owner: object, attr: str, key: str, default: str = ""):
    """Restore a plain string attribute from settings and set it on the owner."""
    _path = _current_group_path()
    gkey = _prefixed_with(_path, key)
    v = _settings.value(gkey, None)
    if v is None:
        v = _settings.value(key, None)
        if v is not None:
            _settings.setValue(gkey, v); _settings.remove(key)
    if v is None:
        v = default
    setattr(owner, attr, str(v))

def save_attr_string(owner: object, attr: str, key: str):
    _path = _current_group_path()
    gkey = _prefixed_with(_path, key)
    _settings.setValue(gkey, getattr(owner, attr, ""))
