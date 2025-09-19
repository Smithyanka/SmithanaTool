# -*- coding: utf-8 -*-

# Юзер-агент для запросов (Playwright и HTTP-загрузок)
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Ограничение ширины изображений при сохранении (0 = не изменять)
MAX_IMG_WIDTH = 720

# Возможные контейнеры с контентом на странице
POSSIBLE_CONTAINERS = [
    'div.mx-auto[style*="max-width: 720px"]',
    'main div[class*="mx-auto"][class*="max-w"]',
    'div[data-viewer="true"]',
    'div#__next main div[class*="mx-auto"]',
    'article',
    'main',
]

# Селекторы для поиска картинок и фоновых изображений
IMG_SELECTORS = [
    "img[src]",
    "img[data-src]",
    "source[srcset]",
    "img[srcset]",
    "[style*='background-image']",
]
