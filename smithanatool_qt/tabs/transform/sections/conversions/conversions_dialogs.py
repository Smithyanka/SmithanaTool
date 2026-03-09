from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer, QTranslator, QLocale, QLibraryInfo
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QListView,
    QTreeView,
    QAbstractItemView,
    QLineEdit,
    QWidget,
    QSplitter,
    QToolButton,
)

from smithanatool_qt.tabs.common.bind import ini_load_str, ini_save_str


def ensure_qt_ru() -> None:
    """Ставит русскую локаль/переводы Qt (один раз на приложение)."""
    app = QApplication.instance()
    if not app or getattr(app, "_qt_ru_installed", False):
        return

    try:
        QLocale.setDefault(QLocale(QLocale.Russian, QLocale.Russia))
    except Exception:
        pass

    tr_path = QLibraryInfo.path(QLibraryInfo.TranslationsPath)
    installed: list[QTranslator] = []

    # qtbase_ru
    try:
        tr1 = QTranslator(app)
        ok1 = tr1.load(QLocale("ru_RU"), "qtbase", "_", tr_path) or tr1.load("qtbase_ru", tr_path)
        if ok1:
            app.installTranslator(tr1)
            installed.append(tr1)
    except Exception:
        pass

    # qt_ru (иногда не требуется, но не мешает)
    try:
        tr2 = QTranslator(app)
        ok2 = tr2.load(QLocale("ru_RU"), "qt", "_", tr_path) or tr2.load("qt_ru", tr_path)
        if ok2:
            app.installTranslator(tr2)
            installed.append(tr2)
    except Exception:
        pass

    # важно держать ссылки, иначе Python GC может выгрузить переводчик
    app._qt_ru_translators = installed
    app._qt_ru_installed = True


def ask_open_directories_multi(parent: QWidget, title: str, section: str, ini_key: str) -> list[str]:
    start_dir = ini_load_str(section, ini_key, os.path.expanduser("~"))

    dlg = QFileDialog(parent, title)
    dlg.setFileMode(QFileDialog.Directory)
    dlg.setOption(QFileDialog.ShowDirsOnly, True)
    dlg.setOption(QFileDialog.DontUseNativeDialog, True)  # для мультивыбора папок
    dlg.setDirectory(start_dir)

    # Разрешаем расширенный выбор в списке/дереве (кроме sidebar)
    for v in dlg.findChildren(QListView) + dlg.findChildren(QTreeView):
        if v.objectName() != "sidebar":
            v.setSelectionMode(QAbstractItemView.ExtendedSelection)

    # Скрыть левую боковую панель (sidebar) и схлопнуть сплиттер
    try:
        for side in dlg.findChildren(QListView, "sidebar"):
            side.hide()
        for w in dlg.findChildren(QWidget):
            if w.objectName() == "sidebar":
                w.hide()
        for sp in dlg.findChildren(QSplitter):
            sizes = sp.sizes()
            if len(sizes) >= 2:
                sp.setSizes([0] + sizes[1:])
    except Exception:
        pass

    # ---------- СКРЫТЬ кнопку «Создать папку» ----------
    try:
        # Спрятать кнопку на тулбаре
        for b in dlg.findChildren(QToolButton):
            tt = (b.toolTip() or "").lower()
            tx = (b.text() or "").lower()
            if ("создать папку" in tt) or ("создать папку" in tx) or ("new folder" in tt) or ("new folder" in tx):
                b.hide()
        # Отключить одноимённые действия (на случай хоткеев)
        for act in dlg.findChildren(QAction):
            txt = (act.text() or "").lower().replace("&", "")
            ttp = (act.toolTip() or "").lower()
            if ("создать папку" in txt) or ("создать папку" in ttp) or ("new folder" in txt) or ("new folder" in ttp):
                act.setEnabled(False)
                act.setVisible(False)
    except Exception:
        pass
    # ---------------------------------------------------

    # --- Автопереход по полю «Каталог» через 300 мс ---
    try:
        # В ненативном диалоге у поля обычно objectName == "fileNameEdit"
        dir_edit = dlg.findChild(QLineEdit, "fileNameEdit")
        if dir_edit is None:
            edits = [e for e in dlg.findChildren(QLineEdit) if e.isVisible()]
            if edits:
                dir_edit = sorted(edits, key=lambda e: e.geometry().y())[-1]

        if dir_edit is not None:
            nav_timer = QTimer(dlg)
            nav_timer.setInterval(300)
            nav_timer.setSingleShot(True)

            def _navigate():
                raw = (dir_edit.text() or "").strip().strip('"')
                if not raw:
                    return
                # Абсолютный или относительный путь
                path = raw
                try:
                    cur = dlg.directory().absolutePath()
                except Exception:
                    cur = start_dir
                if not os.path.isabs(path):
                    path = os.path.join(cur, raw)
                if os.path.isdir(path):
                    try:
                        dlg.setDirectory(path)  # переходим, но НЕ выделяем
                    except Exception:
                        pass

            dir_edit.textEdited.connect(lambda _=None: nav_timer.start())
            nav_timer.timeout.connect(_navigate)
    except Exception:
        pass
    # --- конец автоперехода ---

    if dlg.exec() == QFileDialog.Accepted:
        paths = [p for p in dlg.selectedFiles() if os.path.isdir(p)]
        if paths:
            try:
                common = os.path.commonpath(paths)
            except Exception:
                common = os.path.dirname(paths[0])
            ini_save_str(section, ini_key, common)
        return paths
    return []


def ask_out_dir(parent: QWidget, title: str, section: str, ini_key: str) -> str | None:
    start_dir = ini_load_str(section, ini_key, os.path.expanduser("~"))
    d = QFileDialog.getExistingDirectory(parent, title, start_dir)
    if d:
        ini_save_str(section, ini_key, d)
    return d or None


def ask_open_files(parent: QWidget, title: str, section: str, ini_key: str, filter_str: str) -> list[str]:
    start_dir = ini_load_str(section, ini_key, os.path.expanduser("~"))
    files, _ = QFileDialog.getOpenFileNames(parent, title, start_dir, filter_str)
    if files:
        ini_save_str(section, ini_key, os.path.dirname(files[0]))
    return files


def ask_save_file(parent: QWidget, title: str, section: str, ini_key: str, default_name: str, filter_str: str) -> str | None:
    start_dir = ini_load_str(section, ini_key, os.path.expanduser("~"))
    start_path = os.path.join(start_dir, default_name)
    path, _ = QFileDialog.getSaveFileName(parent, title, start_path, filter_str)
    if path:
        ini_save_str(section, ini_key, os.path.dirname(path))
    return path or None
