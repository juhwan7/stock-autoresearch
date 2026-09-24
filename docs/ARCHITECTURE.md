# 아키텍처

## 전체 구조

```text
                ┌─────────────────────────┐
                │ 10분 Continuous Tick    │
                └────────────┬────────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
       Market Research                 Project Evolution
              │
       Domestic Market Tape
       ├─ 거래대금 상위
       ├─ 1분봉 Burst
       ├─ 신규주 흐름
       ├─ 그룹/섹터 동조
       │   └─ 3분 내 동시 상승+거래대금 Burst
       └─ 종배/눌림 통계
              │                             │
       Luna Scanner                    Luna Scout
              │                             │
       Meaningful Gate                 Improvement Gate
              │                             │
       Terra Researcher                Terra Builder
              │                             │
       Terra Critic                    Path/Risk Validator
              │                             │
       Chief Researcher                tests + diff check
              │                             │
       reports + state                 적용 / 롤백
              │                             │
              └──────────────┬──────────────┘
                             │
                    Decision / Idea Memory
                             │
                     Static Web Dashboard
                             │
                       GitHub Pages
```

## 기억 계층

- `data/state/`: 시장 연구의 이전 상태와 최신 주제 기억.
- `data/evolution/ticks/YYYY-MM-DD.jsonl`: 모든 10분 Tick 판단의 compact 기록.
- `docs/`: 사람이 읽는 장기 설계 기억.
- `reports/`: 시장 리서치 최종 보고서.

## 왜 하나의 10분 Workflow인가

시장 연구와 프로젝트 진화가 각각 저장소에 push하면 서로 충돌할 수 있다. Continuous workflow 하나에서 순서대로 실행하면 단일 writer, 충돌 감소, 동일 상태의 테스트/사이트 갱신이라는 장점이 있다.

## 변경 권한

Evolution Agent의 자동 수정 범위와 보호 범위는 `config/evolution.yaml`과 `docs/EVOLUTION_RULES.md`가 함께 정의한다.


## 국내시장 Market Tape 계층

```text
Kiwoom REST (read-only)
    ├─ KOSPI/KOSDAQ 전체 상승·하락 종목 수
    ├─ 종합지수 등락률
    └─ 거래대금 상위 Universe
    ↓
상위 종목 1분봉
    ↓
MarketStats
 ├─ 분봉 거래대금 Burst
 ├─ 장후반 거래대금 비중
 ├─ 상승/하락 시장 폭
 ├─ 상위 종목 거래대금 집중도
 ├─ 신규주 흐름
 └─ 그룹/섹터 동조
    ↓
Market Regime AI
    ↓
현재 장세 / 종가베팅 경고 / 눌림 관점
    ↓
data/market/latest.json
reports/market/
GitHub Pages
```

시장 데이터가 없을 때 AI가 추측으로 장세를 만들지 않는다. 이 경우 `insufficient_data` 또는 `needs_credentials`를 명시한다.


## Overnight Risk 계층

국내장 종가베팅 분석 위에 별도의 Risk Veto 계층을 둔다.

시장 Tape → 매크로 상태 → 공식 일정 → 의미 상태 Hash → 변화가 있을 때만 Risk Evaluator → Risk Report 순서다.

핵심 입력:
- KOSPI/KOSDAQ 장세
- Nasdaq/S&P 선물
- 미국 2년·10년 금리
- DXY
- USD/KRW
- VIX
- KOSPI200 선물/야간선물
- FOMC, CPI, PPI, 고용, 한국은행 등 예정 일정

Risk는 LOW / WATCH / HIGH / VETO로 구분한다.

단 하나의 severity 5 이벤트도 발표가 임박했고 국내 현물 거래 종료 뒤라면 별도 VETO가 될 수 있다.

## Dirty-state AI 호출

10분 Heartbeat는 유지하지만 매번 같은 분석을 다시 하지 않는다.

의미 상태에는 일정 단계, 반올림된 매크로 구간, 국내장 장세, Risk 규칙/프롬프트 문서 Hash가 들어간다.

Hash가 그대로면 이전 Risk 평가를 재사용한다.

Hash가 바뀌면 관련 Risk AI만 다시 호출한다.

의미 상태가 그대로여도 장기 고착 방지를 위해 설정된 주기마다 강제 재평가한다.

## 종가베팅 데이터와 Risk 연결

15:30 이후 생성된 종가베팅 연구 표본은 그날 밤 Risk 상태가 바뀔 때마다 갱신된다.

최신 Risk와 별도로 그날 밤 관측된 가장 높은 Risk Level을 보존한다.

이를 이용해 향후 VETO일과 LOW/WATCH일의 다음날 갭·MFE·MAE를 비교한다.
