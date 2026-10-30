"""태그 판정. 코드가 숫자로만 판정하고 LLM은 관여하지 않는다 (규칙 문서 §1, §2).

값이 없으면 추측하지 않고 None(빈칸)을 반환한다.
"""
from __future__ import annotations

from briefing import config
from briefing.analysis.macro import memo as macro_memo

UP, FLAT, DOWN = 1, 0, -1


def direction(value: float | None, flat: float) -> int | None:
    """보합 구간 ±flat 안이면 FLAT. 경계값은 방향 있음으로 본다."""
    if value is None:
        return None
    if abs(value) < flat:
        return FLAT
    return UP if value > 0 else DOWN


def flow_tag(net_flow_musd: float | None) -> str | None:
    if not net_flow_musd:  # None 또는 정확히 0
        return None
    return "유입" if net_flow_musd > 0 else "유출"


def risk_tag(nasdaq_chg_pct: float | None) -> str | None:
    if nasdaq_chg_pct is None:
        return None
    if nasdaq_chg_pct >= config.RISK_STRONG_PCT:
        return "강함"
    if nasdaq_chg_pct <= config.RISK_WEAK_PCT:
        return "약함"
    return "중립"


def position_tag(funding_pct: float | None, oi_7d_pct: float | None) -> str | None:
    """위에서부터 먼저 맞는 것. OI를 모르면 정상이라고 단정하지 않는다."""
    if funding_pct is None:
        return None
    if funding_pct >= config.FUNDING_LONG_CROWDED:
        return "롱 과밀"
    if funding_pct <= config.FUNDING_SHORT_CROWDED:
        return "숏 과밀"
    if funding_pct >= config.FUNDING_OVERHEAT:
        return "과열"
    if oi_7d_pct is None:
        return None
    if oi_7d_pct >= config.OI_7D_OVERHEAT_PCT:
        return "과열"
    return "정상"


def cvd_oi_tag(price_pct: float | None, oi_pct: float | None, cvd_ratio_pct: float | None) -> str | None:
    """가격 × OI × 선물 CVD 조합. OI 기준 항목(청산)이 CVD 기준 항목(다이버전스)보다 먼저다."""
    p = direction(price_pct, config.FLAT_PRICE_PCT)
    o = direction(oi_pct, config.FLAT_OI_PCT)
    c = direction(cvd_ratio_pct, config.FLAT_CVD_RATIO_PCT)
    if p is None or o is None or c is None:
        return None
    if p == UP:
        if o == DOWN:
            return "숏 청산 상승"
        if o == UP and c == UP:
            return "신규 롱 주도 상승"
        if c == DOWN:
            return "상승 다이버전스(매도 우세)"
    elif p == DOWN:
        if o == DOWN:
            return "롱 청산 하락(투매)"
        if o == UP and c == DOWN:
            return "신규 숏 주도 하락"
        if c == UP:
            return "하락 다이버전스(매수 우세)"
    return "혼조"


def compute(btc: dict, etf: dict, macro: dict) -> dict:
    nasdaq = macro.get("nasdaq") or {}
    return {
        "flow": flow_tag(etf.get("net_flow_musd")),
        "risk": risk_tag(nasdaq.get("chg_1d")),
        "position": position_tag(btc.get("funding_rate_pct"), btc.get("oi_change_7d_pct")),
        "cvd_oi": cvd_oi_tag(btc.get("change_24h_pct"), btc.get("oi_change_24h_pct"), btc.get("futures_cvd_24h_ratio_pct")),
        "cvd_oi_4h": cvd_oi_tag(btc.get("change_4h_pct"), btc.get("oi_change_4h_pct"), btc.get("futures_cvd_4h_ratio_pct")),
        "flow_memo": etf.get("memo"),
        "macro_memo": macro_memo(macro),
    }
