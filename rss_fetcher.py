import feedparser
from datetime import datetime, timezone, timedelta
import logging
import re
import socket
import time

logger = logging.getLogger("rss_fetcher")
logger.addHandler(logging.NullHandler())


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
    cleaned = re.sub(r"<[^>]+>", "", text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def fetch_articles(sources: list[dict], hours: int = 24) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    articles: list[dict] = []
    seen_urls: set[str] = set()

    for source in sources:
        source_name = source.get("name", "")
        source_url = source.get("url", "")
        category = source.get("category")
        priority = source.get("priority")

        if not source_url:
            logger.warning("Skipping source '%s': missing URL", source_name)
            continue

        previous_timeout = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(10)
            feed = feedparser.parse(source_url)
        except Exception as exc:
            logger.warning("Failed to fetch source '%s' (%s): %s", source_name, source_url, exc)
            continue
        finally:
            socket.setdefaulttimeout(previous_timeout)

        if getattr(feed, "bozo", False):
            err = getattr(feed, "bozo_exception", None)
            if err:
                logger.warning("Feed parse issue for '%s' (%s): %s", source_name, source_url, err)
            else:
                logger.warning("Feed parse issue for '%s' (%s)", source_name, source_url)

        for entry in getattr(feed, "entries", []):
            published = _parse_date(entry)
            if not published or published < cutoff:
                continue

            url = getattr(entry, "link", None)
            if not url and hasattr(entry, "get"):
                url = entry.get("link")

            if not url or url in seen_urls:
                continue

            seen_urls.add(url)

            title = getattr(entry, "title", None)
            if title is None and hasattr(entry, "get"):
                title = entry.get("title", "")

            summary = getattr(entry, "summary", None)
            if summary is None and hasattr(entry, "get"):
                summary = entry.get("summary", "")

            articles.append(
                {
                    "title": title or "",
                    "url": url,
                    "summary": _strip_html(summary or ""),
                    "published": published,
                    "source_name": source_name,
                    "category": category,
                    "priority": priority,
                }
            )

    return articles
