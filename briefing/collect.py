"""수집과 판정 통합 → data/YYYY-MM-DD.json.

바이낸스 숫자의 기준 시각은 실행일 09:00 KST (UTC 00:00, 바이낸스 일봉 마감).
24시간 값은 전일 일봉과 같다 (전날 09:00 ~ 당일 09:00). 차트와 바로 대조할 수 있고,
같은 날짜로 다시 실행해도 같은 기준 시각을 쓰므로 숫자가 재현된다.
그 시각이 아직 오지 않았으면 현재 시각을 쓴다.
"""
from __future__ import annotations

import json
import logging
import time as time_
from datetime import date, datetime, time

from briefing import config
from briefing.analysis import flows, macro, tags
from briefing.sources import binance, sosovalue, yahoo
from briefing.sources.calendar_us import us_target_for

log = logging.getLogger(__name__)

SNAPSHOT_TIME_KST = time(9, 0)  # UTC 00:00


def anchor_time(run_date: date) -> datetime:
    at = datetime.combine(run_date, SNAPSHOT_TIME_KST, tzinfo=config.KST)
    return min(at, datetime.now(config.KST))


def run_status(errors: list[dict], snapshot: dict) -> str:
    if not errors:
        return "성공"
    nothing = snapshot["btc"].get("price") is None and snapshot["etf"]["net_flow_musd"] is None and all(
        v is None for v in snapshot["macro"].values()
    )
    return "실패" if nothing else "일부 실패"


def _round(obj, nd: int = 4):
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, dict):
        return {k: _round(v, nd) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round(v, nd) for v in obj]
    return obj


def collect(run_date: date) -> dict:
    us = us_target_for(run_date)
    as_of = anchor_time(run_date)
    errors: list[dict] = []
    log.info("collect run_date=%s us_target=%s holiday=%s as_of=%s", run_date, us.target_date, us.is_holiday, as_of)

    timings: dict[str, float] = {}

    def timed(name: str, fn, *args):
        t0 = time_.monotonic()
        try:
            return fn(*args)
        finally:
            timings[name] = round(time_.monotonic() - t0, 1)
            log.info("source %s took %.1fs", name, timings[name])

    btc = timed("binance", binance.collect, as_of, errors)

    etf_raw = timed("sosovalue", sosovalue.collect, us.target_date, errors) if not us.is_holiday else {}
    etf = flows.compute(etf_raw, us.target_date, us.is_holiday)
    if etf["data_status"] == "미반영":
        errors.append({"stage": "sosovalue.total", "msg": f"no total or required ETFs for {us.target_date} yet"})

    closes = timed("yahoo", yahoo.collect, us.target_date, errors)
    mac = macro.compute(closes, us.target_date, us.is_holiday)

    snapshot = {
        "run_date": run_date.isoformat(),
        "target_us_date": us.target_date.isoformat(),
        "is_us_holiday": us.is_holiday,
        "as_of": as_of.isoformat(),
        "generated_at": datetime.now(config.KST).isoformat(timespec="seconds"),
        "btc": btc,
        "etf": etf,
        "macro": mac,
    }
    snapshot["tags"] = tags.compute(btc, etf, mac)
    snapshot["status"] = {
        "run": run_status(errors, snapshot),
        "flow_data": etf["data_status"],
        "errors": errors,
    }
    snapshot["source_sec"] = timings
    snapshot["stage"] = "collected"
    return _round(snapshot)


def save(snapshot: dict) -> str:
    config.DATA_DIR.mkdir(exist_ok=True)
    path = config.DATA_DIR / f"{snapshot['run_date']}.json"
    path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)
