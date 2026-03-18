import datetime
import json
import logging
import os

import requests
from article_focus import FOCUS_BUCKET_LABELS, get_focus_bucket

from audience_config import TEAM_ALERT_TITLE, TEAM_BRIEFING_TITLE, TEAM_NAME

NUMBER_MARKERS = [f"{index}." for index in range(1, 11)]
WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]

logger = logging.getLogger("slack_sender")


def _today_korean() -> str:
    now = datetime.datetime.now()
    return f"{now.year}년 {now.month}월 {now.day}일 ({WEEKDAYS_KO[now.weekday()]})"


def _truncate(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}…"


def _compact_join(items, limit: int = 3, fallback: str = "-") -> str:
    if not isinstance(items, list):
        return fallback

    normalized = [str(item).strip() for item in items if str(item).strip()]
    if not normalized:
        return fallback

    joined = ", ".join(normalized[:limit])
    if len(normalized) > limit:
        joined += " 외"
    return joined


def _bullet_list(items, limit: int = 3) -> str:
    if not isinstance(items, list):
        return ""

    normalized = [str(item).strip() for item in items if str(item).strip()]
    if not normalized:
        return ""

    return "\n".join(f"• {item}" for item in normalized[:limit])


def _quote_text(title: str, text: str) -> str:
    cleaned = str(text).strip()
    if not cleaned:
        return ""

    quoted_lines = "\n".join(f"> {line}" for line in cleaned.splitlines() if line.strip())
    return f"*{title}*\n{quoted_lines}"


def _code_block(lines: list[str]) -> str:
    normalized = [str(line).strip() for line in lines if str(line).strip()]
    if not normalized:
        return ""
    return "```\n" + "\n".join(normalized) + "\n```"


def _normalize_digest(digest_or_articles) -> dict:
    if isinstance(digest_or_articles, dict):
        overview = digest_or_articles.get("overview", {})
        articles = digest_or_articles.get("articles", [])
        meta = digest_or_articles.get("meta", {})
        return {
            "overview": {
                "market_summary": str(overview.get("market_summary", "")).strip(),
                "action_items": overview.get("action_items", []),
                "priority_areas": overview.get("priority_areas", []),
            },
            "articles": articles if isinstance(articles, list) else [],
            "meta": meta if isinstance(meta, dict) else {},
        }
    return {
        "overview": {"market_summary": "", "action_items": [], "priority_areas": []},
        "articles": digest_or_articles or [],
        "meta": {},
    }


def _overview_block(overview: dict, message_kind: str) -> list[dict]:
    market_summary = _truncate(str(overview.get("market_summary", "")).strip(), 260)
    action_items = [str(item).strip() for item in overview.get("action_items", []) if str(item).strip()]
    priority_areas = [str(item).strip() for item in overview.get("priority_areas", []) if str(item).strip()]

    if not market_summary and not action_items and not priority_areas:
        return []

    title_text = f"지금의 {TEAM_NAME} 체크포인트" if message_kind == "alert" else f"오늘의 {TEAM_NAME} 체크포인트"
    action_title = "즉시 액션" if message_kind == "alert" else "이번 주 액션"

    blocks: list[dict] = []
    if market_summary:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": _quote_text(title_text, market_summary),
                },
            }
        )

    detail_lines: list[str] = []
    if priority_areas:
        detail_lines.append("priority_areas:")
        detail_lines.extend(f"- {item}" for item in priority_areas[:3])
    if action_items:
        if detail_lines:
            detail_lines.append("")
        detail_lines.append(f"{action_title}:")
        detail_lines.extend(f"- {item}" for item in action_items[:3])

    if detail_lines:
        blocks.append(
            {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": _code_block(detail_lines),
            },
            },
        )

    blocks.append({"type": "divider"})
    return blocks


