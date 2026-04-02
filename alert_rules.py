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
_OPERATIONAL_ALERT_KEYWORDS = {
    "api",
    "sdk",
    "integration",
    "integrates",
    "plugin",
    "partnership",
    "partner",
    "partners",
    "fund",
    "funding",
    "builders program",
    "program",
    "acquires",
    "acquisition",
    "pricing",
    "price",
    "prices",
    "beta",
    "alpha",
    "general availability",
    "generally available",
    "open source",
    "open-source",
    "enterprise",
    "for teams",
    "for creators",
}
_SOFT_CONTEXT_KEYWORDS = {
    "opinion",
    "analysis",
    "review",
    "essay",
    "education",
    "school",
    "schools",
    "curriculum",
    "student",
    "students",
    "artist",
    "artists",
    "art school",
    "art schools",
    "memories",
    "memory",
    "debate",
    "ethics",
    "controversy",
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


def score_alert_details(article: dict) -> dict:
    combined = _combined_text(article)
    headline = _headline_text(article)
    focus_bucket = get_focus_bucket(article)
    kanta_fit_score = get_kanta_fit_score(article)
    watchlist_hit = any(keyword in combined for keyword in _KANTA_WATCHLIST)
    bytedance_hit = any(keyword in headline for keyword in _BYTE_DANCE_KEYWORDS)
    launch_hit = any(keyword in combined for keyword in _LAUNCH_KEYWORDS)
    operational_hit = any(keyword in combined for keyword in _OPERATIONAL_ALERT_KEYWORDS)
    risk_hit = any(keyword in combined for keyword in _RISK_KEYWORDS)
    soft_context_hit = any(keyword in combined for keyword in _SOFT_CONTEXT_KEYWORDS)
    score = 0.0

    if focus_bucket in _FOCUS_BONUS:
        score += _FOCUS_BONUS[focus_bucket]

    priority = str(article.get("priority", "")).lower()
    if priority == "critical":
        score += 1.8
    elif priority == "high":
        score += 1.0

    if bytedance_hit:
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

    if launch_hit:
        score += 2.0

    if operational_hit:
        score += 1.6

    if watchlist_hit:
        score += 1.8

    if any(keyword in combined for keyword in TEAM_PRIORITY_KEYWORDS):
        score += 1.2

    score += max(-1.5, min(1.5, (kanta_fit_score - 5.0) * 0.5))

    if risk_hit:
        if bytedance_hit:
            score += 1.0
            label = "ByteDance Risk"
        elif watchlist_hit or launch_hit or operational_hit:
            score -= 0.4
        else:
            score -= 1.4

    if not (launch_hit or operational_hit or watchlist_hit or priority == "critical"):
        score -= 1.2

    if soft_context_hit and not (launch_hit or operational_hit or watchlist_hit or priority in {"critical", "high"}):
        score -= 2.2

    published = article.get("published")
    age_hours = None
    if isinstance(published, datetime):
        age_hours = (datetime.now(timezone.utc) - published).total_seconds() / 3600
        if age_hours <= 3:
            score += 1.0
        elif age_hours <= 6:
            score += 0.6

    return {
        "score": round(score, 1),
        "label": label,
        "focus_bucket": focus_bucket,
        "kanta_fit_score": kanta_fit_score,
        "watchlist_hit": watchlist_hit,
        "bytedance_hit": bytedance_hit,
        "launch_hit": launch_hit,
        "operational_hit": operational_hit,
        "risk_hit": risk_hit,
        "soft_context_hit": soft_context_hit,
        "priority": priority,
        "age_hours": age_hours,
    }


def score_alert(article: dict) -> tuple[float, str]:
    details = score_alert_details(article)
    return details["score"], details["label"]


def _blend_alert_priority(alert_score: float, kanta_fit_score: float) -> float:
    return round((alert_score * 0.65) + (kanta_fit_score * 0.35), 1)


def select_alert_articles(
    articles: list[dict],
    max_items: int = DEFAULT_MAX_ALERTS,
    min_score: float = DEFAULT_MIN_ALERT_SCORE,
) -> list[dict]:
    ranked: list[dict] = []
    for article in articles:
        details = score_alert_details(article)
        alert_score = details["score"]
        alert_label = details["label"]
        if alert_score < min_score:
            continue

        updated = dict(article)
        updated["focus_bucket"] = details["focus_bucket"]
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
