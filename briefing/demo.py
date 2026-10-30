"""키 없이 돌려보는 데모. 저장된 실행 기록 하나로 코드 판정, LLM 출력 검증, 노션 변환, 안전장치를 보여준다.

네트워크, API 키, 노션 토큰이 필요 없다.
"""
from __future__ import annotations

import json
from pathlib import Path

from briefing.analysis import tags
from briefing.llm import validate
from briefing.notion import client, mapping

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "2026-10-30.json"


def _value(prop: dict):
    """노션 속성 객체에서 사람이 읽을 값만 꺼낸다."""
    (typ, v), = prop.items()
    if typ in ("title", "rich_text"):
        text = "".join(t["text"]["content"] for t in v)
        return text if len(text) <= 60 else text[:60] + "…"
    if typ == "select":
        return v and v["name"]
    if typ == "date":
        return v and v["start"]
    return v


def run(path: Path = EXAMPLE) -> None:
    snap = json.loads(path.read_text(encoding="utf-8"))
    b = snap["btc"]
    print(f"[입력] {path.name}: {snap['run_date']} (미국 {snap['target_us_date']})")
    print(f"  BTC {b['price']:,} (24h {b['change_24h_pct']:+.2f}%), OI 24h {b['oi_change_24h_pct']:+.2f}%, "
          f"선물 CVD 거래량 대비 {b['futures_cvd_24h_ratio_pct']:+.2f}%, 펀딩비 {b['funding_rate_pct']:.4f}%")

    # 1. 판정은 코드: 숫자만으로 태그를 다시 계산하면 저장된 태그와 같아야 한다
    recomputed = tags.compute(snap["btc"], snap["etf"], snap["macro"])
    print("\n[1] 코드 판정 재현 (LLM 관여 없음)")
    for key in ("flow", "risk", "position", "cvd_oi", "cvd_oi_4h"):
        same = "일치" if recomputed[key] == snap["tags"][key] else f"불일치 (저장값 {snap['tags'][key]})"
        print(f"  {key:10s} → {recomputed[key]}  [{same}]")
    print(f"  매크로 메모 → {recomputed['macro_memo']}")

    # 2. LLM 출력 검증: 저장된 서술과, 일부러 규칙을 어긴 서술
    print("\n[2] LLM 출력 검증")
    ok = validate.validate(snap["narrative"], snap["tags"])
    print(f"  실제 서술: {ok['passed']}/{ok['total']} 통과, 경고 {len(ok['warnings'])}, 반려 {len(ok['rejected'])}")
    bad = {**snap["narrative"],
           "one_liner": "ETF 순유출이 이어진 약세 흐름.",          # 수급 태그(유입)와 반대
           "derivatives": "롱 청산이 끝나 매수 기회로 보인다."}    # 매매 권유
    checked = validate.validate(bad, snap["tags"])
    for k, why in checked["rejected"].items():
        print(f"  규칙 위반 예시 반려: {k} ← {why}")
    for w in checked["warnings"]:
        print(f"  규칙 위반 예시 경고: {w}")

    # 3. 노션 변환: 허용 목록 안의 속성만 만들어진다
    props = mapping.snapshot_properties(snap)
    props.update(mapping.narrative_properties(ok["accepted"]))
    print(f"\n[3] 노션 속성 {len(props)}개 생성 (허용 목록 {len(mapping.ALLOWED_PROPERTIES)}개 안)")
    for name in ("제목", "BTC 24h 변동률(%)", "CVD·OI 해석", "수급 메모", "매크로 메모", "한줄 판단"):
        print(f"  {name}: {_value(props[name])}")

    # 4. 안전장치: 허용되지 않은 속성은 네트워크 호출 전에 막힌다
    print("\n[4] 노션 안전장치")
    try:
        client.check_properties({**props, "임의 속성": {"number": 1}})
    except client.NotionGuardError as e:
        print(f"  차단됨: {e}")
