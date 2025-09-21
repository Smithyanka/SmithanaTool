# -*- coding: utf-8 -*-
"""
Логика покупки и работы с модалкой тикетов:
- распознавание модалки с '대여권 / 소장권 / 캐시'
- предложение применить 대여권
- если нет тикетов, покупка за N 캐시
"""
from __future__ import annotations
import re
from typing import Optional

# Precompiled regex patterns (micro-optimization; logic unchanged)
RE_NON_DIGIT = re.compile(r"[^\d]")
RE_RENTAL = re.compile(r"대여권\s*([\d,]+)\s*장")
RE_OWN = re.compile(r"소장권\s*([\d,]+)\s*장")
RE_BALANCE_TRAIL = re.compile(r"([\d,]+)\s*캐시$")

def looks_locked(page) -> bool:
    try:
        if "/buy/ticket" in (page.url or ""):
            return True
    except Exception:
        pass
    sels = [
        "button:has-text('구매')","button:has-text('대여')",
        "text=구매","text=대여","text=결제",
    ]
    for sel in sels:
        try:
            if page.query_selector(sel):
                return True
        except Exception:
            pass
    return False

def read_balance(context, title_id: str, log) -> Optional[int]:
    page = None
    try:
        page = context.new_page()
        page.goto(f"https://page.kakao.com/content/{title_id}",
                  wait_until="domcontentloaded", timeout=90000)
        page.wait_for_load_state("networkidle", timeout=60000)
        sel = "div.flex.w-full.flex-row.items-center.justify-between.rounded-4pxr.bg-bg-b-10.p-14pxr span.font-large4-bold"
        el = page.query_selector(sel) or page.query_selector("div:has(span:text('충전')) span.font-large4-bold")
        if not el:
            return None
        txt = (el.inner_text() or "").strip()
        digits = re.sub(r"[^\d]", "", txt)
        return int(digits) if digits else None
    except Exception:
        return None
    finally:
        try:
            if page: page.close()
        except Exception:
            pass

def _ensure_buy_page(page, title_id: str):
    if "/buy/ticket" not in (page.url or ""):
        page.goto(f"https://page.kakao.com/buy/ticket?seriesId={title_id}",
                  wait_until="domcontentloaded", timeout=90000)
        page.wait_for_load_state("networkidle", timeout=60000)

def _click_price_button(page, price: int) -> bool:
    patterns = [rf"^{price}\s*캐시$", rf"{price}\s*캐시"]
    for pat in patterns:
        try:
            btn = page.get_by_role("button", name=re.compile(pat))
            try:
                if btn.count() > 0:
                    btn.first.click(timeout=5000)
                    return True
            except Exception:
                pass
        except Exception:
            pass
    try:
        any_btn = page.locator("button", has_text=re.compile(r"캐시"))
        if hasattr(any_btn, "count") and any_btn.count() > 0:
            any_btn.first.click(timeout=5000); return True
    except Exception:
        pass
    return False

def _click_charge(page):
    try:
        page.wait_for_timeout(400)
        loc = None
        try:
            loc = page.get_by_role("button", name=re.compile(r"충전하기"))
        except Exception:
            pass
        if not loc:
            loc = page.locator("button", has_text=re.compile(r"충전하기"))
        if loc and (not hasattr(loc, "count") or loc.count() > 0):
            (loc.first if hasattr(loc,"first") else loc).click(timeout=5000)
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass

def auto_buy(page, title_id: str, price_target: int, log) -> bool:
    try:
        _ensure_buy_page(page, title_id)
        if not _click_price_button(page, price_target):
            log("[ERROR] Не нашёл кнопку оплаты '캐시'."); return False
        _click_charge(page)
        log("[OK] Попытка покупки выполнена (кнопки нажаты).")
        return True
    except Exception as e:
        log(f"[ERROR] Автопокупка не удалась: {e}"); return False

