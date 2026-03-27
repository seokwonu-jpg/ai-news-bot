import json
import logging
import os
import re

import requests
from article_focus import get_focus_bucket
from audience_config import TEAM_ALERT_TITLE, TEAM_BRIEFING_TITLE, TEAM_CONTEXT, TEAM_NAME
from gemini_config import gemini_endpoint, resolve_gemini_model

logger = logging.getLogger("summarizer")
_DEFAULT_TIP = "기존 업무 흐름 한 곳을 정해 1주일 파일럿 자동화를 설계해보세요."
_DEFAULT_WHY = "신규 AI 공급자와 기능 변화가 실제 도입 우선순위를 다시 정하게 만드는 신호입니다."
_GENERAL_TOPIC = {
    "name": "general",
    "keywords": [],
    "label": "생성형 AI 업계 동향",
    "title_suffix": "AI 업계 주요 동향",
    "summary": "주요 AI 기업과 서비스의 경쟁 구도가 빠르게 바뀌고 있습니다. 실무 조직은 새 기능 자체보다 업무 적합성과 운영 비용을 함께 봐야 합니다.",
    "why": _DEFAULT_WHY,
    "tip": _DEFAULT_TIP,
    "roles": ["기획", "운영"],
    "workflow": "주간 보고서 초안, 회의록 정리, 반복 문서 요약처럼 바로 테스트할 수 있는 업무에 연결해보세요.",
    "adoption_signal": "바로 테스트",
    "kanta_angle": "Kanta가 현재 운영 중인 생성형 AI 실험의 우선순위를 다시 점검하는 기준으로 활용할 수 있습니다.",
}
_TOPIC_RULES = [
    {
        "name": "bytedance_ecosystem",
        "keywords": ["bytedance", "tiktok", "capcut", "doubao", "jimeng", "seedance", "dreamina"],
        "label": "ByteDance·TikTok 생태계",
        "title_suffix": "ByteDance 생태계 업데이트",
        "summary": "ByteDance, TikTok, CapCut 계열 변화는 생성형 콘텐츠 제작뿐 아니라 배포 채널과 크리에이터 툴 경쟁에도 직접 영향을 줍니다.",
        "why": "생성 콘텐츠를 만드는 도구와 유통되는 플랫폼이 한 회사 생태계 안에서 붙으면 제작 기준과 캠페인 운영 방식이 함께 바뀔 수 있습니다.",
        "tip": "CapCut, TikTok, 기존 제작 툴을 하나의 흐름으로 놓고 소재 제작부터 배포까지 어디가 빨라지는지 비교해보세요.",
        "roles": ["콘텐츠", "마케팅", "전략"],
        "workflow": "짧은 영상 소재 제작, 크리에이터용 광고 컷 편집, 배포용 리사이징 업무와 연결해보기 좋습니다.",
        "adoption_signal": "바로 테스트",
        "kanta_angle": "Kanta가 생성한 영상·이미지 결과물을 실제 유통 채널과 연결해 성과를 보는 데 중요한 생태계 변화입니다.",
    },
    {
        "name": "video_visual",
        "keywords": ["video", "image", "creative", "runway", "midjourney", "luma", "veo", "sora", "pika", "kling"],
        "label": "영상·이미지 생성 AI",
        "title_suffix": "영상·이미지 AI 업데이트",
        "summary": "새로운 영상·이미지 생성 기능이나 모델 변화가 공개됐습니다. 콘텐츠 시안 제작 속도와 품질에 직접 영향을 줄 수 있습니다.",
        "why": "마케팅·콘텐츠 조직의 제작 리드타임과 외주 비용 구조를 빠르게 바꿀 수 있는 영역입니다.",
        "tip": "광고 시안, 썸네일, 스토리보드 중 반복 작업 하나를 골라 새 모델 품질과 비용을 비교해보세요.",
        "roles": ["마케팅", "콘텐츠", "디자인"],
        "workflow": "광고 배너 시안, 썸네일 후보안, 스토리보드 초안 제작 업무에 연결하기 좋습니다.",
        "adoption_signal": "바로 테스트",
        "kanta_angle": "Kanta의 이미지·영상 생성 파이프라인, 캐릭터 시안, 프로모션 소재 실험에 바로 연결할 수 있습니다.",
    },
    {
        "name": "voice_audio",
        "keywords": ["voice", "audio", "speech", "tts", "stt", "dubbing", "dub", "lipsync", "lip sync", "subtitle", "localization", "translation", "elevenlabs", "heygen", "synthesia", "descript"],
        "label": "보이스·더빙·오디오 AI",
        "title_suffix": "보이스·더빙 AI 업데이트",
        "summary": "보이스 생성, 더빙, 립싱크, 음성 현지화 관련 기능이나 제품 변화가 공개됐습니다. 음성 제작 속도와 다국어 운영에 직접 영향을 줄 수 있습니다.",
        "why": "Kanta 같은 영상 플랫폼에서는 성우 테스트, 다국어 더빙, 자막 정합성, 로컬라이제이션 비용 구조를 빠르게 바꿀 수 있는 영역입니다.",
        "tip": "대표 영상 1건을 골라 TTS, 더빙, 자막, 립싱크까지 한 번에 비교하는 파일럿을 짧게 돌려보세요.",
        "roles": ["콘텐츠", "로컬라이제이션", "마케팅"],
        "workflow": "내레이션 초안, 다국어 더빙, 릴스·숏폼용 보이스오버, 자막 QA 업무에 바로 연결하기 좋습니다.",
        "adoption_signal": "바로 테스트",
        "kanta_angle": "Kanta의 성우·더빙·음성 현지화 파이프라인을 줄이거나 자동화하는 후보로 바로 검토할 수 있습니다.",
    },
    {
        "name": "developer",
        "keywords": ["cursor", "coding", "developer", "code", "software", "repo", "programming"],
        "label": "개발 생산성 AI",
        "title_suffix": "개발용 AI 에이전트 출시",
        "summary": "개발자 생산성을 높이는 에이전트형 도구 경쟁이 심해지고 있습니다. 코드 탐색, 수정, 테스트 초안 자동화 효율이 핵심입니다.",
        "why": "엔지니어링 팀의 산출 속도뿐 아니라 리뷰 기준과 보안 통제 방식까지 같이 바뀔 수 있습니다.",
        "tip": "문서화, 테스트 초안, 리팩터링 제안 중 한 업무를 정해 저장소 단위 가드레일과 함께 실험해보세요.",
        "roles": ["개발", "데이터", "프로덕트"],
        "workflow": "테스트 초안 생성, 코드 설명 작성, 기술 문서 업데이트 업무에 먼저 붙여보세요.",
        "adoption_signal": "파일럿 검토",
        "kanta_angle": "Kanta의 생성 콘텐츠 툴체인과 내부 실험 환경을 더 빠르게 연결하는 개발 생산성 기반이 될 수 있습니다.",
    },
    {
        "name": "agents",
        "keywords": ["agent", "agents", "assistant", "workflow", "automation", "research"],
        "label": "업무형 AI 에이전트",
        "title_suffix": "AI 에이전트 기능 출시",
        "summary": "AI 에이전트가 특정 업무 흐름에 투입되는 사례입니다. 조사, 실행, 후속 정리 자동화 범위가 넓어질 수 있습니다.",
        "why": "단순 챗봇을 넘어서 실제 운영 프로세스와 연결되는 자동화 경쟁이 본격화됐다는 신호입니다.",
        "tip": "리서치, 보고서 초안, 고객 문의 분류 중 하나를 골라 입력 데이터와 승인 단계를 분리한 파일럿을 설계해보세요.",
        "roles": ["운영", "기획", "영업"],
        "workflow": "시장조사 초안, VOC 분류, 제안서 초안 작성 같은 반복 지식업무에 연결하기 좋습니다.",
        "adoption_signal": "바로 테스트",
        "kanta_angle": "콘텐츠 리서치, 프롬프트 관리, 실험 결과 정리 같은 주변 업무를 자동화해 제작 속도를 높일 수 있습니다.",
    },
    {
        "name": "healthcare",
        "keywords": ["healthcare", "medical", "clinical", "patient", "hospital"],
        "label": "헬스케어 특화 AI",
        "title_suffix": "헬스케어 AI 플랫폼 발표",
        "summary": "규제가 강한 산업에서도 특화형 AI 플랫폼 도입이 빨라지고 있습니다. 데이터 보안과 현업 적용 기준을 함께 검토해야 합니다.",
        "why": "산업 특화 AI는 일반 모델보다 도입 허들이 높지만, 성공하면 현업 프로세스에 더 깊게 들어갑니다.",
        "tip": "민감정보 비식별화 기준을 먼저 정하고, 문서 분류나 상담 요약처럼 제한된 범위부터 시범 적용해보세요.",
        "roles": ["운영", "전략", "컴플라이언스"],
        "workflow": "민감정보가 섞인 문서 분류, 상담 요약, 내부 지식 검색처럼 범위를 제한한 업무에 적합합니다.",
        "adoption_signal": "파일럿 검토",
        "kanta_angle": "Kanta가 외부 파트너나 사내 데이터로 콘텐츠 실험을 할 때 필요한 보안·운영 기준을 점검하는 데 유용합니다.",
    },
    {
        "name": "governance",
        "keywords": ["supply chain", "supply-chain", "court", "lawsuit", "risk", "export control", "regulation", "policy", "pentagon", "dod"],
        "label": "공급망·정책 리스크",
        "title_suffix": "AI 공급망·규제 이슈",
        "summary": "공급망·정책 리스크가 AI 벤더 선택에 영향을 줄 수 있다는 신호입니다. 기술 성능뿐 아니라 조달 안정성과 규제 이슈도 함께 봐야 합니다.",
        "why": "도입한 AI 벤더가 제약을 받으면 가격, 지원, 배포 일정까지 연쇄적으로 흔들릴 수 있습니다.",
        "tip": "핵심 AI 벤더별 의존도와 대체 가능성을 정리해 공급망 리스크 체크리스트를 만들어두세요.",
        "roles": ["전략", "구매", "IT운영"],
        "workflow": "사용 중인 AI 도구 목록과 대체 벤더를 정리하는 운영 리스크 점검 업무에 연결해보세요.",
        "adoption_signal": "전략 체크",
        "kanta_angle": "영상·이미지 생성에 쓰는 핵심 벤더가 막히면 제작 일정이 흔들릴 수 있으니 선제 대응이 필요합니다.",
    },
    {
        "name": "model_platform",
        "keywords": ["openai", "gpt", "anthropic", "claude", "model", "launches", "launch", "release", "version"],
        "label": "생성형 AI 모델·플랫폼",
        "title_suffix": "생성형 AI 모델 업데이트",
        "summary": "주요 AI 모델 또는 플랫폼이 새 버전과 상품 구성을 내놨습니다. 성능 향상뿐 아니라 가격·사용성 변화가 도입 판단에 영향을 줍니다.",
        "why": "같은 업무라도 모델 교체만으로 품질, 속도, 비용 구조가 달라져 운영 기준을 다시 잡아야 할 수 있습니다.",
        "tip": "현재 쓰는 프롬프트 3개를 기준으로 새 모델과 기존 모델의 응답 품질, 속도, 비용을 비교 측정해보세요.",
        "roles": ["기획", "운영", "마케팅"],
        "workflow": "회의록 요약, 보고서 초안, 고객 응대 문안 같은 기존 프롬프트 업무에 바로 비교 적용할 수 있습니다.",
        "adoption_signal": "바로 테스트",
        "kanta_angle": "Kanta가 쓰는 이미지·영상 생성 프롬프트나 기획 보조 업무의 기본 모델 선택을 다시 평가할 타이밍입니다.",
    },
    {
        "name": "enterprise",
        "keywords": ["aws", "enterprise", "platform", "business", "productivity", "service", "saas"],
        "label": "기업용 AI 서비스",
        "title_suffix": "기업용 AI 서비스 확대",
        "summary": "기업 업무에 직접 연결되는 AI 서비스가 확장되고 있습니다. 비용 대비 생산성 개선 포인트를 구체적으로 따져볼 시점입니다.",
        "why": "범용 모델 경쟁이 기업형 패키지와 도입 지원 경쟁으로 이동하고 있음을 보여줍니다.",
        "tip": "도입 검토 중인 SaaS 목록에 AI 기능을 분리해 정리하고, 실제 절감 가능한 시간을 역할별로 계산해보세요.",
        "roles": ["운영", "영업", "기획"],
        "workflow": "영업 메일 초안, 내부 문서 검색, 반복 리포트 작성처럼 SaaS와 붙어 있는 업무에 연결해보세요.",
        "adoption_signal": "바로 테스트",
        "kanta_angle": "Kanta가 이미 쓰는 협업 툴에 AI 기능이 붙는다면 제작 운영과 커뮤니케이션 비용을 낮출 수 있습니다.",
    },
]


