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
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(12, 12, 12, 12)
        self.v.setSpacing(8)
        self._buttons: list[QPushButton] = []

        self._tail_sp = QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.v.addItem(self._tail_sp)

        if links:
            self.set_links(links)

    def set_links(self, links: list[tuple[str, str]]):
        # убрать старые
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
            btn.clicked.connect(lambda _, u=url: QDesktopServices.openUrl(QUrl(u)))
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.v.insertWidget(self.v.count() - 1, btn)
            self._buttons.append(btn)

class AboutCard(QFrame):
    def __init__(self, title: str, subtitle: str = "", description: str = "", parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 0)
        lay.setSpacing(8)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("InfoAboutTitle")
        self.lbl_title.setAlignment(Qt.AlignCenter)

        self.lbl_sub = QLabel(subtitle)
        self.lbl_sub.setObjectName("InfoAboutSubtitle")
        self.lbl_sub.setWordWrap(True)
        self.lbl_sub.setAlignment(Qt.AlignCenter)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        content_lay = QVBoxLayout(content)
        self.lbl_desc = QLabel(description)
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        content_lay.addWidget(self.lbl_desc, 0, Qt.AlignHCenter | Qt.AlignTop)
        self.scroll.setWidget(content)

        lay.addWidget(self.lbl_title)
        lay.addWidget(self.lbl_sub)
        lay.addWidget(self.scroll)


class InfoTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)



        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # Левая колонка
        left_col = QVBoxLayout()
        left_col.setSpacing(12)
        left_col.addStretch(1)

        self.banner = BannerLabel(self)
        self.banner.set_source(asset_path(BANNER_NAME))
        left_col.addWidget(self.banner, 1)

        self.about = AboutCard(
            title="SmithanaTool",
            subtitle="Приложение написано с помощью ChatGPT"
        )
        # Title
        f = self.about.lbl_title.font()
        f.setPointSize(22)  # или setPointSizeF(22.0)
        f.setWeight(QFont.Weight.Bold)
        self.about.lbl_title.setFont(f)

        # Subtitle
        s = self.about.lbl_sub.font()
        s.setPointSize(10)
        s.setWeight(QFont.Weight.Medium)
        self.about.lbl_sub.setFont(s)




        left_col.addWidget(self.about)

        left_col.addStretch(1)

        left_wrap = QWidget()
        left_wrap.setLayout(left_col)
        root.addWidget(left_wrap, 3)

        # Правая колонка
        right_col = QVBoxLayout()
        right_col.setSpacing(12)

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

        right_wrap = QWidget()
        right_wrap.setLayout(right_col)
        right_wrap.setMinimumWidth(320)
        right_wrap.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        right_col.addWidget(self.links_top)
        right_col.addWidget(self.links_bottom)

        root.addWidget(right_wrap, 2)
