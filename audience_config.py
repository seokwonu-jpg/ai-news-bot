TEAM_NAME = "Kanta"
TEAM_CONTEXT = (
    "Kanta is a video-first content platform. The team cares most about AI updates that can be "
    "applied quickly to real workflows such as pre-production, image/video generation, voice and "
    "dubbing, creator operations, localization, marketing asset production, and research automation."
)
TEAM_BRIEFING_TITLE = "Kanta AI 활용 브리핑"
TEAM_ALERT_TITLE = "Kanta 제작 툴 긴급 알림"

TEAM_PRIORITY_THEMES = [
    "영상/이미지 생성 툴",
    "성우/보이스/더빙 툴",
    "캐릭터/아바타/립싱크",
    "콘텐츠 제작 워크플로우 자동화",
    "로컬라이제이션/번역/음성 현지화",
    "마케팅 크리에이티브 제작",
    "리서치/운영 자동화",
]

VISUAL_PRIORITY_KEYWORDS = [
    "video",
    "image",
    "creative",
    "creator",
    "storyboard",
    "thumbnail",
    "avatar",
    "character",
    "animation",
    "editing",
    "editor",
    "render",
    "multimodal",
    "text-to-video",
    "image-to-video",
    "diffusion",
    "caption",
    "motion",
    "design",
]

VOICE_PRIORITY_KEYWORDS = [
    "voice",
    "audio",
    "speech",
    "tts",
    "stt",
    "asr",
    "dubbing",
    "dub",
    "lip sync",
    "lipsync",
    "voice clone",
    "voiceover",
    "narration",
    "transcription",
    "subtitle",
    "localization",
    "translation",
]

WORKFLOW_PRIORITY_KEYWORDS = [
    "agent",
    "assistant",
    "automation",
    "workflow",
    "research",
    "review",
    "approval",
    "asset",
    "prompt",
    "ops",
    "productivity",
    "campaign",
    "ugc",
]

TEAM_TOOL_WATCHLIST = [
    "bytedance",
    "tiktok",
    "capcut",
    "doubao",
    "jimeng",
    "seedance",
    "dreamina",
    "runway",
    "luma",
    "pika",
    "kling",
    "veo",
    "sora",
    "stability",
    "midjourney",
    "firefly",
    "adobe",
    "elevenlabs",
    "heygen",
    "synthesia",
    "descript",
]

TEAM_PRIORITY_KEYWORDS = list(
    dict.fromkeys(VISUAL_PRIORITY_KEYWORDS + VOICE_PRIORITY_KEYWORDS + WORKFLOW_PRIORITY_KEYWORDS + TEAM_TOOL_WATCHLIST)
)

KANTA_WORK_AREAS = [
    {
        "name": "기획/프리프로덕션",
        "keywords": ["storyboard", "script", "concept", "character", "avatar", "thumbnail", "design"],
        "use_case": "기획안, 콘티, 캐릭터 시안, 썸네일 시안을 빠르게 만드는 실험에 연결할 수 있습니다.",
        "experiment": "다음 콘텐츠 1건을 골라 기획안-콘티-썸네일 시안을 같은 툴 체인으로 1회 생성해 비교해보세요.",
    },
    {
        "name": "이미지/영상 제작",
        "keywords": ["video", "image", "animation", "editing", "render", "text-to-video", "image-to-video", "motion"],
        "use_case": "프로모션 영상, 숏폼 소재, 컷신, 비주얼 에셋 제작 속도를 높이는 데 바로 쓸 수 있습니다.",
        "experiment": "기존 제작물 1개를 골라 생성형 이미지·영상 툴로 대체 가능한 공정을 1단계만 치환해보세요.",
    },
    {
        "name": "성우/보이스/더빙",
        "keywords": ["voice", "audio", "speech", "tts", "stt", "dubbing", "dub", "lip sync", "lipsync", "voice clone"],
        "use_case": "보이스 테스트, 더빙, 립싱크, 내레이션, 음성 현지화 파이프라인 검토에 연결할 수 있습니다.",
        "experiment": "대표 영상 1개를 골라 TTS-더빙-자막 정합성까지 포함한 음성 현지화 파일럿을 돌려보세요.",
    },
    {
        "name": "마케팅/크리에이티브",
        "keywords": ["campaign", "ugc", "creative", "creator", "ads", "short-form", "thumbnail", "caption"],
        "use_case": "광고 소재, SNS 크리에이티브, UGC 스타일 테스트, 프로모션 카피 제작에 적용할 수 있습니다.",
        "experiment": "신규 캠페인 1건에서 배너/숏폼/카피 초안을 AI로 먼저 만들고 사람이 후편집하는 흐름을 시험해보세요.",
    },
    {
        "name": "로컬라이제이션",
        "keywords": ["translation", "subtitle", "localization", "transcription", "voiceover"],
        "use_case": "자막, 번역, 더빙, 다국어 소재 제작과 QA 비용을 줄이는 방향으로 검토할 수 있습니다.",
        "experiment": "한국어 원본 1건을 일본어 또는 영어 자막/더빙까지 한 번에 생성해 품질 체크리스트로 검수해보세요.",
    },
    {
        "name": "운영 자동화/리서치",
        "keywords": ["agent", "assistant", "automation", "workflow", "research", "review", "ops", "productivity"],
        "use_case": "뉴스 모니터링, 리서치 초안, 반복 문서 작성, 운영 체크리스트 자동화에 바로 연결할 수 있습니다.",
        "experiment": "반복 업무 1개를 골라 입력 템플릿-초안 생성-리뷰의 3단계 자동화 흐름으로 바꿔보세요.",
    },
]

PRODUCTHUNT_ALLOWLIST_WORK_AREAS = [
    "기획/프리프로덕션",
    "이미지/영상 제작",
    "성우/보이스/더빙",
    "마케팅/크리에이티브",
    "로컬라이제이션",
]