def _call_gemini(prompt: str, api_key: str) -> str:
    model_name = resolve_gemini_model("summarizer")
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
        },
    }
    logger.info("Gemini summary request started (model=%s prompt chars=%d)", model_name, len(prompt))
    response = requests.post(
        gemini_endpoint("summarizer"),
        headers={"x-goog-api-key": api_key},
        json=payload,
        timeout=60,
    )
    logger.info("Gemini summary response status=%s", response.status_code)
    if response.status_code >= 400:
        logger.error("Gemini summary error body=%s", response.text)
    response.raise_for_status()
    data = response.json()
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text_chunks = [part.get("text", "") for part in parts if isinstance(part, dict) and part.get("text")]
    if text_chunks:
        return "".join(text_chunks)
    raise RuntimeError(f"Gemini summary returned no text parts: {json.dumps(data, ensure_ascii=False)[:800]}")


def _safe_load_json_payload(raw_text: str):
    cleaned = re.sub(r"```(?:json)?\s*", "", raw_text).strip("`").strip()
    candidates = [cleaned]

    for pattern in (r"\{.*\}", r"\[.*\]"):
        match = re.search(pattern, cleaned, re.DOTALL)
        if match:
            candidates.append(match.group())

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    raise json.JSONDecodeError("Unable to parse Gemini JSON", cleaned, 0)


