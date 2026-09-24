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
    ↓
거래대금 상위 Universe
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
