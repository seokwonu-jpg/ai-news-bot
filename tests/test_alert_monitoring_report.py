import unittest

from alert_monitoring_report import _classify_status, _recommendation


class AlertMonitoringReportTests(unittest.TestCase):
    def test_zero_fetched_articles_are_degraded(self) -> None:
        self.assertEqual(_classify_status(0, 0), "degraded")

    def test_zero_alerts_with_articles_is_quiet(self) -> None:
        self.assertEqual(_classify_status(12, 0), "quiet")

    def test_degraded_recommendation_prioritizes_feed_check(self) -> None:
        message = _recommendation("degraded", near_threshold=0, soft_above_threshold=0)

        self.assertIn("기사 수집이 0건", message)
        self.assertIn("피드 상태", message)


if __name__ == "__main__":
    unittest.main()
