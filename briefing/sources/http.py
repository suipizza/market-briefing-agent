"""공통 HTTP 호출. 재시도와 타임아웃만 담당한다."""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

log = logging.getLogger(__name__)

TIMEOUT_SEC = 15


def request_json(
    method: str,
    url: str,
    *,
    params: dict | None = None,
    json: dict | None = None,
    headers: dict | None = None,
    retries: int = 3,
    wait_sec: float = 2.0,
) -> Any:
    """JSON 응답을 반환한다. 429와 5xx는 대기 후 재시도한다."""
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.request(
                method, url, params=params, json=json, headers=headers, timeout=TIMEOUT_SEC
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as e:
            last_err = e
            status = getattr(getattr(e, "response", None), "status_code", None)
            retryable = status is None or status == 429 or status >= 500
            if not retryable or attempt == retries:
                break
            log.warning("retry %d/%d %s: %s", attempt, retries, url, e)
            time.sleep(wait_sec * attempt)
    raise RuntimeError(f"{method} {url} failed: {last_err}")
