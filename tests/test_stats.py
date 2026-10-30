from briefing import stats


def run(d, status="성공", llm=None, etf_source="total", confirm=None, cvd="혼조"):
    return {
        "run_date": d,
        "status": {"run": status, "errors": [] if status == "성공" else [{"stage": "llm", "msg": "x"}]},
        "run": {"duration_sec": 100.0},
        "llm": llm,
        "etf": {"source": etf_source},
        "etf_confirmation": confirm,
        "tags": {"flow": "유입", "risk": "중립", "position": "정상", "cvd_oi": cvd},
    }


LLM_OK = {"passed": 6, "total": 6, "warnings": ["w"], "rejected": {}, "duration_sec": 90.0, "prompt_version": "v2", "sources": [1, 2]}


def test_summarize():
    runs = [
        run("2026-11-02", llm=LLM_OK, etf_source="total",
            confirm={"confirmed": True, "provisional_source": "etf_sum", "diff_musd": -12.5}),
        run("2026-11-03", status="일부 실패", llm={"error": "timeout"}),
    ]
    s = stats.summarize(runs)
    assert s["weekdays_in_period"] == 2
    assert s["run_status"] == {"성공": 1, "일부 실패": 1}
    assert s["llm"]["fields_passed"] == 6 and s["llm"]["failed"] == 1 and s["llm"]["warnings"] == 1
    assert s["etf"]["source_at_run"] == {"etf_sum": 1, "total": 1}
    assert s["etf"]["provisional_vs_final_abs_diff_musd_avg"] == 12.5
    table = stats.render(s)
    assert table.count("\n") >= 10 and "|차이|" not in table


def test_empty():
    assert stats.render(stats.summarize([])) == "실행 기록이 없습니다."
