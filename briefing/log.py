"""로깅 설정. 비밀 값은 로그에 남기지 않는다."""
from __future__ import annotations

import logging
from datetime import datetime

from briefing import config


class _MaskSecrets(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        secrets = [s for s in (config.NOTION_TOKEN, config.SOSOVALUE_API_KEY) if s]
        if secrets:
            msg = record.getMessage()
            for s in secrets:
                msg = msg.replace(s, "***")
            record.msg, record.args = msg, ()
        return True


def setup(level: int = logging.INFO) -> None:
    config.LOG_DIR.mkdir(exist_ok=True)
    log_file = config.LOG_DIR / f"{datetime.now(config.KST):%Y-%m-%d}.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    for h in (logging.StreamHandler(), logging.FileHandler(log_file, encoding="utf-8")):
        h.setFormatter(fmt)
        h.addFilter(_MaskSecrets())
        root.addHandler(h)
    # 외부 라이브러리 소음 줄이기
    for noisy in ("urllib3", "yfinance", "peewee"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
