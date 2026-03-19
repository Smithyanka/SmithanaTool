from __future__ import annotations

from typing import Callable, Optional

from smithanatool_qt.tabs.transform.sections.stitch.service import (
    auto_stitch_chapter
)


def _auto_stitch_chapter(
    chapter_dir: str,
    *,
    auto_cfg: dict,
    log=None,
    stop_flag: Optional[Callable[[], bool]] = None,
):
    """Тонкая обёртка над общим backend автосклейки.

    Используется манхва-парсером после скачивания изображений главы.
    Вся логика режимов count / height / smart живёт в transform.sections.stitch.service.
    """
    return auto_stitch_chapter(
        chapter_dir,
        auto_cfg=auto_cfg,
        log=log,
        stop_flag=stop_flag,
    )
