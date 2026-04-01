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
from llm_client import credential_env_name, credentials_available, resolve_model, resolve_provider
from rss_fetcher import fetch_articles
from selection_policy import annotate_kanta_fit_batch, filter_alert_candidates, filter_daily_candidates
from sources_config import SOURCES
from summarizer import summarize_articles

LOGGER = logging.getLogger("compare_summary_models")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare summary outputs across LLM providers/models.")
    parser.add_argument("--briefing-mode", choices=("daily", "alert"), default="daily")
    parser.add_argument("--hours", type=int, default=None, help="Lookback window. Defaults to 24 for daily, 12 for alert.")
    parser.add_argument("--top-n", type=int, default=3, help="Number of selected articles to compare.")
    parser.add_argument("--baseline-provider", choices=("gemini", "litellm"), default=None)
    parser.add_argument("--baseline-model", default=None, help="Default: current provider-specific summarizer model.")
    parser.add_argument("--candidate-provider", choices=("gemini", "litellm"), default=None)
    parser.add_argument("--candidate-model", default=None, help="Default: candidate provider's summarizer model.")
    parser.add_argument(
        "--output",
        default=None,
        help="Optional markdown output path. Defaults to reports/summary_ab_<timestamp>.md",
    )
    return parser.parse_args()


def _default_hours(briefing_mode: str) -> int:
    return 12 if briefing_mode == "alert" else 24


@contextmanager
def _temporary_envs(updates: dict[str, str | None]):
    sentinel = object()
    previous = {name: os.environ.get(name, sentinel) for name in updates}
    try:
        for name, value in updates.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        yield
    finally:
        for name, value in previous.items():
            if value is sentinel:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


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


def _provider_model_env(provider_name: str, model_name: str | None) -> dict[str, str | None]:
    return {
        "LLM_SUMMARIZER_PROVIDER": provider_name,
        "GEMINI_SUMMARIZER_MODEL": model_name if provider_name == "gemini" else None,
        "LITELLM_SUMMARIZER_MODEL": model_name if provider_name == "litellm" else None,
    }


def _run_summary(articles: list[dict], briefing_mode: str, provider_name: str, model_name: str | None) -> dict:
    with _temporary_envs(_provider_model_env(provider_name, model_name)):
        digest = summarize_articles(articles, briefing_mode=briefing_mode)
        resolved_provider = resolve_provider("summarizer")
        resolved_model = resolve_model("summarizer")
    digest = enrich_digest(digest)
    digest_meta = dict(digest.get("meta", {}))
    digest_meta["comparison_provider"] = resolved_provider
    digest_meta["comparison_model"] = resolved_model
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
    baseline_label: str,
    candidate_label: str,
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
        f"- baseline: {baseline_label}",
        f"- candidate: {candidate_label}",
        f"- selected_articles: {len(baseline_articles)}",
        "",
        "## Overview",
        "",
        _overview_section(f"Baseline ({baseline_label})", baseline_digest),
        "",
        _overview_section(f"Candidate ({candidate_label})", candidate_digest),
        "",
    ]

    for index, baseline_article in enumerate(baseline_articles):
        candidate_article = candidate_articles[index] if index < len(candidate_articles) else {}
        lines.extend(
            [
                _article_heading(baseline_article, index),
                "",
                _article_section(f"Baseline ({baseline_label})", baseline_article),
                "",
                _article_section(f"Candidate ({candidate_label})", candidate_article),
                "",
            ]
        )

    return "\n".join(lines).strip() + "\n"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    load_dotenv(Path(__file__).with_name(".env"))

    args = _parse_args()
    hours = args.hours or _default_hours(args.briefing_mode)
    baseline_provider = (args.baseline_provider or resolve_provider("summarizer")).strip().lower()
    candidate_provider = (args.candidate_provider or baseline_provider).strip().lower()

    with _temporary_envs(_provider_model_env(baseline_provider, args.baseline_model)):
        if not credentials_available("summarizer"):
            raise RuntimeError(
                f"{credential_env_name(resolve_provider('summarizer'))} is required for baseline provider={baseline_provider}."
            )

    with _temporary_envs(_provider_model_env(candidate_provider, args.candidate_model)):
        if not credentials_available("summarizer"):
            raise RuntimeError(
                f"{credential_env_name(resolve_provider('summarizer'))} is required for candidate provider={candidate_provider}."
            )

    selected_articles = _select_articles(args.briefing_mode, hours, args.top_n)
    if not selected_articles:
        raise RuntimeError("No articles were selected for comparison.")

    baseline_digest = _run_summary(selected_articles, args.briefing_mode, baseline_provider, args.baseline_model)
    candidate_digest = _run_summary(selected_articles, args.briefing_mode, candidate_provider, args.candidate_model)

    baseline_label = f"{baseline_digest['meta'].get('comparison_provider', baseline_provider)}:{baseline_digest['meta'].get('comparison_model', '-')}"
    candidate_label = f"{candidate_digest['meta'].get('comparison_provider', candidate_provider)}:{candidate_digest['meta'].get('comparison_model', '-')}"

    report = _build_report(
        baseline_label=baseline_label,
        candidate_label=candidate_label,
        baseline_digest=baseline_digest,
        candidate_digest=candidate_digest,
        briefing_mode=args.briefing_mode,
    )

    output_path = Path(args.output) if args.output else Path("reports") / f"summary_ab_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    print(f"baseline={baseline_label}")
    print(f"candidate={candidate_label}")
    print(f"selected_articles={len(selected_articles)}")
    print(f"output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
