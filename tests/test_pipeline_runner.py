import logging
import unittest
from unittest.mock import Mock, patch

from pipeline_runner import PipelineConfig, run_pipeline


class RunPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.logger = logging.getLogger("test.pipeline_runner")

    @patch("pipeline_runner.annotate_kanta_fit_batch", side_effect=lambda articles: articles)
    @patch("pipeline_runner.annotate_articles", side_effect=lambda articles: articles)
    @patch("pipeline_runner.fetch_articles", return_value=[])
    @patch("pipeline_runner.load_seen", return_value=[])
    def test_fails_when_fetch_returns_zero_articles(
        self,
        _load_seen,
        _fetch_articles,
        _annotate_articles,
        _annotate_kanta_fit_batch,
    ) -> None:
        exit_code = run_pipeline(
            config=PipelineConfig(
                name="Daily news bot",
                cache_file="seen_articles.json",
                fetch_hours=24,
                message_kind="daily",
                briefing_mode="daily",
                empty_selection_message="No articles selected.",
                fail_on_empty_fetch=True,
            ),
            select_articles=lambda articles: articles,
            logger=self.logger,
        )

        self.assertEqual(exit_code, 1)

    @patch("pipeline_runner.write_preview")
    @patch("pipeline_runner.build_payload", side_effect=lambda digest, **_: {"text": "headline", "blocks": [], "meta": digest.get("meta", {})})
    @patch("pipeline_runner.enrich_digest", side_effect=lambda digest: digest)
    @patch(
        "pipeline_runner.summarize_articles",
        side_effect=lambda articles, briefing_mode="daily": {"overview": {}, "articles": articles, "meta": {"briefing_mode": briefing_mode}},
    )
    @patch("pipeline_runner.filter_new", return_value=[])
    @patch("pipeline_runner.load_seen", return_value=["https://example.com/seen"])
    @patch("pipeline_runner.annotate_kanta_fit_batch", side_effect=lambda articles: articles)
    @patch("pipeline_runner.annotate_articles", side_effect=lambda articles: articles)
    @patch(
        "pipeline_runner.fetch_articles",
        return_value=[{"title": "Seen story", "url": "https://example.com/seen"}],
    )
    def test_backfills_seen_articles_when_daily_has_no_new_items(
        self,
        _fetch_articles,
        _annotate_articles,
        _annotate_kanta_fit_batch,
        _load_seen,
        _filter_new,
        summarize_articles,
        _enrich_digest,
        _build_payload,
        write_preview,
    ) -> None:
        selector = Mock(return_value=[{"title": "Seen story", "url": "https://example.com/seen"}])

        exit_code = run_pipeline(
            config=PipelineConfig(
                name="Daily news bot",
                cache_file="seen_articles.json",
                fetch_hours=24,
                message_kind="daily",
                briefing_mode="daily",
                empty_selection_message="No articles selected.",
                dry_run=True,
                preview_path="reports/test-preview.json",
                allow_seen_backfill=True,
            ),
            select_articles=selector,
            logger=self.logger,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(selector.call_count, 1)
        summarize_articles.assert_called_once_with(
            [{"title": "Seen story", "url": "https://example.com/seen"}],
            briefing_mode="daily",
        )
        write_preview.assert_called_once()


if __name__ == "__main__":
    unittest.main()
