from datetime import date

from briefing.analysis import flows


def h(*vals, start_day=1):
    return [{"date": f"2026-10-{start_day + i:02d}", "net_flow_musd": v} for i, v in enumerate(vals)]


class TestStreak:
    def test_inflow_streak(self):
        assert flows.streak(h(-10, 50, 20, 30)) == (3, "+")

    def test_outflow_streak(self):
        assert flows.streak(h(10, -5, -6)) == (2, "-")

    def test_zero_breaks(self):
        assert flows.streak(h(10, 0, 20)) == (1, "+")

    def test_zero_today(self):
        assert flows.streak(h(10, 0)) == (0, None)


def test_sum_last():
    assert flows.sum_last(h(1, 2, 3, 4, 5, 6), 5) == 20
    assert flows.sum_last(h(1, 2), 5) is None


def test_memo():
    assert flows.memo(3, "+", 820.0) == "3일 연속 순유입, 5일 누적 +820.0$M"
    assert flows.memo(2, "-", -1234.5) == "2일 연속 순유출, 5일 누적 -1,234.5$M"
    assert flows.memo(0, None, 10) is None


class TestCompute:
    raw = {"total_history": h(100, 200, -50, 300, 400, 500), "ibit_net_flow_musd": 250.0, "ibit_included": True}

    def test_normal(self):
        out = flows.compute(self.raw, date(2026, 10, 6), False)
        assert out["net_flow_musd"] == 500
        assert out["streak_days"] == 3
        assert out["sum_5d_musd"] == 1350
        assert out["data_status"] == "정상"

    def test_ignores_rows_after_target(self):
        out = flows.compute(self.raw, date(2026, 10, 3), False)
        assert out["net_flow_musd"] == -50

    def test_holiday(self):
        out = flows.compute(self.raw, date(2026, 10, 6), True)
        assert out["net_flow_musd"] is None and out["data_status"] == "휴장"

    def test_target_not_yet_published(self):
        out = flows.compute(self.raw, date(2026, 10, 7), False)
        assert out["data_status"] == "미반영"

    def test_fallback_to_etf_sum(self):
        raw = {**self.raw, "by_etf": {"IBIT": 100.0, "FBTC": 50.0, "GBTC": None}}
        out = flows.compute(raw, date(2026, 10, 7), False)
        assert out["net_flow_musd"] == 150.0
        assert out["source"] == "etf_sum" and out["coverage"] == "2/3"
        assert out["streak_days"] == 4  # 300, 400, 500에 이어서
        assert out["sum_5d_musd"] == -50 + 300 + 400 + 500 + 150
        assert out["data_status"] == "잠정"
        assert out["memo"].endswith("(잠정 2/3)")

    def test_fallback_none_reported(self):
        raw = {**self.raw, "by_etf": {"IBIT": None, "FBTC": None}}
        assert flows.compute(raw, date(2026, 10, 7), False)["data_status"] == "미반영"

    def test_ibit_missing_is_provisional(self):
        raw = {**self.raw, "ibit_included": False, "ibit_net_flow_musd": None}
        assert flows.compute(raw, date(2026, 10, 6), False)["data_status"] == "잠정"

    def test_source_failed(self):
        assert flows.compute({"total_history": None}, date(2026, 10, 6), False)["data_status"] == "실패"
