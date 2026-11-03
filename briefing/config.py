"""경로, 임계값, 환경변수. 임계값은 이 파일 한곳에만 둔다."""
from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"
PROMPTS_DIR = ROOT / "prompts"

load_dotenv(ROOT / ".env")

KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")

# --- 환경변수 (비밀 값과 연결 대상) ---
SOSOVALUE_API_KEY = os.getenv("SOSOVALUE_API_KEY", "").strip()
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "").strip()
NOTION_DATA_SOURCE_ID = os.getenv("NOTION_DATA_SOURCE_ID", "").strip()

# --- 노션 ---
NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2025-09-03"  # data source 모델

# --- 바이낸스 ---
BINANCE_SYMBOL = "BTCUSDT"
BINANCE_FUTURES_URL = "https://fapi.binance.com"
BINANCE_SPOT_URL = "https://api.binance.com"
HOURLY_LOOKBACK_HOURS = 72

# --- SoSoValue ---
SOSOVALUE_URL = "https://openapi.sosovalue.com/openapi/v1"
SOSOVALUE_MAX_RETRIES = 3
SOSOVALUE_RETRY_WAIT_SEC = 7
SOSOVALUE_MIN_INTERVAL_SEC = 6.5  # 분당 10회 한도

# --- 야후 ---
YAHOO_TICKERS = {"us10y": "^TNX", "dxy": "DX-Y.NYB", "nasdaq": "^IXIC"}

# --- 태그 임계값 (규칙 문서 §1, §2) ---
RISK_STRONG_PCT = 0.3        # 나스닥 +0.3% 이상 강함
RISK_WEAK_PCT = -0.3         # 나스닥 -0.3% 이하 약함

FUNDING_LONG_CROWDED = 0.05  # % (8시간)
FUNDING_SHORT_CROWDED = -0.03
FUNDING_OVERHEAT = 0.03
OI_7D_OVERHEAT_PCT = 15.0

FLAT_PRICE_PCT = 0.5         # 가격 보합 구간 ±
FLAT_OI_PCT = 1.0            # OI 보합 구간 ±
FLAT_CVD_RATIO_PCT = 1.5     # 선물 CVD 거래량 대비 보합 구간 ±

# --- 매크로 (규칙 문서 §3) ---
BIG_MOVE_US10Y_BP = 7.0
BIG_MOVE_DXY_PCT = 0.4
NEAR_EXTREME_PCTILE = 10.0   # 1년 범위 상위·하위 10%
NEAR_EXTREME_DIST_PCT = 2.0  # 52주 고점·저점 2% 이내

# --- ETF ---
ETF_SUM_DAYS = 5
ETF_HISTORY_DAYS = 30        # 연속 일수 계산용 조회 범위
ETF_SUM_REQUIRED = ("IBIT", "FBTC")  # ETF별 합산 잠정치를 만들려면 정산돼 있어야 하는 대형 ETF

# --- LLM (Claude Code CLI 헤드리스, 구독 인증) ---
CLAUDE_BIN = os.getenv("CLAUDE_BIN", "").strip()   # 비우면 PATH와 ~/.local/bin에서 찾는다
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()     # 비우면 CLI 기본 모델
LLM_TIMEOUT_SEC = 900
LLM_ALLOWED_TOOLS = ["WebSearch", "WebFetch"]
LLM_DISALLOWED_TOOLS = ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "NotebookEdit", "Task"]
BRIEFING_PROMPT = PROMPTS_DIR / "briefing.md"
SCHEDULED_RUN_KST = (10, 10)                       # 뉴스 기간 계산용 정규 실행 시각

# --- 서술 ---
NARRATIVE_MAX_CHARS = 600
ONE_LINER_MAX_CHARS = 80
