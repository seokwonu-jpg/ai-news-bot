import json
import logging
import os
import re
from datetime import datetime, timezone

from article_focus import get_focus_bucket
from audience_config import (
    TEAM_CONTEXT,
    TEAM_NAME,
    TEAM_PRIORITY_KEYWORDS,
    TEAM_TOOL_WATCHLIST,
    VISUAL_PRIORITY_KEYWORDS,
    VOICE_PRIORITY_KEYWORDS,
    WORKFLOW_PRIORITY_KEYWORDS,
)
from llm_client import call_json_text, credential_env_name, credentials_available, resolve_provider
from selection_policy import DAILY_SOURCE_CAPS, get_kanta_fit_score, take_capped_articles

logger = logging.getLogger("curator")
_PRIORITY_BONUS = {
    "critical": 1.5,
    "high": 1.0,
    "medium": 0.5,
}
_FOCUS_BONUS = {
    "video_image": 3.0,
    "voice_audio": 3.0,
}
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
_OPERATIONAL_KEYWORDS = {
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
_TITLE_TOKEN_STOPWORDS = {
    "about",
    "after",
    "agent",
    "agents",
    "ai",
    "all",
    "and",
    "app",
    "apps",
    "artificial",
    "being",
    "can",
    "content",
    "creative",
    "creator",
    "creators",
    "feature",
    "features",
    "for",
    "from",
    "has",
    "have",
    "how",
    "image",
    "images",
    "into",
    "its",
    "model",
    "models",
    "new",
    "photo",
    "photos",
    "that",
    "the",
    "their",
    "them",
    "this",
    "tools",
    "video",
    "with",
    "your",
}
_POSITIVE_KEYWORDS = {
    "agent": 1.8,
    "assistant": 1.2,
    "launch": 1.5,
    "release": 1.5,
    "introduce": 1.1,
    "creative": 1.1,
    "image": 1.2,
    "video": 1.2,
    "healthcare": 1.0,
    "developer": 1.0,
    "coding": 1.3,
    "automation": 1.2,
    "workflow": 1.0,
    "productivity": 1.0,
    "model": 0.8,
    "gpt": 0.8,
    "openai": 0.8,
    "anthropic": 0.6,
    "aws": 0.6,
    "voice": 1.5,
    "audio": 1.4,
    "speech": 1.4,
    "tts": 1.6,
    "dubbing": 1.8,
    "lipsync": 1.8,
    "lip sync": 1.8,
    "subtitle": 1.1,
    "localization": 1.2,
    "translation": 1.1,
}
_NEGATIVE_KEYWORDS = {
    "court": -2.0,
    "lawsuit": -2.0,
    "supply-chain": -2.2,
    "supply chain": -2.2,
    "risk": -1.0,
    "export control": -1.8,
    "regulation": -1.3,
    "policy": -1.0,
    "label": -0.8,
    "investigation": -1.2,
    "antitrust": -1.2,
    "pentagon": -0.8,
    "dod": -0.8,
}
_KANTA_EXECUTION_KEYWORDS = {keyword: 1.0 for keyword in TEAM_PRIORITY_KEYWORDS}
for keyword in VISUAL_PRIORITY_KEYWORDS:
    _KANTA_EXECUTION_KEYWORDS[keyword] = max(_KANTA_EXECUTION_KEYWORDS.get(keyword, 0.0), 1.4)
for keyword in VOICE_PRIORITY_KEYWORDS:
    _KANTA_EXECUTION_KEYWORDS[keyword] = max(_KANTA_EXECUTION_KEYWORDS.get(keyword, 0.0), 1.5)
for keyword in WORKFLOW_PRIORITY_KEYWORDS:
    _KANTA_EXECUTION_KEYWORDS[keyword] = max(_KANTA_EXECUTION_KEYWORDS.get(keyword, 0.0), 1.2)
for keyword in TEAM_TOOL_WATCHLIST:
    _KANTA_EXECUTION_KEYWORDS[keyword] = max(_KANTA_EXECUTION_KEYWORDS.get(keyword, 0.0), 1.8)
_PRIORITY_FOCUS_BUCKETS = ("video_image", "voice_audio")
_MIN_FOCUS_SCORE = 6.5


def _combined_text(article: dict) -> str:
    return " ".join(
        [
            str(article.get("title", "")).lower(),
            str(article.get("summary", "")).lower(),
            str(article.get("content_text", "")).lower(),
            " ".join(str(keyword).lower() for keyword in article.get("keywords", [])),
        ]
    )


def _story_tokens(article: dict) -> set[str]:
    headline = " ".join(
        [
            str(article.get("title", "")).lower(),
            " ".join(str(keyword).lower() for keyword in article.get("keywords", [])[:5]),
        ]
    )
    tokens: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", headline):
        if len(token) < 3 or token in _TITLE_TOKEN_STOPWORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return set(tokens[:8])


def _has_operational_signal(article: dict) -> bool:
    combined = _combined_text(article)
    return any(keyword in combined for keyword in _LAUNCH_KEYWORDS) or any(keyword in combined for keyword in _OPERATIONAL_KEYWORDS)


def _has_watchlist_signal(article: dict) -> bool:
    combined = _combined_text(article)
    return any(keyword in combined for keyword in TEAM_TOOL_WATCHLIST)


def _is_soft_context_article(article: dict) -> bool:
    combined = _combined_text(article)
    if _has_operational_signal(article) or _has_watchlist_signal(article):
        return False
    return any(keyword in combined for keyword in _SOFT_CONTEXT_KEYWORDS)


def _is_similar_story(candidate: dict, selected: list[dict]) -> bool:
    candidate_tokens = _story_tokens(candidate)
    if not candidate_tokens:
        return False

    for article in selected:
        existing_tokens = _story_tokens(article)
        if not existing_tokens:
            continue
        shared = candidate_tokens & existing_tokens
        if len(shared) >= 3:
            return True
        union = candidate_tokens | existing_tokens
        if len(shared) >= 2 and union and (len(shared) / len(union)) >= 0.5:
            return True
    return False


def _article_context(article: dict, idx: int) -> str:
    title = str(article.get("title", "")).strip()
    summary = str(article.get("summary", "")).strip()
    content_text = str(article.get("content_text", "")).strip()
    category = str(article.get("category", "")).strip()
    focus_bucket = get_focus_bucket(article)
    priority = str(article.get("priority", "")).strip()
    keywords = ", ".join(article.get("keywords", [])[:5])

    context = [
        f"[{idx}]",
        f"category: {category or 'general'}",
        f"focus: {focus_bucket}",
        f"priority: {priority or 'medium'}",
        f"title: {title}",
    ]
    if keywords:
        context.append(f"keywords: {keywords}")
    if summary:
        context.append(f"summary: {summary[:320]}")
    if content_text:
        context.append(f"content: {content_text[:700]}")
    return "\n".join(context)


def _safe_load_json_array(raw_text: str):
    cleaned = re.sub(r"```(?:json)?\s*", "", raw_text).strip("`").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


def _heuristic_score(article: dict) -> float:
    title = str(article.get("title", "")).lower()
    summary = str(article.get("summary", "")).lower()
    content = str(article.get("content_text", "")).lower()
    combined = " ".join([title, summary, content])
    focus_bucket = get_focus_bucket(article)
    kanta_fit_score = get_kanta_fit_score(article)
    operational_hit = any(keyword in combined for keyword in _OPERATIONAL_KEYWORDS)
    launch_hit = any(keyword in combined for keyword in _LAUNCH_KEYWORDS)
    watchlist_hit = any(keyword in combined for keyword in TEAM_TOOL_WATCHLIST)
    soft_context_hit = any(keyword in combined for keyword in _SOFT_CONTEXT_KEYWORDS)

    score = 5.0

    if focus_bucket in _FOCUS_BONUS:
        score += _FOCUS_BONUS[focus_bucket]

    score += _PRIORITY_BONUS.get(str(article.get("priority", "")).lower(), 0.0)

    for keyword, delta in _POSITIVE_KEYWORDS.items():
        if keyword in combined:
            score += delta

    for keyword, delta in _NEGATIVE_KEYWORDS.items():
        if keyword in combined:
            score += delta

    for keyword, delta in _KANTA_EXECUTION_KEYWORDS.items():
        if keyword in combined:
            score += delta

    if launch_hit:
        score += 0.8

    if operational_hit:
        score += 0.8

    score += max(-2.2, min(2.2, (kanta_fit_score - 5.0) * 0.8))

    if soft_context_hit and not (launch_hit or operational_hit or watchlist_hit):
        score -= 1.4

    published = article.get("published")
    if isinstance(published, datetime):
        age_hours = (datetime.now(timezone.utc) - published).total_seconds() / 3600
        if age_hours <= 6:
            score += 0.6
        elif age_hours <= 12:
            score += 0.3

    return max(1.0, min(10.0, score))


def _blend_selection_score(editorial_score: float, kanta_fit_score: float) -> float:
    return round((editorial_score * 0.55) + (kanta_fit_score * 0.45), 1)


def _try_select_article(
    article: dict,
    *,
    selected: list[dict],
    used_urls: set[str],
    used_sources: set[str],
    soft_context_count: int,
    top_n: int,
    enforce_unique_source: bool,
    enforce_soft_limit: bool,
    enforce_story_dedup: bool,
) -> bool:
    article_url = str(article.get("url", "")).strip()
    if article_url and article_url in used_urls:
        return False

    source_name = str(article.get("source_name", "")).strip()
    if enforce_unique_source and len(selected) < min(top_n, 3) and source_name and source_name in used_sources:
        return False

    if enforce_story_dedup and _is_similar_story(article, selected):
        return False

    if enforce_soft_limit and _is_soft_context_article(article) and soft_context_count >= 1:
        return False

    selected.append(article)
    if article_url:
        used_urls.add(article_url)
    if source_name:
        used_sources.add(source_name)
    return True


def _fill_selection(
    candidates: list[dict],
    *,
    selected: list[dict],
    used_urls: set[str],
    used_sources: set[str],
    top_n: int,
    enforce_unique_source: bool,
    enforce_soft_limit: bool,
    enforce_story_dedup: bool,
) -> list[dict]:
    soft_context_count = sum(1 for article in selected if _is_soft_context_article(article))
    for article in candidates:
        if len(selected) >= top_n:
            break
        if _try_select_article(
            article,
            selected=selected,
            used_urls=used_urls,
            used_sources=used_sources,
            soft_context_count=soft_context_count,
            top_n=top_n,
            enforce_unique_source=enforce_unique_source,
            enforce_soft_limit=enforce_soft_limit,
            enforce_story_dedup=enforce_story_dedup,
        ):
            if _is_soft_context_article(article):
                soft_context_count += 1
    return selected


def _apply_focus_balance(ranked_articles: list[dict], top_n: int) -> list[dict]:
    if top_n <= 0 or not ranked_articles:
        return []

    selected: list[dict] = []
    used_urls: set[str] = set()
    used_sources: set[str] = set()

    for focus_bucket in _PRIORITY_FOCUS_BUCKETS:
        if len(selected) >= top_n:
            break

        bucket_candidates = [
            article
            for article in ranked_articles
            if get_focus_bucket(article) == focus_bucket and float(article.get("score", 0)) >= _MIN_FOCUS_SCORE
        ]
        _fill_selection(
            bucket_candidates,
            selected=selected,
            used_urls=used_urls,
            used_sources=used_sources,
            top_n=top_n,
            enforce_unique_source=True,
            enforce_soft_limit=True,
            enforce_story_dedup=True,
        )

    _fill_selection(
        ranked_articles,
        selected=selected,
        used_urls=used_urls,
        used_sources=used_sources,
        top_n=top_n,
        enforce_unique_source=True,
        enforce_soft_limit=True,
        enforce_story_dedup=True,
    )
    _fill_selection(
        ranked_articles,
        selected=selected,
        used_urls=used_urls,
        used_sources=used_sources,
        top_n=top_n,
        enforce_unique_source=False,
        enforce_soft_limit=True,
        enforce_story_dedup=True,
    )
    _fill_selection(
        ranked_articles,
        selected=selected,
        used_urls=used_urls,
        used_sources=used_sources,
        top_n=top_n,
        enforce_unique_source=False,
        enforce_soft_limit=False,
        enforce_story_dedup=True,
    )

    selected.sort(
        key=lambda article: (
            article.get("score", 0),
            article.get("published") or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    return take_capped_articles(selected, top_n, DAILY_SOURCE_CAPS)


def score_articles(articles: list[dict], top_n: int = 8) -> list[dict]:
    if top_n <= 0 or not articles:
        return []

    heuristic_scores = [_heuristic_score(article) for article in articles]

    if not credentials_available("curator"):
        provider = resolve_provider("curator")
        logger.warning(
            "%s 없음 또는 사용 불가 (provider=%s), heuristic fallback 사용",
            credential_env_name(provider),
            provider,
        )
        return _fallback(articles, heuristic_scores, top_n)

    prompt = f"""당신은 {TEAM_NAME} 팀을 위한 AI 뉴스 에디터입니다.
팀 맥락: {TEAM_CONTEXT}
아래 기사들을 '오늘 Slack 브리핑에 실을 가치' 기준으로 1-10점으로 평가하세요.

우선순위 기준:
- 높은 점수: 영상/이미지 생성 AI, 창작 툴, 콘텐츠 제작 자동화, 캐릭터/IP 활용, 제작 파이프라인에 직접 연결되는 제품 출시와 기능 업데이트
- 중간 점수: 주요 업계 동향, 파트너십, 시장 확대, 조직 전략 변화, 업무 자동화
- 낮은 점수: 소송, 낙인, 규제/정책 이슈만 다루고 실무 적용 포인트가 약한 기사

특히 아래 키워드와 관련되면 가치를 높게 보세요:
{", ".join(TEAM_PRIORITY_KEYWORDS[:12])}

반드시 아래 JSON 배열 형식으로만 응답하세요:
[{{"index": 0, "score": 8, "reason": "짧은 이유"}}]

기사 목록:
{chr(10).join(_article_context(article, idx) for idx, article in enumerate(articles))}
"""

    try:
        scored_items = _safe_load_json_array(
            call_json_text(
                task="curator",
                prompt=prompt,
                logger=logger,
                max_output_tokens=2048,
                temperature=0.2,
            )
        )
        llm_scores: dict[int, int] = {}
        for item in scored_items:
            if not isinstance(item, dict):
                continue
            try:
                idx = int(item.get("index"))
                score = int(round(float(item.get("score", 5))))
            except (TypeError, ValueError):
                continue
            llm_scores[idx] = max(1, min(10, score))

        ranked_articles: list[dict] = []
        for idx, article in enumerate(articles):
            updated = dict(article)
            updated["focus_bucket"] = get_focus_bucket(article)
            heuristic_score = heuristic_scores[idx]
            kanta_fit_score = get_kanta_fit_score(article)
            llm_score = llm_scores.get(idx)
            editorial_score = heuristic_score if llm_score is None else round((llm_score * 0.7) + (heuristic_score * 0.3), 1)
            updated["editorial_score"] = editorial_score
            updated["score"] = _blend_selection_score(editorial_score, kanta_fit_score)
            ranked_articles.append(updated)

        ranked_articles.sort(
            key=lambda article: (
                article.get("score", 0),
                article.get("published") or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )
        logger.info("Article scoring completed (llm=%d heuristic=%d)", len(llm_scores), len(articles))
        return _apply_focus_balance(ranked_articles, top_n)
    except Exception as exc:
        logger.exception("LLM scoring failed: %s", exc)
        return _fallback(articles, heuristic_scores, top_n)


def _fallback(articles: list[dict], heuristic_scores: list[float], top_n: int) -> list[dict]:
    ranked_articles: list[dict] = []
    for idx, article in enumerate(articles):
        updated = dict(article)
        updated["focus_bucket"] = get_focus_bucket(article)
        editorial_score = round(heuristic_scores[idx], 1)
        updated["editorial_score"] = editorial_score
        updated["score"] = _blend_selection_score(editorial_score, get_kanta_fit_score(article))
        ranked_articles.append(updated)

    ranked_articles.sort(
        key=lambda article: (
            article.get("score", 0),
            article.get("published") or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    return _apply_focus_balance(ranked_articles, top_n)
