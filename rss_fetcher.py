from __future__ import annotations

import html
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import feedparser
import requests

logger = logging.getLogger("rss_fetcher")
logger.addHandler(logging.NullHandler())

_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/133.0.0.0 Safari/537.36"
    )
}
_FEED_LINK_PATTERN = re.compile(
    r'<link[^>]+type=["\'](?:application/rss\+xml|application/atom\+xml|application/xml|text/xml)["\'][^>]+href=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_HTML_LISTING_PATTERNS = {
    "anthropic_news": re.compile(r'href=["\'](/news/[^"#?]+)["\']', re.IGNORECASE),
    "runway_blog": re.compile(r'href=["\'](/(?:news|research)/[^"#?]+)["\']', re.IGNORECASE),
}
_TITLE_TAG_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_DATE_PATTERNS = [
    (
        re.compile(
            r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b"
        ),
        lambda raw: datetime.strptime(raw, "%B %d, %Y").replace(tzinfo=timezone.utc),
    ),
    (
        re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+\d{1,2},\s+\d{4}\b"),
        lambda raw: datetime.strptime(raw.replace(".", "").replace("Sept", "Sep"), "%b %d, %Y").replace(
            tzinfo=timezone.utc
        ),
    ),
    (
        re.compile(r"\b\d{1,2}/\d{1,2}/\d{2}\b"),
        lambda raw: datetime.strptime(raw, "%m/%d/%y").replace(tzinfo=timezone.utc),
    ),
    (
        re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
        lambda raw: datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc),
    ),
]


def _parse_date(entry) -> datetime | None:
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not parsed and hasattr(entry, "get"):
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")

    if not parsed:
        return None

    try:
        if isinstance(parsed, time.struct_time):
            return datetime(*parsed[:6], tzinfo=timezone.utc)
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    except Exception as exc:
        logger.warning("Unable to parse entry date: %s", exc)
        return None


def _strip_html(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _sanitize_feed_bytes(content: bytes) -> bytes:
    return re.sub(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]", b"", content)


def _discover_feed_url(page_html: str, source_url: str) -> str | None:
    match = _FEED_LINK_PATTERN.search(page_html)
    if not match:
        return None
    href = html.unescape(match.group(1).strip())
    return urljoin(source_url, href)


def _load_feed(source_url: str):
    response = requests.get(source_url, headers=_REQUEST_HEADERS, timeout=15)
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "").lower()
    content = _sanitize_feed_bytes(response.content)

    if "html" in content_type:
        discovered_url = _discover_feed_url(response.text, source_url)
        if discovered_url:
            discovered_response = requests.get(discovered_url, headers=_REQUEST_HEADERS, timeout=15)
            discovered_response.raise_for_status()
            content = _sanitize_feed_bytes(discovered_response.content)
            return feedparser.parse(content)

    return feedparser.parse(content)


def _extract_content_text(entry) -> str:
    candidates: list[str] = []

    if hasattr(entry, "get"):
        for field in ("summary", "description", "subtitle"):
            value = entry.get(field)
            if isinstance(value, str):
                candidates.append(value)

    content_items = getattr(entry, "content", None)
    if content_items is None and hasattr(entry, "get"):
        content_items = entry.get("content")

    if isinstance(content_items, list):
        for item in content_items:
            value = None
            if isinstance(item, dict):
                value = item.get("value")
            else:
                value = getattr(item, "value", None)
            if isinstance(value, str):
                candidates.append(value)

    unique_chunks: list[str] = []
    seen_chunks: set[str] = set()
    for chunk in candidates:
        cleaned = _strip_html(chunk)
        if not cleaned:
            continue
        normalized = cleaned.lower()
        if normalized in seen_chunks:
            continue
        seen_chunks.add(normalized)
        unique_chunks.append(cleaned)

    return " ".join(unique_chunks)[:4000]


def _extract_keywords(entry) -> list[str]:
    tags = getattr(entry, "tags", None)
    if tags is None and hasattr(entry, "get"):
        tags = entry.get("tags")

    keywords: list[str] = []
    if not isinstance(tags, list):
        return keywords

    seen: set[str] = set()
    for tag in tags:
        term = None
        if isinstance(tag, dict):
            term = tag.get("term")
        else:
            term = getattr(tag, "term", None)

        if not isinstance(term, str):
            continue

        cleaned = _strip_html(term)
        normalized = cleaned.lower()
        if not cleaned or normalized in seen:
            continue

        seen.add(normalized)
        keywords.append(cleaned)

    return keywords[:10]


