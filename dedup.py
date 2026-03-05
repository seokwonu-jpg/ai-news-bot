import json
import os
import logging

CACHE_FILE = 'seen_articles.json'
MAX_CACHE_SIZE = 500

logger = logging.getLogger('dedup')


def load_seen() -> set:
    if not os.path.exists(CACHE_FILE):
        return set()

    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        logger.warning('Failed to load seen cache from %s', CACHE_FILE)
        return set()

    if not isinstance(data, list):
        return set()

    return {url for url in data if isinstance(url, str)}


def save_seen(seen: set) -> None:
    limited_seen = list(seen)[-MAX_CACHE_SIZE:]
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(limited_seen, f)
    except OSError:
        logger.warning('Failed to save seen cache to %s', CACHE_FILE)


def filter_new(articles: list, seen: set) -> list:
    return [article for article in articles if article.get('url') not in seen]


def mark_seen(articles: list, seen: set) -> set:
    updated_seen = set(seen)
    for article in articles:
        url = article.get('url')
        if isinstance(url, str):
            updated_seen.add(url)
    return updated_seen
