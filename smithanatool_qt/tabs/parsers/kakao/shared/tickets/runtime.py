from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Optional

from smithanatool_qt.tabs.parsers.kakao.shared.tickets.access import TicketAccessInfo, TicketVariant, parse_ticket_access_info


TicketActionCallback = Callable[[dict[str, Any]], str]


def _variant_title(kind: str) -> str:
    return 'own-ticket' if kind == 'own' else 'rental-ticket'


def _normalize_offer(kind: str, offer: Any, *, fallback_count: int = 0) -> TicketVariant | None:
    if not isinstance(offer, dict):
        return None

    ticket_id = str(offer.get('ticket_id') or offer.get('ticketId') or '').strip() or None
    price_raw = offer.get('price')
    try:
        price = None if price_raw is None else int(price_raw)
    except Exception:
        price = None

    default_ticket_type = 'TT01' if kind == 'own' else 'RT01'
    ticket_type = str(offer.get('ticket_type') or offer.get('ticketType') or default_ticket_type).strip() or default_ticket_type
    buy_type = 1 if kind == 'own' else 2
    sale_available = bool(ticket_id and price is not None)

    return TicketVariant(
        kind=kind,
        ticket_id=ticket_id,
        ticket_type=ticket_type,
        price=price,
        count=max(0, int(fallback_count or 0)),
        buy_type=buy_type,
        sale_available=sale_available,
    )


def _enrich_manhwa_variants_from_catalog(api, series_id: int, info: TicketAccessInfo, *, log: Callable[[str], None]) -> TicketAccessInfo:
    try:
        own_offer = api.get_ticket_offer(series_id, 'own') or {}
    except Exception as e:
        own_offer = {}
        log(f'[WARN] Не удалось получить own-ticket offer: {e}')

    try:
        rental_offer = api.get_ticket_offer(series_id, 'rental') or {}
    except Exception as e:
        rental_offer = {}
        log(f'[WARN] Не удалось получить rental-ticket offer: {e}')

    own = info.own
    rental = info.rental

    norm_own = _normalize_offer('own', own_offer, fallback_count=own.count)
    if norm_own and (norm_own.sale_available or own.sale_available):
        own = replace(
            own,
            ticket_id=norm_own.ticket_id or own.ticket_id,
            ticket_type=norm_own.ticket_type or own.ticket_type,
            price=norm_own.price if norm_own.price is not None else own.price,
            buy_type=norm_own.buy_type or own.buy_type,
            sale_available=bool(own.sale_available or norm_own.sale_available),
        )

    norm_rental = _normalize_offer('rental', rental_offer, fallback_count=rental.count)
    if norm_rental and (norm_rental.sale_available or rental.sale_available):
        rental = replace(
            rental,
            ticket_id=norm_rental.ticket_id or rental.ticket_id,
            ticket_type=norm_rental.ticket_type or rental.ticket_type,
            price=norm_rental.price if norm_rental.price is not None else rental.price,
            buy_type=norm_rental.buy_type or rental.buy_type,
            sale_available=bool(rental.sale_available or norm_rental.sale_available),
        )

    return replace(
        info,
        own=own,
        rental=rental,
        own_price=own.price,
        rental_price=rental.price,
    )


def _build_actions(info: TicketAccessInfo, parser_kind: str) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []

    def add_use_free() -> None:
        if info.free_ticket_available and info.free_ticket_type:
            actions.append(
                {
                    'key': 'use_free',
                    'kind': 'free',
                    'mode': 'use',
                    'label': 'Использовать бесплатный тикет',
                    'price': None,
                    'count': None,
                }
            )

    def add_use(variant: TicketVariant) -> None:
        if variant.count > 0 and variant.ticket_type:
            actions.append(
                {
                    'key': f'use_{variant.kind}',
                    'kind': variant.kind,
                    'mode': 'use',
                    'label': f'Использовать {_variant_title(variant.kind)}',
                    'price': None,
                    'count': variant.count,
                }
            )

    def add_buy(variant: TicketVariant) -> None:
        if variant.sale_available and variant.ticket_id and variant.buy_type:
            actions.append(
                {
                    'key': f'buy_{variant.kind}',
                    'kind': variant.kind,
                    'mode': 'buy',
                    'label': f'Купить {_variant_title(variant.kind)}',
                    'price': variant.price,
                    'count': variant.count,
                }
            )

    add_use_free()

    if parser_kind == 'novel':
        add_use(info.own)
        add_buy(info.own)
        return actions

    add_use(info.rental)
    add_use(info.own)
    add_buy(info.rental)
    add_buy(info.own)
    return actions