def _parse_ticket_modal_text(txt: str) -> dict:
    """
    Ищем '<대여권 N장> · <소장권 M장> · <K캐시>'.
    Возвращает {'rental': int|0, 'own': int|0, 'balance': int|None}
    """
    rental = 0; own = 0; bal = None
    m = re.search(r"대여권\s*([\d,]+)\s*장", txt)
    if m:
        rental = int(re.sub(r"[^\d]", "", m.group(1)) or "0")
    m = re.search(r"소장권\s*([\d,]+)\s*장", txt)
    if m:
        own = int(re.sub(r"[^\d]", "", m.group(1)) or "0")
    m = re.search(r"([\d,]+)\s*캐시", txt)
    if m:
        bal = int(re.sub(r"[^\d]", "", m.group(1)) or "0")
    return {"rental": rental, "own": own, "balance": bal}

def parse_ticket_modal(page) -> Optional[dict]:
    """
    Пытается найти модалку с текстом про 대여권/소장권/캐시 и кнопку '대여권'.
    """
    try:
        # контейнер модалки
        dlg = page.locator("div[role='dialog']").first
        if hasattr(dlg, "count") and dlg.count() == 0:
            # запасной признак — наличие кнопки '대여권'
            dlg = page.locator("div:has(button:has-text('대여권'))").first
            if hasattr(dlg, "count") and dlg.count() == 0:
                return None
        txt = dlg.inner_text()
        info = _parse_ticket_modal_text(txt or "")
        # проверим, видна ли кнопка 대여권
        has_btn = page.locator("button:has-text('대여권')")
        info["has_rental_btn"] = hasattr(has_btn, "count") and has_btn.count() > 0
        return info
    except Exception:
        return None

def click_rental_ticket(page, log) -> bool:
    """
    Нажимает кнопку '대여권' в модалке, ждёт закрытия/загрузки.
    """
    try:
        btn = page.locator("button:has-text('대여권')")
        if hasattr(btn, "count") and btn.count() > 0:
            btn = btn.first
        btn.click(timeout=5000)
        page.wait_for_load_state("networkidle", timeout=15000)
        log("[OK] Тикет использован.")
        return True
    except Exception as e:
        log(f"[ERROR] Не удалось нажать '대여권': {e}")
        return False

