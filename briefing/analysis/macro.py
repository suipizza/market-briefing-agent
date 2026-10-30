"""매크로 지표 계산 (규칙 문서 §3). LLM에 줄 숫자와 플래그를 만든다.

10년물 변동은 bp, DXY와 나스닥은 %. 1년 범위 위치는 (종가 − 1년 저점) / (고점 − 저점) × 100.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from briefing import config


def _chg(s: pd.Series, n: int, unit: str) -> float | None:
    if len(s) <= n:
        return None
    now, past = float(s.iloc[-1]), float(s.iloc[-1 - n])
    return (now - past) * 100 if unit == "bp" else (now / past - 1) * 100


def indicator(s: pd.Series | None, unit: str, big_move: float | None) -> dict | None:
    """s: 대상일 이하의 일봉 종가 (date 인덱스, 오래된 순)."""
    if s is None or s.empty:
        return None
    as_of: date = s.index[-1]
    close = float(s.iloc[-1])
    year = s[[d > as_of - timedelta(days=365) for d in s.index]]
    hi, lo = float(year.max()), float(year.min())
    pos = (close - lo) / (hi - lo) * 100 if hi > lo else 50.0
    dist_hi = (close / hi - 1) * 100
    dist_lo = (close / lo - 1) * 100

    near = None
    if pos >= 100 - config.NEAR_EXTREME_PCTILE or dist_hi >= -config.NEAR_EXTREME_DIST_PCT:
        near = "high"
    elif pos <= config.NEAR_EXTREME_PCTILE or dist_lo <= config.NEAR_EXTREME_DIST_PCT:
        near = "low"

    chg_1d = _chg(s, 1, unit)
    return {
        "close": round(close, 4),
        "as_of": as_of.isoformat(),
        "unit": unit,
        "chg_1d": chg_1d,
        "chg_5d": _chg(s, 5, unit),
        "chg_20d": _chg(s, 20, unit),
        "range_pos_1y": pos,
        "high_52w": hi,
        "low_52w": lo,
        "dist_52w_high_pct": dist_hi,
        "dist_52w_low_pct": dist_lo,
        "big_move": None if big_move is None or chg_1d is None else abs(chg_1d) >= big_move,
        "near_extreme": near,
    }


def _flags(name: str, ind: dict | None) -> list[str]:
    """큰 움직임과 52주 고점·저점 근처를 문장 조각으로."""
    if not ind:
        return []
    unit = "bp" if ind["unit"] == "bp" else "%"
    out = []
    if ind["big_move"]:
        out.append(f"{name} 하루 큰 움직임({ind['chg_1d']:+.{1 if unit == 'bp' else 2}f}{unit})")
    if ind["near_extreme"] == "high":
        out.append(f"{name} 52주 고점 근처(고점 대비 {ind['dist_52w_high_pct']:+.2f}%)")
    elif ind["near_extreme"] == "low":
        out.append(f"{name} 52주 저점 근처(저점 대비 {ind['dist_52w_low_pct']:+.2f}%)")
    return out


def _fmt_chg(v: float | None, unit: str) -> str:
    if v is None:
        return "-"
    return f"{v:+.1f}bp" if unit == "bp" else f"{v:+.2f}%"


def memo(mac: dict) -> str | None:
    """매크로 메모 (코드 템플릿). 특이사항을 앞에, 숫자 요약을 뒤에 둔다.

    예) DXY 52주 고점 근처(고점 대비 -0.75%) | 10Y 4.99% (1일 +3.5bp, 5일 -11.0bp) · DXY 101.81 (1일 +0.20%, 5일 -0.03%)
    """
    us10y, dxy, nasdaq = mac.get("us10y"), mac.get("dxy"), mac.get("nasdaq")
    if not us10y and not dxy:
        return None
    flags = _flags("10Y", us10y) + _flags("DXY", dxy) + _flags("나스닥", nasdaq)
    parts = []
    if us10y:
        parts.append(f"10Y {us10y['close']:.2f}% (1일 {_fmt_chg(us10y['chg_1d'], 'bp')}, 5일 {_fmt_chg(us10y['chg_5d'], 'bp')})")
    if dxy:
        parts.append(f"DXY {dxy['close']:.2f} (1일 {_fmt_chg(dxy['chg_1d'], '%')}, 5일 {_fmt_chg(dxy['chg_5d'], '%')})")
    head = ", ".join(flags) if flags else "특이사항 없음"
    return f"{head} | {' · '.join(parts)}"


def compute(closes: dict[str, pd.Series | None], target: date, is_holiday: bool) -> dict:
    """휴장이거나 나스닥 대상일 행이 없으면 나스닥은 빈칸. 10년물과 DXY는 대상일 이하 최신 값."""
    nasdaq = closes.get("nasdaq")
    if is_holiday or nasdaq is None or nasdaq.empty or nasdaq.index[-1] != target:
        nasdaq_ind = None
    else:
        nasdaq_ind = indicator(nasdaq, "%", None)
    return {
        "us10y": indicator(closes.get("us10y"), "bp", config.BIG_MOVE_US10Y_BP),
        "dxy": indicator(closes.get("dxy"), "%", config.BIG_MOVE_DXY_PCT),
        "nasdaq": nasdaq_ind,
    }
