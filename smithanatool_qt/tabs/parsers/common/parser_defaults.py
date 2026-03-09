from __future__ import annotations

import os


def default_thread_count(*, min_threads: int = 2, max_threads: int = 32) -> int:
    cpu_count = os.cpu_count() or 4
    value = max(min_threads, cpu_count // 2 or min_threads)
    return max(min_threads, min(max_threads, value))
