import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from curator import score_articles
from dedup import CACHE_FILE
from pipeline_runner import PipelineConfig, env_int, require_env_vars, run_pipeline
from selection_policy import filter_daily_candidates

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("bot")


def main():
    load_dotenv(Path(__file__).with_name(".env"))

    try:
        require_env_vars("SLACK_WEBHOOK_URL")
        fetch_hours = env_int("DAILY_FETCH_HOURS", 24, minimum=1)
        top_n = env_int("DAILY_TOP_N", 8, minimum=1)
    except RuntimeError as exc:
        print(str(exc))
        sys.exit(1)

    exit_code = run_pipeline(
        config=PipelineConfig(
            name="Daily news bot",
            cache_file=CACHE_FILE,
            fetch_hours=fetch_hours,
            message_kind="daily",
            briefing_mode="daily",
            empty_selection_message="No articles were selected for the daily briefing.",
            allow_seen_backfill=True,
            fail_on_empty_fetch=True,
        ),
        select_articles=lambda articles: score_articles(filter_daily_candidates(articles), top_n=top_n),
        logger=logger,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