def _default_auto_action(payload: dict[str, Any], *, auto_buy: bool, auto_use: bool) -> str:
    actions = payload.get('actions') or []
    if not isinstance(actions, list):
        return 'skip'

    if auto_use:
        for preferred in ('use_free', 'use_rental', 'use_own'):
            for action in actions:
                if isinstance(action, dict) and action.get('key') == preferred:
                    return preferred

    if auto_buy:
        for preferred in ('buy_rental', 'buy_own'):
            for action in actions:
                if isinstance(action, dict) and action.get('key') == preferred:
                    return preferred

    return 'skip'


def ensure_product_access(
    *,
    api,
    series_id: int,
    product_id: int,
    parser_kind: str,
    log: Optional[Callable[[str], None]] = None,
    stop_flag: Optional[Callable[[], bool]] = None,
    chapter_label: str = '',
    on_choose_action: Optional[TicketActionCallback] = None,
) -> tuple[bool, TicketAccessInfo]:
    _log = log or (lambda *_: None)

    if stop_flag and stop_flag():
        raise RuntimeError('[CANCEL] Остановлено пользователем.')

    ready = api.ready_to_use_ticket(series_id, product_id) or {}
    info = parse_ticket_access_info(ready, fallback_label=chapter_label or f'product_{product_id}')

    if parser_kind == 'manhwa':
        info = _enrich_manhwa_variants_from_catalog(api, series_id, info, log=_log)

    _log(
        '[INFO] readyToUse '
        f'pid={product_id} '
        f'readAccessType={info.read_access} '
        f'title={info.chapter_label!r} '
        f'cash={info.balance} '
        f'own={info.own_count} '
        f'paidRental={info.rental_count} '
        f'ownType={info.own.ticket_type or "-"} '
        f'rentalType={info.rental.ticket_type or "-"} '
        f'freeType={info.free_ticket_type or "-"} '
        f'freeAvailable={str(info.free_ticket_available).lower()} '
        f'waitfreeBlock={str(info.waitfree_block).lower()} '
        f'waitfreeBlockCount={info.waitfree_block_count if info.waitfree_block_count is not None else "-"}'
    )

    if not info.need_ticket:
        return True, info

    actions = _build_actions(info, parser_kind)
    if not actions:
        _log('[WARN] Нет доступных free/own/rental действий для этой главы. Пропускаю.')
        return False, info

    payload = {
        'parser_kind': parser_kind,
        'series_id': int(series_id),
        'product_id': int(product_id),
        'chapter_label': info.chapter_label,
        'balance': info.balance,
        'read_access': info.read_access,
        'actions': actions,
    }
    chosen = str(on_choose_action(payload) if on_choose_action else 'skip').strip() or 'skip'
    selected = next((a for a in actions if isinstance(a, dict) and a.get('key') == chosen), None)

    if not selected:
        _log('[SKIP] Пропуск главы.')
        return False, info

    kind = str(selected.get('kind') or '').strip()
    variant = info.own if kind == 'own' else info.rental

    if selected.get('mode') == 'use':
        if kind == 'free':
            ticket_type = str(info.free_ticket_type or '').strip()
            title = 'бесплатный тикет'
        else:
            ticket_type = variant.ticket_type or ('TT01' if kind == 'own' else 'RT01')
            title = _variant_title(kind)

        try:
            used = api.use_ticket(product_id, ticket_type)
        except Exception as e:
            _log(f'[WARN] Не удалось использовать {title}: {e}')
            return False, info

        ticket_uid = str((used or {}).get('ticket_uid') or (used or {}).get('ticketUid') or '').strip()
        if ticket_uid:
            try:
                api.open_page(series_id, product_id, ticket_uid)
            except Exception as e:
                _log(f'[WARN] Не удалось выполнить open_page после использования тикета: {e}')
        _log(f'[OK] Использован {title} для {info.chapter_label}.')
        return True, info

    price = selected.get('price')
    if price is not None and info.balance is not None and int(info.balance) < int(price):
        _log(f'[SKIP] Недостаточно средств: баланс {info.balance}, цена {price}. Пропускаю.')
        return False, info

    result = api.buy_and_use_ticket(
        series_id,
        product_id,
        kind=kind,
        offer={
            'ticket_id': variant.ticket_id,
            'ticket_type': variant.ticket_type,
            'price': variant.price,
        },
        ticket_type=variant.ticket_type,
    )
    if not result.get('purchased'):
        _log(f'[WARN] Не удалось купить {_variant_title(kind)}: {result}')
        return False, info

    _log(f"[OK] Куплен {_variant_title(kind)}. Остаток: {result.get('remainCash')}")
    return True, info
