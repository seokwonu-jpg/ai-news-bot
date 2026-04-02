from datetime import datetime, timezone
import unittest

from alert_rules import DEFAULT_MIN_ALERT_SCORE, score_alert, select_alert_articles


def _article(**overrides):
    base = {
        "title": "Untitled",
        "summary": "",
        "content_text": "",
        "keywords": [],
        "focus_bucket": "video_image",
        "kanta_fit_score": 8.0,
        "published": datetime.now(timezone.utc),
        "source_name": "TechCrunch AI",
    }
    base.update(overrides)
    return base


class AlertRuleTests(unittest.TestCase):
    def test_launch_story_scores_above_threshold(self) -> None:
        article = _article(
            title="Runway launches builders program for creators",
            summary="Runway launches a new API and builders program for teams using its video model.",
            keywords=["video", "api", "builders program", "runway"],
        )

        score, label = score_alert(article)

        self.assertGreaterEqual(score, DEFAULT_MIN_ALERT_SCORE)
        self.assertEqual(label, "Visual AI")

    def test_soft_trend_story_scores_below_threshold(self) -> None:
        article = _article(
            title="Art schools are being torn apart by AI",
            summary="Students and educators debate curriculum changes as schools adapt to AI tools.",
            keywords=["creative", "education", "school"],
            kanta_fit_score=7.0,
        )

        score, _label = score_alert(article)

        self.assertLess(score, DEFAULT_MIN_ALERT_SCORE)

    def test_selection_prefers_launch_over_soft_context(self) -> None:
        launch = _article(
            title="Runway launches builders program for creators",
            summary="New API access and program benefits are now available for video teams.",
            keywords=["video", "api", "runway", "launch"],
        )
        soft = _article(
            title="AI tools reshape art school debates",
            summary="Students and faculty argue over education and creativity in the classroom.",
            keywords=["creative", "education", "school"],
            kanta_fit_score=7.0,
        )

        selected = select_alert_articles([soft, launch], max_items=2, min_score=DEFAULT_MIN_ALERT_SCORE)

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["title"], launch["title"])


if __name__ == "__main__":
    unittest.main()
