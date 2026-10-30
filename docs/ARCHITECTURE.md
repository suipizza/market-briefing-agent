# 구조

판정 규칙은 [RULES.md](RULES.md), 실행 방법은 [README](../README.md)에 있다. 이 문서는 코드 구조, 데이터 흐름, 모듈 간 계약, 보안 설계를 다룬다.

## 1. 한 줄 요약

평일 10:10 KST에 한 번 실행되어 **수집(코드) → 판정(코드) → 해석(LLM) → 검증(코드) → 기록(코드)** 순서로 노션 DB에 하루 한 행을 만든다. 각 단계는 앞 단계의 JSON만 입력으로 받고, 결과는 `data/날짜.json` 하나에 쌓인다.

## 2. 디렉터리

```
briefing/
├── __main__.py        CLI: run, collect, stats, demo
├── config.py          경로, 임계값 전부, .env 로딩 (유일한 설정 위치)
├── log.py             로깅, 토큰 마스킹
├── sources/           ① 수집: 외부 API 호출만, 판정 로직 없음
│   ├── binance.py       선물·현물 1시간봉, OI, 펀딩비 → CVD·변화율
│   ├── sosovalue.py     ETF 합계, ETF별 순유입 (합계 미확정 시 합산)
│   ├── yahoo.py         ^TNX, DX-Y.NYB, ^IXIC 일봉
│   ├── calendar_us.py   NYSE 거래일, KST 실행일 → 미국 대상일
│   └── http.py          재시도·타임아웃
├── analysis/          ② 판정: 순수 함수, 네트워크 없음
│   ├── tags.py          수급, 위험선호, 포지션, CVD·OI 해석
│   ├── macro.py         1/5/20일 변동, 1년 위치, 큰 움직임·고저점 플래그, 매크로 메모
│   └── flows.py         ETF 연속 일수, 5일 누적, 잠정/확정, 수급 메모
├── collect.py         ①+② → 스냅샷
├── llm/               ③④ 해석과 검증
│   ├── context.py       입력 조립 (스냅샷 + 직전 서술 + 뉴스 기간)
│   ├── runner.py        claude -p 실행과 격리
│   └── validate.py      반려·경고 규칙
├── notion/            ⑤ 기록
│   ├── client.py        ★ 노션 API를 호출하는 유일한 파일
│   └── mapping.py       속성 SCHEMA (정의 = 허용 목록 = 대응표)
├── pipeline.py        전체 실행, 직전 페이지 ETF 확정 갱신, 실행 기록
├── stats.py           운영 지표 요약
└── demo.py            키 없이 돌려보는 데모
prompts/briefing.md    LLM 지시문 (버전 주석 포함), archive/에 이전 버전
scripts/setup_notion_db.py   DB 1회 생성 (실행 코드와 분리)
deploy/                launchd plist 생성기, 실행 스크립트
examples/              공개용 샘플 실행 기록
tests/                 단위 테스트 (네트워크 없음)
```

`sources/`는 숫자만 가져오고 `analysis/`는 네트워크를 쓰지 않는다. 그래서 판정 로직 전체를 고정된 입력으로 테스트할 수 있다.

## 3. 데이터 흐름

```
run_date (KST)
  │
  ├─ calendar_us ─► 미국 대상일, 휴장 여부
  ├─ sources/*   ─► 원시 지표 (실패한 소스는 None + errors[])
  ├─ analysis/*  ─► 태그, 메모
  │                 = 스냅샷
  ├─ llm         ─► 서술 6개 + 출처 → validate → 통과한 항목만
  │                 (실패해도 계속 진행, 실행 상태 = 일부 실패)
  ├─ 직전 페이지 ETF 확정 갱신 (잠정 → 공식 합계, 차이 기록)
  └─ notion      ─► 같은 날짜가 있으면 갱신, 없으면 생성
                    data/날짜.json 저장 (스냅샷 + 서술 + LLM 기록 + 단계별 소요 시간)
```

- **재실행 안전**: 바이낸스 숫자는 실행일 09:00 KST 고정 기준이라 다시 돌려도 같다. 노션은 날짜로 찾아서 갱신한다.
- **dry-run**: 노션에 보낼 페이로드를 `날짜.notion.json`, 실행 기록을 `날짜.dryrun.json`에 저장하고 실제 기록은 건드리지 않는다.

