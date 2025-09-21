# tabs/novel_worker.py
from __future__ import annotations
import threading
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

    # Новое: управление покупками/тикетами
    auto_confirm_purchase: bool = False     # автопокупка без вопросов
    auto_confirm_use_rental: bool = False   # авто-использование 대여권 (аренды)


class NovelParserWorker(QThread):
    log = Signal(str)
    need_login = Signal()
    error = Signal(str)
    finished = Signal()

    # Сигналы вопросов к UI (как в манхве)
    # Покупка: цена (int|None) и баланс (int|None)
    ask_purchase = Signal(object, object)  # price, balance
    # Использование тикета: доступно аренды, «собственных», баланс, подпись главы
    ask_use_rental = Signal(int, int, object, str)

    def __init__(self, cfg: NovelParserConfig):
        super().__init__()
        self.cfg = cfg

        # Синхронизация ответов из UI
        self._purchase_event = threading.Event()
        self._purchase_result: bool = False

        self._rental_event = threading.Event()
        self._rental_result: bool = False

        self._stop_flag_value = False

    # ===== Публичные методы для UI, чтобы вернуть ответ в раннер =====
    @Slot(bool)
    def provide_purchase_answer(self, ans: bool):
        self._purchase_result = bool(ans)
        self._purchase_event.set()

    @Slot(bool)
    def provide_use_rental_answer(self, ans: bool):
        self._rental_result = bool(ans)
        self._rental_event.set()

    # ===== Внутренние колбэки, которые передадим в run_novel_parser =====
    def _on_log(self, s: str):
        self.log.emit(str(s))

    def _on_need_login(self):
        self.need_login.emit()

    def _stop_flag(self) -> bool:
        return self._stop_flag_value

    def _confirm_purchase(self, price: Optional[int], balance: Optional[int]) -> bool:
        """
        Сигнатура для run_novel_parser: (price, balance) -> bool
        """
        # Автопокупка включена — сразу подтверждаем
        if self.cfg.auto_confirm_purchase:
            self._on_log("[AUTO] Покупка подтверждена по настройке автопокупки.")
            return True

        # Иначе — спрашиваем UI
        self._purchase_event.clear()
        self.ask_purchase.emit(price, balance)
        self._purchase_event.wait()
        self._on_log("[OK] Пользователь подтвердил покупку." if self._purchase_result else "[SKIP] Пользователь отменил покупку.")
        return self._purchase_result

    def _confirm_use_rental(self, rental_count: int, own_count: int, balance: Optional[int], chapter_label: str) -> bool:
        """
        Сигнатура для run_novel_parser: (rental_count, own_count, balance, chapter_label) -> bool
        """
        # Автоиспользование тикетов включено — сразу подтверждаем
        if self.cfg.auto_confirm_use_rental:
            self._on_log("[AUTO] Использование тикета подтверждено по настройке автоприменения.")
            return True

        # Иначе — спрашиваем UI
        self._rental_event.clear()
        self.ask_use_rental.emit(rental_count, own_count, balance if balance is not None else None, str(chapter_label))
        self._rental_event.wait()
        self._on_log("[OK] Использую тикет." if self._rental_result else "[SKIP] Пользователь отказался использовать тикет.")
        return self._rental_result

    # ===== Поток запуска =====
    def run(self):
        try:
            # Подготовка спецификации глав
            chapter_spec: Optional[str] = None
            chapters: Optional[Iterable[str]] = None
            if self.cfg.mode == "id":
                chapters = [s.strip() for s in (self.cfg.spec_text or "").split(",") if s.strip()]
            else:
                chapter_spec = (self.cfg.spec_text or "").strip() or None

            run_novel_parser(
                title_id=self.cfg.title_id,
                chapter_spec=chapter_spec,
                chapters=chapters,
                out_dir=self.cfg.out_dir,
                on_log=self._on_log,
                on_need_login=self._on_need_login,
                stop_flag=self._stop_flag,
                min_width=int(self.cfg.min_width),
                auto_concat=None,  # для новелл не используется
                on_confirm_purchase=self._confirm_purchase,
                on_confirm_use_rental=self._confirm_use_rental,
                volume_spec=self.cfg.volume_spec,
            )
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()

    # ===== Управление из UI =====
    def request_stop(self):
        self._stop_flag_value = True
