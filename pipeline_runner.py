from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from article_focus import annotate_articles
from dedup import filter_new, load_seen, mark_seen, save_seen
from kanta_enrichment import enrich_digest
from rss_fetcher import fetch_articles
from selection_policy import annotate_kanta_fit_batch
from slack_sender import build_payload, send_to_slack
from sources_config import SOURCES
from summarizer import summarize_articles

ArticleSelector = Callable[[list[dict]], list[dict]]
DigestMetaBuilder = Callable[[list[dict]], dict[str, str]]


@dataclass(frozen=True)
class PipelineConfig:
    name: str
    cache_file: str
    fetch_hours: int
    message_kind: str
    briefing_mode: str
    empty_selection_message: str
    webhook_url: str | None = None
    digest_meta_builder: DigestMetaBuilder | None = None
    dry_run: bool = False
    preview_path: str | None = None
    allow_seen_backfill: bool = False
    fail_on_empty_fetch: bool = False


def env_int(name: str, default: int, minimum: int = 1) -> int:
    raw_value = os.environ.get(name)
    if raw_value in (None, ""):
        return default

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer. Current value: {raw_value!r}") from exc

    if value < minimum:
        raise RuntimeError(f"{name} must be >= {minimum}. Current value: {value}")
    return value


def env_float(name: str, default: float, minimum: float = 0.0) -> float:
    raw_value = os.environ.get(name)
    if raw_value in (None, ""):
        return default

    try:
        value = float(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number. Current value: {raw_value!r}") from exc

    if value < minimum:
        raise RuntimeError(f"{name} must be >= {minimum}. Current value: {value}")
    return value


def require_env_vars(*names: str) -> None:
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


def first_env_value(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def write_preview(payload: dict, preview_path: str | None, logger: logging.Logger) -> None:
    if not preview_path:
        return

    preview_file = Path(preview_path)
    preview_file.parent.mkdir(parents=True, exist_ok=True)
    preview_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Saved preview to %s", preview_file)


def run_pipeline(
    *,
    config: PipelineConfig,
    select_articles: ArticleSelector,
    logger: logging.Logger,
) -> int:
    logger.info("%s started", config.name)

    seen_urls = load_seen(config.cache_file)
    articles = annotate_kanta_fit_batch(annotate_articles(fetch_articles(SOURCES, hours=config.fetch_hours)))
    logger.info("Fetched %d articles", len(articles))

    if not articles:
        logger.error("Fetched 0 articles for %s", config.name)
        if config.fail_on_empty_fetch:
            return 1
        return 0

    new_articles = filter_new(articles, seen_urls)
    skipped_count = len(articles) - len(new_articles)
    logger.info("New articles: %d (skipped duplicates: %d)", len(new_articles), skipped_count)

    selection_pool = new_articles
    used_seen_backfill = False

    if not new_articles:
        if not config.allow_seen_backfill:
            logger.info("No new articles found. Exiting.")
            return 0

        logger.warning("No new articles found. Falling back to recently fetched articles.")
        selection_pool = articles
        used_seen_backfill = True

    selected_articles = select_articles(selection_pool)
    if not selected_articles and config.allow_seen_backfill and selection_pool is not articles:
        logger.warning("Selection from new articles was empty. Falling back to recently fetched articles.")
        selected_articles = select_articles(articles)
        used_seen_backfill = True

    if not selected_articles:
        logger.info(config.empty_selection_message)
        return 0

    logger.info(
        "Selected %d articles for %s%s",
        len(selected_articles),
        config.message_kind,
        " (seen backfill)" if used_seen_backfill else "",
    )

    digest = summarize_articles(selected_articles, briefing_mode=config.briefing_mode)
    digest = enrich_digest(digest)
    digest_meta = dict(digest.get("meta", {}))
    digest_meta["message_kind"] = config.message_kind
    if used_seen_backfill:
        digest_meta["selection_mode"] = "seen_backfill"
    if config.digest_meta_builder:
        digest_meta.update(config.digest_meta_builder(selected_articles))
    digest["meta"] = digest_meta

    headline_suffix = str(digest_meta.get("headline_suffix", "")).strip()
    payload = build_payload(digest, message_kind=config.message_kind, headline_suffix=headline_suffix)
    payload["meta"] = digest_meta
    write_preview(payload, config.preview_path, logger)

    if config.dry_run:
        logger.info("Dry run enabled. Slack delivery skipped.")
        logger.info("Preview headline: %s", payload.get("text", ""))
        return 0

    success = send_to_slack(
        digest,
        webhook_url=config.webhook_url,
        message_kind=config.message_kind,
        headline_suffix=headline_suffix,
    )
    if not success:
        logger.error("Slack delivery failed")
        return 1

    updated_seen = mark_seen(selected_articles, seen_urls)
    save_seen(updated_seen, config.cache_file)
    logger.info("Slack delivery completed")
    return 0
