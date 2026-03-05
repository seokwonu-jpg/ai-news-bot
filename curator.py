import json
import logging
import os
import re

import google.generativeai as genai

logger = logging.getLogger('curator')


def score_articles(articles: list[dict], top_n: int = 8) -> list[dict]:
    if top_n <= 0 or not articles:
        return []

    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        logger.warning('GEMINI_API_KEY 없음, fallback 처리')
        return _fallback(articles, top_n)

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name='gemini-2.0-flash')

    article_texts = []
    for idx, article in enumerate(articles):
        title = str(article.get('title', '')).strip()
        summary = str(article.get('summary', '')).strip()[:300]
        cat = article.get('category', '')
        category_hint = ' [영상/이미지 AI 카테고리]' if cat == 'video_image' else ''
        article_texts.append(f'[{idx}]{category_hint}\n제목: {title}\n내용: {summary}')

    prompt = f"""당신은 AI 뉴스 큐레이터입니다. 아래 기사들을 1-10점으로 평가하세요.

채점 기준:
- 9-10점: AI 영상/이미지 생성 툴 신기능 (Sora, Veo, Kling, Runway, Pika, Midjourney, DALL-E, Stable Diffusion), I2V/T2V 기술, [영상/이미지 AI 카테고리] 표시 기사
- 7-8점: 지금 바로 사용 가능한 새 AI 툴 출시, 인기 앱(Notion, Google Docs, MS Office 등)에 추가된 AI 기능, 생산성/비용절감 워크플로우
- 5-6점: 일반적인 비즈니스 AI 동향, 전략적 AI 뉴스
- 1-4점: 순수 ML 연구논문, 제품출시 없는 투자/인수 뉴스, AI 정책 논쟁, 개발자 전용 API 업데이트

반드시 아래 JSON 배열 형식으로만 응답하세요 (다른 텍스트 없이):
[{{"index": 0, "score": 8, "reason": "이유"}}, ...]

기사 목록:
{chr(10).join(article_texts)}
"""

    try:
        logger.info("Gemini 스코어링 호출 중... (%d개 기사)", len(articles))
        response = model.generate_content(prompt)
        raw_text = response.text.strip()
        logger.debug("Gemini 스코어링 응답:\n%s", raw_text)

        # 마크다운 코드블록 제거
        raw_text = re.sub(r'```(?:json)?\s*', '', raw_text).strip('`').strip()

        try:
            scored_items = json.loads(raw_text)
        except json.JSONDecodeError:
            match = re.search(r'\[.*\]', raw_text, re.DOTALL)
            if match:
                scored_items = json.loads(match.group())
            else:
                logger.error("스코어링 JSON 파싱 실패:\n%s", raw_text[:500])
                return _fallback(articles, top_n)

        score_by_index: dict[int, int] = {}
        for item in scored_items:
            if not isinstance(item, dict):
                continue
            try:
                idx = int(item.get('index'))
                score = int(round(float(item.get('score', 5))))
                score_by_index[idx] = max(1, min(10, score))
            except (TypeError, ValueError):
                continue

        for idx, article in enumerate(articles):
            article['score'] = score_by_index.get(idx, 5)

        ranked = sorted(articles, key=lambda a: a.get('score', 0), reverse=True)
        logger.info("스코어링 완료: 상위 %d건 선별", min(top_n, len(ranked)))
        return ranked[:top_n]

    except Exception as e:
        logger.exception("Gemini 스코어링 실패: %s", e)
        return _fallback(articles, top_n)


def _fallback(articles: list[dict], top_n: int) -> list[dict]:
    for article in articles:
        article['score'] = 5
    return articles[:top_n]
