from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

CACHE_FILE = 'seen_articles.json'
MAX_CACHE_SIZE = 500
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "source",
    "trk",
}

logger = logging.getLogger('dedup')


def _is_tracking_query_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized.startswith("utm_") or normalized in TRACKING_QUERY_KEYS


def canonicalize_article_url(url: str) -> str | None:
    if not isinstance(url, str):
        return None

    cleaned = url.strip()
    if not cleaned:
        return None

    split = urlsplit(cleaned)
    if not split.scheme or not split.netloc:
        return cleaned

    scheme = split.scheme.lower()
    hostname = (split.hostname or "").lower()
    if not hostname:
        return cleaned

    port = split.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{hostname}:{port}"
    else:
        netloc = hostname

    path = split.path or ""
    if path and path != "/":
        path = path.rstrip("/")

    query_pairs = []
    for key, value in parse_qsl(split.query, keep_blank_values=True):
        if _is_tracking_query_key(key):
            continue
        query_pairs.append((key, value))
    query_pairs.sort()
    query = urlencode(query_pairs, doseq=True)

    return urlunsplit((scheme, netloc, path, query, ""))


def _normalize_seen_urls(urls: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()

    for url in reversed(list(urls)):
        cleaned = canonicalize_article_url(url)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)

    normalized.reverse()
    return normalized[-MAX_CACHE_SIZE:]


def load_seen(cache_file: str = CACHE_FILE) -> list[str]:
    if not os.path.exists(cache_file):
        return []

    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        logger.warning('Failed to load seen cache from %s', cache_file)
        return []

    if not isinstance(data, list):
        return []

    return _normalize_seen_urls(data)


def save_seen(seen: Iterable[str], cache_file: str = CACHE_FILE) -> None:
    limited_seen = _normalize_seen_urls(seen)
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(limited_seen, f, ensure_ascii=False)
    except OSError:
        logger.warning('Failed to save seen cache to %s', cache_file)


def filter_new(articles: list[dict], seen: Iterable[str]) -> list[dict]:
    seen_urls = set(_normalize_seen_urls(seen))
    filtered: list[dict] = []
    for article in articles:
        cleaned = canonicalize_article_url(article.get('url'))
        if not cleaned or cleaned in seen_urls:
            continue
        filtered.append(article)
    return filtered


def mark_seen(articles: list[dict], seen: Iterable[str]) -> list[str]:
    updated_seen = _normalize_seen_urls(seen)
    seen_urls = set(updated_seen)
    for article in articles:
        cleaned = canonicalize_article_url(article.get('url'))
        if not cleaned or cleaned in seen_urls:
            continue
        seen_urls.add(cleaned)
        updated_seen.append(cleaned)
    return updated_seen[-MAX_CACHE_SIZE:]


def dedupe_articles_by_url(articles: list[dict], seen_urls: set[str]) -> list[dict]:
    deduped: list[dict] = []
    for article in articles:
        normalized_url = canonicalize_article_url(article.get("url"))
        if not normalized_url or normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        if normalized_url != article.get("url"):
            article = {**article, "url": normalized_url}
        deduped.append(article)
    return deduped