def _article_blocks(article: dict, index: int, message_kind: str) -> list[dict]:
    marker = NUMBER_MARKERS[index] if index < len(NUMBER_MARKERS) else f"{index + 1}."
    translated_title = _truncate(str(article.get("translated_title") or article.get("title") or "제목 없음").strip(), 80)
    original_title = _truncate(str(article.get("title", "")).strip(), 120)
    summary = _truncate(str(article.get("korean_summary", "")).strip(), 180)
    why_it_matters = _truncate(str(article.get("why_it_matters", "")).strip(), 120)
    workflow_example = _truncate(str(article.get("workflow_example", "")).strip(), 120)
    practical_tip = _truncate(str(article.get("practical_tip", "")).strip(), 120)
    adoption_signal = _truncate(str(article.get("adoption_signal", "")).strip(), 20)
    kanta_angle = _truncate(str(article.get("kanta_angle", "")).strip(), 120)
    kanta_use_case = _truncate(str(article.get("kanta_use_case", "")).strip(), 120)
    kanta_experiment = _truncate(str(article.get("kanta_experiment", "")).strip(), 120)
    alert_label = _truncate(str(article.get("alert_label", "")).strip(), 24)
    target_roles = article.get("target_roles", [])
    kanta_work_areas = article.get("kanta_work_areas", [])
    source_name = str(article.get("source_name", "")).strip()
    url = article.get("url", "")
    focus_label = FOCUS_BUCKET_LABELS.get(get_focus_bucket(article), FOCUS_BUCKET_LABELS["other"])
    roles_text = _compact_join(target_roles, limit=3)
    work_area_text = _compact_join(kanta_work_areas, limit=2)

    title_lines = [f"{marker} *{translated_title}*"]
    if original_title and original_title != translated_title:
        title_lines.append(f"_{original_title}_")
    meta_label = "alert" if message_kind == "alert" else "signal"
    meta_value = alert_label or "-" if message_kind == "alert" else adoption_signal or "-"
    meta_lines = [
        f"source: {source_name or '-'}",
        f"focus: {focus_label}",
        f"{meta_label}: {meta_value}",
        f"work: {work_area_text}",
    ]
    if roles_text != "-":
        meta_lines.append(f"roles: {roles_text}")

    header_block = {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "\n".join(title_lines + ["", _code_block(meta_lines)]),
        },
    }

    if url:
        header_block["accessory"] = {
            "type": "button",
            "text": {"type": "plain_text", "text": "원문 보기", "emoji": False},
            "url": url,
        }

    insight_lines: list[str] = []
    if summary:
        insight_lines.append(_quote_text("핵심 요약", summary))
    if why_it_matters:
        insight_lines.append(_quote_text("왜 중요한가", why_it_matters))
    if kanta_angle:
        insight_lines.append(_quote_text(f"{TEAM_NAME} 관점", kanta_angle))

    action_lines: list[str] = []
    if kanta_use_case:
        action_lines.append(f"*업무 활용 포인트*\n{_bullet_list([kanta_use_case], limit=1)}")
    if workflow_example:
        action_lines.append(f"*업무 연결 예시*\n{_bullet_list([workflow_example], limit=1)}")
    if practical_tip:
        action_prefix = "지금 할 일" if message_kind == "alert" else "이번 주 액션"
        action_lines.append(f"*{action_prefix}*\n{_bullet_list([practical_tip], limit=1)}")
    if kanta_experiment and kanta_experiment != practical_tip:
        action_lines.append(f"*빠른 실험 제안*\n{_bullet_list([kanta_experiment], limit=1)}")

    content_lines = []
    if insight_lines:
        content_lines.extend(insight_lines)
    if action_lines:
        content_lines.extend(action_lines)

    blocks = [header_block]
    if content_lines:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n\n".join(content_lines)},
            }
        )
    blocks.append({"type": "divider"})
    return blocks


