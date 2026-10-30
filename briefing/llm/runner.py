"""Claude Code CLI 헤드리스(`claude -p`) 실행. 개인 구독으로 인증하고 API 키는 쓰지 않는다.

격리
- 도구는 WebSearch, WebFetch만 허용하고 파일·셸 도구는 명시적으로 막는다.
- 빈 임시 폴더에서 실행해서 프로젝트 파일(.env 포함)을 볼 수 없게 한다.
- 자식 프로세스 환경변수에서 노션·SoSoValue 토큰과 ANTHROPIC_API_KEY를 지운다.
  (.env는 python-dotenv로 os.environ에 올라가 있어서 그대로 두면 상속된다)
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from briefing import config

log = logging.getLogger(__name__)

STRIP_ENV = ("NOTION_TOKEN", "NOTION_DATA_SOURCE_ID", "SOSOVALUE_API_KEY", "ANTHROPIC_API_KEY")
INSTRUCTION = "표준 입력으로 받은 지시문과 <input>을 따라 브리핑 서술을 작성하고, JSON 객체 하나만 출력하라."


class LlmError(RuntimeError):
    pass


def find_claude() -> str:
    candidates = [config.CLAUDE_BIN, shutil.which("claude"), str(Path.home() / ".local/bin/claude")]
    for c in candidates:
        if c and Path(c).exists():
            return c
    raise LlmError("claude CLI not found (install Claude Code or set CLAUDE_BIN)")


def child_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k not in STRIP_ENV}
    # launchd처럼 PATH가 짧은 환경에서도 CLI가 node 등을 찾을 수 있게
    env["PATH"] = os.pathsep.join([str(Path.home() / ".local/bin"), "/opt/homebrew/bin", "/usr/local/bin", env.get("PATH", "")])
    return env


def command(claude: str) -> list[str]:
    cmd = [
        claude, "-p", INSTRUCTION,
        "--output-format", "json",
        "--allowedTools", *config.LLM_ALLOWED_TOOLS,
        "--disallowedTools", *config.LLM_DISALLOWED_TOOLS,
    ]
    if config.LLM_MODEL:
        cmd += ["--model", config.LLM_MODEL]
    return cmd


def extract_json(text: str) -> dict:
    """모델 출력에서 JSON 객체를 꺼낸다. 코드 펜스나 앞뒤 문장이 붙어도 처리한다."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise LlmError("no JSON object in model output")
    try:
        obj = json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise LlmError(f"invalid JSON from model: {e}") from e
    if not isinstance(obj, dict):
        raise LlmError("model output is not a JSON object")
    return obj


def run_once(prompt: str) -> dict:
    """한 번 실행. {narrative, raw_text, meta} 반환."""
    claude = find_claude()
    t0 = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="briefing-llm-") as cwd:
        proc = subprocess.run(
            command(claude), input=prompt, capture_output=True, text=True,
            cwd=cwd, env=child_env(), timeout=config.LLM_TIMEOUT_SEC,
        )
    if proc.returncode != 0:
        raise LlmError(f"claude exited {proc.returncode}: {(proc.stderr or proc.stdout)[:500]}")
    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise LlmError(f"unexpected CLI output: {proc.stdout[:300]}") from e
    if envelope.get("is_error"):
        raise LlmError(f"claude error: {str(envelope.get('result'))[:300]}")
    raw = envelope.get("result") or ""
    meta = {
        "duration_sec": round(time.monotonic() - t0, 1),
        "num_turns": envelope.get("num_turns"),
        "models": list((envelope.get("modelUsage") or {}).keys()),
        "usage": envelope.get("usage"),
        "total_cost_usd": envelope.get("total_cost_usd"),  # 구독 인증에서는 참고값 (실제 과금 아님)
        "session_id": envelope.get("session_id"),
    }
    return {"narrative": extract_json(raw), "raw_text": raw, "meta": meta}


def run(prompt: str, retries: int = 1) -> dict:
    """JSON 파싱 실패 등은 한 번 재시도한다."""
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            result = run_once(prompt)
            result["meta"]["attempts"] = attempt + 1
            return result
        except (LlmError, subprocess.TimeoutExpired) as e:
            last = e
            log.warning("LLM attempt %d failed: %s", attempt + 1, e)
    raise LlmError(str(last))