def _extract_meta_content(page_html: str, names: list[str]) -> str:
    for name in names:
        escaped_name = re.escape(name)
        patterns = [
            re.compile(
                rf'<meta[^>]+(?:property|name)=["\']{escaped_name}["\'][^>]+content=["\']([^"\']+)["\']',
                re.IGNORECASE,
            ),
            re.compile(
                rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{escaped_name}["\']',
                re.IGNORECASE,
            ),
        ]
        for pattern in patterns:
            match = pattern.search(page_html)
            if match:
                return _strip_html(html.unescape(match.group(1)))
    return ""


def _extract_title_from_page(page_html: str) -> str:
    title = _extract_meta_content(page_html, ["og:title", "twitter:title"])
    if title:
        return title

    match = _TITLE_TAG_PATTERN.search(page_html)
    if not match:
        return ""
    return _strip_html(html.unescape(match.group(1)))


def _clean_title(title: str, source_name: str) -> str:
    cleaned = title.strip()
    if "|" not in cleaned:
        return cleaned

    parts = [part.strip() for part in cleaned.split("|") if part.strip()]
    if len(parts) < 2:
        return cleaned

    source_root = source_name.split()[0].lower()
    if source_root in parts[0].lower():
        return parts[-1]
    if source_root in parts[-1].lower():
        return parts[0]
    return cleaned


def _parse_date_from_text(text: str) -> datetime | None:
    candidates: list[tuple[int, str, callable]] = []
    for pattern, parser in _DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            candidates.append((match.start(), match.group(0), parser))

    if not candidates:
        return None

    _, raw_value, parser = min(candidates, key=lambda item: item[0])
    try:
        return parser(raw_value)
    except ValueError:
        return None


def _extract_listing_urls(
    page_html: str,
    source_url: str,
    parser_name: str,
    limit: int,
    listing_patterns: list[str] | None = None,
) -> list[str]:
    if listing_patterns:
        patterns = [re.compile(pattern, re.IGNORECASE) for pattern in listing_patterns]
    else:
        pattern = _HTML_LISTING_PATTERNS.get(parser_name)
        if pattern is None:
            raise ValueError(f"Unsupported listing parser: {parser_name}")
        patterns = [pattern]

    urls: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        for match in pattern.finditer(page_html):
            article_url = urljoin(source_url, html.unescape(match.group(1).strip()))
            article_url = article_url.split("#", 1)[0]
            if article_url in seen:
                continue
            if parser_name == "runway_blog" and article_url.endswith("/research/publications"):
                continue
            seen.add(article_url)
            urls.append(article_url)
            if len(urls) >= limit:
                return urls
    return urls


def _parse_html_listing_article(article_url: str, source: dict) -> dict | None:
    response = requests.get(article_url, headers=_REQUEST_HEADERS, timeout=20)
    response.raise_for_status()

    page_html = response.text
    title = _clean_title(_extract_title_from_page(page_html), source.get("name", ""))
    summary = _extract_meta_content(page_html, ["description", "og:description", "twitter:description"])
    published = _parse_date_from_text(_strip_html(page_html[:50000])) or _parse_date_from_text(page_html)

    if not title or not published:
        return None

    content_text = summary or title
    return {
        "title": title,
        "url": article_url,
        "summary": summary,
        "content_text": content_text[:4000],
        "keywords": [],
        "published": published,
        "source_name": source.get("name", ""),
        "category": source.get("category"),
        "priority": source.get("priority"),
    }


def _collect_html_listing_articles(source: dict) -> list[dict]:
    source_url = source.get("url", "")
    parser_name = source.get("listing_parser", "")
    limit = int(source.get("listing_limit", 12))

    response = requests.get(source_url, headers=_REQUEST_HEADERS, timeout=20)
    response.raise_for_status()

    article_urls = _extract_listing_urls(
        response.text,
        source_url,
        parser_name,
        limit=limit,
        listing_patterns=source.get("listing_patterns"),
    )
    articles: list[dict] = []
    for article_url in article_urls:
        try:
            article = _parse_html_listing_article(article_url, source)
        except Exception as exc:
            logger.warning("Failed to fetch HTML article '%s' for '%s': %s", article_url, source.get("name", ""), exc)
            continue

        if article:
            articles.append(article)

    return articles


def _filter_articles_by_cutoff(articles: list[dict], cutoff: datetime) -> list[dict]:
    return [
        article
        for article in articles
        if isinstance(article.get("published"), datetime) and article["published"] >= cutoff
    ]


def _feed_to_articles(feed, source: dict, cutoff: datetime) -> list[dict]:
    articles: list[dict] = []
    for entry in getattr(feed, "entries", []):
        published = _parse_date(entry)
        if not published or published < cutoff:
            continue

        url = getattr(entry, "link", None)
        if not url and hasattr(entry, "get"):
            url = entry.get("link")
        if not url:
            continue

        title = getattr(entry, "title", None)
        if title is None and hasattr(entry, "get"):
            title = entry.get("title", "")

        summary = getattr(entry, "summary", None)
        if summary is None and hasattr(entry, "get"):
            summary = entry.get("summary", "")

        content_text = _extract_content_text(entry)
        if not content_text:
            content_text = _strip_html(summary or "")

        articles.append(
            {
                "title": title or "",
                "url": url,
                "summary": _strip_html(summary or ""),
                "content_text": content_text,
                "keywords": _extract_keywords(entry),
                "published": published,
                "source_name": source.get("name", ""),
                "category": source.get("category"),
                "priority": source.get("priority"),
            }
        )

    return articles


def _dedupe_articles(articles: list[dict], seen_urls: set[str]) -> list[dict]:
    deduped: list[dict] = []
    for article in articles:
        url = article.get("url")
        if not isinstance(url, str) or url in seen_urls:
            continue
        seen_urls.add(url)
        deduped.append(article)
    return deduped


def fetch_articles(sources: list[dict], hours: int = 24) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    articles: list[dict] = []
    seen_urls: set[str] = set()

    for source in sources:
        source_name = source.get("name", "")
        source_url = source.get("url", "")
        fetch_mode = source.get("fetch_mode", "feed")

        if not source_url:
            logger.warning("Skipping source '%s': missing URL", source_name)
            continue

        try:
            if fetch_mode == "html_listing":
                source_articles = _filter_articles_by_cutoff(_collect_html_listing_articles(source), cutoff)
            else:
                feed = _load_feed(source_url)
                if getattr(feed, "bozo", False):
                    err = getattr(feed, "bozo_exception", None)
                    if err:
                        logger.warning("Feed parse issue for '%s' (%s): %s", source_name, source_url, err)
                    else:
                        logger.warning("Feed parse issue for '%s' (%s)", source_name, source_url)
                source_articles = _feed_to_articles(feed, source, cutoff)
        except Exception as exc:
            logger.warning("Failed to fetch source '%s' (%s): %s", source_name, source_url, exc)
            continue

        articles.extend(_dedupe_articles(source_articles, seen_urls))

    return articles


def inspect_source(source: dict, hours: int = 24) -> dict:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    freshness_hours = max(hours, int(source.get("freshness_hours", hours)))
    freshness_cutoff = now - timedelta(hours=freshness_hours)
    source_name = source.get("name", "")
    source_url = source.get("url", "")
    fetch_mode = source.get("fetch_mode", "feed")

    result = {
        "name": source_name,
        "url": source_url,
        "category": source.get("category"),
        "priority": source.get("priority"),
        "status": "ok",
        "entries": 0,
        "recent_entries": 0,
        "latest_published": None,
        "bozo": False,
        "error": "",
    }

    if not source_url:
        result["status"] = "error"
        result["error"] = "missing URL"
        return result

    try:
        if fetch_mode == "html_listing":
            articles = _collect_html_listing_articles(source)
            result["entries"] = len(articles)
            if not articles:
                result["status"] = "empty"
                return result

            latest_published = max((article.get("published") for article in articles), default=None)
            recent_entries = sum(
                1
                for article in articles
                if isinstance(article.get("published"), datetime) and article["published"] >= cutoff
            )
            result["recent_entries"] = recent_entries
            result["latest_published"] = latest_published.isoformat() if latest_published else None

            if latest_published is None:
                result["status"] = "undated"
            elif latest_published < freshness_cutoff:
                result["status"] = "stale"
            return result

        feed = _load_feed(source_url)
    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)
        return result

    result["bozo"] = bool(getattr(feed, "bozo", False))
    entries = list(getattr(feed, "entries", []))
    result["entries"] = len(entries)

    if not entries:
        result["status"] = "empty"
        return result

    latest_published: datetime | None = None
    recent_entries = 0
    for entry in entries:
        published = _parse_date(entry)
        if not published:
            continue
        if latest_published is None or published > latest_published:
            latest_published = published
        if published >= cutoff:
            recent_entries += 1

    result["recent_entries"] = recent_entries
    result["latest_published"] = latest_published.isoformat() if latest_published else None

    if latest_published is None:
        result["status"] = "undated"
    elif latest_published < freshness_cutoff:
        result["status"] = "stale"

    return result


def inspect_sources(sources: list[dict], hours: int = 24) -> list[dict]:
    return [inspect_source(source, hours=hours) for source in sources]
