
from __future__ import annotations
from typing import List, Dict, Tuple
import os, sys, subprocess


from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox, QComboBox,
    QPushButton, QFileDialog, QMessageBox, QProgressDialog
)

from PySide6.QtCore import Qt, QTimer

from smithanatool_qt.settings_bind import (
    group, bind_line_edit, bind_spinbox, bind_attr_string, save_attr_string
)

def _open_in_explorer(path: str):
    try:
        if sys.platform.startswith('win'):
            os.startfile(path)  # type: ignore
        elif sys.platform.startswith('darwin'):
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])
    except Exception:
        pass

def _unique_path(dst: str) -> str:
    """Возвращает уникальный путь: name.png → name (1).png, name (2).png, ..."""
    folder = os.path.dirname(dst) or "."
    stem, ext = os.path.splitext(os.path.basename(dst))
    i = 1
    cand = dst
    while os.path.exists(cand):
        cand = os.path.join(folder, f"{stem} ({i}){ext}")
        i += 1
    return cand

class RenamePanel(QWidget):
    def __init__(self, gallery=None, parent=None):
        super().__init__(parent)
        self._gallery = gallery
        self._undo_stack: List[Dict[str, str]] = []
        self._redo_stack: List[Dict[str, str]] = []


        v = QVBoxLayout(self)
        v.setAlignment(Qt.AlignTop)

        # Шаблон
        row_pattern = QHBoxLayout()
        row_pattern.addWidget(QLabel("Шаблон:"))
        self.edit_pattern = QLineEdit()
        self.edit_pattern.setPlaceholderText("{n} или {stem}_{n}{ext}")
        self.edit_pattern.setText("{n}")
        row_pattern.addWidget(self.edit_pattern, 1)
        v.addLayout(row_pattern)

        # Старт №, Нули
        row_nums = QHBoxLayout()
        row_nums.addWidget(QLabel("Старт №:"))
        self.spin_start = QSpinBox()
        self.spin_start.setRange(0, 99999)

        self.spin_start.setFixedWidth(50)
        self.spin_start.setValue(1)
        row_nums.addWidget(self.spin_start)
        row_nums.addSpacing(12)
        row_nums.addWidget(QLabel("Нули:"))
        self.spin_zeros = QSpinBox(); self.spin_zeros.setRange(1, 6); self.spin_zeros.setValue(2)
        row_nums.addWidget(self.spin_zeros)
        row_nums.addStretch(1)
        v.addLayout(row_nums)

        # Сортировка
        row_sort = QHBoxLayout()
        row_sort.addWidget(QLabel("Сортировка:"))
        self.cmb_order = QComboBox()
        self.cmb_order.addItems(["Как в галерее", "По имени", "По дате"])  # По дате = новые позже
        row_sort.addWidget(self.cmb_order)
        row_sort.addStretch(1)
        v.addLayout(row_sort)


        # Кнопки
        row_btns = QHBoxLayout()
        row_btns.setContentsMargins(0, 8, 0, 0)
        row_btns.addStretch(1)
        self.btn_rename_selected = QPushButton("Переименовать")
        self.btn_pick_files = QPushButton("Выбрать файлы...")
        self.btn_undo = QPushButton("Вернуть")
        self.btn_redo = QPushButton("Вернуть обратно")
        self.btn_redo.setEnabled(False)
        self.btn_undo.setEnabled(False)
        row_btns.addWidget(self.btn_rename_selected)
        row_btns.addWidget(self.btn_pick_files)
        row_btns.addWidget(self.btn_undo)
        row_btns.addWidget(self.btn_redo)
        v.addLayout(row_btns)

        # Подсказка по шаблону
        help_text = (
            "<code>{n}</code> — нумерация с учётом нулей."
        )
        lbl = QLabel(help_text); lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 12px; color: #454545;")
        v.addWidget(lbl)

        # Сигналы
        self.btn_redo.clicked.connect(self._redo_last)
        self.btn_rename_selected.clicked.connect(self._rename_from_gallery)
        self.btn_pick_files.clicked.connect(self._rename_pick_files)
        self.btn_undo.clicked.connect(self._undo_last)
        QTimer.singleShot(0, self._apply_settings_from_ini)

        # --- persist settings to INI ---
        self.edit_pattern.editingFinished.connect(
            lambda: self._save_str_ini("pattern", self.edit_pattern.text().strip())
        )
        self.spin_start.valueChanged.connect(
            lambda v: self._save_int_ini("start", v)
        )
        self.spin_zeros.valueChanged.connect(
            lambda v: self._save_int_ini("zeros", v)
        )
        self.cmb_order.currentIndexChanged.connect(
            lambda v: self._save_int_ini("order", v)
        )

    # ---------- helpers ----------

    def reset_to_defaults(self):
        # дефолты
        default_pattern = "{n}"
        default_start = 1
        default_zeros = 2
        default_order_idx = 0  # "Как в галерее"

        # проставляем без лишних сигналов
        self.edit_pattern.setText(default_pattern)
        self.spin_start.setValue(default_start)
        self.spin_zeros.setValue(default_zeros)
        self.cmb_order.blockSignals(True)
        self.cmb_order.setCurrentIndex(default_order_idx)
        self.cmb_order.blockSignals(False)

        # сохраняем в INI
        self._save_str_ini("pattern", default_pattern)
        self._save_int_ini("start", default_start)
        self._save_int_ini("zeros", default_zeros)
        self._save_int_ini("order", default_order_idx)


    def _refresh_gallery_preserving_order(self):
        gal = self._gallery
        if not gal:
            return
        try:
            lw = getattr(gal, "list", None)  # ожидается QListWidget/QListView
            vsb = lw.verticalScrollBar() if lw and hasattr(lw, "verticalScrollBar") else None
            scroll = vsb.value() if vsb else None

            # запомним выделение по userData (Qt.UserRole)
            selected_keys = []
            if lw and hasattr(lw, "item"):
                for i in range(lw.count()):
                    it = lw.item(i)
                    if it.isSelected():
                        selected_keys.append(it.data(Qt.UserRole))

            # если в галерее есть комбобокс сортировки — запомним индекс
            cmb_sort = getattr(gal, "cmb_sort", None)
            sort_idx = cmb_sort.currentIndex() if cmb_sort and hasattr(cmb_sort, "currentIndex") else None
        except Exception:
            lw = None;
            vsb = None;
            scroll = None;
            selected_keys = [];
            sort_idx = None

        # --- собственно обновление галереи ---
        try:
            if hasattr(gal, "_apply_sort"):
                gal._apply_sort(refresh=True)  # как и раньше, но мы вернём состояние
            elif hasattr(gal, "_refresh_labels"):
                gal._refresh_labels()
        except Exception:
            pass

        # --- восстановление состояния ---
        try:
            if sort_idx is not None and cmb_sort:
                cmb_sort.blockSignals(True)
                cmb_sort.setCurrentIndex(sort_idx)
                cmb_sort.blockSignals(False)

            if lw and selected_keys:
                lw.blockSignals(True)
                lw.clearSelection()
                for i in range(lw.count()):
                    it = lw.item(i)
                    if it.data(Qt.UserRole) in selected_keys:
                        it.setSelected(True)
                lw.blockSignals(False)

            if vsb is not None and scroll is not None:
                vsb.setValue(scroll)
        except Exception:
            pass

    def _apply_settings_from_ini(self):
        with group("RenamePanel"):
            bind_line_edit(self.edit_pattern, "pattern", "{n}")
            bind_spinbox(self.spin_start, "start", 1)
            bind_spinbox(self.spin_zeros, "zeros", 2)
            # ← загрузим сохранённый индекс "order" из INI в теневой атрибут
            bind_attr_string(self, "__order__shadow", "order", "0")

            try:
                idx = int(getattr(self, "__order__shadow", "0"))
            except Exception:
                idx = 0

        # установим выбранный пункт комбобокса
        self.cmb_order.blockSignals(True)
        self.cmb_order.setCurrentIndex(idx)
        self.cmb_order.blockSignals(False)
    def _save_str_ini(self, key: str, value: str):
        try:
            shadow_attr = f"__{key}__shadow"
            setattr(self, shadow_attr, value)
            with group("RenamePanel"):
                save_attr_string(self, shadow_attr, key)
        except Exception:
            pass

    def _save_int_ini(self, key: str, value: int):
        self._save_str_ini(key, str(int(value)))

    def _gather_gallery_paths(self) -> List[str]:
        if not self._gallery:
            return []
        paths = []
        if hasattr(self._gallery, 'selected_files'):
            try:
                paths = list(self._gallery.selected_files())
            except Exception:
                paths = []
        if not paths and hasattr(self._gallery, 'files'):
            try:
                paths = list(self._gallery.files())
            except Exception:
                paths = []
        return [p for p in paths if isinstance(p, str) and p]

    def _build_plan(self, paths: List[str]) -> Tuple[List[Tuple[str, str]], int]:
        pattern = (self.edit_pattern.text() or "{n}")
        if "{n}" not in pattern:
            pattern = pattern + "_{n}"
        start = int(self.spin_start.value())
        pad = int(self.spin_zeros.value())
        order = (self.cmb_order.currentText() or "Как в галерее")

        # Сортировка
        if order == "По имени":
            paths = sorted(paths, key=lambda p: (os.path.dirname(p), os.path.basename(p).lower()))
        elif order == "По дате":
            try:
                paths = sorted(paths, key=lambda p: os.path.getmtime(p))
            except Exception:
                pass

        plan: List[Tuple[str, str]] = []
        seen_targets: set[str] = set()  # имена, уже занятые внутри текущего плана
        i = 0

        for pth in paths:
            folder = os.path.dirname(pth) or "."
            base = os.path.basename(pth)
            stem, ext = os.path.splitext(base)

            nstr = str(start + i).zfill(max(1, pad))
            new_name = pattern.replace("{stem}", stem).replace("{n}", nstr).replace("{ext}", ext or "")

            # Если {ext} не указан в шаблоне и пользователь не дописал расширение вручную — добавим исходное
            if "{ext}" not in pattern:
                root, given_ext = os.path.splitext(new_name)
                if not given_ext:
                    new_name = new_name + (ext or "")

            dst = os.path.join(folder, new_name)

            # Если исходный и целевой совпадают — пропускаем
            if os.path.abspath(dst) == os.path.abspath(pth):
                i += 1
                continue

            # ГАРАНТИЯ уникальности: проверяем и диск, и уже запланированные имена
            # (второе - это то, чего раньше не хватало)
            while dst in seen_targets or os.path.exists(dst):
                dst = _unique_path(dst)

            seen_targets.add(dst)
            plan.append((pth, dst))
            i += 1

        return plan, len(paths)

    def _update_gallery_paths(self, mapping_update: Dict[str, str]):
        try:
            gal = self._gallery
            if gal and hasattr(gal, 'list'):
                lw = gal.list
                for row in range(lw.count()):
                    it = lw.item(row)
                    p = it.data(Qt.UserRole)
                    if p in mapping_update:
                        newp = mapping_update[p]
                        it.setData(Qt.UserRole, newp)
                        it.setText(os.path.basename(newp))
                if hasattr(gal, '_files'):
                    arr = list(getattr(gal, '_files', []))
                    for idx, p in enumerate(arr):
                        if p in mapping_update:
                            arr[idx] = mapping_update[p]
                    gal._files = arr
        except Exception:
            pass

    def _apply_renames(self, plan: List[Tuple[str, str]]) -> Tuple[int, str]:
        if not plan:
            return 0, ""
        dlg = QProgressDialog("Идёт пакетное переименование файлов...", None, 0, len(plan), self)
        dlg.setWindowTitle("Переименование")
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setCancelButton(None)
        dlg.setMinimumDuration(0)
        dlg.show()

        renamed = 0
        mapping_src_to_dst: Dict[str, str] = {}
        mapping_update: Dict[str, str] = {}
        for i, (src_p, dst_p) in enumerate(plan, 1):
            try:
                os.rename(src_p, dst_p)
                renamed += 1
                mapping_src_to_dst[src_p] = dst_p
                mapping_update[src_p] = dst_p
            except Exception:
                pass
            dlg.setValue(i)
            dlg.repaint()

        dlg.close()

        if mapping_src_to_dst:
            inverse = {dst: src for src, dst in mapping_src_to_dst.items()}
            self._undo_stack.append(inverse)
            self.btn_undo.setEnabled(True)

        self._update_gallery_paths(mapping_update)
        # Обновим нумерацию/сортировку в галерее
        try:
            self._refresh_gallery_preserving_order()
        except Exception:
            pass
        out_dir = os.path.dirname(plan[0][1]) if plan else ''

        self._redo_stack.clear()
        if hasattr(self, "btn_redo"):
            self.btn_redo.setEnabled(False)
        return renamed, out_dir

    def _rename_from_gallery(self):
        paths = self._gather_gallery_paths()
        if not paths:
            QMessageBox.warning(self, "Нет выбора", "Выберите файлы во вкладке «Галерея».", parent=self); return
        plan, total = self._build_plan(paths)
        if not plan:
            QMessageBox.information(self, "Переименование", "Файлы уже соответствуют шаблону."); return
        ok, out_dir = self._apply_renames(plan)
        if ok:
            self._done_box(out_dir, f"Переименовано: {ok}")
        else:
            QMessageBox.warning(self, "Ничего не переименовано", "Не удалось переименовать выбранные файлы.", parent=self)

    def _rename_pick_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Выберите файлы для переименования", "", "Все файлы (*.*)")
        if not files:
            return
        plan, total = self._build_plan(files)
        if not plan:
            QMessageBox.information(self, "Переименование", "Файлы уже соответствуют шаблону.", parent=self); return
        ok, out_dir = self._apply_renames(plan)
        if ok:
            self._done_box(out_dir, f"Переименовано: {ok}")
        else:
            QMessageBox.warning(self, "Ничего не переименовано", "Не удалось переименовать выбранные файлы.", parent=self)

    def _undo_last(self):
        if not self._undo_stack:
            return

        # достаём отображение current -> previous
        mapping_curr_to_prev = self._undo_stack.pop()
        items = list(mapping_curr_to_prev.items())

        # подготовим "обратное" отображение для Redo: previous -> current
        redo_map = {prev: curr for (curr, prev) in items}

        # 1) Переносим current во временные файлы (чтобы избежать конфликтов)
        temp_moves: List[Tuple[str, str, str]] = []  # (tmp_path, prev_path, curr_path)
        for curr, prev in items:
            if not os.path.exists(curr):
                continue
            folder = os.path.dirname(curr) or "."
            base = os.path.basename(curr)
            tmp = os.path.join(folder, base + ".undo_tmp")
            idx = 1
            while os.path.exists(tmp):
                tmp = os.path.join(folder, f"{base}.undo_tmp{idx}")
                idx += 1
            try:
                os.rename(curr, tmp)
                temp_moves.append((tmp, prev, curr))
            except Exception:
                pass

        # 2) Переносим временные на место previous
        restored = 0
        mapping_update: Dict[str, str] = {}
        dlg = QProgressDialog("Откат выполняется...", None, 0, len(temp_moves), self)
        dlg.setWindowTitle("Переименование")
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setCancelButton(None)
        dlg.setMinimumDuration(0)
        dlg.show()

        for i, (tmp, prev, curr) in enumerate(temp_moves, 1):
            dest = prev
            if os.path.exists(dest):
                dest = _unique_path(dest)
            try:
                os.rename(tmp, dest)
                restored += 1
                mapping_update[curr] = dest
            except Exception:
                try:
                    os.rename(tmp, curr)
                except Exception:
                    pass
            dlg.setValue(i)
            dlg.repaint()

        dlg.close()

        # обновляем галерею
        self._update_gallery_paths(mapping_update)
        try:
            self._refresh_gallery_preserving_order()
        except Exception:
            pass

        # если удалось восстановить хотя бы что-то
        if restored:
            # пушим карту для Redo
            self._redo_stack.append(redo_map)
            self.btn_redo.setEnabled(True)

            out_dir = os.path.dirname(list(mapping_update.values())[0])
            self._done_box(out_dir, f"Отменено: {restored}")
        else:
            QMessageBox.information(self, "Переименование", "Нечего отменять или не удалось выполнить откат.")

        # обновляем доступность кнопки Undo
        self.btn_undo.setEnabled(bool(self._undo_stack))

    def _done_box(self, out_dir: str, msg: str):
        box = QMessageBox(self)
        box.setWindowTitle("Готово")
        box.setText(msg)
        btn_open = box.addButton("Открыть папку", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is btn_open and out_dir:
            _open_in_explorer(out_dir)

    def _redo_last(self):
        if not self._redo_stack:
            return
        mapping_prev_to_curr = self._redo_stack.pop()  # previous -> current
        items = list(mapping_prev_to_curr.items())

        # 1) Перенос prev во временные, чтобы избежать конфликтов
        temp_moves: List[Tuple[str, str, str]] = []  # (tmp_path, curr_path, prev_path)
        for prev, curr in items:
            if not os.path.exists(prev):
                continue
            folder = os.path.dirname(prev) or "."
            base = os.path.basename(prev)
            tmp = os.path.join(folder, base + ".redo_tmp")
            idx = 1
            while os.path.exists(tmp):
                tmp = os.path.join(folder, f"{base}.redo_tmp{idx}")
                idx += 1
            try:
                os.rename(prev, tmp)
                temp_moves.append((tmp, curr, prev))
            except Exception:
                pass

        # 2) Из временных в нужные «current» (если занято — подобрать уникальное имя)
        restored = 0
        mapping_update: Dict[str, str] = {}
        dlg = QProgressDialog("Повтор выполняется...", None, 0, len(temp_moves), self)
        dlg.setWindowTitle("Переименование")
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setCancelButton(None)
        dlg.setMinimumDuration(0)
        dlg.show()

        for i, (tmp, curr, prev) in enumerate(temp_moves, 1):
            dest = curr
            if os.path.exists(dest):
                dest = _unique_path(dest)
            try:
                os.rename(tmp, dest)
                restored += 1
                mapping_update[prev] = dest  # было prev, стало dest(≈curr)
            except Exception:
                # не удалось — вернём tmp на место prev
                try:
                    os.rename(tmp, prev)
                except Exception:
                    pass
            dlg.setValue(i)
            dlg.repaint()

        dlg.close()

        # Обновить галерею
        self._update_gallery_paths(mapping_update)
        try:
            self._refresh_gallery_preserving_order()
        except Exception:
            pass

        # После успешного Redo добавим обратную операцию обратно в Undo-стек
        if restored:
            undo_map = {v: k for (k, v) in mapping_update.items()}  # current -> previous
            self._undo_stack.append(undo_map)
            self.btn_undo.setEnabled(True)

        # Кнопка "Вернуть обратно" активна, пока есть записи
        self.btn_redo.setEnabled(bool(self._redo_stack))

        if restored:
            out_dir = os.path.dirname(list(mapping_update.values())[0])
            self._done_box(out_dir, f"Повторено: {restored}")
        else:
            QMessageBox.information(self, "Переименование", "Нечего повторять или не удалось выполнить повтор.")
