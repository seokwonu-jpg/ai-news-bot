from __future__ import annotations

import re

from article_focus import get_focus_bucket
from audience_config import KANTA_WORK_AREAS, PRODUCTHUNT_ALLOWLIST_WORK_AREAS, TEAM_TOOL_WATCHLIST

DAILY_SOURCE_CAPS = {"ProductHunt AI": 2}
ALERT_SOURCE_CAPS = {"ProductHunt AI": 1}

_DAILY_PRODUCTHUNT_MIN_FIT = 6.0
_ALERT_PRODUCTHUNT_MIN_FIT = 7.0
_DAILY_MIN_OTHER_FIT = 2.5
_ALERT_MIN_OTHER_FIT = 3.0

_DIRECT_EXECUTION_SIGNALS = {
    "video",
    "image",
    "thumbnail",
    "storyboard",
    "render",
    "animation",
    "avatar",
    "editing",
    "editor",
    "voice",
    "audio",
    "speech",
    "tts",
    "stt",
    "asr",
    "dubbing",
    "dub",
    "lip sync",
    "lipsync",
    "subtitle",
    "subtitles",
    "caption",
    "voiceover",
    "narration",
    "localization",
    "translation",
}
_WORKFLOW_SIGNALS = {
    "creator",
    "creative",
    "marketing",
    "campaign",
    "ugc",
    "asset",
    "review",
    "approval",
    "research",
    "workflow",
    "automation",
    "script",
    "character",
    "transcription",
    "short-form",
    "short form",
}
_NOISE_KEYWORDS = {
    "crypto",
    "token",
    "blockchain",
    "wallet",
    "defi",
    "solana",
    "database",
    "sql",
    "kubernetes",
    "devops",
    "observability",
    "github",
    "repo",
    "repository",
    "deploy",
    "deployment",
    "incident",
    "bug",
    "payment",
    "payments",
    "book appointments",
    "appointment",
    "calendar",
    "meeting",
    "outbound",
    "crm",
    "accounting",
    "invoice",
    "second brain",
    "journal",
    "todo",
    "interview",
    "recruiting",
    "hiring",
}
_WORK_AREA_KEYWORDS = {area["name"]: set(area["keywords"]) for area in KANTA_WORK_AREAS}
_PRODUCTHUNT_ALLOWLIST = set(PRODUCTHUNT_ALLOWLIST_WORK_AREAS)
_PRODUCTHUNT_PROOF_KEYWORDS = {
    "api",
    "sdk",
    "plugin",
    "integration",
    "integrates",
    "export",
    "desktop",
    "ios",
    "android",
    "beta",
    "alpha",
    "generally available",
    "pricing",
    "price",
    "free trial",
    "enterprise",
    "for teams",
    "for creators",
    "customer",
    "customers",
    "case study",
    "open source",
    "open-source",
    "local",
    "locally",
}
_PRODUCTHUNT_PROOF_PATTERN = re.compile(r"\b\d+(?:\.\d+)?x\b|\b\d+%\b", re.IGNORECASE)


def _normalized_text(article: dict) -> str:
    fields = [
        article.get("source_name", ""),
        article.get("category", ""),
        article.get("title", ""),
        article.get("summary", ""),
        article.get("content_text", ""),
        article.get("korean_summary", ""),
        " ".join(str(item) for item in article.get("keywords", [])),
        " ".join(str(item) for item in article.get("insight_keywords", [])),
    ]
    return re.sub(r"\s+", " ", " ".join(str(field) for field in fields).lower()).strip()


def _matched_keywords(combined: str, keywords: set[str]) -> list[str]:
    return [keyword for keyword in keywords if keyword in combined]


def _match_work_areas(combined: str) -> list[tuple[int, str]]:
    matches: list[tuple[int, str]] = []
    for area_name, keywords in _WORK_AREA_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in combined)
        if score > 0:
            matches.append((score, area_name))
    matches.sort(key=lambda item: item[0], reverse=True)
    return matches


