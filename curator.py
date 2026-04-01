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

    score += max(-2.2, min(2.2, (kanta_fit_score - 5.0) * 0.8))

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


def _apply_focus_balance(ranked_articles: list[dict], top_n: int) -> list[dict]:
    if top_n <= 0 or not ranked_articles:
        return []

    selected: list[dict] = []
    used_urls: set[str] = set()

    for focus_bucket in _PRIORITY_FOCUS_BUCKETS:
        if len(selected) >= top_n:
            break

        candidate = next(
            (
                article
                for article in ranked_articles
                if get_focus_bucket(article) == focus_bucket and float(article.get("score", 0)) >= _MIN_FOCUS_SCORE
            ),
            None,
        )
        if candidate is None:
            continue

        candidate_url = str(candidate.get("url", "")).strip()
        if candidate_url and candidate_url in used_urls:
            continue

        selected.append(candidate)
        if candidate_url:
            used_urls.add(candidate_url)

    for article in ranked_articles:
        if len(selected) >= top_n:
            break

        article_url = str(article.get("url", "")).strip()
        if article_url and article_url in used_urls:
            continue

        selected.append(article)
        if article_url:
            used_urls.add(article_url)

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
