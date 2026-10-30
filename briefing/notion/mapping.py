"""스냅샷 JSON → 노션 속성. 속성 이름과 타입은 이 파일의 SCHEMA 한곳에만 둔다.

SCHEMA는 세 가지 역할을 한다.
1. DB 생성 스크립트가 속성을 만들 때의 정의
2. 노션에 쓸 수 있는 속성 이름의 허용 목록 (client.py가 검사)
3. 스냅샷 값을 어느 속성에 넣을지의 대응표
"""
from __future__ import annotations

from typing import Any, Callable

RICH_TEXT_LIMIT = 2000  # 노션 텍스트 객체당 최대 글자 수

# select 선택지와 색
FLOW_OPTIONS = [("유입", "green"), ("유출", "red")]
RISK_OPTIONS = [("강함", "green"), ("중립", "gray"), ("약함", "red")]
POSITION_OPTIONS = [("롱 과밀", "red"), ("숏 과밀", "blue"), ("과열", "orange"), ("정상", "gray")]
CVD_OI_OPTIONS = [
    ("신규 롱 주도 상승", "green"),
    ("숏 청산 상승", "yellow"),
    ("상승 다이버전스(매도 우세)", "orange"),
    ("신규 숏 주도 하락", "red"),
    ("롱 청산 하락(투매)", "purple"),
    ("하락 다이버전스(매수 우세)", "blue"),
    ("혼조", "gray"),
]
RUN_OPTIONS = [("성공", "green"), ("일부 실패", "yellow"), ("실패", "red")]
FLOW_DATA_OPTIONS = [
    ("확정", "green"), ("정상", "blue"), ("잠정", "yellow"), ("미반영", "orange"), ("휴장", "gray"), ("실패", "red"),
]


def _get(path: str) -> Callable[[dict], Any]:
    """'btc.price' 같은 점 경로로 스냅샷 값을 꺼내는 함수."""
    def f(snap: dict) -> Any:
        cur: Any = snap
        for key in path.split("."):
            if not isinstance(cur, dict):
                return None
            cur = cur.get(key)
        return cur
    return f


def _round(path: str, nd: int) -> Callable[[dict], Any]:
    get = _get(path)
    return lambda s: None if get(s) is None else round(get(s), nd)


# (속성 이름, 타입, 값 추출 함수 또는 None, 추가 정의)
# 값 추출 함수가 None이면 코드가 쓰지 않는 속성 (서술은 LLM 단계에서 따로 채운다, 수식은 노션이 계산)
SCHEMA: list[tuple[str, str, Callable[[dict], Any] | None, dict]] = [
    # 기본
    ("제목", "title", lambda s: f"{s['run_date']} 브리핑", {}),
    ("날짜", "date", _get("run_date"), {}),
    # 숫자
    ("BTC 가격", "number", _round("btc.price", 1), {"format": "number_with_commas"}),
    ("BTC 24h 변동률(%)", "number", _round("btc.change_24h_pct", 2), {}),
    ("OI 24h 변화율(%)", "number", _round("btc.oi_change_24h_pct", 2), {}),
    ("OI 7일 변화율(%)", "number", _round("btc.oi_change_7d_pct", 2), {}),
    ("펀딩비(%)", "number", _round("btc.funding_rate_pct", 4), {}),
    ("선물 CVD 변화(BTC)", "number", _round("btc.futures_cvd_24h_btc", 0), {"format": "number_with_commas"}),
    ("현물 CVD 변화(BTC)", "number", _round("btc.spot_cvd_24h_btc", 0), {"format": "number_with_commas"}),
    ("ETF 순유입($M)", "number", _round("etf.net_flow_musd", 1), {"format": "number_with_commas"}),
    ("US10Y(%)", "number", _round("macro.us10y.close", 3), {}),
    ("US10Y 1일(bp)", "number", _round("macro.us10y.chg_1d", 1), {}),
    ("US10Y 5일(bp)", "number", _round("macro.us10y.chg_5d", 1), {}),
    ("DXY 1일(%)", "number", _round("macro.dxy.chg_1d", 2), {}),
    ("DXY 5일(%)", "number", _round("macro.dxy.chg_5d", 2), {}),
    ("나스닥 변동률(%)", "number", _round("macro.nasdaq.chg_1d", 2), {}),
    # 태그 (코드 판정)
    ("수급", "select", _get("tags.flow"), {"options": FLOW_OPTIONS}),
    ("위험선호", "select", _get("tags.risk"), {"options": RISK_OPTIONS}),
    ("포지션", "select", _get("tags.position"), {"options": POSITION_OPTIONS}),
    ("CVD·OI 해석", "select", _get("tags.cvd_oi"), {"options": CVD_OI_OPTIONS}),
    ("수급 메모", "rich_text", _get("tags.flow_memo"), {}),
    ("매크로 메모", "rich_text", _get("tags.macro_memo"), {}),
    # 서술 (LLM)
    ("한줄 판단", "rich_text", None, {"narrative_key": "one_liner"}),
    ("매크로", "rich_text", None, {"narrative_key": "macro"}),
    ("파생·수급 해석", "rich_text", None, {"narrative_key": "derivatives"}),
    ("지정학·정치", "rich_text", None, {"narrative_key": "news_geo"}),
    ("크립토 뉴스", "rich_text", None, {"narrative_key": "news_crypto"}),
    ("경제 일정", "rich_text", None, {"narrative_key": "calendar"}),
    # 관리
    ("실행 상태", "select", _get("status.run"), {"options": RUN_OPTIONS}),
    ("수급 데이터 상태", "select", _get("status.flow_data"), {"options": FLOW_DATA_OPTIONS}),
    ("실행 시각", "date", _get("generated_at"), {}),
    ("경과일", "formula", None, {"expression": 'dateBetween(now(), prop("날짜"), "days")'}),
]

