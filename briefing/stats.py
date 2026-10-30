"""운영 지표: 쌓인 실행 기록(data/날짜.json)을 요약한다.

포트폴리오의 "운영 결과와 평가" 표를 손으로 모으지 않고 코드로 뽑기 위한 명령이다.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from statistics import mean

from briefing import config


def load_runs(data_dir: Path | None = None) -> list[dict]:
    data_dir = data_dir or config.DATA_DIR
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(data_dir.glob("????-??-??.json"))]


def weekdays_between(start: date, end: date) -> int:
    return sum(1 for i in range((end - start).days + 1) if (start + timedelta(days=i)).weekday() < 5)


def summarize(runs: list[dict]) -> dict:
    if not runs:
        return {"runs": 0}
    dates = [date.fromisoformat(r["run_date"]) for r in runs]
    llm_runs = [r["llm"] for r in runs if r.get("llm") and "passed" in r["llm"]]
    llm_failed = sum(1 for r in runs if (r.get("llm") or {}).get("error"))
    confirmations = [r["etf_confirmation"] for r in runs if (r.get("etf_confirmation") or {}).get("confirmed")]
    diffs = [abs(c["diff_musd"]) for c in confirmations if c.get("diff_musd") is not None]
    durations = [r["run"]["duration_sec"] for r in runs if r.get("run")]

    return {
        "runs": len(runs),
        "period": f"{min(dates)} ~ {max(dates)}",
        "weekdays_in_period": weekdays_between(min(dates), max(dates)),
        "run_status": dict(Counter(r["status"]["run"] for r in runs)),
        "error_stages": dict(Counter(e["stage"].split(".")[0] for r in runs for e in r["status"]["errors"])),
        "duration_sec_avg": round(mean(durations), 1) if durations else None,
        "llm": {
            "runs": len(llm_runs),
            "failed": llm_failed,
            "fields_passed": sum(l["passed"] for l in llm_runs),
            "fields_total": sum(l["total"] for l in llm_runs),
            "warnings": sum(len(l["warnings"]) for l in llm_runs),
            "rejected": sum(len(l["rejected"]) for l in llm_runs),
            "duration_sec_avg": round(mean(l["duration_sec"] for l in llm_runs), 1) if llm_runs else None,
            "prompt_versions": dict(Counter(l.get("prompt_version") for l in llm_runs)),
            "sources_avg": round(mean(len(l.get("sources") or []) for l in llm_runs), 1) if llm_runs else None,
        },
        "etf": {
            # 확정 갱신 뒤에는 etf가 공식 합계로 바뀌므로 실행 당시 출처는 확정 기록에서 읽는다
            "source_at_run": dict(Counter(
                (r.get("etf_confirmation") or {}).get("provisional_source") or r["etf"].get("source") or "없음"
                for r in runs
            )),
            "confirmed": len(confirmations),
            "provisional_vs_final_abs_diff_musd_avg": round(mean(diffs), 2) if diffs else None,
            "provisional_vs_final_abs_diff_musd_max": round(max(diffs), 2) if diffs else None,
        },
        "tags": {
            name: dict(Counter(r["tags"].get(name) for r in runs))
            for name in ("flow", "risk", "position", "cvd_oi")
        },
    }


def render(s: dict) -> str:
    if not s.get("runs"):
        return "실행 기록이 없습니다."
    l, e = s["llm"], s["etf"]
    rate = f"{l['fields_passed']}/{l['fields_total']}" if l["fields_total"] else "-"
    lines = [
        "| 지표 | 값 |",
        "|---|---|",
        f"| 기간 | {s['period']} (평일 {s['weekdays_in_period']}일 중 {s['runs']}회 실행) |",
        f"| 실행 상태 | {', '.join(f'{k} {v}' for k, v in s['run_status'].items())} |",
        f"| 오류 단계 | {', '.join(f'{k} {v}' for k, v in s['error_stages'].items()) or '없음'} |",
        f"| 평균 소요 | {s['duration_sec_avg']}초 (LLM {l['duration_sec_avg']}초) |",
        f"| LLM 서술 검증 통과 | {rate} 항목, 경고 {l['warnings']}건, 반려 {l['rejected']}건, 실행 실패 {l['failed']}회 |",
        f"| 프롬프트 버전 | {', '.join(f'{k} {v}회' for k, v in l['prompt_versions'].items()) or '-'} |",
        f"| 실행당 평균 출처 수 | {l['sources_avg']} |",
        f"| 실행 시 ETF 출처 | {', '.join(f'{k} {v}' for k, v in e['source_at_run'].items())} |",
        f"| ETF 확정 갱신 | {e['confirmed']}회, 잠정→확정 평균 절대 차이 {e['provisional_vs_final_abs_diff_musd_avg']}$M (최대 {e['provisional_vs_final_abs_diff_musd_max']}$M) |",
    ]
    for name, label in (("cvd_oi", "CVD·OI 해석"), ("position", "포지션"), ("flow", "수급"), ("risk", "위험선호")):
        dist = ", ".join(f"{k or '빈칸'} {v}" for k, v in s["tags"][name].items())
        lines.append(f"| {label} 분포 | {dist} |")
    return "\n".join(lines)
