from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTextBrowser, QFrame, QHBoxLayout
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette

def _card(title_html: str, body_widget: QWidget) -> QFrame:
    card = QFrame()
    card.setObjectName("card")
    v = QVBoxLayout(card); v.setContentsMargins(12, 10, 12, 12); v.setSpacing(8)

    title = QLabel(title_html)
    title.setObjectName("cardTitle")
    title.setTextFormat(Qt.RichText)
    title.setWordWrap(True)

    v.addWidget(title)
    v.addWidget(body_widget)
    return card

class InfoTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("keep_qss", True)


        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        # --- Заголовок сверху ---
        header = QLabel(
            '<div style="text-align:center; font-size:18px; font-weight:600;">'
            '<h2>Приложение написано с помощью ChatGPT'
            '</div>'
        )
        header.setAlignment(Qt.AlignCenter)
        root.addWidget(header)



        # --- Карточка: Используемые модули ---
        mods = QTextBrowser()
        mods.setOpenExternalLinks(True)
        mods.setFrameShape(QFrame.NoFrame)
        mods.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        mods.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        mods.setReadOnly(True)
        mods.setHtml(
            "<ul;'>"
            "<li>PySide6-Essentials</li>"
            "<li>Pillow</li>"
            "<li>requests</li>"
            "<li>playwright</li>"
            "<li>psd-tools</li>"
            "</ul>"
        )
        card_mods = _card("Используемые библиотеки", mods)

        # --- Карточка: Полезные ссылки ---
        links = QTextBrowser()
        links.setObjectName("infoLinks")
        links.setOpenExternalLinks(True)
        links.setFrameShape(QFrame.NoFrame)
        links.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        links.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        links.setReadOnly(True)

        # Стили для HTML-содержимого QTextBrowser
        links.document().setDefaultStyleSheet("""
        a { color: #1E88E5; text-decoration: none; }
        a:visited { color: #1fbae5; }
        a:hover { text-decoration: underline; }
        ul { margin-left: 14px; padding-left: 0; }  /* заодно фикс отступов */
        """)

        links.setHtml(
            "<ul'>"
            "<li><a href='https://sites.google.com/view/scanlatewait'>Шрифты</a></li>"
            "<li><a href='https://openmodeldb.info/'>Модели для апскейла</a></li>"
            "<li><a href='https://github.com/lltcggie/waifu2x-caffe/releases'>Вайфу</a></li>"
            "<li><a href='https://github.com/Flowseal/zapret-discord-youtube/releases'>Обход блокировок</a></li>"
            "</ul>"
        )
        card_links = _card("Полезные ссылки", links)

        # Разместим карточки в ряд
        row = QHBoxLayout(); row.setSpacing(10)
        row.addWidget(card_mods, 1)
        row.addWidget(card_links, 1)

        root.addLayout(row)
        root.addStretch(1)



        # --- Контакты внизу по центру ---
        version_label = QLabel(
            '<div style="text-align:center; font-size:14px; color:#6b7280;">v1.0.1</div>'
        )
        version_label.setAlignment(Qt.AlignCenter)
        root.addWidget(version_label)


        # --- Подзаголовок (ссылка на GitHub) ---
        update_label = QLabel(
            '<div style="text-align:center; font-size:18px;">'
            '<a href="https://github.com/Smithyanka/SmithanaToolGit/releases" style="color:#1E88E5; text-decoration:none;">Проверить обновления</a>'
            '</div>'
        )
        update_label.setOpenExternalLinks(True)
        update_label.setAlignment(Qt.AlignCenter)
        root.addWidget(update_label)

        footer = QLabel(
            '<div style="text-align:center; font-size:18px;">'
            'По вопросам и предложениям '
            '<a href="https://t.me/smithyanka" style="color:#1E88E5; text-decoration:none;">@smithyanka</a>'
            '</div>'
        )
        footer.setTextFormat(Qt.RichText)
        footer.setOpenExternalLinks(True)
        footer.setAlignment(Qt.AlignCenter)
        root.addWidget(footer)

        # --- Мини-стили ---
        self.setStyleSheet("""
            QWidget { font-size: 16px; }
            QFrame#card {
                border: 1px solid rgba(0,0,0,40);
                border-radius: 8px;
                background: rgba(0,0,0,8);
            }
            QLabel#cardTitle {
                font-size: 18px;
                font-weight: 600;
            }
            QTextBrowser {
                background: transparent;
            }
            a { text-decoration: none; }
            a:hover { text-decoration: underline; }
        """)
