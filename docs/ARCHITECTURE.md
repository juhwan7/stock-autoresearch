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
