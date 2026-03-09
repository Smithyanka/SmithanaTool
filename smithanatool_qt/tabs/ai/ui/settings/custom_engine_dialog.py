from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QComboBox,
    QLabel,
)


class CustomEngineDialog(QDialog):
    """Модальное окно добавления/редактирования кастомного OCR-движка.

    Возвращает dict:
      - name: str
      - kind: str (openai_compat | anthropic | gemini_native | azure_openai)
      - provider: str (base_url / endpoint)
      - models: list[str] (model_id / deployment-id)
      - extra: str (сырой JSON)
    """

    KIND_ITEMS = [
        ("OpenAI-compatible", "openai_compat"),
        ("Anthropic (Claude)", "anthropic"),
        ("Gemini API (native)", "gemini_native"),
        ("Azure OpenAI", "azure_openai"),
    ]

    def __init__(self, parent=None, title: str = "Добавить движок", initial: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(560)

        # Валидация: подсветка пустых обязательных полей.
        # Extra(JSON) НЕ обязателен (пустота не считается ошибкой).
        self._validation_active = False


        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        root.addLayout(form)

        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("Например: Мой движок")
        form.addRow("Название:", self.ed_name)

        self.ed_name.textChanged.connect(lambda _=None: self._validate_live())

        self.cmb_kind = QComboBox()
        for title_k, kind_k in self.KIND_ITEMS:
            self.cmb_kind.addItem(title_k, kind_k)
        form.addRow("Тип API:", self.cmb_kind)

        self.ed_provider = QLineEdit()
        form.addRow("Endpoint / base_url:", self.ed_provider)

        self.ed_provider.textChanged.connect(lambda _=None: self._validate_live())

        # Models block
        models_box = QWidget()
        vb = QVBoxLayout(models_box)
        vb.setContentsMargins(0, 0, 0, 0)
        vb.setSpacing(6)

        self._models_rows: list[QLineEdit] = []
        self._model_row_widgets: list[QWidget] = []
        self._model_del_btns: list[QPushButton] = []
        self._models_placeholder = ""

        self.models_container = QVBoxLayout()
        self.models_container.setContentsMargins(0, 0, 0, 0)
        self.models_container.setSpacing(6)
        vb.addLayout(self.models_container)

        # Add button (single, below list)
        add_row = QHBoxLayout()
        add_row.setContentsMargins(0, 0, 0, 0)
        add_row.setSpacing(6)

        self.btn_add_model = QPushButton("+")
        self.btn_add_model.setFixedWidth(27)
        self.btn_add_model.setFixedHeight(27)
        self.btn_add_model.setToolTip("Добавить модель")

        add_row.addWidget(self.btn_add_model, 0, Qt.AlignLeft)
        add_row.addStretch(1)
        vb.addLayout(add_row)

        self.btn_add_model.clicked.connect(self._add_model_row)

        form.addRow("Модели:", models_box)

        self.ed_extra = QPlainTextEdit()
        self.ed_extra.setPlaceholderText(
            "Опционально: JSON с доп. настройками.\n"
            "Примеры:\n"
            '  {"path": "/chat/completions"}  # openai_compat\n'
            '  {"anthropic_version": "2023-06-01"}  # anthropic\n'
            '  {"api_version": "2024-10-21"}  # azure_openai\n'
        )
        self.ed_extra.setMinimumHeight(110)
        form.addRow("Extra (JSON):", self.ed_extra)

        self.cmb_kind.currentIndexChanged.connect(self._refresh_placeholders)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        # Prefill (edit mode)
        if initial:
            try:
                self.ed_name.setText(str(initial.get("name") or ""))
                self._set_kind(str(initial.get("kind") or "openai_compat"))
                self._refresh_placeholders()
                self.ed_provider.setText(str(initial.get("provider") or ""))

                self._set_models(initial.get("models") or [])

                extra = initial.get("extra") or {}
                if isinstance(extra, dict) and extra:
                    self.ed_extra.setPlainText(json.dumps(extra, ensure_ascii=False, indent=2))
                elif isinstance(extra, str) and extra.strip():
                    self.ed_extra.setPlainText(extra.strip())

                self.ed_name.selectAll()
            except Exception:
                pass
        else:
            self._refresh_placeholders()
            self._add_model_row()

        # На старте ошибок не показываем.
        self._clear_all_errors()

    def _set_kind(self, kind: str) -> None:
        kind = (kind or "openai_compat").strip()
        for i in range(self.cmb_kind.count()):
            if str(self.cmb_kind.itemData(i) or "") == kind:
                self.cmb_kind.setCurrentIndex(i)
                return

    def _refresh_placeholders(self):
        kind = str(self.cmb_kind.currentData() or "openai_compat")

        if kind == "openai_compat":
            self.ed_provider.setPlaceholderText("https://routerai.ru/api/v1")
            self._models_placeholder = "gpt-4o-mini"
        elif kind == "anthropic":
            self.ed_provider.setPlaceholderText("https://api.anthropic.com")
            self._models_placeholder = "claude-3-5-sonnet-20240620"
        elif kind == "gemini_native":
            self.ed_provider.setPlaceholderText("https://generativelanguage.googleapis.com")
            self._models_placeholder = "gemini-2.0-flash"
        elif kind == "azure_openai":
            self.ed_provider.setPlaceholderText("https://<resource>.openai.azure.com")
            self._models_placeholder = "deployment-name"
        else:
            self.ed_provider.setPlaceholderText("")
            self._models_placeholder = "model"

        # update placeholders for existing rows
        for ed in self._models_rows:
            if not ed.text().strip():
                ed.setPlaceholderText(self._models_placeholder)

    def _add_model_row(self):
        row = QWidget()
        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)

        ed = QLineEdit()
        ed.setPlaceholderText(self._models_placeholder or "model")
        hl.addWidget(ed, 1)

        # only delete button per row (as in your sketch)
        btn_del = QPushButton("-")  # обычный '-', не '−' (может быть невидим в шрифте)
        btn_del.setFixedWidth(27)
        btn_del.setFixedHeight(27)
        btn_del.setToolTip("Удалить модель")
        hl.addWidget(btn_del)

        self.models_container.addWidget(row)

        self._models_rows.append(ed)
        self._model_row_widgets.append(row)
        self._model_del_btns.append(btn_del)  # add_btns больше не нужны

        btn_del.clicked.connect(lambda: self._remove_model_row(row))

        ed.textChanged.connect(lambda _=None: self._validate_live())

    def _remove_model_row(self, row_widget: QWidget):
        if row_widget not in self._model_row_widgets:
            return

        if len(self._model_row_widgets) <= 1:
            # оставляем минимум одну строку
            try:
                idx = self._model_row_widgets.index(row_widget)
                self._models_rows[idx].clear()
            except Exception:
                pass
            return

        idx = self._model_row_widgets.index(row_widget)

        # remove widgets
        ed = self._models_rows.pop(idx)
        row = self._model_row_widgets.pop(idx)
        self._model_del_btns.pop(idx)

        try:
            ed.deleteLater()
        except Exception:
            pass

        try:
            row.setParent(None)
            row.deleteLater()
        except Exception:
            pass

        self._validate_live()

    def _clear_models(self):
        for w in list(self._model_row_widgets):
            try:
                w.setParent(None)
                w.deleteLater()
            except Exception:
                pass
        self._models_rows.clear()
        self._model_row_widgets.clear()
        self._model_del_btns.clear()

    def _set_models(self, models):
        self._clear_models()

        models = list(models or [])
        if isinstance(models, str):
            models = [models]

        models = [str(m).strip() for m in models if str(m).strip()]
        if not models:
            self._add_model_row()
            return

        for m in models:
            self._add_model_row()
            self._models_rows[-1].setText(str(m))

        self._validate_live()

    # ------------------------
    # Validation (red highlight)
    # ------------------------

    def _required_edits(self) -> list[QLineEdit]:
        """Список обязательных полей (Extra сюда не входит)."""
        return [self.ed_name, self.ed_provider, *list(self._models_rows or [])]

    @staticmethod
    def _set_error_flag(w: QWidget, is_error: bool) -> None:
        try:
            w.setProperty("error", "true" if is_error else "false")
            # обновить стиль для dynamic property
            st = w.style()
            st.unpolish(w)
            st.polish(w)
            w.update()
        except Exception:
            pass

    def _clear_all_errors(self) -> None:
        for ed in self._required_edits():
            self._set_error_flag(ed, False)

    def _validate_live(self) -> None:
        """Если пользователь уже нажимал OK — обновляем подсветку по мере ввода."""
        if not self._validation_active:
            return
        self._validate_required(mark_only=True)

    def _validate_required(self, *, mark_only: bool) -> bool:
        """Проверяет обязательные поля и подсвечивает пустые красным.

        Returns:
            True если все обязательные поля заполнены.
        """

        first_bad: QWidget | None = None
        ok = True

        for ed in self._required_edits():
            empty = not (ed.text() or "").strip()
            self._set_error_flag(ed, empty)
            if empty:
                ok = False
                if first_bad is None:
                    first_bad = ed

        if (not ok) and (not mark_only) and first_bad is not None:
            try:
                first_bad.setFocus()
            except Exception:
                pass
        return ok

    def accept(self) -> None:
        # Активируем валидацию только после первой попытки сохранить.
        self._validation_active = True

        if not self._validate_required(mark_only=False):
            return
        super().accept()

    def get_value(self) -> dict:
        name = (self.ed_name.text() or "").strip()
        kind = str(self.cmb_kind.currentData() or "openai_compat")
        provider = (self.ed_provider.text() or "").strip()
        models = [(e.text() or "").strip() for e in self._models_rows]
        models = [m for m in models if m]
        extra = (self.ed_extra.toPlainText() or "").strip()
        return {"name": name, "kind": kind, "provider": provider, "models": models, "extra": extra}
