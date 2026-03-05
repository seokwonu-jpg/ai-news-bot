import json
import logging
import os
import re

import google.generativeai as genai

logger = logging.getLogger("summarizer")


def summarize_articles(articles: list[dict]) -> list[dict]:
    if not articles:
        return []

    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        logger.error('GEMINI_API_KEY 환경변수가 없습니다.')
        return _fallback(articles)

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name='gemini-2.0-flash')

    # 기사 목록을 프롬프트에 포함 (system_instruction 사용 안함)
    article_texts = []
    for idx, article in enumerate(articles):
        title = str(article.get('title', '')).strip()
        summary = str(article.get('summary', '')).strip()[:400]
        article_texts.append(f'[{idx}]\n제목: {title}\n내용: {summary}')

    prompt = f"""당신은 한국 비즈니스 실무자를 위한 AI 뉴스 큐레이터입니다.
아래 영어 AI 뉴스 기사들을 한국어로 요약하고, 구체적인 실무 활용법을 제시하세요.

반드시 아래 JSON 배열 형식으로만 응답하세요 (다른 텍스트 없이):
[
  {{
    "index": 0,
    "korean_summary": "기사 핵심을 자연스러운 한국어로 2-3문장 요약",
    "practical_tip": "한국 비즈니스 실무자가 바로 활용할 수 있는 구체적인 팁. 예: 'Notion AI 회의록 기능을 팀 미팅에 적용하면 정리 시간 절반으로 단축 가능' 처럼 구체적으로 작성. '원문을 확인하세요' 같은 무의미한 답변 절대 금지."
  }},
  ...
]

기사 목록:
{chr(10).join(article_texts)}
"""

    try:
        logger.info("Gemini API 호출 중... (%d개 기사)", len(articles))
        response = model.generate_content(prompt)
        raw_text = response.text.strip()
        logger.debug("Gemini 원본 응답:\n%s", raw_text)

        # JSON 추출 (마크다운 코드블록 제거)
        raw_text = re.sub(r'```(?:json)?\s*', '', raw_text).strip('`').strip()

        try:
            result_items = json.loads(raw_text)
        except json.JSONDecodeError:
            # JSON 배열만 추출 시도
            match = re.search(r'\[.*\]', raw_text, re.DOTALL)
            if match:
                result_items = json.loads(match.group())
            else:
                logger.error("JSON 파싱 실패. 응답 내용:\n%s", raw_text[:500])
                return _fallback(articles)

        # 인덱스 기준으로 매핑
        result_map = {}
        for item in result_items:
            if isinstance(item, dict) and 'index' in item:
                result_map[int(item['index'])] = item

        summarized = []
        for idx, article in enumerate(articles):
            updated = dict(article)
            if idx in result_map:
                updated['korean_summary'] = result_map[idx].get('korean_summary', article['title'])
                tip = result_map[idx].get('practical_tip', '')
                updated['practical_tip'] = tip if tip else '관련 AI 기능 도입을 팀 내 검토해보세요.'
            else:
                logger.warning("기사 [%d] 요약 누락", idx)
                updated['korean_summary'] = article['title']
                updated['practical_tip'] = '관련 AI 기능 도입을 팀 내 검토해보세요.'
            summarized.append(updated)

        logger.info("요약 완료: %d/%d건 성공", len(result_map), len(articles))
        return summarized

    except Exception as e:
        logger.exception("Gemini 요약 실패: %s", e)
        return _fallback(articles)


def _fallback(articles: list[dict]) -> list[dict]:
    result = []
    for article in articles:
        updated = dict(article)
        updated['korean_summary'] = article.get('title', '')
        updated['practical_tip'] = '관련 AI 기능 도입을 팀 내 검토해보세요.'
        result.append(updated)
    return result
