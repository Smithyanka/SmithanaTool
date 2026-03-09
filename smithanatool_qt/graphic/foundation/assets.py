from __future__ import annotations

from pathlib import Path
import sys
import json
from typing import Optional, Tuple, Dict, Iterable, Any

from PySide6.QtCore import QSize, QFile, Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPalette

from PySide6.QtWidgets import QWidget, QFrame, QApplication

try:
    # Если QtSvg недоступен, SVG-тонирование будет отключено (иконка вернётся как есть).
    from PySide6.QtSvg import QSvgRenderer  # type: ignore
except Exception:  # pragma: no cover
    QSvgRenderer = None  # type: ignore


def asset_path(*parts: str) -> Path:
    """
    Возвращает корректный путь к файлам из папки assets:
    - DEV: <package_root>/assets/...
    - EXE (PyInstaller): <_MEIPASS>/assets/... или рядом с exe (если так упаковали)

    Примечание:
    Если используешь .qrc, файловая система может вообще не использоваться.
    """
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    else:
        base = Path(__file__).resolve().parents[2]  # корень пакета smithanatool_qt
    return base / "assets" / Path(*parts)


# -----------------------------------------------------------------------------
# Обычные иконки (без перекрашивания)
# -----------------------------------------------------------------------------
DEFAULT_ICON_SIZE = QSize(16, 16)

# key: (path, w, h)
_icon_cache: Dict[Tuple[str, int, int], QIcon] = {}

# key: (path, w, h, rgba, dpr100)
_tinted_icon_cache: Dict[Tuple[str, int, int, int, int], QIcon] = {}

# key: (path, w, h, rgba_norm, rgba_dis, opacity100, dpr100)
_tinted_icon_disabled_cache: Dict[Tuple[str, int, int, int, int, int, int], QIcon] = {}

_THEME_ICON_DATA_PROP = "_smithana_themed_icon"


def _build_icon(path: str, size: QSize) -> QIcon:
    icon_obj = QIcon()
    icon_obj.addFile(path, size)
    return icon_obj


def _path_exists(path: str) -> bool:
    if path.startswith(":/"):
        return QFile.exists(path)
    return Path(path).exists()


def _try_icon(path: str, size: QSize) -> Optional[QIcon]:
    key = (path, size.width(), size.height())
    cached = _icon_cache.get(key)
    if cached is not None:
        return cached if not cached.isNull() else None

    if not _path_exists(path):
        _icon_cache[key] = QIcon()  # кешируем "пусто"
        return None

    icon_obj = _build_icon(path, size)
    _icon_cache[key] = icon_obj
    return icon_obj if not icon_obj.isNull() else None


def _iter_icon_candidates(name: str) -> Iterable[str]:
    if name.startswith(":/"):
        yield name
        return

    # Сначала ресурсы (.qrc)
    yield f":/assets/icons/{name}"
    yield f":/icons/{name}"

    # Потом файловая система
    yield str(asset_path("icons", name))


def _resolve_icon_path(*names: str) -> Optional[str]:
    for name in names:
        for path in _iter_icon_candidates(name):
            if _path_exists(path):
                return path
    return None


def icon_from_file(
    widget: Optional[QWidget],
    file_path: Path,
    *,
    size: QSize = DEFAULT_ICON_SIZE,
) -> QIcon:
    _ = (widget)
    found = _try_icon(str(file_path), size)
    return found or QIcon()


def icon(
    widget: Optional[QWidget],
    *names: str,
    size: QSize = DEFAULT_ICON_SIZE,
) -> QIcon:
    _ = (widget)

    for name in names:
        for path in _iter_icon_candidates(name):
            found = _try_icon(path, size)
            if found is not None:
                return found

    return QIcon()


def set_icon(
    target: Any,
    *names: str,
    size: QSize = DEFAULT_ICON_SIZE,
) -> None:
    """
    Единый способ поставить "обычную" иконку (как есть, без перекрашивания):
      - сам выбирает первый существующий файл/ресурс из списка names
      - ставит icon + iconSize (если доступно)
    """
    try:
        target.setIcon(icon(target if isinstance(target, QWidget) else None, *names, size=size))
        if hasattr(target, "setIconSize"):
            target.setIconSize(size)
    except Exception:
        return


