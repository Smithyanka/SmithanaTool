from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class TicketVariant:
    kind: str  # 'own' | 'rental'
    ticket_id: Optional[str]
    ticket_type: Optional[str]
    price: Optional[int]
    count: int
    buy_type: Optional[int]
    sale_available: bool


@dataclass(frozen=True)
class TicketAccessInfo:
    chapter_label: str
    read_access: str
    need_ticket: bool
    rental_count: int
    own_count: int
    balance: Optional[int]
    rental_price: Optional[int]
    own_price: Optional[int]
    free_ticket_type: Optional[str]
    free_ticket_available: bool
    waitfree_block: bool
    waitfree_block_count: Optional[int]
    own: TicketVariant
    rental: TicketVariant
    available: dict[str, Any]
    single: dict[str, Any]
    my: dict[str, Any]
    purchase: dict[str, Any]


_READ_ACCESS_MAP = {
    'RAT1': 'notpurchased',
    'RAT2': 'readable',
    'RAT3': 'expired',
    'notpurchased': 'notpurchased',
    'expired': 'expired',
    'free': 'free',
    'owned': 'owned',
    'readable': 'readable',
}


def _to_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    if value is None:
        return default
    try:
        return int(value)
    except Exception:
        return default


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _build_variant(kind: str, info: dict[str, Any], count: int) -> TicketVariant:
    ticket_id = str(info.get('ticket_id') or info.get('ticketId') or '').strip() or None
    default_ticket_type = 'TT01' if kind == 'own' else 'RT01'
    ticket_type = str(info.get('ticket_type') or info.get('ticketType') or default_ticket_type).strip() or default_ticket_type
    price = _to_int(info.get('price'))
    buy_type = 1 if kind == 'own' else 2
    sale_available = bool(ticket_id and price is not None)
    return TicketVariant(
        kind=kind,
        ticket_id=ticket_id,
        ticket_type=ticket_type,
        price=price,
        count=max(0, int(count or 0)),
        buy_type=buy_type,
        sale_available=sale_available,
    )


def parse_ticket_access_info(rtu: dict[str, Any] | None, fallback_label: str = '') -> TicketAccessInfo:
    payload = _as_dict(rtu)
    single = _as_dict(payload.get('single'))
    my = _as_dict(payload.get('my'))
    available = _as_dict(payload.get('available'))
    purchase = _as_dict(payload.get('purchase'))
    series = _as_dict(payload.get('series'))

    raw_access = str(single.get('read_access_type') or single.get('readAccessType') or '').strip()
    read_access = _READ_ACCESS_MAP.get(raw_access, raw_access.lower())
    chapter_label = str(single.get('title') or fallback_label or '').strip() or (fallback_label or '?')

    rental_count = int(_to_int(my.get('ticket_rental_count') if 'ticket_rental_count' in my else my.get('ticketRentalCount'), 0) or 0)
    own_count = int(_to_int(my.get('ticket_own_count') if 'ticket_own_count' in my else my.get('ticketOwnCount'), 0) or 0)
    balance = _to_int(my.get('cash_amount') if 'cash_amount' in my else my.get('cashAmount'))

    own_info = _as_dict(purchase.get('ticket_own') or available.get('own'))
    rental_info = _as_dict(purchase.get('ticket_rental') or available.get('rental'))

    free_ticket_type = str(
        available.get('ticket_rental_type')
        or available.get('ticketRentalType')
        or ''
    ).strip() or None
    waitfree_block = bool(single.get('waitfree_block') if 'waitfree_block' in single else single.get('waitfreeBlock'))
    waitfree_block_count = _to_int(
        series.get('waitfree_block_count') if 'waitfree_block_count' in series else series.get('waitfreeBlockCount')
    )
    free_ticket_available = bool(free_ticket_type) and not waitfree_block

    own = _build_variant('own', own_info, own_count)
    rental = _build_variant('rental', rental_info, rental_count)

    return TicketAccessInfo(
        chapter_label=chapter_label,
        read_access=read_access,
        need_ticket=read_access in ('notpurchased', 'expired', 'rat1', 'rat3'),
        rental_count=rental_count,
        own_count=own_count,
        balance=balance,
        rental_price=rental.price,
        own_price=own.price,
        free_ticket_type=free_ticket_type,
        free_ticket_available=free_ticket_available,
        waitfree_block=waitfree_block,
        waitfree_block_count=waitfree_block_count,
        own=own,
        rental=rental,
        available=available,
        single=single,
        my=my,
        purchase=purchase,
    )
