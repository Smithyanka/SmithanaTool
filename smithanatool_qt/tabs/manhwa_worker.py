
from __future__ import annotations
import threading
from dataclasses import dataclass
from typing import Optional, List, Iterable, Callable

from PySide6.QtCore import QObject, Signal, Slot, QThread

from smithanatool_qt.parsers.kakao.core import run_parser

@dataclass
class ParserConfig:
    title_id: str
    mode: str  # 'number'|'id'|'index'
    spec_text: str
    out_dir: str
    min_width: int = 720
    # auto concat options
    auto_enabled: bool = True
    no_resize_width: bool = True
    target_width: int = 800
    same_dir: bool = False
    stitch_out_dir: Optional[str] = None
    delete_sources: bool = True
    optimize_png: bool = True
    compress_level: int = 6
    strip_metadata: bool = True
    per: int = 12
    auto_confirm_purchase: bool = False  # автопокупка без вопросов
    auto_confirm_use_rental: bool = False  # авто-использование 대여권

class ManhwaParserWorker(QObject):
    log = Signal(str)
    started = Signal()
    finished = Signal()
    need_login = Signal()  # UI should show "press Continue after login"
    error = Signal(str)

    ask_purchase = Signal(object, object)  # ch_num, price(int|None)
    ask_use_rental = Signal(int, int, object, str)  # rental_count, own_count, balance(int|None), chapter_label

    def __init__(self, cfg: ParserConfig):
        super().__init__()
        self.cfg = cfg
        self._stop_event = threading.Event()
        self._resume_event = threading.Event()
        self._thread: Optional[QThread] = None

        self._purchase_event = threading.Event()
        self._purchase_result: bool = False
        self._rental_event = threading.Event()
        self._rental_result: bool = False

    # threading helpers
    def move_to_thread_and_start(self):
        th = QThread()
        self._thread = th
        self.moveToThread(th)
        th.started.connect(self._run)

        # ВАЖНО: чистим поток реакцией на сигнал finished (в главном потоке)
        self.finished.connect(th.quit)
        self.finished.connect(self.deleteLater)  # удалим worker в его же потоке
        th.finished.connect(th.deleteLater)  # удалим сам QThread
        th.finished.connect(lambda: setattr(self, "_thread", None))

        th.start()

    @Slot(bool)
    def provide_purchase_answer(self, ans: bool):
        self._purchase_result = bool(ans)
        self._purchase_event.set()

    @Slot(bool)
    def provide_use_rental_answer(self, ans: bool):
        self._rental_result = bool(ans)
        self._rental_event.set()

    @Slot()
    def stop(self):
        self._stop_event.set()

    @Slot()
    def resume_after_login(self):
        self._resume_event.set()

    def _stop_flag(self) -> bool:
        return self._stop_event.is_set()

    def _on_need_login(self):
        # Notify UI and block until user clicks "Continue after login"
        self._resume_event.clear()
        self.need_login.emit()
        # Block this worker thread until resumed
        self._resume_event.wait()

    def _on_log(self, s: str):
        self.log.emit(s)

    def _build_auto_concat(self) -> Optional[dict]:
        if not self.cfg.auto_enabled:
            return None
        out_dir = self.cfg.stitch_out_dir or self.cfg.out_dir
        return {
            "per": int(self.cfg.per),
            "same_dir": bool(self.cfg.same_dir),
            "out_dir": out_dir,
            "target_width": 0 if self.cfg.no_resize_width else int(self.cfg.target_width),
            "strip_metadata": bool(self.cfg.strip_metadata),
            "optimize_png": bool(self.cfg.optimize_png),
            "compress_level": int(self.cfg.compress_level),
            "delete_sources": bool(self.cfg.delete_sources),
            "enable": True,
        }

    @Slot()
    def _run(self):
        self.started.emit()
        try:
            # Prepare params based on mode
            mode = self.cfg.mode
            title_id = self.cfg.title_id.strip()
            spec = self.cfg.spec_text.strip()
            chapter_spec = None
            chapters: Optional[Iterable[str]] = None
            by_index: Optional[int] = None

            if mode == "number":
                chapter_spec = spec  # e.g. "1,2,5-7 10"
            elif mode == "id":
                parts = [p.strip() for p in spec.replace(",", " ").split() if p.strip()]
                chapters = parts
            elif mode == "index":
                try:
                    by_index = int(spec)
                except Exception:
                    self.error.emit("Индекс должен быть числом.")
                    return
            else:
                self.error.emit("Неизвестный режим.")
                return

            auto_cfg = self._build_auto_concat()
            def _confirm_purchase(price: Optional[int], balance: Optional[int]) -> bool:
                if self.cfg.auto_confirm_purchase:
                    self.log.emit(f"[ASK] Покупка за {price} кредитов (авто).")
                    return True
                self._purchase_event.clear()
                self.ask_purchase.emit(price, balance)
                self._purchase_event.wait()
                self.log.emit(
                    "[OK] Покупка разрешена пользователем." if self._purchase_result else "[SKIP] Покупка отклонена пользователем.")
                return self._purchase_result

            def _confirm_use_rental(rental_count: int, own_count: int, balance: Optional[int],
                                    chapter_label: str) -> bool:
                # если автоприменение 대여권 — не спрашиваем
                if self.cfg.auto_confirm_use_rental:
                    self.log.emit(f"[ASK] Использовать тикет аренды для {chapter_label}? (авто: да)")
                    return True
                # иначе — спросить UI и подождать
                self._rental_event.clear()
                self.ask_use_rental.emit(rental_count, own_count, balance, chapter_label)
                self._rental_event.wait()
                self.log.emit(
                    "[OK] Использую тикет." if self._rental_result else "[SKIP] Пользователь отказал от использования тикета.")
                return self._rental_result

            run_parser(
                title_id=title_id,
                chapter_spec=chapter_spec,
                chapters=chapters,
                out_dir=self.cfg.out_dir,
                on_log=self._on_log,
                on_need_login=self._on_need_login,
                stop_flag=self._stop_flag,
                min_width=int(self.cfg.min_width),
                auto_concat=auto_cfg,
                on_confirm_purchase=_confirm_purchase,
                on_confirm_use_rental=_confirm_use_rental,
                by_index=by_index,
            )
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()
