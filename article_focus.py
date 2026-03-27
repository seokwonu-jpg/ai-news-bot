import re

from audience_config import VISUAL_PRIORITY_KEYWORDS, VOICE_PRIORITY_KEYWORDS

FOCUS_BUCKET_LABELS = {
    "video_image": "영상/이미지/제작 툴",
    "voice_audio": "보이스/더빙/오디오 툴",
    "other": "업무 활용/운영/기타 AI",
}

_VISUAL_BRANDS = {
    "runway",
    "luma",
    "pika",
    "kling",
    "veo",
    "sora",
    "stability",
    "midjourney",
    "firefly",
    "adobe",
    "capcut",
    "dreamina",
    "jimeng",
    "seedance",
}
_VOICE_BRANDS = {
    "elevenlabs",
    "descript",
    "heygen",
    "synthesia",
    "voiceover",
    "voice clone",
}
_VISUAL_HINTS = set(VISUAL_PRIORITY_KEYWORDS) | _VISUAL_BRANDS | {"short-form", "short form", "thumbnail"}
_VOICE_HINTS = set(VOICE_PRIORITY_KEYWORDS) | _VOICE_BRANDS | {"subtitles", "multilingual dub", "translation"}
_VOICE_TIEBREAKER_HINTS = {"voice", "speech", "audio", "tts", "dubbing", "dub", "subtitle", "localization"}


def _normalized_text(article: dict) -> str:
    parts = [
        article.get("source_name", ""),
        article.get("category", ""),
        article.get("title", ""),
        article.get("summary", ""),
        article.get("content_text", ""),
        article.get("korean_summary", ""),
        " ".join(str(item) for item in article.get("keywords", [])),
        " ".join(str(item) for item in article.get("insight_keywords", [])),
    ]
    return re.sub(r"\s+", " ", " ".join(str(part) for part in parts).lower()).strip()


def _keyword_score(combined: str, keywords: set[str]) -> int:
    return sum(1 for keyword in keywords if keyword in combined)


def infer_focus_bucket(article: dict) -> str:
    combined = _normalized_text(article)
    category = str(article.get("category", "")).strip().lower()

    visual_score = _keyword_score(combined, _VISUAL_HINTS)
    voice_score = _keyword_score(combined, _VOICE_HINTS)

    visual_brand_hit = any(brand in combined for brand in _VISUAL_BRANDS)
    voice_brand_hit = any(brand in combined for brand in _VOICE_BRANDS)

    if visual_brand_hit:
        visual_score += 2
    if voice_brand_hit:
        voice_score += 2

    if category == "video_image":
        visual_score += 2
    elif category == "voice_audio":
        voice_score += 2

    if voice_score > visual_score and voice_score >= 2:
        return "voice_audio"
    if visual_score > voice_score and visual_score >= 2:
        return "video_image"
    if voice_score >= 2 and any(keyword in combined for keyword in _VOICE_TIEBREAKER_HINTS):
        return "voice_audio"
    if visual_score >= 2:
        return "video_image"
    if category in {"video_image", "voice_audio"}:
        return category
    return "other"


def get_focus_bucket(article: dict) -> str:
    existing = str(article.get("focus_bucket", "")).strip().lower()
    if existing in FOCUS_BUCKET_LABELS:
        return existing
    return infer_focus_bucket(article)


def annotate_article(article: dict) -> dict:
    updated = dict(article)
    updated["focus_bucket"] = get_focus_bucket(article)
    return updated


def annotate_articles(articles: list[dict]) -> list[dict]:
    return [annotate_article(article) for article in articles]
