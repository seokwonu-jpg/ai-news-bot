import requests
import json
import logging
import os
import datetime

NUMBER_EMOJIS = ['1️⃣','2️⃣','3️⃣','4️⃣','5️⃣','6️⃣','7️⃣','8️⃣','9️⃣','🔟']
WEEKDAYS_KO = ['월','화','수','목','금','토','일']

logger = logging.getLogger('slack_sender')


def _today_korean() -> str:
    now = datetime.datetime.now()
    return f"{now.year}년 {now.month}월 {now.day}일 ({WEEKDAYS_KO[now.weekday()]})"


def _article_block(article: dict, index: int) -> dict:
    emoji = NUMBER_EMOJIS[index] if index < len(NUMBER_EMOJIS) else f"{index + 1}."
    title = article.get('title', '제목 없음')
    summary = article.get('korean_summary', '')
    practical_tip = article.get('practical_tip', '')
    url = article.get('url', '')

    block = {
        'type': 'section',
        'text': {
            'type': 'mrkdwn',
            'text': f"{emoji} *{title}*\n📌 {summary}\n💡 실무 활용: {practical_tip}",
        },
    }

    if url:
        block['accessory'] = {
            'type': 'button',
            'text': {'type': 'plain_text', 'text': '🔗 원문 보기', 'emoji': True},
            'url': url,
        }

    return block


def build_blocks(articles: list[dict], date_str: str = None) -> list:
    if date_str is None:
        date_str = _today_korean()

    video_image_articles = [a for a in articles if a.get('category') == 'video_image']
    other_articles = [a for a in articles if a.get('category') != 'video_image']

    blocks = [
        {
            'type': 'header',
            'text': {
                'type': 'plain_text',
                'text': f"🤖 AI 트렌드 데일리 브리핑 | {date_str}",
                'emoji': True,
            },
        },
        {'type': 'divider'},
        {'type': 'section', 'text': {'type': 'mrkdwn', 'text': '🎬 *영상 · 이미지 AI 콘텐츠 트렌드*'}},
    ]

    for i, article in enumerate(video_image_articles):
        blocks.append(_article_block(article, i))

    blocks.append({'type': 'divider'})
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': '💼 *비즈니스 AI 실무 트렌드*'}})

    for i, article in enumerate(other_articles):
        blocks.append(_article_block(article, i))

    blocks.append({'type': 'divider'})

    unique_sources = []
    seen = set()
    for article in articles:
        source_name = article.get('source_name')
        if source_name and source_name not in seen:
            seen.add(source_name)
            unique_sources.append(source_name)

    source_text = ', '.join(unique_sources) if unique_sources else '미상'
    blocks.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': f"출처: {source_text} 외"}]})

    return blocks


def send_to_slack(articles: list[dict], webhook_url: str = None) -> bool:
    webhook = webhook_url or os.environ.get('SLACK_WEBHOOK_URL')
    if not webhook:
        logger.error('Slack webhook URL is missing. Provide webhook_url or set SLACK_WEBHOOK_URL.')
        return False

    payload = {'blocks': build_blocks(articles)}

    try:
        response = requests.post(
            webhook,
            headers={'Content-Type': 'application/json'},
            data=json.dumps(payload),
            timeout=10,
        )
        if response.status_code == 200:
            return True

        logger.error(
            'Failed to send Slack message. status_code=%s body=%s',
            response.status_code,
            response.text,
        )
        return False
    except requests.RequestException as e:
        logger.error('Error while sending Slack message: %s', e)
        return False
