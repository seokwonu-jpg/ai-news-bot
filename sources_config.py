"""RSS 피드 소스 설정"""

SOURCES = [
    # 해외 주요 미디어
    {
        "name": "TechCrunch AI",
        "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
        "category": "general",
        "priority": "high",
    },
    {
        "name": "The Verge AI",
        "url": "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
        "category": "general",
        "priority": "high",
    },
    {
        "name": "VentureBeat AI",
        "url": "https://venturebeat.com/category/ai/feed/",
        "category": "general",
        "priority": "high",
    },
    {
        "name": "MIT Technology Review",
        "url": "https://www.technologyreview.com/feed/",
        "category": "general",
        "priority": "medium",
    },
    # 공식 AI 블로그
    {
        "name": "OpenAI Blog",
        "url": "https://openai.com/blog/rss/",
        "category": "official",
        "priority": "critical",
    },
    {
        "name": "Google DeepMind Blog",
        "url": "https://deepmind.google/blog/rss.xml",
        "category": "official",
        "priority": "critical",
    },
    {
        "name": "Anthropic Blog",
        "url": "https://www.anthropic.com/rss.xml",
        "category": "official",
        "priority": "critical",
    },
    # AI 툴 출시
    {
        "name": "ProductHunt AI",
        "url": "https://www.producthunt.com/feed?category=artificial-intelligence",
        "category": "tools",
        "priority": "high",
    },
    # 영상/이미지 AI 특화
    {
        "name": "Runway Blog",
        "url": "https://runwayml.com/blog/rss/",
        "category": "video_image",
        "priority": "critical",
    },
    {
        "name": "Stability AI Blog",
        "url": "https://stability.ai/blog/rss",
        "category": "video_image",
        "priority": "critical",
    },
    {
        "name": "Hugging Face Blog",
        "url": "https://huggingface.co/blog/feed.xml",
        "category": "video_image",
        "priority": "high",
    },
]

# 소스 카테고리별 표시 이름
CATEGORY_LABELS = {
    "video_image": "영상 · 이미지 AI 콘텐츠 트렌드",
    "official": "공식 발표",
    "general": "비즈니스 AI 실무 트렌드",
    "tools": "신규 AI 툴",
}

# 카테고리별 이모지
CATEGORY_EMOJIS = {
    "video_image": "🎬",
    "official": "📢",
    "general": "💼",
    "tools": "🛠️",
}
