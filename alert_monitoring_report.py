from __future__ import annotations

import argparse
import json
import os

from alert_rules import DEFAULT_ALERT_HOURS, DEFAULT_MIN_ALERT_SCORE, score_alert_details
from article_focus import annotate_articles
from rss_fetcher import fetch_articles
from selection_policy import annotate_kanta_fit_batch, filter_alert_candidates
from sources_config import SOURCES


def _default_hours() -> int:
    raw_value = os.environ.get("ALERT_FETCH_HOURS", str(DEFAULT_ALERT_HOURS))
    try:
        return max(1, int(raw_value))
    except ValueError:
        return DEFAULT_ALERT_HOURS


def _classify_status(fetched_articles: int, above_threshold: int) -> str:
    if fetched_articles == 0:
        return "degraded"
    if above_threshold == 0:
        return "quiet"
    if above_threshold <= 3:
        return "healthy"
    return "noisy"


def _recommendation(status: str, near_threshold: int, soft_above_threshold: int) -> str:
    if status == "degraded":
        return "기사 수집이 0건입니다. 피드 상태나 네트워크를 먼저 확인한 뒤 threshold 조정을 판단하세요."
    if status == "quiet":
        if near_threshold >= 2:
            return "경계선 기사들이 있어 `ALERT_MIN_SCORE`를 0.3 정도만 낮춰 볼 수 있습니다."
        return "현재는 조용한 상태입니다. 하루 정도 더 보고 실제 긴급 신호 누락이 없으면 유지하세요."
    if status == "noisy":
        if soft_above_threshold:
            return "트렌드성 기사가 함께 올라오고 있어 soft-context 감점 또는 `ALERT_MIN_SCORE` 상향을 검토하세요."
        return "긴급 알림이 많은 편입니다. `ALERT_MIN_SCORE`를 0.3~0.5 올리는 쪽이 안전합니다."
    return "현재 알림 밀도는 안정적입니다. 실제 팀 반응만 확인하면서 유지해도 괜찮습니다."


def _build_snapshot(hours: int, min_score: float, top_n: int) -> dict:
    articles = annotate_kanta_fit_batch(annotate_articles(fetch_articles(SOURCES, hours=hours)))
    candidates = filter_alert_candidates(articles)

    scored: list[dict] = []
    for article in candidates:
        details = score_alert_details(article)
        enriched = dict(article)
        enriched.update(
            {
                "alert_score": details["score"],
                "alert_label": details["label"],
                "watchlist_hit": details["watchlist_hit"],
                "launch_hit": details["launch_hit"],
                "operational_hit": details["operational_hit"],
                "risk_hit": details["risk_hit"],
                "soft_context_hit": details["soft_context_hit"],
            }
        )
        scored.append(enriched)

    scored.sort(
        key=lambda article: (
            article.get("alert_score", 0),
            article.get("published"),
        ),
        reverse=True,
    )

    above_threshold = [article for article in scored if float(article.get("alert_score", 0)) >= min_score]
    near_threshold = [article for article in scored if min_score - 0.7 <= float(article.get("alert_score", 0)) < min_score]
    soft_above_threshold = [article for article in above_threshold if article.get("soft_context_hit")]
    operational_above_threshold = [
        article
        for article in above_threshold
        if article.get("launch_hit") or article.get("operational_hit") or article.get("watchlist_hit")
    ]
    status = _classify_status(len(articles), len(above_threshold))

    return {
        "lookback_hours": hours,
        "min_score": min_score,
        "fetched_articles": len(articles),
        "candidate_articles": len(candidates),
        "above_threshold": len(above_threshold),
        "near_threshold": len(near_threshold),
        "operational_above_threshold": len(operational_above_threshold),
        "soft_context_above_threshold": len(soft_above_threshold),
        "status": status,
        "recommendation": _recommendation(status, len(near_threshold), len(soft_above_threshold)),
        "top_candidates": [
            {
                "score": article.get("alert_score"),
                "label": article.get("alert_label"),
                "source_name": article.get("source_name"),
                "title": article.get("title"),
                "launch_hit": bool(article.get("launch_hit")),
                "operational_hit": bool(article.get("operational_hit")),
                "watchlist_hit": bool(article.get("watchlist_hit")),
                "soft_context_hit": bool(article.get("soft_context_hit")),
            }
            for article in scored[: max(1, top_n)]
        ],
    }


def _plain_text_report(snapshot: dict) -> str:
    lines = [
        f"Alert monitoring snapshot (lookback={snapshot['lookback_hours']}h threshold={snapshot['min_score']:.1f})",
        f"status={snapshot['status']}",
        (
            f"fetched={snapshot['fetched_articles']} candidates={snapshot['candidate_articles']} "
            f"above_threshold={snapshot['above_threshold']} near_threshold={snapshot['near_threshold']}"
        ),
        (
            f"operational_above_threshold={snapshot['operational_above_threshold']} "
            f"soft_context_above_threshold={snapshot['soft_context_above_threshold']}"
        ),
        f"recommendation={snapshot['recommendation']}",
        "",
        "Top candidates:",
    ]

    for index, article in enumerate(snapshot["top_candidates"], start=1):
        flags = []
        if article.get("launch_hit"):
            flags.append("launch")
        if article.get("operational_hit"):
            flags.append("operational")
        if article.get("watchlist_hit"):
            flags.append("watchlist")
        if article.get("soft_context_hit"):
            flags.append("soft")
        flag_text = ",".join(flags) if flags else "-"
        lines.append(
            f"{index}. [{article['score']:.1f}] {article['label']} | {article.get('source_name') or '-'} | {article.get('title') or '-'}"
        )
        lines.append(f"   flags={flag_text}")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize current urgent-alert monitoring status for the AI news bot.")
    parser.add_argument("--hours", type=int, default=_default_hours(), help="Lookback window for current alert candidates.")
    parser.add_argument("--min-score", type=float, default=DEFAULT_MIN_ALERT_SCORE, help="Alert threshold to evaluate.")
    parser.add_argument("--top-n", type=int, default=8, help="How many top candidates to include.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of plain text.")
    args = parser.parse_args()

    snapshot = _build_snapshot(max(1, args.hours), max(0.0, args.min_score), max(1, args.top_n))

    if args.json:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    else:
        print(_plain_text_report(snapshot))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
