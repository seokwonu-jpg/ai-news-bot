from __future__ import annotations

import argparse
import json
import os

from rss_fetcher import inspect_sources
from sources_config import SOURCES

FAIL_STATUSES = {"error", "empty", "stale"}


def _default_hours() -> int:
    raw_value = os.environ.get("SOURCE_HEALTHCHECK_HOURS", "168")
    try:
        return max(1, int(raw_value))
    except ValueError:
        return 168


def _plain_text_report(results: list[dict], hours: int) -> str:
    lines = [f"Source health check (lookback={hours}h)"]
    for result in results:
        latest = result.get("latest_published") or "-"
        line = (
            f"[{result['status']:<7}] recent={result['recent_entries']:>2} "
            f"entries={result['entries']:>3} source={result['name']}"
        )
        lines.append(line)
        lines.append(f"           latest={latest}")
        if result.get("error"):
            lines.append(f"           error={result['error']}")

    failing = [result["name"] for result in results if result["status"] in FAIL_STATUSES]
    if failing:
        lines.append("")
        lines.append(f"Failing sources: {', '.join(failing)}")
    else:
        lines.append("")
        lines.append("All sources responded without stale/empty/error status.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check RSS source health for the AI news bot.")
    parser.add_argument("--hours", type=int, default=_default_hours(), help="Lookback window for recent articles.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of plain text.")
    args = parser.parse_args()

    hours = max(1, args.hours)
    results = inspect_sources(SOURCES, hours=hours)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(_plain_text_report(results, hours))

    return 1 if any(result["status"] in FAIL_STATUSES for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
