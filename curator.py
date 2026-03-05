import json
import logging
import os
import re

import requests

logger = logging.getLogger("curator")

_GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash:generateContent"
)


def _call_gemini(prompt: str, api_key: str) -> str:
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2048},
    }
    print(f"[curator] Gemini REST 호출 시작 (prompt chars={len(prompt)})")
    response = requests.post(
        _GEMINI_ENDPOINT,
        params={"key": api_key},
        json=payload,
        timeout=60,
    )
    print(f"[curator] Gemini HTTP status: {response.status_code}")
    if response.status_code >= 400:
        print("[curator] Gemini error response:")
        print(response.text)
    response.raise_for_status()
    data = response.json()
    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
    print("[curator] Gemini raw response:")
    print(raw_text[:500])
    return raw_text


def score_articles(articles: list[dict], top_n: int = 8) -> list[dict]:
    if top_n <= 0 or not articles:
        return []

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY 없음, fallback 처리")
        return _fallback(articles, top_n)

    article_texts = []
    for idx, article in enumerate(articles):
        title = str(article.get("title", "")).strip()
        summary = str(article.get("summary", "")).strip()[:300]
        cat = article.get("category", "")
        category_hint = " [영상/이미지 AI]" if cat == "video_image" else ""
        article_texts.append(f"[{idx}]{category_hint}\n제목: {title}\n내용: {summary}")

    prompt = f"""당신은 AI 뉴스 큐레이터입니다. 아래 기사들을 1-10점으로 평가하세요.

채점 기준:
- 9-10점: AI 영상/이미지 생성 모델/기능(Sora, Veo, Kling, Runway, Pika, Midjourney, DALL-E, Stable Diffusion), I2V/T2V 기술, [영상/이미지 AI] 표시 기사
- 7-8점: 실무 적용도 높은 생성형 AI 신기능/제품 출시, 업무 자동화/생산성 향상 기사
- 5-6점: 일반적인 AI 트렌드/업계 동향
- 1-4점: 순수 연구/정책/규제 중심, 실무 적용도 낮은 기사

반드시 아래 JSON 배열 형식으로만 응답하세요 (다른 텍스트 없이):
[{{"index": 0, "score": 8, "reason": "이유"}}, ...]

기사 목록:
{chr(10).join(article_texts)}
"""

    try:
        raw_text = _call_gemini(prompt, api_key)
        cleaned = re.sub(r"```(?:json)?\s*", "", raw_text).strip("`").strip()

        try:
            scored_items = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", cleaned, re.DOTALL)
            if match:
                scored_items = json.loads(match.group())
            else:
                print("[curator] JSON 파싱 실패 -> fallback")
                return _fallback(articles, top_n)

        score_by_index: dict[int, int] = {}
        for item in scored_items:
            if not isinstance(item, dict):
                continue
            try:
                idx = int(item.get("index"))
                score = int(round(float(item.get("score", 5))))
                score_by_index[idx] = max(1, min(10, score))
            except (TypeError, ValueError):
                continue

        for idx, article in enumerate(articles):
            article["score"] = score_by_index.get(idx, 5)

        ranked = sorted(articles, key=lambda a: a.get("score", 0), reverse=True)
        print(f"[curator] 스코어링 완료: parsed={len(score_by_index)}, total={len(articles)}")
        return ranked[:top_n]

    except Exception as e:
        logger.exception("Gemini 스코어링 실패: %s", e)
        print(f"[curator] 예외 발생 -> fallback: {e}")
        return _fallback(articles, top_n)


def _fallback(articles: list[dict], top_n: int) -> list[dict]:
    for article in articles:
        article["score"] = 5
    return articles[:top_n]
