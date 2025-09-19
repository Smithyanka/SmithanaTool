# -*- coding: utf-8 -*-
"""Современная модульная версия: публичный API сохранён.
Экспортируем только run_novel_parser из .runner.
"""

from .runner import run_novel_parser

__all__ = ['run_novel_parser']

