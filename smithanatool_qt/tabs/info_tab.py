from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QPixmap, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFrame, QLabel, QPushButton,
    QGroupBox, QSizePolicy, QScrollArea, QSpacerItem
)
from smithanatool_qt.graphic.foundation.assets import asset_path

BANNER_NAME = "chill.png"


class BannerLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(400)
        self._pixmap_orig: QPixmap | None = None

    def set_source(self, path: str | Path):
        pm = QPixmap(str(path))
        if pm.isNull():
            self.setText("Не удалось загрузить изображение")
            self._pixmap_orig = None
            return
        self._pixmap_orig = pm
        self._rescale()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._rescale()

    def _rescale(self):
        if not self._pixmap_orig:
            return
        scaled = self._pixmap_orig.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.setPixmap(scaled)


class LinkPanel(QGroupBox):
    def __init__(self, title: str, links: list[tuple[str, str]] | None = None, parent=None):
        super().__init__(title, parent)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(12, 12, 12, 12)
        self.v.setSpacing(15)

        self._buttons: list[QPushButton] = []
        self._tail_sp = QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.v.addItem(self._tail_sp)

        if links:
            self.set_links(links)

    def set_links(self, links: list[tuple[str, str]]):
        for b in self._buttons:
            self.v.removeWidget(b)
            b.deleteLater()
        self._buttons.clear()

        self.v.removeItem(self._tail_sp)
        self.v.addItem(self._tail_sp)

        for text, url in links:
            btn = QPushButton(text)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(36)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.clicked.connect(lambda _, u=url: QDesktopServices.openUrl(QUrl(u)))
            self.v.insertWidget(self.v.count() - 1, btn)
            self._buttons.append(btn)


class AboutCard(QFrame):
    def __init__(self, title: str, subtitle: str = "", description: str = "", parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("InfoAboutTitle")
        self.lbl_title.setAlignment(Qt.AlignCenter)

        self.lbl_sub = QLabel(subtitle)
        self.lbl_sub.setObjectName("InfoAboutSubtitle")
        self.lbl_sub.setAlignment(Qt.AlignCenter)

        lay.addWidget(self.lbl_title)
        lay.addWidget(self.lbl_sub)

        self.scroll = None
        self.lbl_desc = None

        if description.strip():
            self.scroll = QScrollArea()
            self.scroll.setWidgetResizable(True)
            self.scroll.setFrameShape(QFrame.NoFrame)
            self.scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

            content = QWidget()
            content_lay = QVBoxLayout(content)
            content_lay.setContentsMargins(0, 0, 0, 0)

            self.lbl_desc = QLabel(description)
            self.lbl_desc.setWordWrap(True)
            self.lbl_desc.setAlignment(Qt.AlignHCenter | Qt.AlignTop)

            content_lay.addWidget(self.lbl_desc, 0, Qt.AlignHCenter | Qt.AlignTop)
            self.scroll.setWidget(content)
            lay.addWidget(self.scroll)


class InfoTab(QWidget):
    CONTENT_MAX_WIDTH = 1800

    def __init__(self, parent=None):
        super().__init__(parent)

        # Внешний layout — центрирует весь контентный блок
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(0)
        outer.addStretch(1)

        center_row = QHBoxLayout()
        center_row.setContentsMargins(0, 0, 0, 0)
        center_row.setSpacing(0)
        center_row.addStretch(1)

        # Центральный контейнер
        content = QWidget(self)
        content.setObjectName("InfoCenterBlock")
        content.setMaximumWidth(self.CONTENT_MAX_WIDTH)
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        root = QHBoxLayout(content)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(32)

        center_row.addWidget(content, 0, Qt.AlignCenter)
        center_row.addStretch(1)

        outer.addLayout(center_row)
        outer.addStretch(1)

        # Левая колонка
        left_col = QVBoxLayout()
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(16)
        left_col.addStretch(1)

        self.banner = BannerLabel(self)
        self.banner.set_source(asset_path(BANNER_NAME))
        self.banner.setFixedSize(350, 350)
        left_col.addWidget(self.banner, 0, Qt.AlignHCenter)

        self.about = AboutCard(
            title="SmithanaTool",
            subtitle="Приложение написано с помощью ChatGPT"
        )

        title_font = self.about.lbl_title.font()
        title_font.setPointSize(22)
        title_font.setWeight(QFont.Weight.Bold)
        self.about.lbl_title.setFont(title_font)

        subtitle_font = self.about.lbl_sub.font()
        subtitle_font.setPointSize(10)
        subtitle_font.setWeight(QFont.Weight.Medium)
        self.about.lbl_sub.setFont(subtitle_font)

        left_col.addWidget(self.about, 0, Qt.AlignHCenter)
        left_col.addStretch(8)

        left_wrap = QWidget()
        left_wrap.setLayout(left_col)
        left_wrap.setFixedWidth(400)
        left_wrap.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Maximum)
        root.addWidget(left_wrap, 3)

        # Правая колонка
        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(16)

        self.links_top = LinkPanel(
            "Основные ссылки",
            links=[
                ("Телеграм-канал", "https://t.me/smithanatool"),
                ("Проверить обновления", "https://github.com/Smithyanka/SmithanaTool/releases"),
                ("По вопросам и предложениям", "https://t.me/smithyanka"),
            ],
        )

        self.links_bottom = LinkPanel(
            "Полезные ссылки",
            links=[
                ("Обход блокировок", "https://github.com/Flowseal/zapret-discord-youtube/releases/"),
                ("Апскейл Вайфу", "https://github.com/lltcggie/waifu2x-caffe/releases/"),
                ("Модели для апскейла", "https://openmodeldb.info/"),
                ("Шрифты", "https://sites.google.com/view/scanlatewait/"),
            ],
        )

        right_col.addWidget(self.links_top)
        right_col.addWidget(self.links_bottom)

        right_wrap = QWidget()
        right_wrap.setLayout(right_col)
        right_wrap.setMinimumWidth(400)
        right_wrap.setMaximumWidth(1000)
        right_wrap.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        root.addWidget(right_wrap, 2)