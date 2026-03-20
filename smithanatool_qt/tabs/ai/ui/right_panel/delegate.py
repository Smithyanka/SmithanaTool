from __future__ import annotations

from PySide6.QtCore import Qt, QSize, QRect, QEvent
from PySide6.QtGui import QColor, QPen, QFontMetrics, QTextOption, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QTextEdit, QFrame
)


class FragmentItemDelegate(QStyledItemDelegate):
    """
    Многострочное отображение и редактирование фрагмента:
    - номер рисуется отдельно;
    - текст переносится по словам;
    - редактор многострочный (QTextEdit);
    - высота строки считается по фактической ширине текста.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.badge_w = 28
        self.h_pad = 8
        self.right_pad = 8
        self.v_pad = 6
        self.min_h = 40
        self._view = parent

        try:
            if self._view is not None and self._view.viewport() is not None:
                self._view.viewport().installEventFilter(self)
        except Exception:
            pass

    # ---------- helpers ----------

    @staticmethod
    def _content_from_display(full: str) -> str:
        full = full or ""
        return full.split(". ", 1)[1] if ". " in full else full

    def _text_rect(self, rect: QRect) -> QRect:
        return rect.adjusted(
            self.badge_w + self.h_pad,
            self.v_pad,
            -self.right_pad,
            -self.v_pad,
        )

    def _wrap_width(self, option: QStyleOptionViewItem) -> int:
        if option.widget is not None:
            width = option.widget.viewport().width()
        else:
            width = option.rect.width()

        return max(80, width - self.badge_w - self.h_pad - self.right_pad - 6)

    def _text_height(self, option: QStyleOptionViewItem, text: str) -> int:
        text = text or " "
        fm = QFontMetrics(option.font)
        flags = int(Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap)
        br = fm.boundingRect(QRect(0, 0, self._wrap_width(option), 100000), flags, text)
        return max(fm.height(), br.height())

    def _editor_height(self, editor: QTextEdit) -> int:
        doc_h = int(editor.document().size().height())
        frame = editor.frameWidth() * 2
        return max(self.min_h - self.v_pad * 2, doc_h + frame)

    def _emit_all_size_hints_changed(self) -> None:
        if self._view is None:
            return
        model = self._view.model()
        if model is None:
            return
        for row in range(model.rowCount()):
            self.sizeHintChanged.emit(model.index(row, 0))

    def _on_editor_text_changed(self, editor: QTextEdit, index) -> None:
        try:
            editor.setFixedHeight(self._editor_height(editor))
            self._sync_editor_vcenter(editor)
        except Exception:
            pass
        self.sizeHintChanged.emit(index)

    # ---------- painting ----------

    def paint(self, painter, option: QStyleOptionViewItem, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        full = index.data(Qt.DisplayRole) or ""
        content = self._content_from_display(full)

        style = opt.widget.style() if opt.widget else QApplication.style()

        # Сначала рисуем фон/selection/focus без текста
        opt.text = ""
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        text_rect = self._text_rect(opt.rect)

        # Бейдж с номером
        badge_rect = QRect(
            opt.rect.left() + 6,
            opt.rect.top() + max(0, (opt.rect.height() - 18) // 2),
            20,
            18,
        )

        painter.save()

        if opt.state & QStyle.State_Selected:
            painter.fillRect(badge_rect, opt.palette.highlight().color().lighter(120))
        else:
            painter.fillRect(badge_rect, QColor(142, 53, 253, 200))

        painter.setPen(QPen(QColor(255, 255, 255)))
        painter.drawText(badge_rect, Qt.AlignCenter, str(index.row() + 1))

        # Текст с переносом
        if opt.state & QStyle.State_Selected:
            painter.setPen(opt.palette.highlightedText().color())
        else:
            painter.setPen(opt.palette.text().color())

        text_h = self._text_height(opt, content)

        draw_rect = QRect(
            text_rect.left(),
            text_rect.top() + max(0, (text_rect.height() - text_h) // 2),
            text_rect.width(),
            text_h,
        )

        painter.drawText(
            draw_rect,
            Qt.AlignLeft | Qt.TextWordWrap,
            content,
        )

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        full = index.data(Qt.DisplayRole) or ""
        content = self._content_from_display(full)

        text_h = self._text_height(opt, content)
        height = max(self.min_h, text_h + self.v_pad * 2 + 4)

        base = super().sizeHint(option, index)
        return QSize(base.width(), height)

    # ---------- editing ----------
    def _sync_editor_vcenter(self, editor: QTextEdit) -> None:
        doc_h = int(editor.document().size().height())
        frame = editor.frameWidth() * 2
        inner_h = max(0, editor.height() - frame)

        free = max(0, inner_h - doc_h)
        top = free // 2
        bottom = free - top

        editor.setViewportMargins(0, top, 0, bottom)

    def createEditor(self, parent, option, index):
        editor = QTextEdit(parent)
        editor.setAcceptRichText(False)
        editor.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        editor.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        editor.setLineWrapMode(QTextEdit.WidgetWidth)
        editor.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)

        editor.setContentsMargins(0, 0, 0, 0)
        editor.document().setDocumentMargin(0)
        editor.setStyleSheet("QTextEdit { padding: 5px; }")

        editor.installEventFilter(self)
        editor.textChanged.connect(
            lambda ed=editor, ix=index: self._on_editor_text_changed(ed, ix)
        )
        return editor

    def setEditorData(self, editor: QTextEdit, index):
        full = index.data(Qt.DisplayRole) or ""
        editor.setPlainText(self._content_from_display(full))
        editor.moveCursor(QTextCursor.End)
        editor.setFixedHeight(self._editor_height(editor))
        self._sync_editor_vcenter(editor)

    def setModelData(self, editor: QTextEdit, model, index):
        content = editor.toPlainText()
        n = index.row() + 1
        model.setData(index, f"{n}. {content}", Qt.EditRole)

    def _editor_rect(self, rect: QRect) -> QRect:
        return rect.adjusted(
            self.badge_w + 2,  # слева почти вплотную к бейджу
            1,  # сверху почти без зазора
            -1,  # справа почти до края
            -1,  # снизу почти до края
        )

    def updateEditorGeometry(self, editor, option, index):
        rect = self._editor_rect(option.rect)
        editor.setGeometry(rect)
        try:
            editor.setFixedHeight(max(rect.height(), self._editor_height(editor)))
            self._sync_editor_vcenter(editor)
        except Exception:
            pass

    # ---------- events ----------

    def eventFilter(self, obj, event):
        # Пересчёт высоты всех строк при изменении ширины списка
        if self._view is not None and obj is self._view.viewport():
            if event.type() == QEvent.Resize:
                self._emit_all_size_hints_changed()

        # Управление многострочным редактором
        if isinstance(obj, QTextEdit):
            if event.type() == QEvent.FocusOut:
                self.commitData.emit(obj)
                self.closeEditor.emit(obj, QStyledItemDelegate.NoHint)
                return False

            if event.type() == QEvent.KeyPress:
                key = event.key()
                mods = event.modifiers()

                # Ctrl+Enter = сохранить и закрыть
                if key in (Qt.Key_Return, Qt.Key_Enter) and mods == Qt.ControlModifier:
                    self.commitData.emit(obj)
                    self.closeEditor.emit(obj, QStyledItemDelegate.NoHint)
                    return True

                # Esc = отмена
                if key == Qt.Key_Escape:
                    self.closeEditor.emit(obj, QStyledItemDelegate.RevertModelCache)
                    return True

        return super().eventFilter(obj, event)