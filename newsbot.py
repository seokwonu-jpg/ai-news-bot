from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from alert_rules import (
    ALERT_CACHE_FILE,
    DEFAULT_ALERT_HOURS,
    DEFAULT_MAX_ALERTS,
    DEFAULT_MIN_ALERT_SCORE,
    select_alert_articles,
)
from curator import score_articles
from dedup import CACHE_FILE
from pipeline_runner import (
    PipelineConfig,
    env_float,
    env_int,
    first_env_value,
    require_env_vars,
    run_pipeline,
)
from selection_policy import filter_alert_candidates, filter_daily_candidates

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("newsbot")


def _daily_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("daily", help="Run the daily briefing pipeline.")
    parser.add_argument("--fetch-hours", type=int, default=None, help="Override DAILY_FETCH_HOURS.")
    parser.add_argument("--top-n", type=int, default=None, help="Override DAILY_TOP_N.")
    parser.add_argument("--dry-run", action="store_true", help="Build a Slack preview without sending it.")
    parser.add_argument("--preview-path", default=None, help="Optional JSON output path for dry-run payloads.")
    parser.set_defaults(handler=run_daily)


def _alert_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("alert", help="Run the urgent alert pipeline.")
    parser.add_argument("--fetch-hours", type=int, default=None, help="Override ALERT_FETCH_HOURS.")
    parser.add_argument("--max-items", type=int, default=None, help="Override ALERT_MAX_ITEMS.")
    parser.add_argument("--min-score", type=float, default=None, help="Override ALERT_MIN_SCORE.")
    parser.add_argument("--dry-run", action="store_true", help="Build a Slack preview without sending it.")
    parser.add_argument("--preview-path", default=None, help="Optional JSON output path for dry-run payloads.")
    parser.set_defaults(handler=run_alert)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified runner for the Kanta AI news bot.")
    subparsers = parser.add_subparsers(dest="mode", required=True)
    _daily_parser(subparsers)
    _alert_parser(subparsers)
    return parser


def run_daily(args: argparse.Namespace) -> int:
    if not args.dry_run:
        require_env_vars("SLACK_WEBHOOK_URL")

    fetch_hours = args.fetch_hours if args.fetch_hours is not None else env_int("DAILY_FETCH_HOURS", 24, minimum=1)
    top_n = args.top_n if args.top_n is not None else env_int("DAILY_TOP_N", 8, minimum=1)

    return run_pipeline(
        config=PipelineConfig(
            name="Daily news bot",
            cache_file=CACHE_FILE,
            fetch_hours=fetch_hours,
            message_kind="daily",
            briefing_mode="daily",
            empty_selection_message="No articles were selected for the daily briefing.",
            dry_run=args.dry_run,
            preview_path=args.preview_path,
            allow_seen_backfill=True,
            fail_on_empty_fetch=True,
        ),
        select_articles=lambda articles: score_articles(filter_daily_candidates(articles), top_n=top_n),
        logger=logger,
    )


def run_alert(args: argparse.Namespace) -> int:
    webhook = first_env_value("SLACK_ALERT_WEBHOOK_URL", "SLACK_WEBHOOK_URL")
    if not args.dry_run and not webhook:
        raise RuntimeError("Missing required environment variables: SLACK_ALERT_WEBHOOK_URL or SLACK_WEBHOOK_URL")

    fetch_hours = args.fetch_hours if args.fetch_hours is not None else env_int("ALERT_FETCH_HOURS", DEFAULT_ALERT_HOURS, minimum=1)
    max_items = args.max_items if args.max_items is not None else env_int("ALERT_MAX_ITEMS", DEFAULT_MAX_ALERTS, minimum=1)
    min_score = args.min_score if args.min_score is not None else env_float("ALERT_MIN_SCORE", DEFAULT_MIN_ALERT_SCORE, minimum=0.0)

    return run_pipeline(
        config=PipelineConfig(
            name="Urgent alert bot",
            cache_file=ALERT_CACHE_FILE,
            fetch_hours=fetch_hours,
            message_kind="alert",
            briefing_mode="alert",
            webhook_url=webhook,
            empty_selection_message="No alert-worthy articles were selected.",
            digest_meta_builder=lambda articles: {
                "headline_suffix": str(articles[0].get("alert_label", "Alert")).strip() or "Alert",
            },
            dry_run=args.dry_run,
            preview_path=args.preview_path,
        ),
        select_articles=lambda articles: select_alert_articles(
            filter_alert_candidates(articles),
            max_items=max_items,
            min_score=min_score,
        ),
        logger=logger,
    )


def main() -> int:
    load_dotenv(Path(__file__).with_name(".env"))
    parser = build_parser()
    args = parser.parse_args()

    try:
        return args.handler(args)
    except RuntimeError as exc:
        print(str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
