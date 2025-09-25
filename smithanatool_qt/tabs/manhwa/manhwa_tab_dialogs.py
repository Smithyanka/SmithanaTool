import re
from typing import Optional
from PySide6.QtWidgets import QMessageBox, QWidget

def show_use_ticket_dialog(parent: QWidget, rental_count: int, own_count: int, balance: Optional[int], chapter_label: str) -> bool:
    def _extract_num(label: str) -> str:
        m = re.search(r'(\d+)\s*화|#\s*(\d+)|глава\s*(\d+)', (label or '').lower())
        for g in (1, 2, 3):
            if m and m.group(g):
                return m.group(g)
        return label or "?"

    ch_no = _extract_num(chapter_label)
    bal_txt = f"{balance} кредитов" if balance is not None else "—"
    msg = (
        f"Глава недоступна\n"
        f"Номер: {ch_no}\n"
        f"Название: {chapter_label}\n\n"
        f"Доступные тикеты:\n"
        f" • Аренда: {rental_count} шт\n"
        f" • Владение: {own_count} шт\n"
        f"Баланс: {bal_txt}\n\n"
        f"Использовать тикет аренды для этой главы?"
    )
    return QMessageBox.question(
        parent, "Глава недоступна",
        msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
    ) == QMessageBox.Yes


def show_purchase_ticket_dialog(parent: QWidget, price: Optional[int], balance: Optional[int]) -> bool:
    """Показывает окно покупки тикета.
    Возвращает True, если пользователь подтвердил покупку.
    """
    price_txt = f"{int(price)} кредитов" if isinstance(price, int) or (isinstance(price, str) and price.isdigit()) else "не удалось определить"
    bal_txt = f"{int(balance)} кредитов" if (balance is not None) else "—"
    msg = (
        "Отсутствуют доступные тикеты\n\n"
        f"Цена: {price_txt}\n"
        f"Баланс: {bal_txt}\n\n"
        "Купить тикет?"
    )
    return QMessageBox.question(
        parent, "Покупка тикета",
        msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No
    ) == QMessageBox.Yes