ALLOWED_PROPERTIES: frozenset[str] = frozenset(name for name, typ, _, _ in SCHEMA if typ != "formula")
NARRATIVE_PROPERTIES: dict[str, str] = {extra["narrative_key"]: name for name, _, _, extra in SCHEMA if "narrative_key" in extra}

# ETF 확정 갱신 때 다시 쓰는 속성
ETF_CONFIRM_PROPERTIES = ("ETF 순유입($M)", "수급", "수급 메모", "수급 데이터 상태")


# ---------- 값 → 노션 속성 객체 ----------

def rich_text(text: str | None) -> list[dict]:
    if not text:
        return []
    return [{"type": "text", "text": {"content": text[i:i + RICH_TEXT_LIMIT]}} for i in range(0, len(text), RICH_TEXT_LIMIT)]


def to_value(typ: str, value: Any) -> dict:
    if typ == "title":
        return {"title": rich_text(value)}
    if typ == "rich_text":
        return {"rich_text": rich_text(value)}
    if typ == "number":
        return {"number": value}
    if typ == "select":
        return {"select": {"name": value} if value else None}
    if typ == "date":
        return {"date": {"start": value} if value else None}
    raise ValueError(f"unsupported property type: {typ}")


def snapshot_properties(snap: dict, only: tuple[str, ...] | None = None) -> dict:
    """숫자, 태그, 관리 속성. only를 주면 그 속성만."""
    props = {}
    for name, typ, getter, _ in SCHEMA:
        if getter is None or (only and name not in only):
            continue
        props[name] = to_value(typ, getter(snap))
    return props


def narrative_properties(narrative: dict) -> dict:
    """LLM 서술 → rich_text 속성. 검증을 통과한 키만 들어온다고 가정한다."""
    return {name: to_value("rich_text", narrative.get(key)) for key, name in NARRATIVE_PROPERTIES.items() if key in narrative}


def schema_definition() -> dict:
    """DB 생성용 속성 정의."""
    out: dict = {}
    for name, typ, _, extra in SCHEMA:
        if typ == "number":
            out[name] = {"number": {"format": extra.get("format", "number")}}
        elif typ == "select":
            out[name] = {"select": {"options": [{"name": n, "color": c} for n, c in extra["options"]]}}
        elif typ == "formula":
            out[name] = {"formula": {"expression": extra["expression"]}}
        else:
            out[name] = {typ: {}}
    return out
