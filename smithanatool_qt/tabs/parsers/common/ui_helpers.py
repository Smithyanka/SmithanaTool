from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QPushButton


def build_reset_footer(owner, target_layout, *, button_text: str = 'Сброс настроек'):
    footer = QHBoxLayout()
    footer.setContentsMargins(0, 8, 15, 0)
    footer.setSpacing(0)
    owner.btn_reset = QPushButton(button_text)
    footer.addStretch(1)
    footer.addWidget(owner.btn_reset)
    target_layout.addLayout(footer)
    return footer
