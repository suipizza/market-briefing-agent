"""NYSE 거래일 판정. KST 실행일을 미국 대상 거래일로 대응시킨다.

KST 오전(09:00~10:10)은 미국 동부 기준 전날 밤이므로 대상은 KST 실행일의 전날(미국 날짜)이다.
- 전날이 주말이면 직전 금요일로 거슬러 간다 (월요일 실행 → 금요일, 휴장 아님).
- 전날이 평일인데 NYSE 휴장이면 휴장으로 판정한다 (ETF, 나스닥 빈칸).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

import pandas_market_calendars as mcal


@dataclass(frozen=True)
class UsTarget:
    target_date: date      # ETF·나스닥 기준 미국 날짜
    is_holiday: bool       # 평일 휴장이면 True


@lru_cache(maxsize=8)
def _trading_days(year: int) -> frozenset[date]:
    cal = mcal.get_calendar("NYSE")
    days = cal.valid_days(start_date=f"{year - 1}-12-01", end_date=f"{year + 1}-01-31")
    return frozenset(d.date() for d in days)


def is_trading_day(d: date) -> bool:
    return d in _trading_days(d.year)


def us_target_for(run_date: date) -> UsTarget:
    d = run_date - timedelta(days=1)
    while d.weekday() >= 5:  # 토, 일
        d -= timedelta(days=1)
    return UsTarget(target_date=d, is_holiday=not is_trading_day(d))


def previous_trading_day(d: date) -> date:
    d -= timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


if __name__ == "__main__":
    import sys

    rd = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    print(rd, "->", us_target_for(rd))
