"""LLM 출력 검증. 통과한 서술만 노션에 쓴다.

- 반려(rejected): 키 누락, 문자열 아님, 길이 2배 초과, 금지 표현(매매 권유, 방향 예측) → 그 항목은 빈칸
- 경고(warnings): 길이 초과, 태그와 반대되는 표현, 파생 서술에 분류명이 없음 → 쓰되 기록
결과는 실행 JSON에 남겨서 검증 통과율과 모순 건수를 운영 지표로 쓴다.
"""
from __future__ import annotations

from briefing import config

NARRATIVE_KEYS = ("one_liner", "macro", "derivatives", "news_geo", "news_crypto", "calendar")

FORBIDDEN_PHRASES = (
    # 시장 참여자의 행동 묘사("공격적으로 매수하며", "신규 진입")는 막지 않도록 권유·예측 표현만 둔다
    "매수 기회", "매도 기회", "매수 추천", "매도 추천", "매수하세요", "매도하세요",
    "상승할 것", "하락할 것", "오를 것", "내릴 것", "반등할 것", "반등 예상", "하락 예상", "상승 예상",
    "목표가", "손절가",
)

# 태그 값 → 같이 나오면 모순인 표현
CONTRADICTIONS = {
    ("flow", "유입"): ("순유출", "ETF 유출"),
    ("flow", "유출"): ("순유입", "ETF 유입"),
    ("risk", "강함"): ("위험선호 약", "위험회피"),
    ("risk", "약함"): ("위험선호 강",),
}


def validate(narrative: dict, tags: dict) -> dict:
    limit = config.NARRATIVE_MAX_CHARS
    accepted: dict[str, str] = {}
    rejected: dict[str, str] = {}
    warnings: list[str] = []

    for key in NARRATIVE_KEYS:
        text = narrative.get(key)
        if text is None:
            rejected[key] = "missing"
            continue
        if not isinstance(text, str):
            rejected[key] = f"not a string ({type(text).__name__})"
            continue
        text = text.strip()
        if len(text) > limit * 2:
            rejected[key] = f"too long ({len(text)} chars)"
            continue
        hits = [p for p in FORBIDDEN_PHRASES if p in text]
        if hits:
            rejected[key] = f"forbidden phrase: {', '.join(hits)}"
            continue
        if len(text) > limit:
            warnings.append(f"{key}: over {limit} chars ({len(text)})")
        accepted[key] = text

    one_liner = accepted.get("one_liner", "")
    if len(one_liner) > config.ONE_LINER_MAX_CHARS:
        warnings.append(f"one_liner: over {config.ONE_LINER_MAX_CHARS} chars ({len(one_liner)})")
    for (tag, value), opposites in CONTRADICTIONS.items():
        if tags.get(tag) == value:
            for o in opposites:
                if o in one_liner:
                    warnings.append(f"one_liner contradicts tag {tag}={value}: '{o}'")

    cvd_oi = tags.get("cvd_oi")
    if cvd_oi and "derivatives" in accepted and cvd_oi.split("(")[0] not in accepted["derivatives"]:
        warnings.append(f"derivatives does not mention tag '{cvd_oi}'")

    sources = narrative.get("sources") if isinstance(narrative.get("sources"), list) else []
    return {
        "accepted": accepted,
        "rejected": rejected,
        "warnings": warnings,
        "sources": sources,
        "passed": len(accepted),
        "total": len(NARRATIVE_KEYS),
    }
