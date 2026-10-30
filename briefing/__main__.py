"""CLI 진입점.

python -m briefing collect [--date YYYY-MM-DD]
python -m briefing run [--date YYYY-MM-DD] [--dry-run] [--no-llm]
python -m briefing stats     # 운영 지표 요약
python -m briefing demo      # 키 없이 돌려보는 데모 (examples/)
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, datetime

from briefing import collect, config, demo, log, pipeline, stats


def _date(s: str) -> date:
    return date.fromisoformat(s)


def main() -> None:
    parser = argparse.ArgumentParser(prog="briefing", description="BTC 마켓 브리핑 에이전트")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_collect = sub.add_parser("collect", help="수집과 판정만 실행하고 data/날짜.json 저장")
    p_collect.add_argument("--date", type=_date, default=None, help="KST 실행일 (기본: 오늘)")

    p_run = sub.add_parser("run", help="전체 실행: 수집·판정, ETF 확정 갱신, 노션 기록")
    p_run.add_argument("--date", type=_date, default=None, help="KST 실행일 (기본: 오늘)")
    p_run.add_argument("--dry-run", action="store_true", help="노션에 쓰지 않고 data/날짜.notion.json에 저장")
    p_run.add_argument("--no-llm", action="store_true", help="LLM 서술 없이 숫자와 태그만")

    sub.add_parser("stats", help="쌓인 실행 기록으로 운영 지표 요약")
    sub.add_parser("demo", help="키·네트워크 없이 저장된 예시로 판정, 검증, 노션 변환, 안전장치 확인")

    args = parser.parse_args()
    if args.cmd == "stats":
        print(stats.render(stats.summarize(stats.load_runs())))
        return
    if args.cmd == "demo":
        demo.run()
        return
    log.setup()
    run_date = args.date or datetime.now(config.KST).date()

    if args.cmd == "collect":
        snap = collect.collect(run_date)
        path = collect.save(snap)
        logging.info("saved %s status=%s flow_data=%s", path, snap["status"]["run"], snap["status"]["flow_data"])
        _print_summary(snap)
    elif args.cmd == "run":
        snap = pipeline.run(run_date, dry_run=args.dry_run, use_llm=not args.no_llm)
        _print_summary(snap)
        llm = snap.get("llm")
        if llm and "error" not in llm:
            print(f"  LLM: {llm['passed']}/{llm['total']} 통과, {llm['duration_sec']}초, 프롬프트 {llm['prompt_version']}")
            for w in llm["warnings"]:
                print(f"    경고: {w}")
        if snap.get("narrative", {}) and snap["narrative"].get("one_liner"):
            print(f"  한줄 판단: {snap['narrative']['one_liner']}")
        n = snap.get("notion") or {}
        print(f"  노션: {n.get('action')} {n.get('url') or n.get('payload') or ''}")
        c = snap.get("etf_confirmation_of_previous")
        if c and c.get("confirmed"):
            print(f"  직전 페이지 {c['run_date']} ETF 확정: {c['provisional_musd']} → {c['final_musd']} (차이 {c['diff_musd']})")
        print(f"  소요 {snap['run']['duration_sec']}초")


def _print_summary(snap: dict) -> None:
    t = snap["tags"]
    print(f"\n{snap['run_date']} (미국 {snap['target_us_date']}) → {snap['status']['run']}")
    print(f"  수급 {t['flow']} | 위험선호 {t['risk']} | 포지션 {t['position']} | CVD·OI {t['cvd_oi']} (4h {t['cvd_oi_4h']})")
    print(f"  수급 메모: {t['flow_memo']}")
    for e in snap["status"]["errors"]:
        print(f"  ! {e['stage']}: {e['msg']}")


if __name__ == "__main__":
    main()
