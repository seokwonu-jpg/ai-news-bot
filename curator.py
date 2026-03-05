import json
import logging
import os

import google.generativeai as genai

logger = logging.getLogger('curator')

SCORING_SYSTEM_PROMPT = (
    'You are an AI news curator. Score each article from 1 to 10.\n'
    'Scoring rules:\n'
    '- 9-10: AI video/image generation tools and I2V/T2V technology, including Sora, Veo, Kling, Runway, Pika, Midjourney, DALL-E, and Stable Diffusion.\n'
    '- 7-8: New AI tools available now, AI features in popular apps, and productivity workflows.\n'
    '- 5-6: General business AI news.\n'
    '- 1-4: Pure ML research papers, investment news without product launch, policy debates, and developer-only API updates.\n'
    'Respond ONLY with a JSON array like [{"index":0,"score":8,"reason":"..."}, ...].'
)


def score_articles(articles: list[dict], top_n: int = 8) -> list[dict]:
    try:
        if top_n <= 0 or not articles:
            return []

        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            logger.warning('GEMINI_API_KEY is not set.')
        genai.configure(api_key=api_key)

        model = genai.GenerativeModel(
            model_name='gemini-2.0-flash',
            system_instruction=SCORING_SYSTEM_PROMPT,
        )

        lines = []
        for idx, article in enumerate(articles):
            title = str(article.get('title', '')).strip()
            summary = str(article.get('summary', '')).strip()
            lines.append(f'{idx}. Title: {title}\nSummary: {summary}')

        user_prompt = 'Score the following AI news articles using the rubric.\n\n' + '\n\n'.join(lines)

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
        if isinstance(scored_items, list):
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
        return ranked[:top_n]

    except Exception:
        logger.exception('Failed to score articles')
        fallback = articles[:top_n]
        for article in fallback:
            article['score'] = 5
        return fallback
