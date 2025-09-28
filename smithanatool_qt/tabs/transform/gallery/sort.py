from __future__ import annotations
from ..common import natural_key, mtime_key

# Единая точка сортировки
def apply_sort(files: list[str], field_text: str, order_text: str, added_order: dict[str, int]) -> list[str]:
    reverse = (order_text == "По убыванию")
    if field_text == "По названию":
        key_fn = natural_key
    elif field_text == "По добавлению":
        key_fn = lambda p: added_order.get(p, float("inf"))
    else:
        key_fn = mtime_key
    return sorted(files, key=key_fn, reverse=reverse)
