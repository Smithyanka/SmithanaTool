
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional, Iterable, Callable

from PySide6.QtCore import QObject, Signal, Slot, QThread

from smithanatool_qt.parsers.kakao_novel.runner import run_novel_parser

@dataclass
class NovelParserConfig:
    title_id: str
    mode: str  # 'number' | 'id'
    spec_text: str  # chapters or viewer IDs
    out_dir: str
    volume_spec: Optional[str] = None
    min_width: int = 720

class NovelParserWorker(QObject):
    log = Signal(str)
    need_login = Signal()
    error = Signal(str)
    finished = Signal()

    def __init__(self, cfg: NovelParserConfig, parent: Optional[QObject]=None):
        super().__init__(parent)
        self.cfg = cfg
        self._thread: Optional[QThread] = None
        self._stop = False

    @Slot()
    def start(self):
        # запуск в отдельном QThread
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.started.connect(self._run)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    @Slot()
    def stop(self):
        self._stop = True

    @Slot()
    def continue_after_login(self):
        # для совместимости с UI — ничего не делаем, раннер сам подхватит сессию
        pass

    # callbacks
    def _on_log(self, s: str):
        self.log.emit(s)

    def _on_need_login(self):
        self.need_login.emit()

    def _stop_flag(self) -> bool:
        return self._stop

    def _confirm_purchase(self, ch_no: int, vol_no: Optional[int]) -> bool:
        # Автоматически подтверждаем покупки? По умолчанию — спрашивать в UI не реализуем, оставим False
        return False

    def _confirm_use_rental(self, ticket_id: int, ch_no: int, vol_no: Optional[int], title: str) -> bool:
        return False

    @Slot()
    def _run(self):
        try:
            title_id = self.cfg.title_id.strip()
            spec = (self.cfg.spec_text or '').strip()
            volume_spec = (self.cfg.volume_spec or None)
            if self.cfg.mode == 'id':
                # В режиме ID ожидаем список ViewerID через запятую/пробел/новые строки
                ids: Iterable[str] = [t.strip() for t in re.split(r'[\s,;]+', spec) if t.strip()]
                chapters = ids
                chapter_spec = None
            else:
                chapters = None
                chapter_spec = spec  # строки вида "1-5,8,10"
            run_novel_parser(
                title_id=title_id,
                chapter_spec=chapter_spec,
                chapters=chapters,
                out_dir=self.cfg.out_dir,
                on_log=self._on_log,
                on_need_login=self._on_need_login,
                stop_flag=self._stop_flag,
                min_width=int(self.cfg.min_width),
                auto_concat=None,
                on_confirm_purchase=self._confirm_purchase,
                on_confirm_use_rental=self._confirm_use_rental,
                volume_spec=volume_spec,
            )
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()
