from __future__ import annotations

import re
from typing import Any

from PySide6.QtWidgets import QMessageBox, QPushButton, QWidget



def _extract_chapter_number(label: str) -> str:
    m = re.search(r'(\d+)\s*화|#\s*(\d+)|глава\s*(\d+)', (label or '').lower())
    for idx in (1, 2, 3):
        if m and m.group(idx):
            return m.group(idx)
    return label or '?'



def _format_price(value: Any) -> str:
    if value is None:
        return '—'
    try:
        return f'{int(value)} кредитов'
    except Exception:
        return str(value)



def _show_choice_box(
    parent: QWidget,
    *,
    title: str,
    lines: list[str],
    button_specs: list[tuple[str, str]],
    default_key: str = 'skip',
) -> str:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Question)
    box.setWindowTitle(title)
    box.setText('\n'.join(lines))

    buttons: dict[QPushButton, str] = {}
    default_button = None
    for text, key in button_specs:
        btn = box.addButton(text, QMessageBox.ActionRole)
        buttons[btn] = key
        if key == default_key:
            default_button = btn

    if default_button is not None:
        box.setDefaultButton(default_button)

    box.exec()
    clicked = box.clickedButton()
    return buttons.get(clicked, 'skip')



def _build_common_lines(chapter_label: str, balance: Any) -> list[str]:
    ch_no = _extract_chapter_number(chapter_label)
    return [
        'Глава недоступна',
        f'Номер: {ch_no}',
        f'Название: {chapter_label}',
        f'Баланс: {_format_price(balance)}',
        '',
    ]



def _purchase_label_text(offer: dict) -> str:
    kind = str(offer.get('kind') or '')
    price = offer.get('price')

    if kind == 'rental':
        base = 'Тикет аренды'
    elif kind == 'own':
        base = 'Тикет навсегда'
    else:
        base = 'Тикет'

    if price is not None:
        return f'{base} — {price} кредитов'
    return base


def _purchase_button_text(offer: dict) -> str:
    kind = str(offer.get('kind') or '')

    if kind == 'rental':
        return 'Тикет аренды'
    if kind == 'own':
        return 'Тикет навсегда'
    return 'Тикет'


def show_ticket_action_dialog(parent: QWidget, payload: dict[str, Any]) -> str:
    chapter_label = str(payload.get('chapter_label') or '')
    balance = payload.get('balance')
    actions = payload.get('actions') or []
    parser_kind = str(payload.get('parser_kind') or '').strip()

    action_map = {
        str(action.get('key') or '').strip(): action
        for action in actions
        if isinstance(action, dict)
    }

    if parser_kind == 'novel':
        lines = _build_common_lines(chapter_label, balance)
        lines.append('Выберите действие:')
        for key in ('use_free', 'use_own', 'buy_own'):
            action = action_map.get(key)
            if not action:
                continue

            label = str(action.get('label') or key)
            if key == 'buy_own':
                label = 'Купить тикет'

            suffix = []
            if action.get('count') is not None:
                suffix.append(f'доступно: {action.get("count")}')
            if action.get('price') is not None:
                suffix.append(f'цена: {_format_price(action.get("price"))}')
            lines.append(f'• {label}' + (f' ({", ".join(suffix)})' if suffix else ''))
        button_specs: list[tuple[str, str]] = []
        if 'use_free' in action_map:
            button_specs.append(('Бесплатный тикет', 'use_free'))
        if 'use_own' in action_map:
            button_specs.append(('Использовать тикет', 'use_own'))
        if 'buy_own' in action_map:
            button_specs.append(('Купить', 'buy_own'))
        button_specs.append(('Отмена', 'skip'))
        return _show_choice_box(
            parent,
            title='Тикеты',
            lines=lines,
            button_specs=button_specs,
            default_key='skip',
        )

    use_free = action_map.get('use_free')
    use_rental = action_map.get('use_rental')
    use_own = action_map.get('use_own')
    buy_rental = action_map.get('buy_rental')
    buy_own = action_map.get('buy_own')
    has_use = bool(use_free or use_rental or use_own)

    if has_use:
        lines = _build_common_lines(chapter_label, balance)
        lines.append('Выберите действие:')
        if use_free:
            lines.append('• Бесплатный тикет')
        if use_rental:
            lines.append(f'• Тикет аренды (доступно: {use_rental.get("count")})')
        if use_own:
            lines.append(f'• Тикет навсегда (доступно: {use_own.get("count")})')
        if buy_rental or buy_own:
            lines.append('• Купить')

        first_buttons = []
        if use_free:
            first_buttons.append(('Бесплатный тикет', 'use_free'))
        if buy_rental or buy_own:
            first_buttons.append(('Купить', '__open_purchase__'))
        if use_rental:
            first_buttons.append(('Тикет аренды', 'use_rental'))
        if use_own:
            first_buttons.append(('Тикет навсегда', 'use_own'))
        first_buttons.append(('Отмена', 'skip'))

        first_choice = _show_choice_box(
            parent,
            title='Тикеты / действие по главе',
            lines=lines,
            button_specs=first_buttons,
            default_key='skip',
        )
        if first_choice != '__open_purchase__':
            return first_choice

    purchase_actions: list[dict[str, Any]] = []
    if buy_rental:
        purchase_actions.append(buy_rental)
    if buy_own:
        purchase_actions.append(buy_own)

    if not purchase_actions:
        return 'skip'

    lines = _build_common_lines(chapter_label, balance)
    lines.append('Выберите тикет для покупки:')
    for action in purchase_actions:
        lines.append(f'• {_purchase_label_text(action)}')

    button_specs: list[tuple[str, str]] = []
    if buy_rental:
        button_specs.append((_purchase_button_text(buy_rental), 'buy_rental'))
    if buy_own:
        button_specs.append((_purchase_button_text(buy_own), 'buy_own'))
    button_specs.append(('Отмена', 'skip'))

    return _show_choice_box(
        parent,
        title='Тикеты',
        lines=lines,
        button_specs=button_specs,
        default_key='skip',
    )
