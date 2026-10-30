from datetime import date, timedelta

import pandas as pd
import pytest

from briefing.analysis import macro
from briefing.sources import binance, calendar_us


def series(values, end=date(2026, 10, 23)):
    idx = [end - timedelta(days=len(values) - 1 - i) for i in range(len(values))]
    return pd.Series(values, index=idx, dtype=float)


class TestMacro:
    def test_bp_change_and_big_move(self):
        s = series([4.00] * 30 + [4.10])
        ind = macro.indicator(s, "bp", 7.0)
        assert ind["chg_1d"] == pytest.approx(10.0)
        assert ind["big_move"] is True
        assert ind["near_extreme"] == "high"

    def test_small_move_mid_range(self):
        s = series([3.0, 5.0] + [4.0] * 30 + [4.03])
        ind = macro.indicator(s, "bp", 7.0)
        assert ind["big_move"] is False
        assert ind["near_extreme"] is None

    def test_pct_change(self):
        ind = macro.indicator(series([100.0, 100.5]), "%", 0.4)
        assert ind["chg_1d"] == pytest.approx(0.5)
        assert ind["chg_5d"] is None

    def test_nasdaq_blank_on_holiday(self):
        closes = {"us10y": series([4.0, 4.1]), "dxy": series([100.0, 101.0]), "nasdaq": series([1.0, 2.0])}
        out = macro.compute(closes, date(2026, 10, 23), True)
        assert out["nasdaq"] is None
        assert out["us10y"] is not None

    def test_nasdaq_blank_when_target_row_missing(self):
        closes = {"nasdaq": series([1.0, 2.0], end=date(2026, 10, 22))}
        assert macro.compute(closes, date(2026, 10, 23), False)["nasdaq"] is None


def kline(open_, close, vol, taker_buy, close_time=0):
    return [0, str(open_), "0", "0", str(close), str(vol), close_time, "0", 0, str(taker_buy), "0", "0"]


class TestBinanceCalc:
    def test_cvd(self):
        ks = [kline(100, 101, 10, 6), kline(101, 102, 10, 4), kline(102, 103, 20, 15)]
        delta, ratio = binance.cvd(ks, 2)
        assert delta == pytest.approx((8 - 10) + (30 - 20))
        assert ratio == pytest.approx(8 / 30 * 100)

    def test_price_change(self):
        ks = [kline(100, 101, 1, 1), kline(101, 110, 1, 1)]
        assert binance.price_change_pct(ks, 2) == pytest.approx(10.0)
        assert binance.price_change_pct(ks, 3) is None

    def test_closed_only(self):
        ks = [kline(1, 1, 1, 1, close_time=99), kline(1, 1, 1, 1, close_time=200)]
        assert len(binance.closed_klines(ks, 100)) == 1

    def test_oi_change(self):
        hist = [{"sumOpenInterest": v} for v in (100, 105, 110)]
        assert binance.oi_change_pct(hist, 2) == pytest.approx(10.0)
        assert binance.oi_change_pct(hist, 3) is None


class TestCalendar:
    def test_saturday_run_targets_friday(self):
        assert calendar_us.us_target_for(date(2026, 10, 24)) == calendar_us.UsTarget(date(2026, 10, 23), False)

    def test_monday_run_targets_friday(self):
        assert calendar_us.us_target_for(date(2026, 10, 26)).target_date == date(2026, 10, 23)

    def test_after_thanksgiving_is_holiday(self):
        assert calendar_us.us_target_for(date(2026, 11, 27)).is_holiday is True


class TestMacroMemo:
    def ind(self, unit, close, chg_1d, chg_5d, big=False, near=None, dist_hi=-5.0, dist_lo=10.0):
        return {"unit": unit, "close": close, "chg_1d": chg_1d, "chg_5d": chg_5d, "big_move": big,
                "near_extreme": near, "dist_52w_high_pct": dist_hi, "dist_52w_low_pct": dist_lo}

    def test_nothing_special(self):
        mac = {"us10y": self.ind("bp", 4.38, 1.2, 3.0), "dxy": self.ind("%", 100.0, 0.1, -0.2), "nasdaq": None}
        assert macro.memo(mac) == "특이사항 없음 | 10Y 4.38% (1일 +1.2bp, 5일 +3.0bp) · DXY 100.00 (1일 +0.10%, 5일 -0.20%)"

    def test_flags_first(self):
        mac = {
            "us10y": self.ind("bp", 4.99, 8.2, -11.0, big=True),
            "dxy": self.ind("%", 101.81, 0.2, 0.0, near="high", dist_hi=-0.75),
            "nasdaq": None,
        }
        assert macro.memo(mac).startswith("10Y 하루 큰 움직임(+8.2bp), DXY 52주 고점 근처(고점 대비 -0.75%) | ")

    def test_missing(self):
        assert macro.memo({"us10y": None, "dxy": None, "nasdaq": None}) is None
