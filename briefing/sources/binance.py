"""바이낸스 BTCUSDT 선물·현물 수집과 CVD·OI·펀딩비 계산.

CVD 델타 = 2 × 테이커 매수량 − 전체 거래량 (캔들 단위, BTC). 바이낸스 단일 거래소 기준 근사치.
모든 구간은 기준 시각(as_of) 이전에 마감된 1시간봉만 쓴다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from briefing import config
from briefing.sources.http import request_json

log = logging.getLogger(__name__)

HOUR_MS = 3_600_000
FUNDING_TIME_TOLERANCE_MS = 60_000

# kline 배열 인덱스
K_OPEN_TIME, K_OPEN, K_CLOSE, K_VOLUME, K_CLOSE_TIME, K_TAKER_BUY = 0, 1, 4, 5, 6, 9


# ---------- 계산 (순수 함수) ----------

def closed_klines(klines: list[list], as_of_ms: int) -> list[list]:
    """as_of 이전에 마감된 캔들만 남긴다."""
    return [k for k in klines if int(k[K_CLOSE_TIME]) < as_of_ms]


def price_change_pct(klines: list[list], hours: int) -> float | None:
    """마지막 n개 캔들의 시가 대비 마지막 종가 변동률."""
    if len(klines) < hours:
        return None
    window = klines[-hours:]
    first_open = float(window[0][K_OPEN])
    last_close = float(window[-1][K_CLOSE])
    return (last_close / first_open - 1) * 100


def cvd(klines: list[list], hours: int) -> tuple[float, float] | None:
    """(누적 델타 BTC, 거래량 대비 %)."""
    if len(klines) < hours:
        return None
    window = klines[-hours:]
    delta = sum(2 * float(k[K_TAKER_BUY]) - float(k[K_VOLUME]) for k in window)
    volume = sum(float(k[K_VOLUME]) for k in window)
    ratio = delta / volume * 100 if volume else 0.0
    return delta, ratio


def oi_change_pct(oi_hist: list[dict], hours: int) -> float | None:
    """1시간 간격 OI 기록에서 n시간 전 대비 변화율."""
    if len(oi_hist) < hours + 1:
        return None
    now = float(oi_hist[-1]["sumOpenInterest"])
    past = float(oi_hist[-1 - hours]["sumOpenInterest"])
    return (now / past - 1) * 100 if past else None


# ---------- 수집 ----------

def _klines(base: str, path: str, as_of_ms: int) -> list[list]:
    limit = config.HOURLY_LOOKBACK_HOURS + 2
    data = request_json(
        "GET",
        f"{base}{path}",
        params={"symbol": config.BINANCE_SYMBOL, "interval": "1h", "limit": limit, "endTime": as_of_ms},
    )
    return closed_klines(data, as_of_ms)


def fetch_futures_klines(as_of_ms: int) -> list[list]:
    return _klines(config.BINANCE_FUTURES_URL, "/fapi/v1/klines", as_of_ms)


def fetch_spot_klines(as_of_ms: int) -> list[list]:
    return _klines(config.BINANCE_SPOT_URL, "/api/v3/klines", as_of_ms)


def fetch_oi_hist(as_of_ms: int) -> list[dict]:
    """1시간 간격 OI 기록 (7일 + 여유). 바이낸스는 최근 30일까지만 제공한다."""
    data = request_json(
        "GET",
        f"{config.BINANCE_FUTURES_URL}/futures/data/openInterestHist",
        params={"symbol": config.BINANCE_SYMBOL, "period": "1h", "limit": 7 * 24 + 2, "endTime": as_of_ms},
    )
    data = [d for d in data if int(d["timestamp"]) <= as_of_ms]
    return sorted(data, key=lambda d: int(d["timestamp"]))


def fetch_funding_pct(as_of_ms: int) -> float | None:
    """as_of 이전에 확정된 마지막 펀딩비 (8시간 기준, %)."""
    data = request_json(
        "GET",
        f"{config.BINANCE_FUTURES_URL}/fapi/v1/fundingRate",
        params={"symbol": config.BINANCE_SYMBOL, "limit": 3, "endTime": as_of_ms + FUNDING_TIME_TOLERANCE_MS},
    )
    # 정산 시각이 정각보다 몇 ms 늦게 찍히는 경우가 있어 1분 여유를 둔다
    data = [d for d in data if int(d["fundingTime"]) <= as_of_ms + FUNDING_TIME_TOLERANCE_MS]
    if not data:
        return None
    return float(max(data, key=lambda d: int(d["fundingTime"]))["fundingRate"]) * 100


def collect(as_of: datetime, errors: list[dict]) -> dict:
    """선물·현물 지표를 모은다. 실패한 항목은 None으로 두고 errors에 기록한다."""
    as_of_ms = int(as_of.timestamp() * 1000)
    out: dict = {
        "as_of": as_of.isoformat(),
        "price": None, "change_24h_pct": None, "change_4h_pct": None,
        "oi_btc": None, "oi_change_24h_pct": None, "oi_change_4h_pct": None, "oi_change_7d_pct": None,
        "funding_rate_pct": None,
        "futures_cvd_24h_btc": None, "futures_cvd_24h_ratio_pct": None, "futures_cvd_4h_ratio_pct": None,
        "spot_cvd_24h_btc": None, "spot_cvd_24h_ratio_pct": None,
    }

    def guard(name: str, fn):
        try:
            return fn()
        except Exception as e:  # 한 항목 실패가 전체를 멈추지 않게
            log.error("binance %s failed: %s", name, e)
            errors.append({"stage": f"binance.{name}", "msg": str(e)})
            return None

    fut = guard("futures_klines", lambda: fetch_futures_klines(as_of_ms))
    if fut:
        out["price"] = float(fut[-1][K_CLOSE])
        out["change_24h_pct"] = price_change_pct(fut, 24)
        out["change_4h_pct"] = price_change_pct(fut, 4)
        if (c24 := cvd(fut, 24)) is not None:
            out["futures_cvd_24h_btc"], out["futures_cvd_24h_ratio_pct"] = c24
        if (c4 := cvd(fut, 4)) is not None:
            out["futures_cvd_4h_ratio_pct"] = c4[1]

    spot = guard("spot_klines", lambda: fetch_spot_klines(as_of_ms))
    if spot and (s24 := cvd(spot, 24)) is not None:
        out["spot_cvd_24h_btc"], out["spot_cvd_24h_ratio_pct"] = s24

    oi = guard("open_interest", lambda: fetch_oi_hist(as_of_ms))
    if oi:
        out["oi_btc"] = float(oi[-1]["sumOpenInterest"])
        out["oi_change_24h_pct"] = oi_change_pct(oi, 24)
        out["oi_change_4h_pct"] = oi_change_pct(oi, 4)
        out["oi_change_7d_pct"] = oi_change_pct(oi, 7 * 24)

    out["funding_rate_pct"] = guard("funding", lambda: fetch_funding_pct(as_of_ms))
    return out


if __name__ == "__main__":
    import json

    errs: list[dict] = []
    print(json.dumps(collect(datetime.now(timezone.utc), errs), indent=2, ensure_ascii=False))
    print("errors:", errs)
