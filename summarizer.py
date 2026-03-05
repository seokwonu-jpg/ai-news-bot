import json
import logging
import os
import re

import requests

logger = logging.getLogger("summarizer")

_GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)
_DEFAULT_TIP = "관련 AI 기능 도입을 팀 내 검토해보세요."


def _call_gemini(prompt: str, api_key: str) -> str:
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2048},
    }
    print(f"[summarizer] Gemini REST 호출 시작 (prompt chars={len(prompt)})")
    response = requests.post(
        _GEMINI_ENDPOINT,
        params={"key": api_key},
        json=payload,
        timeout=60,
    )
    print(f"[summarizer] Gemini HTTP status: {response.status_code}")
    if response.status_code >= 400:
        print("[summarizer] Gemini error response:")
        print(response.text)
    response.raise_for_status()
    data = response.json()
    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
    print("[summarizer] Gemini raw response text:")
    print(raw_text)
    return raw_text


def summarize_articles(articles: list[dict]) -> list[dict]:
    if not articles:
        return []

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY 환경변수가 없습니다.")
        print("[summarizer] GEMINI_API_KEY 없음 -> fallback")
        return _fallback(articles)

    article_texts = []
    for idx, article in enumerate(articles):
        title = str(article.get("title", "")).strip()
        summary = str(article.get("summary", "")).strip()[:400]
        article_texts.append(f"[{idx}]\n제목: {title}\n내용: {summary}")

    prompt = f"""당신은 한국 비즈니스 실무자를 위한 AI 뉴스 큐레이터입니다.
아래 영어 AI 뉴스 기사들을 한국어로 요약하고, 구체적인 실무 활용법을 제시하세요.

반드시 아래 JSON 배열 형식으로만 응답하세요 (다른 텍스트 없이):
[
  {{
    "index": 0,
    "korean_summary": "기사 핵심을 자연스러운 한국어로 2-3문장 요약",
    "practical_tip": "한국 비즈니스 실무자가 바로 적용할 수 있는 구체적인 실무 팁. 예: 'Notion AI 회의록 기능으로 팀 미팅 정리 시간 50% 절감 가능'. 절대로 '원문을 확인하세요' 같은 무의미한 답변 금지."
  }}
]

기사 목록:
{chr(10).join(article_texts)}
"""

    try:
        raw_text = _call_gemini(prompt, api_key)
        cleaned = re.sub(r"```(?:json)?\s*", "", raw_text).strip("`").strip()

        try:
            result_items = json.loads(cleaned)
        except json.JSONDecodeError:
            print("[summarizer] 1차 JSON 파싱 실패, 배열 추출 재시도")
            match = re.search(r"\[.*\]", cleaned, re.DOTALL)
            if match:
                result_items = json.loads(match.group())
            else:
                print("[summarizer] JSON 파싱 최종 실패 -> fallback")
                print(cleaned[:1000])
                return _fallback(articles)

        result_map = {}
        for item in result_items:
            if isinstance(item, dict) and "index" in item:
                try:
                    result_map[int(item["index"])] = item
                except (TypeError, ValueError):
                    continue

        summarized = []
        for idx, article in enumerate(articles):
            updated = dict(article)
            if idx in result_map:
                updated["korean_summary"] = result_map[idx].get(
                    "korean_summary", article.get("title", "")
                )
                tip = str(result_map[idx].get("practical_tip", "")).strip()
                updated["practical_tip"] = tip if tip else _DEFAULT_TIP
            else:
                logger.warning("기사 [%d] 요약 누락", idx)
                updated["korean_summary"] = article.get("title", "")
                updated["practical_tip"] = _DEFAULT_TIP
            summarized.append(updated)

        print(f"[summarizer] 요약 완료: parsed={len(result_map)}, total={len(articles)}")
        return summarized

    except Exception as e:
        logger.exception("Gemini 요약 실패: %s", e)
        print(f"[summarizer] 예외 발생 -> fallback: {e}")
        return _fallback(articles)


def _fallback(articles: list[dict]) -> list[dict]:
    result = []
    for article in articles:
        updated = dict(article)
        updated["korean_summary"] = article.get("title", "")
        updated["practical_tip"] = _DEFAULT_TIP
        result.append(updated)
    return result