def handle_ticket_modal(
    page,
    context,
    title_id: str,
    viewer_url: str,
    price_target: int,
    log,
    confirm_use_rental_cb,   # (rental_count:int, own_count:int, balance:int|None) -> bool
    confirm_purchase_cb,      # (price:int, balance:int|None) -> bool
    chapter_label: str | None = None
) -> str:
    """
    Обработка модалки с '대여권 / 소장권 / ...캐시'.
    Возвращает: 'consumed' (нажали 대여권) | 'purchased' (купили) | 'skipped' | 'absent'
    """

    def _ensure_viewer():
        """Гарантированный возврат на страницу главы после действия."""
        try:
            # если вдруг открылся новый таб с viewer — переключимся
            if context:
                for p in reversed(context.pages):
                    if "/viewer/" in (p.url or ""):
                        try:
                            p.bring_to_front()
                        except Exception:
                            pass
                        return p
            # иначе — явно открываем viewer_url в текущей вкладке
            page.goto(viewer_url, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_load_state("networkidle", timeout=60000)
        except Exception:
            pass
        return page

    info = parse_ticket_modal(page)
    if not info:
        return "absent"

    rental = int(info.get("rental", 0) or 0)
    own    = int(info.get("own", 0) or 0)
    bal    = info.get("balance")
    log(f"[INFO] Тикеты: Аренды {rental} · Владения {own}장 · баланс {bal if bal is not None else '—'} кредитов")
    # log(f"[INFO] 티켓: 대여권 {rental}장 · 소장권 {own}장 · баланс {bal if bal is not None else '—'} 캐시") # если есть 소장권

    # 1) Есть 대여권 — спрашиваем и жмём
    has_rental_btn = bool(info.get("has_rental_btn"))
    if rental > 0 and has_rental_btn:
        use = True
        if callable(confirm_use_rental_cb):
            use = bool(confirm_use_rental_cb(rental, own, bal, chapter_label or ""))
        if use:
            if click_rental_ticket(page, log):
                return "consumed"
            else:
                log("[ERROR] Не удалось применить тикет аренды.")
                return "skipped"


        else:
            # Пользователь отказал от использования тикета — пропускаем главу
            return "skipped"
    # 2) ТИКЕТОВ НЕТ ВОВСЕ — предлагать покупку
    if rental == 0 and own == 0:
        log(f"[INFO] Тикетов нет — предложу покупку за {price_target} кредитов.")
        do_buy = True
        if callable(confirm_purchase_cb):
            do_buy = bool(confirm_purchase_cb(price_target, bal))
        if not do_buy:
            return "skipped"
        # Сообщаем ядру, что нужна покупка (или сразу перейти на /buy/ticket)
        return "need_buy"


def handle_buy_page(
    page,
    context,
    title_id: str,
    viewer_url: str,
    price_target: int,
    log,   # (price:int, balance:int|None) -> bool
    confirm_purchase_cb,
    balance_hint: int | None = None
) -> str:
    """
    Когда модалки нет, но мы оказались на /buy/ticket?seriesId=...
    Показываем «Купить 1 за <price_target> кредитов?», покупаем и возвращаемся к главе.
    Возвращает: 'purchased' | 'skipped' | 'absent'
    """

    if "/buy/ticket" not in (page.url or ""):
        return "absent"

    # баланс по желанию — выводим в диалог
    bal = balance_hint
    if bal is None:
        try:
            bal = read_balance(context, title_id, log)  # запасной путь
            if bal is not None:
                log(f"[INFO] Текущий баланс: {bal} 캐시.")
        except Exception:
            pass

    ok = False
    if callable(confirm_purchase_cb):
        ok = bool(confirm_purchase_cb(price_target, bal))
    if not ok:
        log("[SKIP] Покупка тикета отменена пользователем.")
        return "skipped"

    if not auto_buy(page, title_id, price_target, log):
        log("[ERROR] Покупка на /buy/ticket не удалась.")
        return "skipped"

    # возвращаемся на страницу главы
    try:
        # если сайт уже сам открыл viewer в новом табе — переключимся
        if context:
            for p in reversed(context.pages):
                if "/viewer/" in (p.url or ""):
                    try:
                        p.bring_to_front()
                    except Exception:
                        pass
                    page = p
                    break
        page.goto(viewer_url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_load_state("networkidle", timeout=60000)
        log("[OK] Тикет куплен. Возврат к чтению главы.")
        return "purchased"
    except Exception:
        log("[ERROR] После покупки не удалось открыть страницу главы.")
        return "skipped"

def handle_rental_expired_modal(page, log) -> bool:
    """Проверяет наличие модалки "대여기간 만료" (истёк срок аренды).
    Если найдена — нажимает "보던화" (если есть), иначе "확ин".
    Возвращает True, если модалка была обработана (нажата кнопка), иначе False.
    """
    try:
        # Ищем диалог (role=dialog) с текстом '대여기간 만료'
        dlg = None
        try:
            candidate = page.locator("div[role='dialog']").first
            if hasattr(candidate, 'count') and candidate.count() > 0:
                txt = (candidate.inner_text() or '').strip()
                if '대여기간 만료' in txt:
                    dlg = candidate
        except Exception:
            dlg = None

        # fallback: ищем любой диалог, где встречается фраза
        if dlg is None:
            try:
                candidate = page.locator("div:has-text('대여기간 만료')").first
                if hasattr(candidate, 'count') and candidate.count() > 0:
                    dlg = candidate
            except Exception:
                dlg = None

        if dlg is None:
            return False  # модалки нет

        # Сначала пробуем "보던화" (продолжить чтение), затем "확인"
        for label in ['보던화', '확인']:
            try:
                btn = dlg.locator(f"button:has-text('{label}')")
                if hasattr(btn, 'count') and btn.count() > 0:
                    btn.first.click(timeout=4000)
                    try:
                        page.wait_for_load_state('networkidle', timeout=60000)
                    except Exception:
                        pass
                    log(f"[OK] Нажата кнопка '{label}' в модалке истечения аренды.")
                    return True
            except Exception:
                continue

        # Если конкретных кнопок не нашли, кликнем первую видимую кнопку
        try:
            any_btn = dlg.locator('button')
            if hasattr(any_btn, 'count') and any_btn.count() > 0:
                any_btn.first.click(timeout=4000)
                try:
                    page.wait_for_load_state('networkidle', timeout=60000)
                except Exception:
                    pass
                log("[OK] Модалка истечения аренды закрыта (первая доступная кнопка)." )
                return True
        except Exception:
            pass

        return False
    except Exception as e:
        log(f"[DEBUG] handle_rental_expired_modal: {e}")
        return False
