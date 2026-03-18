from __future__ import annotations

import argparse
import logging
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from alert_rules import DEFAULT_MAX_ALERTS, DEFAULT_MIN_ALERT_SCORE, select_alert_articles
from article_focus import annotate_articles, get_focus_bucket
from curator import score_articles
from kanta_enrichment import enrich_digest
from rss_fetcher import fetch_articles
from selection_policy import annotate_kanta_fit_batch, filter_alert_candidates, filter_daily_candidates
from sources_config import SOURCES
from summarizer import summarize_articles

LOGGER = logging.getLogger("compare_summary_models")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare summary outputs across Gemini models.")
    parser.add_argument("--briefing-mode", choices=("daily", "alert"), default="daily")
    parser.add_argument("--hours", type=int, default=None, help="Lookback window. Defaults to 24 for daily, 12 for alert.")
    parser.add_argument("--top-n", type=int, default=3, help="Number of selected articles to compare.")
    parser.add_argument("--baseline-model", default=None, help="Default: current GEMINI_SUMMARIZER_MODEL or GEMINI_MODEL.")
    parser.add_argument("--candidate-model", default="gemini-2.5-pro", help="Model to compare against the baseline.")
    parser.add_argument(
        "--output",
        default=None,
        help="Optional markdown output path. Defaults to reports/summary_ab_<timestamp>.md",
    )
    return parser.parse_args()


def _default_hours(briefing_mode: str) -> int:
    return 12 if briefing_mode == "alert" else 24


@contextmanager
def _temporary_env(name: str, value: str | None):
    sentinel = object()
    previous = os.environ.get(name, sentinel)
    try:
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
        yield
    finally:
        if previous is sentinel:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


def _select_articles(briefing_mode: str, hours: int, top_n: int) -> list[dict]:
    articles = annotate_kanta_fit_batch(annotate_articles(fetch_articles(SOURCES, hours=hours)))
    LOGGER.info("Fetched %d articles for comparison", len(articles))

    if briefing_mode == "alert":
        return select_alert_articles(
            filter_alert_candidates(articles),
            max_items=max(1, top_n),
            min_score=DEFAULT_MIN_ALERT_SCORE,
        )

    return score_articles(filter_daily_candidates(articles), top_n=max(1, top_n))


def _run_summary(articles: list[dict], briefing_mode: str, model_name: str | None) -> dict:
    with _temporary_env("GEMINI_SUMMARIZER_MODEL", model_name):
        digest = summarize_articles(articles, briefing_mode=briefing_mode)
    digest = enrich_digest(digest)
    digest_meta = dict(digest.get("meta", {}))
    digest_meta["comparison_model"] = model_name or os.getenv("GEMINI_SUMMARIZER_MODEL") or os.getenv("GEMINI_MODEL", "")
    digest["meta"] = digest_meta
    return digest


def _article_heading(article: dict, index: int) -> str:
    title = str(article.get("title") or article.get("translated_title") or "Untitled").strip()
    source = str(article.get("source_name", "")).strip() or "-"
    focus = get_focus_bucket(article)
    return f"## {index + 1}. {title}\n`source: {source} | focus: {focus}`"


def _overview_section(label: str, digest: dict) -> str:
    overview = digest.get("overview", {})
    market_summary = str(overview.get("market_summary", "")).strip() or "-"
    action_items = [str(item).strip() for item in overview.get("action_items", []) if str(item).strip()]

    lines = [f"### {label}", f"> {market_summary}"]
    if action_items:
        lines.append("")
        lines.extend(f"- {item}" for item in action_items[:3])
    return "\n".join(lines)


def _article_section(label: str, article: dict) -> str:
    translated_title = str(article.get("translated_title") or article.get("title") or "-").strip()
    korean_summary = str(article.get("korean_summary", "")).strip() or "-"
    why_it_matters = str(article.get("why_it_matters", "")).strip() or "-"
    practical_tip = str(article.get("practical_tip", "")).strip() or "-"
    kanta_angle = str(article.get("kanta_angle", "")).strip() or "-"

    lines = [
        f"### {label}",
        f"- title: {translated_title}",
        f"- summary: {korean_summary}",
        f"- why: {why_it_matters}",
        f"- action: {practical_tip}",
        f"- kanta: {kanta_angle}",
    ]
    return "\n".join(lines)


def _build_report(
    *,
    baseline_model: str,
    candidate_model: str,
    baseline_digest: dict,
    candidate_digest: dict,
    briefing_mode: str,
) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    baseline_articles = baseline_digest.get("articles", [])
    candidate_articles = candidate_digest.get("articles", [])

    lines = [
        "# Summary Model A/B Test",
        "",
        f"- timestamp: {timestamp}",
        f"- briefing_mode: {briefing_mode}",
        f"- baseline_model: {baseline_model}",
        f"- candidate_model: {candidate_model}",
        f"- selected_articles: {len(baseline_articles)}",
        "",
        "## Overview",
        "",
        _overview_section(f"Baseline ({baseline_model})", baseline_digest),
        "",
        _overview_section(f"Candidate ({candidate_model})", candidate_digest),
        "",
    ]

    for index, baseline_article in enumerate(baseline_articles):
        candidate_article = candidate_articles[index] if index < len(candidate_articles) else {}
        lines.extend(
            [
                _article_heading(baseline_article, index),
                "",
                _article_section(f"Baseline ({baseline_model})", baseline_article),
                "",
                _article_section(f"Candidate ({candidate_model})", candidate_article),
                "",
            ]
        )

    return "\n".join(lines).strip() + "\n"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    load_dotenv(Path(__file__).with_name(".env"), override=True)

    args = _parse_args()
    hours = args.hours or _default_hours(args.briefing_mode)
    baseline_model = (
        args.baseline_model
        or os.getenv("GEMINI_SUMMARIZER_MODEL", "").strip()
        or os.getenv("GEMINI_MODEL", "").strip()
        or "gemini-2.5-flash"
    )
    candidate_model = args.candidate_model.strip()

    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY is required for summary model comparison.")

    selected_articles = _select_articles(args.briefing_mode, hours, args.top_n)
    if not selected_articles:
        raise RuntimeError("No articles were selected for comparison.")

    baseline_digest = _run_summary(selected_articles, args.briefing_mode, baseline_model)
    candidate_digest = _run_summary(selected_articles, args.briefing_mode, candidate_model)

    report = _build_report(
        baseline_model=baseline_model,
        candidate_model=candidate_model,
        baseline_digest=baseline_digest,
        candidate_digest=candidate_digest,
        briefing_mode=args.briefing_mode,
    )

    output_path = Path(args.output) if args.output else Path("reports") / f"summary_ab_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    print(f"baseline_model={baseline_model}")
    print(f"candidate_model={candidate_model}")
    print(f"selected_articles={len(selected_articles)}")
    print(f"output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