def _normalize_text(text) -> str:
    if text is None:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def _article_context(article: dict, idx: int) -> str:
    keywords = ", ".join(article.get("keywords", [])[:5])
    focus_bucket = get_focus_bucket(article)
    context = [
        f"[{idx}]",
        f"source: {_normalize_text(article.get('source_name')) or 'unknown'}",
        f"category: {_normalize_text(article.get('category')) or 'general'}",
        f"focus: {focus_bucket}",
        f"title: {_normalize_text(article.get('title'))}",
    ]
    if keywords:
        context.append(f"keywords: {keywords}")

    summary = _normalize_text(article.get("summary"))
    if summary:
        context.append(f"summary: {summary[:360]}")

    content_text = _normalize_text(article.get("content_text"))
    if content_text:
        context.append(f"content: {content_text[:900]}")

    return "\n".join(context)


def _extract_brands(title: str) -> list[str]:
    candidates = re.findall(r"\b(?:[A-Z]{2,}|[A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)\b", title)
    stop_words = {"The", "Its", "This", "That", "Exclusive", "EXCLUSIVE"}
    brands: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        cleaned = candidate.strip()
        if cleaned in stop_words:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        brands.append(cleaned)
    return brands[:2]


def _match_topic(article: dict) -> dict:
    combined = " ".join(
        [
            _normalize_text(article.get("title")).lower(),
            _normalize_text(article.get("summary")).lower(),
            _normalize_text(article.get("content_text")).lower(),
            " ".join(str(item).lower() for item in article.get("keywords", [])),
        ]
    )
    focus_bucket = get_focus_bucket(article)

    bytedance_topic = next((rule for rule in _TOPIC_RULES if rule["name"] == "bytedance_ecosystem"), None)
    video_visual_topic = next((rule for rule in _TOPIC_RULES if rule["name"] == "video_visual"), _TOPIC_RULES[0])
    voice_audio_topic = next((rule for rule in _TOPIC_RULES if rule["name"] == "voice_audio"), _TOPIC_RULES[0])

    if bytedance_topic and any(keyword in combined for keyword in bytedance_topic["keywords"]):
        return bytedance_topic

    if focus_bucket == "voice_audio" or article.get("category") == "voice_audio":
        return voice_audio_topic

    if focus_bucket == "video_image" or article.get("category") == "video_image":
        return video_visual_topic

    best_rule = _GENERAL_TOPIC
    best_matches = 0
    for rule in _TOPIC_RULES:
        matches = sum(1 for keyword in rule["keywords"] if keyword in combined)
        if matches > best_matches:
            best_rule = rule
            best_matches = matches
    return best_rule


