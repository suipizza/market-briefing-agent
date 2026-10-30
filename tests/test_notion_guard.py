"""노션 안전장치 테스트. 네트워크 없이 requests를 가로채서 확인한다."""
import inspect
import re

import pytest

from briefing import config
from briefing.notion import client, mapping

DS = "11111111-2222-3333-4444-555555555555"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setattr(config, "NOTION_TOKEN", "test-token")
    monkeypatch.setattr(config, "NOTION_DATA_SOURCE_ID", DS)


class FakeResp:
    def __init__(self, data):
        self.data, self.ok, self.status_code, self.text = data, True, 200, ""

    def json(self):
        return self.data


class Sent(list):
    """보낸 요청 기록. parent_ds는 페이지 조회 때 돌려줄 부모 data source."""
    parent_ds = DS


@pytest.fixture
def calls(monkeypatch):
    sent = Sent()

    def fake(method, url, headers=None, json=None, timeout=None):
        sent.append((method, url, json))
        if method == "GET" and "/pages/" in url:
            return FakeResp({"id": "p1", "parent": {"type": "data_source_id", "data_source_id": sent.parent_ds}})
        return FakeResp({"id": "p1", "results": []})

    monkeypatch.setattr(client.requests, "request", fake)
    return sent


def test_public_api_is_four_functions():
    public = {n for n, f in inspect.getmembers(client, inspect.isfunction) if not n.startswith("_") and f.__module__ == client.__name__}
    assert public == {"find_page_by_date", "get_page", "create_page", "update_properties", "check_properties", "check_parent"}


def test_no_block_search_delete_endpoints_in_source():
    src = inspect.getsource(client)
    code = re.sub(r'""".*?"""', "", src, flags=re.S)  # 문서 문자열 제외
    for forbidden in ("/blocks", "/search", '"DELETE"', "archived", "in_trash", "children"):
        assert forbidden not in code, forbidden


def test_unknown_property_rejected_before_request(calls):
    with pytest.raises(client.NotionGuardError):
        client.create_page({"제목": mapping.to_value("title", "x"), "임의 속성": {"number": 1}})
    assert calls == []


def test_formula_property_not_writable(calls):
    with pytest.raises(client.NotionGuardError):
        client.update_properties("p1", {"경과일": {"number": 1}})


def test_create_parent_is_fixed_data_source(calls):
    client.create_page({"제목": mapping.to_value("title", "x")})
    method, url, body = calls[-1]
    assert method == "POST" and url.endswith("/pages")
    assert body["parent"] == {"type": "data_source_id", "data_source_id": DS}
    assert "children" not in body


def test_update_rejects_page_from_other_data_source(calls):
    calls.parent_ds = "00000000-0000-0000-0000-000000000000"
    with pytest.raises(client.NotionGuardError):
        client.update_properties("p1", {"수급": mapping.to_value("select", "유입")})
    assert all(m != "PATCH" for m, _, _ in calls)


def test_update_allowed(calls):
    client.update_properties("p1", {"수급": mapping.to_value("select", "유입")})
    assert calls[-1][0] == "PATCH"


def test_missing_config_blocks(monkeypatch, calls):
    monkeypatch.setattr(config, "NOTION_DATA_SOURCE_ID", "")
    with pytest.raises(client.NotionGuardError):
        client.create_page({"제목": mapping.to_value("title", "x")})


class TestMapping:
    snap = {
        "run_date": "2026-10-24",
        "generated_at": "2026-10-24T10:12:00+09:00",
        "btc": {"price": 80588.34, "funding_rate_pct": 0.00391},
        "etf": {"net_flow_musd": -137.936},
        "macro": {"us10y": {"close": 4.988}, "dxy": None, "nasdaq": None},
        "tags": {"flow": "유출", "risk": None, "flow_memo": "2일 연속 순유출"},
        "status": {"run": "성공", "flow_data": "잠정"},
    }

    def test_values(self):
        p = mapping.snapshot_properties(self.snap)
        assert p["제목"]["title"][0]["text"]["content"] == "2026-10-24 브리핑"
        assert p["BTC 가격"] == {"number": 80588.3}
        assert p["ETF 순유입($M)"] == {"number": -137.9}
        assert p["DXY 1일(%)"] == {"number": None}
        assert p["수급"] == {"select": {"name": "유출"}}
        assert p["위험선호"] == {"select": None}
        assert set(p) <= mapping.ALLOWED_PROPERTIES

    def test_only_subset(self):
        p = mapping.snapshot_properties(self.snap, only=mapping.ETF_CONFIRM_PROPERTIES)
        assert set(p) == set(mapping.ETF_CONFIRM_PROPERTIES)

    def test_rich_text_split(self):
        chunks = mapping.rich_text("가" * 4500)
        assert [len(c["text"]["content"]) for c in chunks] == [2000, 2000, 500]

    def test_narrative_only_known_keys(self):
        p = mapping.narrative_properties({"macro": "짧은 서술", "unknown": "x"})
        assert list(p) == ["매크로"]