def annotate_kanta_fit(article: dict) -> dict:
    updated = dict(article)
    combined = _normalized_text(article)
    focus_bucket = get_focus_bucket(article)
    direct_hits = _matched_keywords(combined, _DIRECT_EXECUTION_SIGNALS)
    workflow_hits = _matched_keywords(combined, _WORKFLOW_SIGNALS)
    watchlist_hits = _matched_keywords(combined, set(TEAM_TOOL_WATCHLIST))
    noise_hits = _matched_keywords(combined, _NOISE_KEYWORDS)
    proof_hits = _matched_keywords(combined, _PRODUCTHUNT_PROOF_KEYWORDS)
    work_area_matches = _match_work_areas(combined)
    matched_area_names = [area_name for _, area_name in work_area_matches[:3]]
    allowlist_area_names = [area_name for area_name in matched_area_names if area_name in _PRODUCTHUNT_ALLOWLIST]
    quantified_proof = _PRODUCTHUNT_PROOF_PATTERN.findall(combined)
    if quantified_proof:
        proof_hits.extend(quantified_proof)
    unique_signals = list(dict.fromkeys(direct_hits + workflow_hits + watchlist_hits))

    score = 0.0
    if focus_bucket == "video_image":
        score += 4.2
    elif focus_bucket == "voice_audio":
        score += 4.2

    score += min(2.6, len(set(direct_hits)) * 0.65)
    score += min(2.2, len(set(workflow_hits)) * 0.45)
    score += min(1.8, len(set(watchlist_hits)) * 0.9)
    score += min(1.2, len(allowlist_area_names) * 0.6)
    score += min(1.2, len(set(proof_hits)) * 0.6)

    if str(article.get("source_name", "")).strip() == "ProductHunt AI":
        score -= 1.0

    penalty = min(4.0, len(set(noise_hits)) * 1.0)
    if penalty and focus_bucket == "other" and not direct_hits:
        penalty += 1.2
    score -= penalty

    score = round(max(0.0, min(10.0, score)), 1)

    updated["focus_bucket"] = focus_bucket
    updated["kanta_fit_score"] = score
    updated["kanta_fit_signals"] = unique_signals[:6]
    updated["kanta_fit_noise"] = noise_hits[:4]
    updated["kanta_fit_proof_signals"] = list(dict.fromkeys(proof_hits))[:4]
    updated["kanta_fit_watchlist_hits"] = list(dict.fromkeys(watchlist_hits))[:4]
    updated["kanta_work_area_matches"] = matched_area_names
    updated["kanta_allowlist_work_areas"] = allowlist_area_names
    return updated


def annotate_kanta_fit_batch(articles: list[dict]) -> list[dict]:
    return [annotate_kanta_fit(article) for article in articles]


def get_kanta_fit_score(article: dict) -> float:
    if "kanta_fit_score" in article:
        try:
            return float(article["kanta_fit_score"])
        except (TypeError, ValueError):
            pass
    return float(annotate_kanta_fit(article)["kanta_fit_score"])


def _allow_producthunt(article: dict, minimum_score: float) -> bool:
    focus_bucket = get_focus_bucket(article)
    fit_score = get_kanta_fit_score(article)
    noise_hits = article.get("kanta_fit_noise")
    area_hits = article.get("kanta_allowlist_work_areas")
    signal_hits = article.get("kanta_fit_signals")
    proof_hits = article.get("kanta_fit_proof_signals")
    watchlist_hits = article.get("kanta_fit_watchlist_hits")
    if not isinstance(noise_hits, list):
        noise_hits = annotate_kanta_fit(article).get("kanta_fit_noise", [])
    if not isinstance(area_hits, list):
        area_hits = annotate_kanta_fit(article).get("kanta_allowlist_work_areas", [])
    if not isinstance(signal_hits, list):
        signal_hits = annotate_kanta_fit(article).get("kanta_fit_signals", [])
    if not isinstance(proof_hits, list):
        proof_hits = annotate_kanta_fit(article).get("kanta_fit_proof_signals", [])
    if not isinstance(watchlist_hits, list):
        watchlist_hits = annotate_kanta_fit(article).get("kanta_fit_watchlist_hits", [])

    if not area_hits:
        return False

    if focus_bucket in {"video_image", "voice_audio"}:
        if noise_hits:
            return False
        if fit_score < max(4.8, minimum_score - 1.0):
            return False
        if watchlist_hits:
            return True
        return bool(proof_hits) and len(set(signal_hits)) >= 2
    if focus_bucket == "other":
        return False
    if noise_hits:
        return False
    return fit_score >= minimum_score


def filter_daily_candidates(articles: list[dict]) -> list[dict]:
    filtered: list[dict] = []
    for article in annotate_kanta_fit_batch(articles):
        if get_focus_bucket(article) == "other" and get_kanta_fit_score(article) < _DAILY_MIN_OTHER_FIT:
            continue
        if str(article.get("source_name", "")).strip() == "ProductHunt AI":
            if not _allow_producthunt(article, _DAILY_PRODUCTHUNT_MIN_FIT):
                continue
        filtered.append(article)
    return filtered


def filter_alert_candidates(articles: list[dict]) -> list[dict]:
    filtered: list[dict] = []
    for article in annotate_kanta_fit_batch(articles):
        if get_focus_bucket(article) == "other" and get_kanta_fit_score(article) < _ALERT_MIN_OTHER_FIT:
            continue
        if str(article.get("source_name", "")).strip() == "ProductHunt AI":
            if not _allow_producthunt(article, _ALERT_PRODUCTHUNT_MIN_FIT):
                continue
        filtered.append(article)
    return filtered


def take_capped_articles(articles: list[dict], max_items: int, source_caps: dict[str, int] | None = None) -> list[dict]:
    if max_items <= 0:
        return []

    counts: dict[str, int] = {}
    selected: list[dict] = []
    source_caps = source_caps or {}

    for article in articles:
        source_name = str(article.get("source_name", "")).strip()
        limit = source_caps.get(source_name)
        if limit is not None and counts.get(source_name, 0) >= limit:
            continue

        selected.append(article)
        counts[source_name] = counts.get(source_name, 0) + 1

        if len(selected) >= max_items:
            break

    return selected