def build_blocks(digest_or_articles, date_str: str = None, message_kind: str = "daily", headline_suffix: str = "") -> list:
    digest = _normalize_digest(digest_or_articles)
    articles = digest["articles"]
    meta = digest.get("meta", {})

    resolved_message_kind = str(meta.get("message_kind") or message_kind or "daily")
    resolved_headline_suffix = str(meta.get("headline_suffix") or headline_suffix or "").strip()

    if date_str is None:
        date_str = _today_korean()

    category_groups = [
        ("video_image", FOCUS_BUCKET_LABELS["video_image"]),
        ("voice_audio", FOCUS_BUCKET_LABELS["voice_audio"]),
        ("other", FOCUS_BUCKET_LABELS["other"]),
    ]

    grouped_articles = {
        "video_image": [article for article in articles if get_focus_bucket(article) == "video_image"],
        "voice_audio": [article for article in articles if get_focus_bucket(article) == "voice_audio"],
        "other": [article for article in articles if get_focus_bucket(article) == "other"],
    }

    if resolved_message_kind == "alert":
        header_title = f"[긴급 알림] {TEAM_ALERT_TITLE}"
        if resolved_headline_suffix:
            header_title = f"{header_title} | {resolved_headline_suffix}"
    else:
        header_title = f"[정기 브리핑] {TEAM_BRIEFING_TITLE}"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{header_title} | {date_str}",
                "emoji": False,
            },
        },
        {"type": "divider"},
    ]

    blocks.extend(_overview_block(digest["overview"], resolved_message_kind))

    if resolved_message_kind == "alert":
        if articles:
            label = f"*{TEAM_NAME}가 바로 체크할 기사*"
            if resolved_headline_suffix:
                label = f"*{TEAM_NAME}가 바로 체크할 기사 | {resolved_headline_suffix}*"
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": label}})
            for index, article in enumerate(articles):
                blocks.extend(_article_blocks(article, index, resolved_message_kind))
    else:
        running_index = 0
        for group_key, label in category_groups:
            category_articles = grouped_articles[group_key]
            if not category_articles:
                continue

            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*{label}*"}})
            for article in category_articles:
                blocks.extend(_article_blocks(article, running_index, resolved_message_kind))
                running_index += 1

    unique_sources = []
    seen = set()
    for article in articles:
        source_name = article.get("source_name")
        if source_name and source_name not in seen:
            seen.add(source_name)
            unique_sources.append(source_name)

    source_text = ", ".join(unique_sources[:6]) if unique_sources else "미상"
    if len(unique_sources) > 6:
        source_text += " 외"

    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"출처: {source_text}"}]})
    return blocks


def build_fallback_text(digest_or_articles, message_kind: str = "daily", headline_suffix: str = "") -> str:
    digest = _normalize_digest(digest_or_articles)
    meta = digest.get("meta", {})

    resolved_message_kind = str(meta.get("message_kind") or message_kind or "daily")
    resolved_headline_suffix = str(meta.get("headline_suffix") or headline_suffix or "").strip()

    title = TEAM_ALERT_TITLE if resolved_message_kind == "alert" else TEAM_BRIEFING_TITLE
    if resolved_headline_suffix:
        title = f"{title} | {resolved_headline_suffix}"

    article_titles: list[str] = []
    for article in digest.get("articles", [])[:3]:
        candidate = _truncate(str(article.get("translated_title") or article.get("title") or "").strip(), 60)
        if candidate:
            article_titles.append(candidate)

    if article_titles:
        return f"{title}: {' / '.join(article_titles)}"

    market_summary = _truncate(str(digest.get("overview", {}).get("market_summary", "")).strip(), 120)
    if market_summary:
        return f"{title}: {market_summary}"
    return title


def build_payload(digest_or_articles, message_kind: str = "daily", headline_suffix: str = "") -> dict:
    return {
        "text": build_fallback_text(digest_or_articles, message_kind=message_kind, headline_suffix=headline_suffix),
        "blocks": build_blocks(digest_or_articles, message_kind=message_kind, headline_suffix=headline_suffix),
    }


def send_to_slack(
    digest_or_articles,
    webhook_url: str = None,
    message_kind: str = "daily",
    headline_suffix: str = "",
) -> bool:
    webhook = (
        webhook_url
        or (os.environ.get("SLACK_ALERT_WEBHOOK_URL") if message_kind == "alert" else None)
        or os.environ.get("SLACK_WEBHOOK_URL")
    )
    if not webhook:
        logger.error("Slack webhook URL is missing. Provide webhook_url or set SLACK_WEBHOOK_URL/SLACK_ALERT_WEBHOOK_URL.")
        return False

    payload = build_payload(digest_or_articles, message_kind=message_kind, headline_suffix=headline_suffix)

    try:
        response = requests.post(
            webhook,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload, ensure_ascii=False),
            timeout=10,
        )
        if response.status_code == 200:
            return True

        logger.error(
            "Failed to send Slack message. status_code=%s body=%s",
            response.status_code,
            response.text,
        )
        return False
    except requests.RequestException as exc:
        logger.error("Error while sending Slack message: %s", exc)
        return False
