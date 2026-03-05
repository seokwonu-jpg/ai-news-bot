import json
import logging
import os

import google.generativeai as genai

logger = logging.getLogger("summarizer")

SUMMARY_SYSTEM_PROMPT = """당신은 한국 비즈니스 실무자를 위한 AI 뉴스 큐레이터입니다.
영어 기사를 한국어로 번역·요약하고, 실무 적용 방법을 제시합니다.

각 기사에 대해 아래 JSON 형식으로만 응답하세요:
[
  {
    "index": 0,
    "korean_summary": "한국어로 번역된 핵심 내용 요약 (2-3문장, 사실 중심)",
    "practical_tip": "한국 비즈니스 실무자가 바로 활용할 수 있는 구체적인 팁 (예: 어떤 도구를 어떤 업무에 쓸 수 있는지, 어떤 전략적 시사점이 있는지)"
  },
  ...
]

주의사항:
- korean_summary: 기사의 핵심을 정확하게 한국어로 요약 (번역투 지양, 자연스러운 한국어 사용)
- practical_tip: "원문을 확인하세요" 같은 무의미한 답변 절대 금지. 반드시 구체적인 실무 활용법 제시
- 예시 practical_tip: "Notion AI 회의록 기능을 팀 미팅에 도입하면 정리 시간 50% 절감 가능", "Runway Gen-4를 브랜드 홍보 영상 제작에 활용하면 외주 비용 절감 가능"
- JSON 외 다른 텍스트 출력 금지"""


def summarize_articles(articles: list[dict]) -> list[dict]:
    if not articles:
        return []

    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        logger.error('GEMINI_API_KEY is not set.')
        return _fallback(articles)

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name='gemini-2.0-flash',
        system_instruction=SUMMARY_SYSTEM_PROMPT,
    )

    # 전체 기사를 한 번의 API 호출로 처리
    lines = []
    for idx, article in enumerate(articles):
        title = str(article.get('title', '')).strip()
        summary = str(article.get('summary', '')).strip()[:500]  # 너무 길면 자름
        lines.append(f'[{idx}] 제목: {title}\n내용: {summary}')

    user_prompt = '다음 AI 뉴스 기사들을 한국어로 요약하고 실무 활용법을 제시해주세요:\n\n' + '\n\n'.join(lines)

    try:
        response = model.generate_content(user_prompt)
        raw_text = response.text.strip()
        logger.info("Gemini 응답 수신 완료")

        # JSON 파싱
        try:
            result_items = json.loads(raw_text)
        except json.JSONDecodeError:
            start = raw_text.find('[')
            end = raw_text.rfind(']')
            if start != -1 and end != -1 and end > start:
                result_items = json.loads(raw_text[start:end + 1])
            else:
                raise ValueError(f"JSON 파싱 실패. 응답: {raw_text[:200]}")

        # 결과를 인덱스 기준으로 매핑
        result_map = {}
        for item in result_items:
            if isinstance(item, dict):
                idx = item.get('index')
                if idx is not None:
                    result_map[int(idx)] = item

        # 원본 기사에 요약 추가
        summarized = []
        for idx, article in enumerate(articles):
            updated = dict(article)
            if idx in result_map:
                updated['korean_summary'] = result_map[idx].get('korean_summary', article['title'])
                updated['practical_tip'] = result_map[idx].get('practical_tip', '관련 도구 도입을 검토해보세요.')
            else:
                logger.warning("기사 %d 요약 누락, 제목으로 대체", idx)
                updated['korean_summary'] = article['title']
                updated['practical_tip'] = '관련 AI 도구 도입을 검토해보세요.'
            summarized.append(updated)

        logger.info("요약 완료: %d/%d건", len(result_map), len(articles))
        return summarized

    except Exception:
        logger.exception("Gemini 요약 실패, fallback 처리")
        return _fallback(articles)


def _fallback(articles: list[dict]) -> list[dict]:
    """API 실패 시 영어 제목 그대로 반환"""
    result = []
    for article in articles:
        updated = dict(article)
        updated['korean_summary'] = article.get('title', '')
        updated['practical_tip'] = '관련 AI 도구 도입을 검토해보세요.'
        result.append(updated)
    return result
