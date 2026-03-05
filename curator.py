import json
import logging
import os

import google.generativeai as genai

logger = logging.getLogger('curator')

SCORING_SYSTEM_PROMPT = """당신은 AI 뉴스 큐레이터입니다. 각 기사를 1-10점으로 평가하세요.

채점 기준:
- 9-10점: AI 영상/이미지 생성 툴 신기능 (Sora, Veo, Kling, Runway, Pika, Midjourney, DALL-E, Stable Diffusion), I2V/T2V 기술
- 7-8점: 지금 바로 사용 가능한 새 AI 툴, 인기 앱에 추가된 AI 기능 (Notion, Google Docs 등), 생산성 향상 워크플로우
- 5-6점: 일반적인 비즈니스 AI 동향
- 1-4점: 순수 ML 연구 논문, 제품 출시 없는 투자/인수 소식, 정책 논쟁, 개발자 전용 API 업데이트

다음 JSON 형식으로만 응답하세요:
[{"index":0,"score":8,"reason":"이유"}, ...]"""


def score_articles(articles: list[dict], top_n: int = 8) -> list[dict]:
    if top_n <= 0 or not articles:
        return []

    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        logger.warning('GEMINI_API_KEY is not set.')
        return _fallback(articles, top_n)

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name='gemini-2.0-flash',
        system_instruction=SCORING_SYSTEM_PROMPT,
    )

    lines = []
    for idx, article in enumerate(articles):
        title = str(article.get('title', '')).strip()
        summary = str(article.get('summary', '')).strip()[:300]
        lines.append(f'{idx}. {title}\n{summary}')

    user_prompt = '다음 AI 뉴스 기사들을 채점해주세요:\n\n' + '\n\n'.join(lines)

    try:
        response = model.generate_content(user_prompt)
        raw_text = response.text.strip()

        try:
            scored_items = json.loads(raw_text)
        except json.JSONDecodeError:
            start = raw_text.find('[')
            end = raw_text.rfind(']')
            if start == -1 or end == -1 or end < start:
                raise
            scored_items = json.loads(raw_text[start:end + 1])

        score_by_index: dict[int, int] = {}
        for item in scored_items:
            if not isinstance(item, dict):
                continue
            try:
                idx = int(item.get('index'))
                score = int(round(float(item.get('score'))))
                score_by_index[idx] = max(1, min(10, score))
            except (TypeError, ValueError):
                continue

        for idx, article in enumerate(articles):
            article['score'] = score_by_index.get(idx, 5)

        ranked = sorted(articles, key=lambda a: a.get('score', 0), reverse=True)
        logger.info("스코어링 완료: 상위 %d건 선별", min(top_n, len(ranked)))
        return ranked[:top_n]

    except Exception:
        logger.exception('Gemini 스코어링 실패, fallback 처리')
        return _fallback(articles, top_n)


def _fallback(articles: list[dict], top_n: int) -> list[dict]:
    for article in articles:
        article['score'] = 5
    return articles[:top_n]
