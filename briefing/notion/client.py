"""노션 API를 호출하는 유일한 파일.

공개 함수는 4개뿐이다: find_page_by_date, get_page, create_page, update_properties.
본문(블록), 검색, 삭제·보관 API는 구현하지 않는다 (tests/test_notion_guard.py가 고정).

안전장치
- 쓰는 속성 이름은 mapping.ALLOWED_PROPERTIES 안에 있어야 한다.
- 생성은 부모를 NOTION_DATA_SOURCE_ID로 고정한다.
- 갱신 전에 대상 페이지의 부모가 NOTION_DATA_SOURCE_ID인지 확인한다.
- 요청 바디에 children(본문)이 들어가지 않는다.
"""
from __future__ import annotations

import logging

import requests

from briefing import config
from briefing.notion.mapping import ALLOWED_PROPERTIES

log = logging.getLogger(__name__)

TIMEOUT_SEC = 30


class NotionGuardError(RuntimeError):
    """안전장치에 걸린 요청. 노션에 보내지 않는다."""


def _norm(id_: str) -> str:
    return id_.replace("-", "").lower()


def _headers() -> dict:
    if not config.NOTION_TOKEN:
        raise NotionGuardError("NOTION_TOKEN is not set")
    return {
        "Authorization": f"Bearer {config.NOTION_TOKEN}",
        "Notion-Version": config.NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _data_source_id() -> str:
    if not config.NOTION_DATA_SOURCE_ID:
        raise NotionGuardError("NOTION_DATA_SOURCE_ID is not set")
    return config.NOTION_DATA_SOURCE_ID


def _request(method: str, path: str, body: dict | None = None) -> dict:
    r = requests.request(method, f"{config.NOTION_API_URL}{path}", headers=_headers(), json=body, timeout=TIMEOUT_SEC)
    if not r.ok:
        raise RuntimeError(f"notion {method} {path} failed {r.status_code}: {r.text[:300]}")
    return r.json()


def check_properties(properties: dict) -> None:
    unknown = set(properties) - ALLOWED_PROPERTIES
    if unknown:
        raise NotionGuardError(f"properties not in allowlist: {sorted(unknown)}")


def check_parent(page: dict) -> None:
    parent = page.get("parent", {})
    if parent.get("type") != "data_source_id" or _norm(parent.get("data_source_id", "")) != _norm(_data_source_id()):
        raise NotionGuardError(f"page {page.get('id')} is not in the configured data source")


# ---------- 공개 함수 4개 ----------

def find_page_by_date(date_iso: str) -> dict | None:
    """날짜 속성이 date_iso인 페이지. 여러 개면 가장 먼저 만든 것."""
    body = {
        "filter": {"property": "날짜", "date": {"equals": date_iso}},
        "sorts": [{"timestamp": "created_time", "direction": "ascending"}],
        "page_size": 5,
    }
    results = _request("POST", f"/data_sources/{_data_source_id()}/query", body).get("results", [])
    return results[0] if results else None


def get_page(page_id: str) -> dict:
    return _request("GET", f"/pages/{page_id}")


def create_page(properties: dict) -> dict:
    check_properties(properties)
    body = {"parent": {"type": "data_source_id", "data_source_id": _data_source_id()}, "properties": properties}
    page = _request("POST", "/pages", body)
    log.info("notion page created %s", page.get("id"))
    return page


def update_properties(page_id: str, properties: dict) -> dict:
    check_properties(properties)
    check_parent(get_page(page_id))
    page = _request("PATCH", f"/pages/{page_id}", {"properties": properties})
    log.info("notion page updated %s (%d properties)", page_id, len(properties))
    return page
