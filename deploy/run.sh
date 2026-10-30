#!/bin/zsh
# launchd가 실행하는 진입점. 프로젝트 폴더 기준 상대 경로만 쓴다.
# 사용: deploy/run.sh [briefing run 옵션...]   예) deploy/run.sh --dry-run --no-llm
set -u
cd "$(dirname "$0")/.." || exit 1
mkdir -p logs
echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') start: run $*" >> logs/launchd.log
.venv/bin/python -m briefing run "$@" >> logs/launchd.log 2>&1
code=$?
echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') end: exit $code" >> logs/launchd.log
exit $code
