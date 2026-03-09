from __future__ import annotations

import importlib
import time
from typing import Callable, Dict, Iterable, Optional, Tuple

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QTabWidget, QWidget

from smithanatool_qt.settings_bind import group, get_value, set_value


TabSpec = Tuple[str, str, str, str]
# (instance_attr_name, module_path, class_name, title)


class TabManager:
    def __init__(
        self,
        owner: object,
        tabs: QTabWidget,
        tab_specs: Dict[str, TabSpec],
        show_loading: Optional[Callable[[str], None]] = None,
        hide_loading: Optional[Callable[[], None]] = None,
        restore_widget_state: Optional[Callable[[QWidget], None]] = None,
    ):
        self.owner = owner
        self.tabs = tabs
        self.tab_specs = tab_specs
        self._show_loading = show_loading or (lambda _text="": None)
        self._hide_loading = hide_loading or (lambda: None)
        self._restore_widget_state = restore_widget_state or (lambda _w: None)

        self._startup_realized = False
        self._in_realize = False

    # -------- settings helpers --------

    def tab_enabled(self, key: str, default: bool = True) -> bool:
        with group("MainWindow"):
            with group("Tabs"):
                return bool(get_value(key, default, typ=bool))

    def set_tab_enabled(self, key: str, enabled: bool) -> None:
        with group("MainWindow"):
            with group("Tabs"):
                set_value(key, bool(enabled))

        self.tabs.blockSignals(True)
        try:
            self._ensure_tab_enabled(key, enabled)
            self._reorder_tabs_to_spec()
        finally:
            self.tabs.blockSignals(False)

        QTimer.singleShot(0, self._realize_current_if_needed)

    def _realize_current_if_needed(self) -> None:
        if self._in_realize:
            return
        idx = self.tabs.currentIndex()
        if idx < 0:
            return
        w = self.tabs.widget(idx)
        if w is None:
            return
        key = w.property("tab_key")

        if isinstance(key, str):
            self.realize_tab_async(key)

    # -------- public actions --------

    def apply_tabs_from_settings(self) -> None:
        self.tabs.blockSignals(True)
        try:
            for key in self.tab_specs:
                enabled = self.tab_enabled(key, True)
                self._ensure_tab_enabled(key, enabled)

            self._reorder_tabs_to_spec()
        finally:
            self.tabs.blockSignals(False)

    def realize_active_tab(self, sync: bool = False) -> None:
        """
        Realize current tab. If sync=True, instantiate immediately (before show),
        so first render is not an empty placeholder.
        """
        idx = self.tabs.currentIndex()
        if idx < 0:
            return
        w = self.tabs.widget(idx)
        if w is None:
            return
        key = w.property("tab_key")
        if not isinstance(key, str):
            return

        self._startup_realized = True
        if sync:
            self.realize_tab_sync(key)
        else:
            self.realize_tab_async(key)

    def realize_active_tab_later(self) -> None:
        if self._startup_realized:
            return
        # async realize on first show if sync wasn't called
        self.realize_active_tab(sync=False)

    def on_current_tab_changed(self, idx: int) -> None:
        if self._in_realize or idx is None or idx < 0:
            return
        w = self.tabs.widget(idx)
        if w is None:
            return
        key = w.property("tab_key")
        if isinstance(key, str):
            self.realize_tab_async(key)

    def iter_realized_tabs(self) -> Iterable[QWidget]:
        for _key, (attr, _m, _c, _t) in self.tab_specs.items():
            w = getattr(self.owner, attr, None)
            if w is not None and w.property("realized") is True:
                yield w

    # -------- realize impl --------

    def realize_tab_async(self, key: str) -> None:
        if self._in_realize:
            return
        if self._is_realized(key):
            return

        try:
            _attr, _module_path, _class_name, title = self.tab_specs[key]
        except Exception:
            title = "вкладки…"

        self._in_realize = True
        self._show_loading(f"Открываю «{title}»…")

        def _do_realize():
            try:
                self._realize_into_tabs(key)
            finally:
                self._hide_loading()
                self._in_realize = False

        QTimer.singleShot(0, _do_realize)

    def realize_tab_sync(self, key: str) -> None:
        """
        Synchronous realize (useful before show()).
        """
        if self._in_realize:
            return
        if self._is_realized(key):
            return

        self._in_realize = True
        try:
            self._realize_into_tabs(key)
        finally:
            self._in_realize = False

    def _is_realized(self, key: str) -> bool:
        try:
            attr, _m, _c, _t = self.tab_specs[key]
        except Exception:
            return False
        w = getattr(self.owner, attr, None)
        return w is not None and w.property("realized") is True

    def _realize_into_tabs(self, key: str) -> None:

        try:
            attr, module_path, class_name, title = self.tab_specs[key]
        except Exception:
            return

        current = getattr(self.owner, attr, None)
        if current is not None and current.property("realized") is True:
            return

        # найти индекс заглушки
        ph = getattr(self.owner, attr, None)
        idx = -1
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if w is ph or (w is not None and w.property("tab_key") == key):
                idx = i
                break
        if idx == -1:
            return

        t0 = time.perf_counter()
        module = importlib.import_module(module_path)
        t1 = time.perf_counter()

        cls = getattr(module, class_name)
        inst = cls(self.owner)
        t2 = time.perf_counter()

        print(f"[startup] {key}: import={t1 - t0:.3f}s init={t2 - t1:.3f}s total={t2 - t0:.3f}s")

        inst.setProperty("tab_key", key)
        inst.setProperty("realized", True)

        try:
            self._restore_widget_state(inst)
        except Exception:
            pass

        self.tabs.blockSignals(True)
        try:
            self.tabs.removeTab(idx)
            self.tabs.insertTab(idx, inst, title)
            self.tabs.setCurrentIndex(idx)
        finally:
            self.tabs.blockSignals(False)

        setattr(self.owner, attr, inst)

    # -------- internals --------

    def _add_lazy_tab(self, key: str, title: str) -> None:
        placeholder = QWidget()
        placeholder.setProperty("tab_key", key)
        placeholder.setProperty("realized", False)

        attr, _module, _cls, _title = self.tab_specs[key]
        setattr(self.owner, attr, placeholder)
        self.tabs.addTab(placeholder, title)

    def _ensure_tab_enabled(self, key: str, enable: bool) -> None:
        attr, _module_path, _class_name, title = self.tab_specs[key]
        current = getattr(self.owner, attr, None)

        if enable and current is None:
            self._add_lazy_tab(key, title)
            return

        if not enable and current is not None:
            idx = self.tabs.indexOf(current)
            if idx != -1:
                self.tabs.removeTab(idx)
            current.deleteLater()
            setattr(self.owner, attr, None)

    def _reorder_tabs_to_spec(self) -> None:
        desired = []
        for _key, (attr, _m, _c, title) in self.tab_specs.items():
            w = getattr(self.owner, attr, None)
            if w is not None:
                desired.append((attr, w, title))

        self.tabs.blockSignals(True)
        try:
            for target_index, (_attr, w, title) in enumerate(desired):
                cur_index = self.tabs.indexOf(w)
                if cur_index == -1:
                    self.tabs.insertTab(target_index, w, title)
                elif cur_index != target_index:
                    self.tabs.removeTab(cur_index)
                    self.tabs.insertTab(target_index, w, title)
        finally:
            self.tabs.blockSignals(False)
