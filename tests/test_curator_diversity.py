from datetime import datetime, timezone
from typing import Optional
import unittest

from curator import score_articles


def _article(
    *,
    title: str,
    source_name: str,
    summary: str = "",
    keywords: Optional[list[str]] = None,
    focus_bucket: str = "video_image",
    kanta_fit_score: float = 8.0,
    priority: str = "high",
    url: Optional[str] = None,
) -> dict:
    slug = (url or title.lower().replace(" ", "-").replace("$", ""))
    return {
        "title": title,
        "summary": summary,
        "content_text": summary,
        "keywords": keywords or [],
        "focus_bucket": focus_bucket,
        "kanta_fit_score": kanta_fit_score,
        "published": datetime.now(timezone.utc),
        "source_name": source_name,
        "priority": priority,
        "url": f"https://example.com/{slug}",
    }


class CuratorDiversityTests(unittest.TestCase):
    def test_same_story_from_multiple_sources_only_appears_once(self) -> None:
        runway_techcrunch = _article(
            title="Runway launches builders program for creators",
            source_name="TechCrunch AI",
            summary="Runway launches a builders program and fund for teams using its video tools.",
            keywords=["runway", "video", "builders program", "fund"],
        )
        runway_verge = _article(
            title="Runway launches $10M fund and builders program for AI startups",
            source_name="The Verge AI",
            summary="Runway unveiled a $10M fund and builders program tied to its creative video stack.",
            keywords=["runway", "video", "builders program", "funding"],
        )
        adobe = _article(
            title="Adobe releases Firefly API for creative teams",
            source_name="Adobe Blog",
            summary="Adobe opened a Firefly API and enterprise workflow integration for creative teams.",
            keywords=["adobe", "firefly", "api", "creative"],
        )

        selected = score_articles([runway_techcrunch, runway_verge, adobe], top_n=2)
        titles = [article["title"] for article in selected]

        self.assertEqual(len(selected), 2)
        self.assertEqual(sum("Runway" in title for title in titles), 1)
        self.assertIn(adobe["title"], titles)

    def test_daily_selection_limits_soft_context_duplicates(self) -> None:
        runway = _article(
            title="Runway launches builders program for creators",
            source_name="TechCrunch AI",
            summary="New API access and builder support are now available for video teams.",
            keywords=["runway", "video", "api", "builders program"],
        )
        adobe = _article(
            title="Adobe releases Firefly API for creative teams",
            source_name="Adobe Blog",
            summary="Adobe expanded Firefly with API access and integrations for enterprise creative teams.",
            keywords=["adobe", "firefly", "api", "creative"],
        )
        galaxy = _article(
            title="The Galaxy S26's photo app can sloppify your memories",
            source_name="The Verge AI",
            summary="A review of Samsung photo AI raises memory and authenticity concerns for edited images.",
            keywords=["photo", "memory", "editing", "review"],
            kanta_fit_score=7.2,
            priority="medium",
        )
        art_school = _article(
            title="Art schools are being torn apart by AI",
            source_name="The Verge AI",
            summary="Students and schools debate how creative education should change around AI tools.",
            keywords=["creative", "school", "education", "debate"],
            kanta_fit_score=7.0,
            priority="medium",
        )

        selected = score_articles([runway, adobe, galaxy, art_school], top_n=3)
        titles = [article["title"] for article in selected]
        soft_titles = {galaxy["title"], art_school["title"]}

        self.assertEqual(len(selected), 3)
        self.assertEqual(sum(title in soft_titles for title in titles), 1)
        self.assertGreaterEqual(len({article["source_name"] for article in selected}), 2)

    def test_daily_selection_prefers_underfill_over_near_duplicate_story(self) -> None:
        feature = _article(
            title="The gig workers who are training humanoid robots at home",
            source_name="MIT Technology Review",
            summary="Gig workers film task demonstrations at home so humanoid systems can learn real-world actions.",
            keywords=["gig workers", "humanoid", "training", "robots"],
            focus_bucket="video_image",
            kanta_fit_score=6.8,
            priority="medium",
        )
        newsletter = _article(
            title="The Download: gig workers training humanoids, and better AI benchmarks",
            source_name="MIT Technology Review",
            summary="A newsletter recap covers the same humanoid training story alongside AI benchmark discussion.",
            keywords=["gig workers", "humanoids", "training", "benchmarks"],
            focus_bucket="other",
            kanta_fit_score=6.4,
            priority="medium",
        )

        selected = score_articles([feature, newsletter], top_n=2)

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["title"], feature["title"])


if __name__ == "__main__":
    unittest.main()
