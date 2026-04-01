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
from pipeline_runner import (
    PipelineConfig,
    env_float,
    env_int,
    first_env_value,
    run_pipeline,
)
from selection_policy import filter_alert_candidates

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("alert_bot")


def main():
    load_dotenv(Path(__file__).with_name(".env"))

    try:
        webhook = first_env_value("SLACK_ALERT_WEBHOOK_URL", "SLACK_WEBHOOK_URL")
        if not webhook:
            raise RuntimeError("Missing required environment variables: SLACK_ALERT_WEBHOOK_URL or SLACK_WEBHOOK_URL")

        fetch_hours = env_int("ALERT_FETCH_HOURS", DEFAULT_ALERT_HOURS, minimum=1)
        max_items = env_int("ALERT_MAX_ITEMS", DEFAULT_MAX_ALERTS, minimum=1)
        min_score = env_float("ALERT_MIN_SCORE", DEFAULT_MIN_ALERT_SCORE, minimum=0.0)
    except RuntimeError as exc:
        print(str(exc))
        sys.exit(1)

    exit_code = run_pipeline(
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
        ),
        select_articles=lambda articles: select_alert_articles(
            filter_alert_candidates(articles),
            max_items=max_items,
            min_score=min_score,
        ),
        logger=logger,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
