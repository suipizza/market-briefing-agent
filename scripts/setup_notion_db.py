"""노션 DB를 한 번만 만드는 스크립트. 매일 실행되는 코드와 분리한다.

사용법:
    .venv/bin/python scripts/setup_notion_db.py <상위 페이지 ID 또는 URL>

상위 페이지에 integration 연결이 되어 있어야 한다. 끝나면 data source ID를 출력하고,
그 값을 .env의 NOTION_DATA_SOURCE_ID에 넣는다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from briefing import config  # noqa: E402
from briefing.notion.mapping import schema_definition  # noqa: E402

DB_TITLE = "Market Direction Log"


def page_id_from(arg: str) -> str:
    m = re.search(r"([0-9a-f]{32})", arg.replace("-", ""))
    if not m:
        raise SystemExit(f"페이지 ID를 찾을 수 없음: {arg}")
    return m.group(1)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    if not config.NOTION_TOKEN:
        raise SystemExit("NOTION_TOKEN이 .env에 없음")
    parent = page_id_from(sys.argv[1])
    headers = {
        "Authorization": f"Bearer {config.NOTION_TOKEN}",
        "Notion-Version": config.NOTION_VERSION,
        "Content-Type": "application/json",
    }
    body = {
        "parent": {"type": "page_id", "page_id": parent},
        "title": [{"type": "text", "text": {"content": DB_TITLE}}],
        "is_inline": True,
        "initial_data_source": {"properties": schema_definition()},
    }
    r = requests.post(f"{config.NOTION_API_URL}/databases", headers=headers, json=body, timeout=30)
    if not r.ok:
        raise SystemExit(f"DB 생성 실패 {r.status_code}: {r.text[:500]}")
    db = r.json()
    ds = db["data_sources"][0]
    print(f"DB 생성 완료: {db.get('url')}")
    print(f"database id   : {db['id']}")
    print(f"data source id: {ds['id']}")
    print(f"\n.env에 추가:\nNOTION_DATA_SOURCE_ID={ds['id']}")


if __name__ == "__main__":
    main()
