import unittest

from summarizer import _safe_load_json_payload


class SafeLoadJsonPayloadTests(unittest.TestCase):
    def test_parses_fenced_json_payload(self) -> None:
        payload = _safe_load_json_payload(
            """```json
            {"overview": {"market_summary": "x", "action_items": []}, "articles": []}
            ```"""
        )

        self.assertEqual(payload["overview"]["market_summary"], "x")
        self.assertEqual(payload["articles"], [])

    def test_parses_json_wrapped_as_string_literal(self) -> None:
        payload = _safe_load_json_payload(
            '"{\\"overview\\": {\\"market_summary\\": \\"x\\", \\"action_items\\": []}, \\"articles\\": []}"'
        )

        self.assertEqual(payload["overview"]["market_summary"], "x")
        self.assertEqual(payload["articles"], [])


if __name__ == "__main__":
    unittest.main()
