"""ETF 연속 일수, 5일 누적, 수급 메모 (규칙 문서 §4).

SoSoValue 기록에는 휴장일 행이 없으므로 휴장일은 자연히 건너뛰고 연속을 끊지 않는다.
순유입이 정확히 0이면 연속이 끊긴다.
"""
from __future__ import annotations

from datetime import date

from briefing import config


def streak(history: list[dict]) -> tuple[int, str | None]:
    """마지막 행부터 같은 부호가 몇 일 이어졌는지. (일수, '+'|'-'|None)."""
    if not history or not history[-1]["net_flow_musd"]:
        return 0, None
    sign = 1 if history[-1]["net_flow_musd"] > 0 else -1
    n = 0
    for row in reversed(history):
        v = row["net_flow_musd"]
        if not v or (v > 0) != (sign > 0):
            break
        n += 1
    return n, "+" if sign > 0 else "-"


def sum_last(history: list[dict], days: int) -> float | None:
    window = history[-days:]
    if len(window) < days or any(r["net_flow_musd"] is None for r in window):
        return None
    return sum(r["net_flow_musd"] for r in window)


def memo(streak_days: int, sign: str | None, sum_5d: float | None, coverage: str | None = None) -> str | None:
    if not streak_days or sign is None:
        return None
    word = "순유입" if sign == "+" else "순유출"
    parts = [f"{streak_days}일 연속 {word}"]
    if sum_5d is not None:
        parts.append(f"{config.ETF_SUM_DAYS}일 누적 {sum_5d:+,.1f}$M")
    text = ", ".join(parts)
    return f"{text} (잠정 {coverage})" if coverage else text


def etf_sum(by_etf: dict[str, float | None] | None) -> tuple[float, str] | None:
    """ETF별 값 합산. (합계 $M, '반영 수/전체 수').

    필수 ETF(IBIT 등 대형)가 아직 정산 전이면 None. 소형 ETF는 보고 전에도 0으로 찍히는 경우가 있어서,
    대형이 빠진 합산은 0이나 작은 값으로 나와 틀린 숫자가 된다 (2026-11-03: 6/12 반영, 합계 0.0).
    """
    if not by_etf:
        return None
    if any(by_etf.get(t) is None for t in config.ETF_SUM_REQUIRED):
        return None
    reported = [v for v in by_etf.values() if v is not None]
    return sum(reported), f"{len(reported)}/{len(by_etf)}"


def compute(raw: dict, target: date, is_holiday: bool) -> dict:
    """raw: sources.sosovalue.collect 결과."""
    out = {
        "target_date": target.isoformat(),
        "net_flow_musd": None,
        "ibit_net_flow_musd": raw.get("ibit_net_flow_musd"),
        "ibit_included": raw.get("ibit_included", False),
        "streak_days": None,
        "streak_sign": None,
        "sum_5d_musd": None,
        "memo": None,
        "source": None,          # "total" | "etf_sum"
        "coverage": None,        # ETF별 합산일 때 "11/12"
        "by_etf": raw.get("by_etf"),
        "is_provisional": True,  # 다음 날 확정 갱신 대상
        "data_status": "실패",
    }
    if is_holiday:
        out["data_status"] = "휴장"
        return out
    history = raw.get("total_history")
    if history is None:
        return out
    t = target.isoformat()
    history = [r for r in history if r["date"] <= t]
    has_total = bool(history) and history[-1]["date"] == t and history[-1]["net_flow_musd"] is not None

    if has_total:
        out["source"] = "total"
        status = "정상" if out["ibit_included"] else "잠정"
    else:
        # 합계 미확정 → ETF별 합산을 대상일 행으로 붙여서 계산한다
        summed = etf_sum(raw.get("by_etf"))
        if summed is None:
            out["data_status"] = "미반영"
            return out
        value, out["coverage"] = summed
        history = [r for r in history if r["date"] != t] + [{"date": t, "net_flow_musd": value}]
        out["source"] = "etf_sum"
        status = "잠정"

    n, sign = streak(history)
    s5 = sum_last(history, config.ETF_SUM_DAYS)
    out.update(
        net_flow_musd=history[-1]["net_flow_musd"],
        streak_days=n,
        streak_sign=sign,
        sum_5d_musd=s5,
        memo=memo(n, sign, s5, out["coverage"]),
        data_status=status,
    )
    return out
