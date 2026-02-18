from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QStyledItemDelegate, QLineEdit, QStyleOptionViewItem, QStyle


class FragmentItemDelegate(QStyledItemDelegate):
    """
    Рисует номер отдельно, редактирование — только текст без нумерации.
    Также увеличивает высоту строки.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.badge_w = 28
        self.h_pad = 8
        self.min_h = 40

    def paint(self, painter, option: QStyleOptionViewItem, index):
        opt = QStyleOptionViewItem(option)
        full = index.data(Qt.DisplayRole) or ""
        content = full.split(". ", 1)[1] if ". " in full else full

        text_rect = opt.rect.adjusted(self.badge_w + self.h_pad, 0, 0, 0)
        opt.text = ""
        opt.widget.style().drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        opt2 = QStyleOptionViewItem(opt)
        opt2.rect = text_rect
        opt2.text = content
        super().paint(painter, opt2, index)

        num = str(index.row() + 1)
        badge_rect = option.rect.adjusted(6, (option.rect.height() - 18) // 2, 0, 0)
        badge_rect.setSize(QSize(20, 18))

        painter.save()
        if option.state & QStyle.State_Selected:
            painter.fillRect(badge_rect, option.palette.highlight().color().lighter(120))
        else:
            from PySide6.QtGui import QColor, QPen
            painter.fillRect(badge_rect, QColor(255, 193, 7, 200))
            painter.setPen(QPen(Qt.black))
        painter.drawText(badge_rect, Qt.AlignCenter, num)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index):
        base = super().sizeHint(option, index)
        h = max(self.min_h, base.height() + 8)
        return QSize(base.width(), h)

    def createEditor(self, parent, option, index):
        return QLineEdit(parent)

    def setEditorData(self, editor: QLineEdit, index):
        full = index.data(Qt.DisplayRole) or ""
        editor.setText(full.split(". ", 1)[1] if ". " in full else full)

    def setModelData(self, editor: QLineEdit, model, index):
        content = editor.text()
        n = index.row() + 1
        model.setData(index, f"{n}. {content}", Qt.EditRole)