def _fallback_title(article: dict, topic: dict) -> str:
    brands = _extract_brands(_normalize_text(article.get("title")))
    if brands:
        title_suffix = topic["title_suffix"]
        if brands[0].lower() in title_suffix.lower():
            return title_suffix
        return f"{brands[0]} {title_suffix}"
    return topic["title_suffix"]


def _fallback_summary(article: dict, topic: dict) -> str:
    source = _normalize_text(article.get("source_name")) or "해당 매체"
    return f"{source}는 {topic['label']} 관련 변화를 다뤘습니다. {topic['summary']}"


def _fallback_keywords(article: dict, topic: dict) -> list[str]:
    fallback = [topic["label"]]
    for keyword in article.get("keywords", []):
        cleaned = _normalize_text(keyword)
        if cleaned and cleaned not in fallback:
            fallback.append(cleaned)
        if len(fallback) >= 3:
            break
    return fallback[:3]


def _fallback_article(article: dict) -> dict:
    topic = _match_topic(article)
    updated = dict(article)
    updated["translated_title"] = _fallback_title(article, topic)
    updated["korean_summary"] = _fallback_summary(article, topic)
    updated["why_it_matters"] = topic.get("why", _DEFAULT_WHY)
    updated["practical_tip"] = topic.get("tip", _DEFAULT_TIP)
    updated["insight_topic"] = topic["label"]
    updated["insight_keywords"] = _fallback_keywords(article, topic)
    updated["target_roles"] = topic.get("roles", _GENERAL_TOPIC["roles"])
    updated["workflow_example"] = topic.get("workflow", _GENERAL_TOPIC["workflow"])
    updated["adoption_signal"] = topic.get("adoption_signal", _GENERAL_TOPIC["adoption_signal"])
    updated["kanta_angle"] = topic.get("kanta_angle", _GENERAL_TOPIC["kanta_angle"])
    return updated


