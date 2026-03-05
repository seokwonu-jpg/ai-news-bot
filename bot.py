import logging
import os
import sys

from dotenv import load_dotenv
from sources_config import SOURCES
from rss_fetcher import fetch_articles
from curator import score_articles
from summarizer import summarize_articles
from slack_sender import send_to_slack
from dedup import load_seen, filter_new, mark_seen, save_seen

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('bot')


def main():
    load_dotenv()

    required_vars = ['GEMINI_API_KEY', 'SLACK_WEBHOOK_URL']
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        print(f"Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)

    logger.info('AI 뉴스봇 시작')

    seen = load_seen()
    articles = fetch_articles(SOURCES, hours=24)
    logger.info(f'{len(articles)}개 기사 수집됨')

    new_articles = filter_new(articles, seen)
    logger.info(f'{len(new_articles)}개 신규 기사 (중복 {len(articles)-len(new_articles)}개 제외)')

    if not new_articles:
        logger.info('새 기사 없음, 종료')
        sys.exit(0)

    scored = score_articles(new_articles, top_n=8)
    logger.info(f'상위 {len(scored)}개 기사 선별')

    summarized = summarize_articles(scored)
    success = send_to_slack(summarized)

    if success:
        seen = mark_seen(summarized, seen)
        save_seen(seen)
        logger.info('Slack 전송 완료')
    else:
        logger.error('Slack 전송 실패')
        sys.exit(1)


if __name__ == '__main__':
    main()
