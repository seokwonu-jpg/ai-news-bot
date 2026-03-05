import anthropic
import logging
import os

logger = logging.getLogger("summarizer")

SUMMARY_SYSTEM_PROMPT = (
    "You are an AI news summarizer for Korean business professionals. "
    "For each article, output EXACTLY 2 lines. "
    "Line 1: concise Korean summary of what happened (1-2 sentences, under 80 chars). "
    "Line 2: starts with '실무 활용:' then a concrete actionable tip for Korean business users. "
    "No other text."
)


def summarize_article(article: dict) -> dict:
    try:
        client = anthropic.Anthropic()

        user_message = f'제목: {article["title"]}\n내용: {article["summary"]}'
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=SUMMARY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        response_text = "".join(
            block.text for block in getattr(response, "content", []) if getattr(block, "text", None)
        )
        lines = [line.strip() for line in response_text.splitlines() if line.strip()]

        korean_summary = lines[0] if lines else article["title"]
        practical_tip = ""
        for line in lines:
            if line.startswith("실무 활용:"):
                practical_tip = line[len("실무 활용:") :].strip()
                break
        if not practical_tip:
            practical_tip = "원문을 확인하세요."

        updated_article = dict(article)
        updated_article["korean_summary"] = korean_summary
        updated_article["practical_tip"] = practical_tip
        return updated_article
    except Exception:
        logger.exception("Failed to summarize article")
        updated_article = dict(article)
        updated_article["korean_summary"] = article["title"]
        updated_article["practical_tip"] = "원문을 확인하세요."
        return updated_article


def summarize_articles(articles: list[dict]) -> list[dict]:
    total = len(articles)
    summarized = []
    for index, article in enumerate(articles, start=1):
        logger.info("Summarizing article %d/%d", index, total)
        summarized.append(summarize_article(article))
    return summarized