def _normalize_keywords(items, article: dict) -> list[str]:
    if not isinstance(items, list):
        items = []

    keywords: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = _normalize_text(item)
        lowered = cleaned.lower()
        if not cleaned or lowered in seen:
            continue
        seen.add(lowered)
        keywords.append(cleaned)
        if len(keywords) >= 3:
            break

    if keywords:
        return keywords
    return _fallback_keywords(article, _match_topic(article))


def _coerce_action_items(items: list[str]) -> list[str]:
    if not isinstance(items, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = _normalize_text(item)
        lowered = cleaned.lower()
        if not cleaned or lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(cleaned)
        if len(normalized) >= 3:
            break
    return normalized


def _normalize_roles(items, article: dict) -> list[str]:
    if not isinstance(items, list):
        items = []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = _normalize_text(item)
        lowered = cleaned.lower()
        if not cleaned or lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(cleaned)
        if len(normalized) >= 3:
            break

    if normalized:
        return normalized
    return _match_topic(article).get("roles", _GENERAL_TOPIC["roles"])


def _build_fallback_overview(articles: list[dict], briefing_mode: str = "daily") -> dict:
    topic_counts: dict[str, int] = {}
    action_items: list[str] = []
    for article in articles:
        topic = article.get("insight_topic") or _match_topic(article)["label"]
        topic_counts[topic] = topic_counts.get(topic, 0) + 1
        tip = _normalize_text(article.get("practical_tip"))
        if tip and tip not in action_items:
            action_items.append(tip)

    top_topics = sorted(topic_counts.items(), key=lambda item: item[1], reverse=True)
    if top_topics:
        theme_text = ", ".join(label for label, _ in top_topics[:3])
        if briefing_mode == "alert":
            market_summary = f"{TEAM_NAME} 관점에서 지금 바로 확인할 이슈는 {theme_text}입니다. 제작 파이프라인이나 배포 흐름에 연결되는지 우선 점검해야 합니다."
        else:
            market_summary = f"{TEAM_NAME} 관점에서는 오늘 {theme_text} 이슈가 중요합니다. 생성 콘텐츠 제작과 운영 실험에 바로 연결할 수 있는 항목부터 점검할 필요가 있습니다."
    else:
        if briefing_mode == "alert":
            market_summary = f"{TEAM_NAME} 관점에서 지금 바로 체크할 생성형 AI 이슈를 정리했습니다."
        else:
            market_summary = f"{TEAM_NAME} 관점에서 오늘 브리핑은 생성형 AI 제품 변화와 제작 워크플로우 연결 가능성을 중심으로 정리됐습니다."

    if not action_items:
        action_items = [_DEFAULT_TIP]

    return {
        "market_summary": market_summary,
        "action_items": action_items[:3],
    }


def _normalize_article_result(article: dict, result_map: dict[int, dict], idx: int) -> dict:
    fallback = _fallback_article(article)
    item = result_map.get(idx)
    if not isinstance(item, dict):
        return fallback

    updated = dict(article)
    updated["translated_title"] = _normalize_text(item.get("translated_title")) or fallback["translated_title"]
    updated["korean_summary"] = _normalize_text(item.get("korean_summary")) or fallback["korean_summary"]
    updated["why_it_matters"] = _normalize_text(item.get("why_it_matters")) or fallback["why_it_matters"]
    updated["practical_tip"] = _normalize_text(item.get("practical_tip")) or fallback["practical_tip"]
    updated["insight_topic"] = _normalize_text(item.get("insight_topic")) or fallback["insight_topic"]
    updated["insight_keywords"] = _normalize_keywords(item.get("keywords"), article)
    updated["target_roles"] = _normalize_roles(item.get("target_roles"), article)
    updated["workflow_example"] = _normalize_text(item.get("workflow_example")) or fallback["workflow_example"]
    updated["adoption_signal"] = _normalize_text(item.get("adoption_signal")) or fallback["adoption_signal"]
    updated["kanta_angle"] = _normalize_text(item.get("kanta_angle")) or fallback["kanta_angle"]
    return updated


def summarize_articles(articles: list[dict], briefing_mode: str = "daily") -> dict:
    if not articles:
        return {"overview": {"market_summary": "", "action_items": []}, "articles": [], "meta": {"briefing_mode": briefing_mode}}

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY 없음, heuristic fallback 사용")
        fallback_articles = [_fallback_article(article) for article in articles]
        return {
            "overview": _build_fallback_overview(fallback_articles, briefing_mode=briefing_mode),
            "articles": fallback_articles,
            "meta": {"briefing_mode": briefing_mode},
        }

    briefing_title = TEAM_ALERT_TITLE if briefing_mode == "alert" else TEAM_BRIEFING_TITLE
    mode_instruction = (
        "긴급 알림이므로 '왜 지금 봐야 하는지'와 '오늘 바로 할 일'을 더 짧고 직접적으로 작성하세요."
        if briefing_mode == "alert"
        else "일간 브리핑이므로 하루 흐름과 실행 가능성을 균형 있게 정리하세요."
    )

    prompt = f"""당신은 {TEAM_NAME} 팀을 위한 한국어 AI 전략/실무 브리핑 에디터입니다.
브리핑 제목: {briefing_title}
팀 맥락: {TEAM_CONTEXT}
아래 영문 AI 기사들을 바탕으로 Slack 뉴스 브리핑용 JSON만 생성하세요.

출력 형식:
{{
  "overview": {{
    "market_summary": "오늘 기사 전체 흐름을 한국어 2문장으로 요약",
    "action_items": ["이번 주 팀이 실행할 액션 1", "액션 2", "액션 3"]
  }},
  "articles": [
    {{
      "index": 0,
      "translated_title": "영문 제목을 자연스러운 한국어 제목으로 번역",
      "korean_summary": "기사 핵심 2문장 요약",
      "why_it_matters": "왜 중요한지 1문장",
      "target_roles": ["이 기사를 특히 봐야 하는 팀 1", "팀 2"],
      "workflow_example": "비개발자가 자신의 업무와 연결해볼 수 있는 구체적 업무 예시 1문장",
      "adoption_signal": "바로 테스트 / 파일럿 검토 / 전략 체크 중 하나",
      "kanta_angle": "이 뉴스가 Kanta의 생성 콘텐츠 실험과 제작/운영 워크플로우에 주는 시사점 1문장",
      "practical_tip": "이번 주 바로 실행 가능한 액션 1문장",
      "insight_topic": "한글 주제 라벨",
      "keywords": ["키워드1", "키워드2", "키워드3"]
    }}
  ]
}}

작성 규칙:
- JSON 외 텍스트 금지
- 과장 금지, 기사에 없는 내용은 추정하지 말 것
- translated_title은 28자 내외
- workflow_example은 비개발자도 바로 이해할 수 있는 업무 예시로 작성
- target_roles는 최대 3개
- adoption_signal은 '바로 테스트', '파일럿 검토', '전략 체크' 중 하나
- kanta_angle은 Kanta의 영상/이미지 포함 생성 콘텐츠 워크플로우와 연결해서 작성
- practical_tip은 '도입 검토' 같은 추상 표현 금지, 팀이 바로 실행할 수 있는 행동으로 작성
- why_it_matters는 시장/조직/업무 영향 중심으로 작성
- {mode_instruction}

기사 목록:
{chr(10).join(_article_context(article, idx) for idx, article in enumerate(articles))}
"""

    try:
        payload = _safe_load_json_payload(_call_gemini(prompt, api_key))
        if isinstance(payload, list):
            payload = {"overview": {}, "articles": payload}

        result_map: dict[int, dict] = {}
        for item in payload.get("articles", []):
            if not isinstance(item, dict):
                continue
            try:
                idx = int(item.get("index"))
            except (TypeError, ValueError):
                continue
            result_map[idx] = item

        summarized_articles = [
            _normalize_article_result(article, result_map, idx)
            for idx, article in enumerate(articles)
        ]

        overview = payload.get("overview", {})
        normalized_overview = {
            "market_summary": _normalize_text(overview.get("market_summary")),
            "action_items": _coerce_action_items(overview.get("action_items")),
        }
        fallback_overview = _build_fallback_overview(summarized_articles, briefing_mode=briefing_mode)
        if not normalized_overview["market_summary"]:
            normalized_overview["market_summary"] = fallback_overview["market_summary"]
        if not normalized_overview["action_items"]:
            normalized_overview["action_items"] = fallback_overview["action_items"]

        logger.info("Article summaries completed (parsed=%d total=%d)", len(result_map), len(articles))
        return {
            "overview": normalized_overview,
            "articles": summarized_articles,
            "meta": {"briefing_mode": briefing_mode},
        }
    except Exception as exc:
        logger.exception("Gemini summary failed: %s", exc)
        fallback_articles = [_fallback_article(article) for article in articles]
        return {
            "overview": _build_fallback_overview(fallback_articles, briefing_mode=briefing_mode),
            "articles": fallback_articles,
            "meta": {"briefing_mode": briefing_mode},
        }
