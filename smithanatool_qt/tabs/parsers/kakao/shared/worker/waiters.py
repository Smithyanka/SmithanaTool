from __future__ import annotations

import threading
from typing import Optional

BROWSER_CLOSED_NEEDLES = [
    'page.goto:',
    'net::err_aborted',
    'frame was detached',
    'page closed',
    'navigation failed because page was closed',
    'target page, context or browser has been closed',
    'execution context was destroyed',
    'no such window',
    'target closed',
    'chrome not reachable',
    'disconnected: not connected to devtools',
    'websocket disconnected',
    'invalid session id',
    'connection refused',
    'net::err_connection_closed',
    'net::err_internet_disconnected',
    'browser has been closed',
    'renderer process unavailable',
    'unknown error: cannot determine loading status',
    'session deleted because of page crash',
]


def is_browser_closed_logline(text: str) -> bool:
    s_low = (text or '').lower()
    return any(needle in s_low for needle in BROWSER_CLOSED_NEEDLES)



def browser_closed_text_if_any(err: BaseException) -> Optional[str]:
    s_low = (str(err) or '').lower()
    return 'Браузер был закрыт' if any(needle in s_low for needle in BROWSER_CLOSED_NEEDLES) else None



def wait_event_or_stop(event: threading.Event, stop_event: threading.Event, timeout: float = 0.2) -> bool:
    while not stop_event.is_set():
        if event.wait(timeout=timeout):
            return True
    return False
