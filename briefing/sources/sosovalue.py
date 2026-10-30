"""SoSoValue 미국 BTC 현물 ETF 순유입.

API v1 (https://sosovalue.gitbook.io/soso-value-api-doc):
- GET /etfs/summary-history?symbol=BTC&country_code=US  → 합계 일별 (휴장일 제외, 최근 1개월)
- GET /etfs?symbol=BTC&country_code=US                 → ETF 목록 (12개)
- GET /etfs/{ticker}/history                           → ETF별 일별. 정산 전이면 net_inflow가 null
헤더 x-soso-api-key. 한도 분당 10회.

합계는 모든 운용사 숫자가 들어와야 확정되어 개별 ETF보다 늦게 나온다.
대상일 합계가 없으면 ETF별 값을 더해 잠정치를 만들고, 다음 날 확정 갱신 때 공식 합계로 덮어쓴다.
"""
from __future__ import annotations

import logging
import time
from datetime import date

from briefing import config
from briefing.sources.http import request_json

log = logging.getLogger(__name__)

_last_call = 0.0


def _throttle() -> None:
    """분당 10회 한도를 넘지 않도록 호출 간격을 둔다."""
    global _last_call
    wait = config.SOSOVALUE_MIN_INTERVAL_SEC - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def _get(path: str, params: dict | None = None) -> list[dict]:
    if not config.SOSOVALUE_API_KEY:
        raise RuntimeError("SOSOVALUE_API_KEY is not set")
    _throttle()
    data = request_json(
        "GET",
        f"{config.SOSOVALUE_URL}{path}",
        params=params,
        headers={"x-soso-api-key": config.SOSOVALUE_API_KEY},
        retries=config.SOSOVALUE_MAX_RETRIES,
        wait_sec=config.SOSOVALUE_RETRY_WAIT_SEC,
    )
    # 응답이 배열이거나 {"code":0, "data":[...]} 형태일 수 있다
    if isinstance(data, dict):
        if data.get("code") not in (None, 0, "0"):
            raise RuntimeError(f"sosovalue error: {data.get('code')} {data.get('msg')}")
        data = data.get("data", [])
    if not isinstance(data, list):
        raise RuntimeError(f"unexpected sosovalue response: {type(data).__name__}")
    return data


def _to_musd(v) -> float | None:
    return None if v is None else float(v) / 1e6


def fetch_total_history(limit: int = config.ETF_HISTORY_DAYS) -> list[dict]:
    """[{date, net_flow_musd}] 오래된 순."""
    rows = _get("/etfs/summary-history", {"symbol": "BTC", "country_code": "US", "limit": limit})
    out = [{"date": r["date"], "net_flow_musd": _to_musd(r.get("total_net_inflow"))} for r in rows]
    return sorted(out, key=lambda r: r["date"])


def fetch_tickers() -> list[str]:
    return [r["ticker"] for r in _get("/etfs", {"symbol": "BTC", "country_code": "US"})]


def fetch_etf_flow(ticker: str, target: date) -> float | None:
    """대상일 ETF별 순유입 ($M). 행이 없거나 정산 전이면 None."""
    rows = _get(f"/etfs/{ticker}/history")
    by_date = {r["date"]: r.get("net_inflow") for r in rows}
    return _to_musd(by_date.get(target.isoformat()))


def collect(target: date, errors: list[dict]) -> dict:
    """합계 기록, IBIT 값, (합계가 없을 때) ETF별 값. 계산은 analysis/flows.py가 한다."""
    out: dict = {"total_history": None, "ibit_net_flow_musd": None, "ibit_included": False, "by_etf": None}
    try:
        out["total_history"] = fetch_total_history()
    except Exception as e:
        log.error("sosovalue total failed: %s", e)
        errors.append({"stage": "sosovalue.total", "msg": str(e)})
        return out
    try:
        v = fetch_etf_flow("IBIT", target)
        out["ibit_net_flow_musd"] = v
        out["ibit_included"] = v is not None
    except Exception as e:
        log.error("sosovalue IBIT failed: %s", e)
        errors.append({"stage": "sosovalue.ibit", "msg": str(e)})

    if any(r["date"] == target.isoformat() for r in out["total_history"]):
        return out

    # 대상일 합계 미확정 → ETF별 합산으로 잠정치
    log.info("sosovalue total for %s not published, summing per-ETF flows", target)
    try:
        by_etf: dict[str, float | None] = {}
        for ticker in fetch_tickers():
            if ticker == "IBIT":
                by_etf[ticker] = out["ibit_net_flow_musd"]
                continue
            try:
                by_etf[ticker] = fetch_etf_flow(ticker, target)
            except Exception as e:
                log.warning("sosovalue %s failed: %s", ticker, e)
                by_etf[ticker] = None
        out["by_etf"] = by_etf
    except Exception as e:
        log.error("sosovalue ETF list failed: %s", e)
        errors.append({"stage": "sosovalue.by_etf", "msg": str(e)})
    return out


if __name__ == "__main__":
    import json
    import sys

    t = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    errs: list[dict] = []
    print(json.dumps(collect(t, errs), indent=2, ensure_ascii=False))
    print("errors:", errs)
