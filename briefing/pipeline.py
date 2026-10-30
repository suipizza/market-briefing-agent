"""전체 실행: 수집·판정 → (해석) → 직전 페이지 ETF 확정 갱신 → 오늘 페이지 기록.

LLM 단계는 아직 없다. 숫자와 태그만 노션에 쓴다.
같은 날짜로 다시 실행하면 새 페이지를 만들지 않고 기존 페이지를 갱신한다.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime
from pathlib import Path

from briefing import collect, config
from briefing.analysis import flows
from briefing.analysis.tags import flow_tag
from briefing.llm import context, runner, validate
from briefing.notion import client, mapping
from briefing.sources import sosovalue

log = logging.getLogger(__name__)


class Timer:
    """단계별 소요 시간과 성공 여부 기록 (포트폴리오 운영 지표용)."""

    def __init__(self) -> None:
        self.stages: dict[str, dict] = {}

    def run(self, name: str, fn, *args, **kwargs):
        t0 = time.monotonic()
        try:
            result = fn(*args, **kwargs)
            self.stages[name] = {"ok": True, "sec": round(time.monotonic() - t0, 2)}
            return result
        except Exception as e:
            self.stages[name] = {"ok": False, "sec": round(time.monotonic() - t0, 2), "error": str(e)}
            raise


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(snap: dict) -> Path:
    return Path(collect.save(snap))


def _save_run(snap: dict, dry_run: bool) -> Path:
    """실행 결과 저장. dry-run은 실제 기록(날짜.json)을 덮어쓰지 않도록 따로 저장한다."""
    if not dry_run:
        return _save(snap)
    path = config.DATA_DIR / f"{snap['run_date']}.dryrun.json"
    path.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def previous_snapshot(run_date: date) -> Path | None:
    """run_date 이전의 가장 최근 실행 JSON."""
    paths = sorted(
        p for p in config.DATA_DIR.glob("????-??-??.json") if p.stem < run_date.isoformat()
    )
    return paths[-1] if paths else None


# ---------- ETF 확정 갱신 ----------

def confirm_previous_etf(run_date: date, dry_run: bool) -> dict | None:
    """직전 실행의 잠정 ETF 값을 공식 합계로 확정한다. 잠정→확정 차이를 기록한다."""
    path = previous_snapshot(run_date)
    if path is None:
        return None
    prev = _load(path)
    etf = prev.get("etf", {})
    if not etf.get("is_provisional") or prev.get("is_us_holiday"):
        return None

    target = date.fromisoformat(prev["target_us_date"])
    history = sosovalue.fetch_total_history()
    confirmed = flows.compute(
        {"total_history": history, "ibit_net_flow_musd": etf.get("ibit_net_flow_musd"), "ibit_included": True},
        target,
        False,
    )
    if confirmed["source"] != "total":
        log.info("ETF total for %s still not published, keep provisional", target)
        return {"run_date": prev["run_date"], "confirmed": False}

    provisional_value = etf.get("net_flow_musd")
    final_value = confirmed["net_flow_musd"]
    record = {
        "run_date": prev["run_date"],
        "target_us_date": prev["target_us_date"],
        "confirmed": True,
        "provisional_musd": provisional_value,
        "provisional_source": etf.get("source"),
        "provisional_coverage": etf.get("coverage"),
        "final_musd": round(final_value, 4),
        "diff_musd": None if provisional_value is None else round(final_value - provisional_value, 4),
        "confirmed_at": datetime.now(config.KST).isoformat(timespec="seconds"),
    }

    confirmed.update(is_provisional=False, data_status="확정", by_etf=etf.get("by_etf"))
    prev["etf"] = confirmed
    prev["etf_confirmation"] = record
    prev["tags"]["flow"] = flow_tag(final_value)
    prev["tags"]["flow_memo"] = confirmed["memo"]
    prev["status"]["flow_data"] = "확정"

    if dry_run:
        log.info("[dry-run] would confirm ETF for %s: %s -> %s", prev["run_date"], provisional_value, final_value)
        return record

    page_id = (prev.get("notion") or {}).get("page_id")
    if page_id is None:
        page = client.find_page_by_date(prev["run_date"])
        page_id = page["id"] if page else None
    if page_id:
        client.update_properties(page_id, mapping.snapshot_properties(prev, only=mapping.ETF_CONFIRM_PROPERTIES))
    _save(prev)
    log.info("ETF confirmed for %s: %s -> %s", prev["run_date"], provisional_value, final_value)
    return record


# ---------- 오늘 페이지 ----------

def write_page(snap: dict, narrative: dict | None, dry_run: bool) -> dict:
    props = mapping.snapshot_properties(snap)
    if narrative:
        props.update(mapping.narrative_properties(narrative))
    if dry_run:
        out = config.DATA_DIR / f"{snap['run_date']}.notion.json"
        out.write_text(json.dumps(props, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"action": "dry-run", "payload": str(out)}
    existing = client.find_page_by_date(snap["run_date"])
    if existing:
        page = client.update_properties(existing["id"], props)
        action = "updated"
    else:
        page = client.create_page(props)
        action = "created"
    return {"action": action, "page_id": page["id"], "url": page.get("url")}


# ---------- 해석 (LLM) ----------

def interpret(snap: dict) -> tuple[dict, dict]:
    """(검증을 통과한 서술, 실행 기록). 원문 응답은 data/날짜.llm.txt에 남긴다."""
    prev_path = previous_snapshot(date.fromisoformat(snap["run_date"]))
    previous_narrative = _load(prev_path).get("narrative") if prev_path else None
    prompt, version = context.build_prompt(snap, previous_narrative)
    result = runner.run(prompt)
    checked = validate.validate(result["narrative"], snap["tags"])
    (config.DATA_DIR / f"{snap['run_date']}.llm.txt").write_text(result["raw_text"], encoding="utf-8")
    record = {
        "prompt_version": version,
        **result["meta"],
        "passed": checked["passed"],
        "total": checked["total"],
        "rejected": checked["rejected"],
        "warnings": checked["warnings"],
        "sources": checked["sources"],
    }
    return checked["accepted"], record


def run(run_date: date, dry_run: bool = False, use_llm: bool = True) -> dict:
    started = datetime.now(config.KST)
    timer = Timer()

    snap = timer.run("collect", collect.collect, run_date)

    narrative: dict | None = None
    existing = config.DATA_DIR / f"{run_date.isoformat()}.json"
    if not use_llm and existing.exists():
        # LLM 없이 다시 돌릴 때는 기존 서술 기록을 유지한다 (노션 서술 칸도 건드리지 않는다)
        old = _load(existing)
        snap["llm"] = old.get("llm")
        snap["narrative_kept"] = old.get("narrative")
    if use_llm:
        try:
            narrative, snap["llm"] = timer.run("llm", interpret, snap)
            if snap["llm"]["rejected"]:
                snap["status"]["errors"].append({"stage": "llm.validate", "msg": f"rejected: {snap['llm']['rejected']}"})
        except Exception as e:  # LLM이 실패해도 숫자와 태그는 쓴다
            log.error("LLM failed: %s", e)
            snap["status"]["errors"].append({"stage": "llm", "msg": str(e)})
            snap["llm"] = {"error": str(e)}
    snap["narrative"] = narrative if use_llm else snap.pop("narrative_kept", None)
    snap["status"]["run"] = collect.run_status(snap["status"]["errors"], snap)

    try:
        confirmation = timer.run("etf_confirm", confirm_previous_etf, run_date, dry_run)
    except Exception as e:
        log.error("ETF confirm failed: %s", e)
        snap["status"]["errors"].append({"stage": "etf_confirm", "msg": str(e)})
        confirmation = None

    try:
        snap["notion"] = timer.run("notion_write", write_page, snap, narrative, dry_run)
    except Exception as e:
        log.error("notion write failed: %s", e)
        snap["status"]["errors"].append({"stage": "notion_write", "msg": str(e)})
        snap["status"]["run"] = "실패"
        snap["notion"] = None

    snap["etf_confirmation_of_previous"] = confirmation
    snap["run"] = {
        "started_at": started.isoformat(timespec="seconds"),
        "duration_sec": round((datetime.now(config.KST) - started).total_seconds(), 1),
        "dry_run": dry_run,
        "stages": timer.stages,
    }
    snap["stage"] = "written" if snap.get("notion") else "collected"
    _save_run(snap, dry_run)
    return snap
