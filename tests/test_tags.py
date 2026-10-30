import pytest

from briefing.analysis import tags


class TestDirection:
    def test_flat_inside(self):
        assert tags.direction(0.49, 0.5) == tags.FLAT

    def test_boundary_is_direction(self):
        assert tags.direction(0.5, 0.5) == tags.UP
        assert tags.direction(-0.5, 0.5) == tags.DOWN

    def test_none(self):
        assert tags.direction(None, 0.5) is None


class TestFlow:
    @pytest.mark.parametrize("v,expected", [(120.5, "유입"), (-3.2, "유출"), (0, None), (None, None)])
    def test_flow(self, v, expected):
        assert tags.flow_tag(v) == expected


class TestRisk:
    @pytest.mark.parametrize(
        "v,expected",
        [(0.3, "강함"), (1.2, "강함"), (0.29, "중립"), (0.0, "중립"), (-0.29, "중립"), (-0.3, "약함"), (None, None)],
    )
    def test_risk(self, v, expected):
        assert tags.risk_tag(v) == expected


class TestPosition:
    def test_long_crowded_first(self):
        assert tags.position_tag(0.05, 30) == "롱 과밀"

    def test_short_crowded(self):
        assert tags.position_tag(-0.03, 30) == "숏 과밀"

    def test_overheat_by_funding_without_oi(self):
        assert tags.position_tag(0.03, None) == "과열"

    def test_overheat_by_oi(self):
        assert tags.position_tag(0.01, 15.0) == "과열"

    def test_normal(self):
        assert tags.position_tag(0.01, 14.9) == "정상"

    def test_unknown_oi_is_not_normal(self):
        assert tags.position_tag(0.01, None) is None

    def test_unknown_funding(self):
        assert tags.position_tag(None, 30) is None


class TestCvdOi:
    # 가격 ±0.5, OI ±1, CVD ±1.5
    @pytest.mark.parametrize(
        "p,o,c,expected",
        [
            (1.0, 2.0, 2.0, "신규 롱 주도 상승"),
            (1.0, -2.0, 5.0, "숏 청산 상승"),
            (1.0, -2.0, -5.0, "숏 청산 상승"),          # OI 기준이 다이버전스보다 먼저
            (1.0, 0.0, -2.0, "상승 다이버전스(매도 우세)"),
            (1.0, 2.0, -2.0, "상승 다이버전스(매도 우세)"),
            (1.0, 2.0, 0.0, "혼조"),
            (1.0, 0.0, 2.0, "혼조"),
            (-1.0, 2.0, -2.0, "신규 숏 주도 하락"),
            (-1.0, -2.0, 2.0, "롱 청산 하락(투매)"),
            (-1.0, 0.0, 2.0, "하락 다이버전스(매수 우세)"),
            (-1.0, 2.0, 2.0, "하락 다이버전스(매수 우세)"),
            (-1.0, 0.0, 0.0, "혼조"),
            (0.1, 5.0, 5.0, "혼조"),                     # 가격 보합
            (0.5, 1.0, 1.5, "신규 롱 주도 상승"),         # 경계값은 방향 있음
        ],
    )
    def test_table(self, p, o, c, expected):
        assert tags.cvd_oi_tag(p, o, c) == expected

    def test_missing_value(self):
        assert tags.cvd_oi_tag(1.0, None, 2.0) is None
