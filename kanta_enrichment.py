import re

from audience_config import KANTA_WORK_AREAS


def _normalized_text(article: dict) -> str:
    fields = [
        article.get("title", ""),
        article.get("summary", ""),
        article.get("content_text", ""),
        article.get("korean_summary", ""),
        article.get("why_it_matters", ""),
        " ".join(str(item) for item in article.get("keywords", [])),
        " ".join(str(item) for item in article.get("insight_keywords", [])),
    ]
    return re.sub(r"\s+", " ", " ".join(str(field) for field in fields).lower()).strip()


def _match_work_areas(article: dict) -> list[dict]:
    combined = _normalized_text(article)
    matches: list[tuple[int, dict]] = []

    for area in KANTA_WORK_AREAS:
        score = sum(1 for keyword in area["keywords"] if keyword in combined)
        if score > 0:
            matches.append((score, area))

    matches.sort(key=lambda item: item[0], reverse=True)
    return [area for _, area in matches[:3]]


def enrich_article(article: dict) -> dict:
    updated = dict(article)
    matched_areas = _match_work_areas(article)

    if not matched_areas:
        matched_areas = [KANTA_WORK_AREAS[-1]]

    updated["kanta_work_areas"] = [area["name"] for area in matched_areas]
    updated["kanta_use_case"] = matched_areas[0]["use_case"]
    updated["kanta_experiment"] = matched_areas[0]["experiment"]

    if not str(updated.get("practical_tip", "")).strip():
        updated["practical_tip"] = matched_areas[0]["experiment"]

    return updated


def enrich_digest(digest: dict) -> dict:
    updated = dict(digest)
    articles = [enrich_article(article) for article in digest.get("articles", [])]
    updated["articles"] = articles

    overview = dict(updated.get("overview", {}))
    area_counts: dict[str, int] = {}
    for article in articles:
        for area in article.get("kanta_work_areas", []):
            area_counts[area] = area_counts.get(area, 0) + 1

    if area_counts:
        priority_areas = [name for name, _ in sorted(area_counts.items(), key=lambda item: item[1], reverse=True)[:3]]
        overview["priority_areas"] = priority_areas

    updated["overview"] = overview
    return updated
