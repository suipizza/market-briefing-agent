import json
from datetime import date

import pytest

from briefing.llm import context, runner, validate

TAGS = {"flow": "유출", "risk": "중립", "cvd_oi": "롱 청산 하락(투매)"}


def good():
    return {
        "one_liner": "ETF 2일 연속 순유출 속에 롱 청산이 이어진 하루.",
        "macro": "10년물 4.99%, 변동 미미.",
        "derivatives": "롱 청산 하락 패턴. 가격 -1.0%, OI -2.7%.",
        "news_geo": "특이사항 없음",
        "news_crypto": "특이사항 없음",
        "calendar": "10/28(수) 21:30 미국 GDP",
        "sources": [{"title": "t", "url": "https://example.com", "used_in": "macro"}],
    }


class TestValidate:
    def test_all_pass(self):
        r = validate.validate(good(), TAGS)
        assert r["passed"] == 6 and not r["rejected"] and not r["warnings"]
        assert len(r["sources"]) == 1

    def test_missing_and_wrong_type(self):
        n = good()
        del n["calendar"]
        n["macro"] = ["list"]
        r = validate.validate(n, TAGS)
        assert set(r["rejected"]) == {"calendar", "macro"}

    def test_forbidden_phrase_rejected(self):
        n = good()
        n["derivatives"] = "롱 청산 하락이지만 반등 예상, 매수 기회."
        assert "derivatives" in validate.validate(n, TAGS)["rejected"]

    def test_length(self):
        n = good()
        n["macro"] = "가" * 700
        n["news_geo"] = "가" * 1300
        r = validate.validate(n, TAGS)
        assert "macro" in r["accepted"] and any("macro" in w for w in r["warnings"])
        assert "news_geo" in r["rejected"]

    def test_contradiction_warning(self):
        n = good()
        n["one_liner"] = "ETF 순유입이 이어지며 강세."
        assert any("contradicts" in w for w in validate.validate(n, TAGS)["warnings"])

    def test_derivatives_must_mention_tag(self):
        n = good()
        n["derivatives"] = "가격과 OI가 같이 빠졌다."
        assert any("does not mention" in w for w in validate.validate(n, TAGS)["warnings"])


class TestExtractJson:
    def test_plain(self):
        assert runner.extract_json('{"a": 1}') == {"a": 1}

    def test_fenced_with_text(self):
        assert runner.extract_json('설명입니다\n```json\n{"a": "b"}\n```') == {"a": "b"}

    def test_invalid(self):
        with pytest.raises(runner.LlmError):
            runner.extract_json("JSON 없음")


class TestRunnerIsolation:
    def test_secrets_stripped(self, monkeypatch):
        monkeypatch.setenv("NOTION_TOKEN", "secret")
        monkeypatch.setenv("SOSOVALUE_API_KEY", "secret")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
        env = runner.child_env()
        assert not {"NOTION_TOKEN", "SOSOVALUE_API_KEY", "ANTHROPIC_API_KEY"} & set(env)

    def test_only_web_tools(self):
        cmd = runner.command("claude")
        allowed = cmd[cmd.index("--allowedTools") + 1: cmd.index("--disallowedTools")]
        assert allowed == ["WebSearch", "WebFetch"]
        assert "Bash" in cmd and "Read" in cmd


class TestContext:
    def test_window_weekday(self):
        s, e = context.news_window(date(2026, 10, 28))  # 수
        assert s.isoformat().startswith("2026-10-27T10:10") and e.isoformat().startswith("2026-10-28T10:10")

    def test_window_monday_72h(self):
        s, e = context.news_window(date(2026, 10, 26))  # 월
        assert (e - s).total_seconds() == 72 * 3600

    def test_input_excludes_internal_fields(self):
        snap = {"run_date": "2026-10-24", "btc": {}, "status": {"errors": []}, "run": {}, "tags": TAGS}
        inp = context.build_input(snap, None)
        assert "status" not in inp["snapshot"] and "run" not in inp["snapshot"]
        assert inp["today_kst"] == "2026-10-24 (토)"
        json.dumps(inp, ensure_ascii=False)


def test_one_liner_length_warning():
    n = good()
    n["one_liner"] = "가" * 81
    assert any("one_liner: over" in w for w in validate.validate(n, TAGS)["warnings"])
