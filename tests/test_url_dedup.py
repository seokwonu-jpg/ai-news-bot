import unittest

from dedup import _normalize_seen_urls, canonicalize_article_url, dedupe_articles_by_url, filter_new, mark_seen


class CanonicalizeArticleUrlTests(unittest.TestCase):
    def test_strips_tracking_fragment_and_trailing_slash(self) -> None:
        url = "HTTPS://Example.com/post/?utm_source=newsletter&id=42#section"
        self.assertEqual(canonicalize_article_url(url), "https://example.com/post?id=42")

    def test_preserves_meaningful_query_keys(self) -> None:
        url = "https://example.com/article?p=123&lang=ko"
        self.assertEqual(canonicalize_article_url(url), "https://example.com/article?lang=ko&p=123")


class SeenCacheTests(unittest.TestCase):
    def test_normalize_seen_urls_collapses_url_variants(self) -> None:
        seen = [
            "https://example.com/post?utm_source=feed",
            "https://example.com/post/",
            "https://example.com/post#fragment",
        ]
        self.assertEqual(_normalize_seen_urls(seen), ["https://example.com/post"])

    def test_filter_new_uses_canonical_urls(self) -> None:
        articles = [
            {"url": "https://example.com/post?utm_medium=rss"},
            {"url": "https://example.com/new-story"},
        ]
        filtered = filter_new(articles, ["https://example.com/post"])
        self.assertEqual(filtered, [{"url": "https://example.com/new-story"}])

    def test_mark_seen_stores_canonical_url_once(self) -> None:
        updated = mark_seen(
            [
                {"url": "https://example.com/post?utm_medium=rss"},
                {"url": "https://example.com/post/"},
            ],
            [],
        )
        self.assertEqual(updated, ["https://example.com/post"])


class FetchDedupTests(unittest.TestCase):
    def test_fetch_dedup_collapses_tracking_variants(self) -> None:
        articles = [
            {"url": "https://example.com/post?utm_source=feed", "title": "A"},
            {"url": "https://example.com/post/", "title": "A duplicate"},
            {"url": "https://example.com/other", "title": "B"},
        ]
        deduped = dedupe_articles_by_url(articles, set())
        self.assertEqual(
            deduped,
            [
                {"url": "https://example.com/post", "title": "A"},
                {"url": "https://example.com/other", "title": "B"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