# -----------------------------------------------------------------------------
# Themed / tinted иконки (перекрашиваются под палитру → светлая/тёмная тема)
# -----------------------------------------------------------------------------
def _palette_color(widget: Optional[QWidget], role: str, *, disabled: bool = False) -> QColor:
    role = (role or "buttonText").strip().lower()

    role_map = {
        "buttontext": QPalette.ButtonText,
        "windowtext": QPalette.WindowText,
        "text": QPalette.Text,
        "highlight": QPalette.Highlight,
        "accent": QPalette.Highlight,
        "link": QPalette.Link,
    }
    qt_role = role_map.get(role, QPalette.ButtonText)

    pal = QApplication.palette()  # вместо widget.palette()
    if disabled:
        return pal.color(QPalette.Disabled, qt_role)
    return pal.color(QPalette.Active, qt_role)


def _render_base_pixmap(path: str, size: QSize, dpr: float) -> QPixmap:
    w = max(1, int(size.width() * dpr))
    h = max(1, int(size.height() * dpr))

    if path.lower().endswith(".svg") and QSvgRenderer is not None:
        renderer = QSvgRenderer(path)
        if not renderer.isValid():
            return QPixmap()
        pix = QPixmap(w, h)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        renderer.render(p)
        p.end()
        pix.setDevicePixelRatio(dpr)
        return pix

    pix = QPixmap(path)
    if pix.isNull():
        return pix

    pix = pix.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    pix.setDevicePixelRatio(dpr)
    return pix


def _tint_pixmap(src: QPixmap, color: QColor) -> QPixmap:
    if src.isNull():
        return src

    dpr = src.devicePixelRatioF() if hasattr(src, "devicePixelRatioF") else 1.0
    out = QPixmap(src.size())
    out.fill(Qt.transparent)
    out.setDevicePixelRatio(dpr)

    p = QPainter(out)
    p.drawPixmap(0, 0, src)
    p.setCompositionMode(QPainter.CompositionMode_SourceIn)
    p.fillRect(out.rect(), color)
    p.end()
    return out


def tinted_icon(
    widget: Optional[QWidget],
    *names: str,
    size: QSize = DEFAULT_ICON_SIZE,
    role: str = "buttonText",
    color_hex: Optional[str] = None,
) -> QIcon:
    """
    Возвращает перекрашенную иконку под текущую палитру.
    Лучше всего работает с монохромными SVG/PNG (силуэты/обводки).
    """
    path = _resolve_icon_path(*names)
    if not path:
        return QIcon()

    if path.lower().endswith(".svg") and QSvgRenderer is None:
        # QtSvg нет → возвращаем обычную иконку
        return icon(widget, *names, size=size)

    if color_hex:
        color = QColor(color_hex)
    else:
        color = _palette_color(widget, role, disabled=False)

    dpr = 1.0
    if widget is not None and hasattr(widget, "devicePixelRatioF"):
        try:
            dpr = float(widget.devicePixelRatioF())
        except Exception:
            dpr = 1.0

    key = (path, size.width(), size.height(), int(color.rgba()), int(round(dpr * 100)))
    cached = _tinted_icon_cache.get(key)
    if cached is not None:
        return cached if not cached.isNull() else QIcon()

    base_pix = _render_base_pixmap(path, size, dpr)
    if base_pix.isNull():
        _tinted_icon_cache[key] = QIcon()
        return QIcon()

    out_pix = _tint_pixmap(base_pix, color)
    icon_obj = QIcon(out_pix)
    _tinted_icon_cache[key] = icon_obj
    return icon_obj


