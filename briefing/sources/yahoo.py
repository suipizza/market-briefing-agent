"""야후 파이낸스에서 US10Y, DXY, 나스닥 일봉 종가를 가져온다. 계산은 analysis/macro.py가 한다.

- ^TNX는 이미 % 단위다 (4.38 = 4.38%).
- DXY는 거의 24시간 거래되어 대상일 이후 행이 있을 수 있으므로 대상일 이후 행은 버린다.
"""
from __future__ import annotations

import logging
import warnings
from datetime import date

import pandas as pd
import yfinance as yf

from briefing import config

log = logging.getLogger(__name__)

# yfinance 내부의 pandas 사용 중단 경고 (동작에는 영향 없음)
warnings.filterwarnings("ignore", message=".*inplace keyword.*")


def fetch_closes(ticker: str, target: date) -> pd.Series:
    """대상일 이하의 일봉 종가 (약 13개월). 인덱스는 date."""
    start = pd.Timestamp(target) - pd.DateOffset(months=13)
    end = pd.Timestamp(target) + pd.Timedelta(days=2)
    df = yf.Ticker(ticker).history(start=start.date(), end=end.date(), interval="1d", auto_adjust=False)
    if df.empty:
        raise RuntimeError(f"no data for {ticker}")
    s = df["Close"].dropna()
    s.index = [ts.date() for ts in s.index]
    return s[[d <= target for d in s.index]]


def collect(target: date, errors: list[dict]) -> dict[str, pd.Series | None]:
    out: dict[str, pd.Series | None] = {}
    for key, ticker in config.YAHOO_TICKERS.items():
        try:
            out[key] = fetch_closes(ticker, target)
        except Exception as e:
            log.error("yahoo %s failed: %s", ticker, e)
            errors.append({"stage": f"yahoo.{key}", "msg": str(e)})
            out[key] = None
    return out


if __name__ == "__main__":
    import sys

    t = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    errs: list[dict] = []
    for k, s in collect(t, errs).items():
        print(k, None if s is None else s.tail(3).to_dict())
    print("errors:", errs)