## 4. 모듈 간 계약

### 스냅샷 (코드가 만든다, LLM은 읽기만)

```jsonc
{
  "run_date": "2026-10-30", "target_us_date": "2026-10-29", "is_us_holiday": false,
  "as_of": "2026-10-30T09:00:00+09:00",
  "btc":   { "price", "change_24h_pct", "change_4h_pct", "oi_btc", "oi_change_24h_pct", "oi_change_4h_pct",
             "oi_change_7d_pct", "funding_rate_pct", "futures_cvd_24h_btc", "futures_cvd_24h_ratio_pct",
             "futures_cvd_4h_ratio_pct", "spot_cvd_24h_btc", "spot_cvd_24h_ratio_pct" },
  "etf":   { "net_flow_musd", "ibit_net_flow_musd", "streak_days", "sum_5d_musd", "memo",
             "source": "total | etf_sum", "coverage": "11/12", "by_etf": {...},
             "is_provisional", "data_status": "정상 | 잠정 | 미반영 | 휴장 | 실패 | 확정" },
  "macro": { "us10y" | "dxy" | "nasdaq": { "close", "as_of", "chg_1d", "chg_5d", "chg_20d", "range_pos_1y",
             "dist_52w_high_pct", "dist_52w_low_pct", "big_move", "near_extreme" } },
  "tags":  { "flow", "risk", "position", "cvd_oi", "cvd_oi_4h", "flow_memo", "macro_memo" },
  "status": { "run": "성공 | 일부 실패 | 실패", "flow_data", "errors": [{ "stage", "msg" }] }
}
```

### 서술 (LLM 출력, JSON 하나)

`one_liner`, `macro`, `derivatives`, `news_geo`, `news_crypto`, `calendar`, `sources[]`

### 실행 기록 (같은 파일에 추가)

`narrative`(검증 통과분), `llm`(프롬프트 버전, 소요 시간, 턴 수, 모델, 토큰 사용량, 통과·반려·경고, 출처), `notion`, `etf_confirmation`(잠정→확정 차이), `run`(단계별 소요 시간)

## 5. 보안 설계

### 노션 (최소 권한 + 코드 안전장치)

- integration은 개인 워크스페이스의 페이지 하나에만 연결한다.
- `notion/client.py`가 노션을 호출하는 유일한 파일이고 공개 함수는 4개다: `find_page_by_date`, `get_page`, `create_page`, `update_properties`.
- 쓰는 속성은 `mapping.ALLOWED_PROPERTIES` 안에 있어야 한다. 수식 속성은 쓸 수 없다.
- 생성은 부모를 `NOTION_DATA_SOURCE_ID`로 고정하고, 갱신 전에 대상 페이지의 부모를 확인한다.
- 본문(블록), 검색, 삭제·보관 API는 코드에 없다. 테스트가 소스를 검사해서 고정한다.
- DB 생성은 `scripts/setup_notion_db.py`로 한 번만 한다. 매일 도는 코드에는 스키마를 바꾸는 기능이 없다.

### LLM (격리)

- 도구: `WebSearch`, `WebFetch`만 허용하고 파일·셸 도구는 명시적으로 막는다.
- 작업 폴더: 빈 임시 폴더. 프로젝트 파일과 `.env`를 볼 수 없다.
- 환경변수: `.env`는 python-dotenv로 `os.environ`에 올라가므로, 그대로 두면 자식 프로세스가 토큰을 물려받는다. 노션·SoSoValue 토큰과 `ANTHROPIC_API_KEY`를 지우고 실행한다.
- 노션에 쓰는 것은 항상 코드다. LLM 출력은 검증을 통과한 텍스트 속성에만 들어간다.

## 6. 실행 환경

- macOS launchd, 평일 10:10 KST (`deploy/make_plist.py`). 잠자기 중이었으면 깨어난 직후 실행된다.
- LLM은 Claude Code CLI 헤드리스(`claude -p`), 개인 구독 인증. 러너가 한 파일이라 API 방식으로 바꾸기 쉽다.
- GitHub Actions 같은 클라우드 실행은 쓰지 않는다. 미국 IP에서는 바이낸스 API가 차단된다(HTTP 451).
- macOS는 백그라운드 작업의 바탕화면·문서 폴더 접근을 막으므로 프로젝트는 그 밖에 둔다.
