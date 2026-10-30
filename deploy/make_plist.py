"""launchd plist 생성. 경로를 하드코딩하지 않도록 현재 프로젝트 위치로 만든다.

사용:
    .venv/bin/python deploy/make_plist.py                 # 평일 10:10 정규 실행
    .venv/bin/python deploy/make_plist.py --test ARGS...  # 등록 즉시 1회 실행 (테스트용)
결과는 표준 출력으로 나온다. ~/Library/LaunchAgents/에 저장해서 launchctl로 등록한다.
"""
from __future__ import annotations

import plistlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LABEL = "com.aeagent.briefing"
HOUR, MINUTE = 10, 10


def build(test_args: list[str] | None) -> dict:
    plist = {
        "Label": LABEL + (".test" if test_args is not None else ""),
        "ProgramArguments": [str(ROOT / "deploy/run.sh"), *(test_args or [])],
        "WorkingDirectory": str(ROOT),
        "EnvironmentVariables": {
            "PATH": f"{Path.home()}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
            "LANG": "ko_KR.UTF-8",
        },
        "StandardOutPath": str(ROOT / "logs/launchd.stdout"),
        "StandardErrorPath": str(ROOT / "logs/launchd.stderr"),
    }
    if test_args is not None:
        plist["RunAtLoad"] = True
    else:
        # 월(1)~금(5) 10:10. 그 시각에 잠자기 중이었으면 깨어난 직후 한 번 실행된다.
        plist["StartCalendarInterval"] = [{"Weekday": d, "Hour": HOUR, "Minute": MINUTE} for d in range(1, 6)]
    return plist


if __name__ == "__main__":
    args = sys.argv[1:]
    test_args = args[1:] if args[:1] == ["--test"] else None
    sys.stdout.buffer.write(plistlib.dumps(build(test_args)))
