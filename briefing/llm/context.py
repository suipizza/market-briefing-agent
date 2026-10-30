"""LLM 입력 조립. 오늘 스냅샷, 직전 서술, 뉴스 기간을 하나의 JSON으로 만든다."""
from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta

from briefing import config

WEEKDAYS = "월화수목금토일"

# LLM에 줄 스냅샷 키 (실행 기록, 오류 목록 같은 내부 정보는 빼고 판단에 필요한 것만)
SNAPSHOT_KEYS = ("run_date", "target_us_date", "is_us_holiday", "btc", "etf", "macro", "tags")


def news_window(run_date: date) -> tuple[datetime, datetime]:
    """직전 정규 실행(평일 10:10)부터 이번 정규 실행까지. 월요일은 금요일부터 72시간."""
    h, m = config.SCHEDULED_RUN_KST
    end = datetime.combine(run_date, time(h, m), tzinfo=config.KST)
    prev = run_date - timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= timedelta(days=1)
    start = datetime.combine(prev, time(h, m), tzinfo=config.KST)
    return start, end


def build_input(snapshot: dict, previous_narrative: dict | None) -> dict:
    run_date = date.fromisoformat(snapshot["run_date"])
    start, end = news_window(run_date)
    return {
        "today_kst": f"{run_date.isoformat()} ({WEEKDAYS[run_date.weekday()]})",
        "news_window": {"start_kst": start.isoformat(timespec="minutes"), "end_kst": end.isoformat(timespec="minutes")},
        "snapshot": {k: snapshot.get(k) for k in SNAPSHOT_KEYS},
        "previous_narrative": previous_narrative,
    }


def prompt_version(prompt_text: str) -> str | None:
    m = re.search(r"prompt_version:\s*(\S+)", prompt_text)
    return m.group(1) if m else None


def build_prompt(snapshot: dict, previous_narrative: dict | None) -> tuple[str, str | None]:
    """(LLM에 보낼 전체 텍스트, 프롬프트 버전)."""
    instructions = config.BRIEFING_PROMPT.read_text(encoding="utf-8")
    payload = json.dumps(build_input(snapshot, previous_narrative), ensure_ascii=False, indent=1)
    return f"{instructions}\n\n<input>\n{payload}\n</input>\n", prompt_version(instructions)