def themed_icon_with_disabled(
    widget: Optional[QWidget],
    *names: str,
    size: QSize = DEFAULT_ICON_SIZE,
    role: str = "buttonText",
    disabled_opacity: float = 0.45,
    color_hex: Optional[str] = None,
) -> QIcon:
    """
    Themed-иконка с нормальным + disabled состоянием.
    Disabled берётся из palette(Disabled, role) и дополнительно ослабляется opacity.
    """
    path = _resolve_icon_path(*names)
    if not path:
        return QIcon()

    if path.lower().endswith(".svg") and QSvgRenderer is None:
        # QtSvg нет → fallback без перекрашивания
        return icon(widget, *names, size=size)

    if color_hex:
        col_norm = QColor(color_hex)
    else:
        col_norm = _palette_color(widget, role, disabled=False)

    col_dis = _palette_color(widget, role, disabled=True)
    col_dis = QColor(col_dis)
    try:
        col_dis.setAlphaF(float(disabled_opacity))
    except Exception:
        col_dis.setAlphaF(0.45)

    dpr = 1.0
    if widget is not None and hasattr(widget, "devicePixelRatioF"):
        try:
            dpr = float(widget.devicePixelRatioF())
        except Exception:
            dpr = 1.0

    key = (
        path,
        size.width(),
        size.height(),
        int(col_norm.rgba()),
        int(col_dis.rgba()),
        int(round(float(disabled_opacity) * 100)),
        int(round(dpr * 100)),
    )
    cached = _tinted_icon_disabled_cache.get(key)
    if cached is not None:
        return cached if not cached.isNull() else QIcon()

    base_pix = _render_base_pixmap(path, size, dpr)
    if base_pix.isNull():
        _tinted_icon_disabled_cache[key] = QIcon()
        return QIcon()

    pm_norm = _tint_pixmap(base_pix, col_norm)
    pm_dis = _tint_pixmap(base_pix, col_dis)

    out = QIcon()
    out.addPixmap(pm_norm, QIcon.Normal, QIcon.Off)
    out.addPixmap(pm_dis, QIcon.Disabled, QIcon.Off)

    _tinted_icon_disabled_cache[key] = out
    return out


def set_themed_icon(
    target: Any,
    *names: str,
    size: QSize = DEFAULT_ICON_SIZE,
    role: str = "buttonText",
    disabled_opacity: float = 0.45,
) -> None:
    data = {
        "names": list(names),
        "w": size.width(),
        "h": size.height(),
        "role": role,
        "disabled": True,
    }

    try:
        target.setProperty(_THEME_ICON_DATA_PROP, json.dumps(data, ensure_ascii=False))
    except Exception:
        pass

    try:
        w = target if isinstance(target, QWidget) else None
        ico = themed_icon_with_disabled(w, *names, size=size, role=role, disabled_opacity=disabled_opacity)

        target.setIcon(ico)
        if hasattr(target, "setIconSize"):
            target.setIconSize(size)
    except Exception:
        return



def refresh_themed_icons(root: QWidget) -> None:
    """
    Переустанавливает все зарегистрированные themed-иконки под текущую палитру.

    Вызывать после смены темы (после apply_theme/app.setPalette/app.setStyleSheet).
    """
    if root is None:
        return

    widgets = [root] + list(root.findChildren(QWidget))
    for w in widgets:
        raw = w.property(_THEME_ICON_DATA_PROP)
        if not raw:
            continue
        try:
            data = json.loads(raw)
            names = data.get("names") or []
            size = QSize(int(data.get("w", DEFAULT_ICON_SIZE.width())), int(data.get("h", DEFAULT_ICON_SIZE.height())))
            role = str(data.get("role", "buttonText"))
            if bool(data.get("disabled", False)):
                disabled_opacity = float(data.get("disabled_opacity", 0.45))
                w.setIcon(themed_icon_with_disabled(w, *names, size=size, role=role, disabled_opacity=disabled_opacity))
            else:
                w.setIcon(tinted_icon(w, *names, size=size, role=role))
            if hasattr(w, "setIconSize"):
                w.setIconSize(size)
        except Exception:
            continue


def clear_icon_cache() -> None:
    """Сбрасывает кеш иконок (и обычных, и themed)."""
    _icon_cache.clear()
    _tinted_icon_cache.clear()
    _tinted_icon_disabled_cache.clear()


def make_sep(parent: QWidget) -> QFrame:
    sep = QFrame(parent)
    sep.setObjectName("makeSep")
    sep.setFixedHeight(1)
    return sep