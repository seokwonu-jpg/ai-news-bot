from datetime import datetime, timezone

from article_focus import get_focus_bucket
from audience_config import TEAM_PRIORITY_KEYWORDS, TEAM_TOOL_WATCHLIST, VOICE_PRIORITY_KEYWORDS, WORKFLOW_PRIORITY_KEYWORDS
from selection_policy import ALERT_SOURCE_CAPS, get_kanta_fit_score, take_capped_articles

ALERT_CACHE_FILE = "seen_alerts.json"
DEFAULT_ALERT_HOURS = 12
DEFAULT_MAX_ALERTS = 3
DEFAULT_MIN_ALERT_SCORE = 6.0
_FOCUS_BONUS = {
    "video_image": 3.0,
    "voice_audio": 3.0,
}

_BYTE_DANCE_KEYWORDS = {
    "bytedance",
    "tiktok",
    "capcut",
    "doubao",
    "jimeng",
    "seedance",
    "dreamina",
}
_VISUAL_ALERT_KEYWORDS = {
    "video",
    "image",
    "creative",
    "creator",
    "content",
    "storyboard",
    "avatar",
    "character",
    "animation",
    "editing",
    "render",
    "multimodal",
    "text-to-video",
    "image-to-video",
    "thumbnail",
}
_VOICE_ALERT_KEYWORDS = set(VOICE_PRIORITY_KEYWORDS)
_WORKFLOW_ALERT_KEYWORDS = set(WORKFLOW_PRIORITY_KEYWORDS)
_KANTA_WATCHLIST = set(TEAM_TOOL_WATCHLIST)
_LAUNCH_KEYWORDS = {
    "launch",
    "launches",
    "released",
    "release",
    "introduces",
    "introduce",
    "rolls out",
    "new model",
    "new version",
    "available",
    "unveils",
}
_RISK_KEYWORDS = {
    "copyright",
    "lawsuit",
    "ban",
    "policy",
    "regulation",
    "licensing",
    "export control",
    "risk",
}


def _combined_text(article: dict) -> str:
    title = str(article.get("title", "")).lower()
    summary = str(article.get("summary", "")).lower()[:500]
    content = str(article.get("content_text", "")).lower()[:500]
    keywords = " ".join(str(keyword).lower() for keyword in article.get("keywords", []))
    return " ".join([title, summary, content, keywords])


def _headline_text(article: dict) -> str:
    return " ".join(
        [
            str(article.get("title", "")).lower(),
            str(article.get("summary", "")).lower()[:500],
            " ".join(str(keyword).lower() for keyword in article.get("keywords", [])),
        ]
    )


def score_alert(article: dict) -> tuple[float, str]:
    combined = _combined_text(article)
    headline = _headline_text(article)
    focus_bucket = get_focus_bucket(article)
    kanta_fit_score = get_kanta_fit_score(article)
    score = 0.0

    if focus_bucket in _FOCUS_BONUS:
        score += _FOCUS_BONUS[focus_bucket]

    priority = str(article.get("priority", "")).lower()
    if priority == "critical":
        score += 1.8
    elif priority == "high":
        score += 1.0

    if any(keyword in headline for keyword in _BYTE_DANCE_KEYWORDS):
        score += 3.0
        label = "ByteDance"
    elif any(keyword in combined for keyword in _VOICE_ALERT_KEYWORDS):
        score += 2.4
        label = "Voice AI"
    elif any(keyword in combined for keyword in _VISUAL_ALERT_KEYWORDS):
        score += 2.2
        label = "Visual AI"
    elif any(keyword in combined for keyword in _WORKFLOW_ALERT_KEYWORDS):
        score += 1.8
        label = "Workflow AI"
    elif focus_bucket == "voice_audio":
        label = "Voice AI"
    elif focus_bucket == "video_image":
        label = "Visual AI"
    else:
        label = "AI Update"

    if any(keyword in combined for keyword in _LAUNCH_KEYWORDS):
        score += 2.0

    if any(keyword in combined for keyword in _KANTA_WATCHLIST):
        score += 1.8

    if any(keyword in combined for keyword in TEAM_PRIORITY_KEYWORDS):
        score += 1.2

    score += max(-1.5, min(1.5, (kanta_fit_score - 5.0) * 0.5))

    if any(keyword in combined for keyword in _RISK_KEYWORDS):
        if any(keyword in combined for keyword in _BYTE_DANCE_KEYWORDS):
            score += 1.0
            label = "ByteDance Risk"
        else:
            score -= 1.2

    published = article.get("published")
    if isinstance(published, datetime):
        age_hours = (datetime.now(timezone.utc) - published).total_seconds() / 3600
        if age_hours <= 3:
            score += 1.0
        elif age_hours <= 6:
            score += 0.6

    return round(score, 1), label


def _blend_alert_priority(alert_score: float, kanta_fit_score: float) -> float:
    return round((alert_score * 0.65) + (kanta_fit_score * 0.35), 1)


def select_alert_articles(
    articles: list[dict],
    max_items: int = DEFAULT_MAX_ALERTS,
    min_score: float = DEFAULT_MIN_ALERT_SCORE,
) -> list[dict]:
    ranked: list[dict] = []
    for article in articles:
        alert_score, alert_label = score_alert(article)
        if alert_score < min_score:
            continue

        updated = dict(article)
        updated["focus_bucket"] = get_focus_bucket(article)
        updated["alert_score"] = alert_score
        updated["alert_priority_score"] = _blend_alert_priority(alert_score, get_kanta_fit_score(article))
        updated["alert_label"] = alert_label
        ranked.append(updated)

    ranked.sort(
        key=lambda article: (
            article.get("alert_priority_score", article.get("alert_score", 0)),
            article.get("published") or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    return take_capped_articles(ranked, max_items, ALERT_SOURCE_CAPS)
