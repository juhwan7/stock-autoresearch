# 문서 지도

어떤 페이지가 어떤 데이터와 문서를 사용하는지 한눈에 보기 위한 지도다.

## 먼저 읽을 순서

| 순서 | 문서 | 무엇을 이해하는가 | 다음 추천 |
|---:|---|---|---|
| 1 | [USER_INTENT](USER_INTENT.md) | 프로젝트의 최상위 목적 | ARCHITECTURE |
| 2 | [ARCHITECTURE](ARCHITECTURE.md) | 전체 시스템 구조 | TRADING_RESEARCH_MANDATE |
| 3 | [TRADING_RESEARCH_MANDATE](TRADING_RESEARCH_MANDATE.md) | 종가베팅·눌림 연구 원칙 | MARKET_DATA_SPEC |
| 4 | [MARKET_DATA_SPEC](MARKET_DATA_SPEC.md) | 분봉·일봉·시장 데이터 정의 | RISK_VETO |
| 5 | [RISK_VETO](RISK_VETO.md) | 일정·매크로·갭 리스크 | DECISIONS |
| 6 | [DECISIONS](DECISIONS.md) | 왜 기능을 도입했는지 | IDEAS |
| 7 | [IDEAS](IDEAS.md) | 채택·실험·보류 아이디어 | EXPERIMENTS |
| 8 | [EXPERIMENTS](EXPERIMENTS.md) | 실제 실험 결과 | CHANGELOG_AI |

## 대시보드 연결표

| 대시보드 영역 | 주요 데이터 | 관련 코드 | 읽을 문서 |
|---|---|---|---|
| Overnight Risk | 일정, 매크로, Market Tape | risk_engine.py | [RISK_VETO](RISK_VETO.md) |
| 국내시장 장세 | KOSPI/KOSDAQ 폭, 1분봉 거래대금 | market_intel.py, market_stats.py | [TRADING_RESEARCH_MANDATE](TRADING_RESEARCH_MANDATE.md) |
| 신규주 흐름 | 상장일, 1분 거래대금 Burst | market_stats.py | [MARKET_DATA_SPEC](MARKET_DATA_SPEC.md) |
| 동조 수급 | 그룹/섹터 동시 Burst | market_stats.py | [TRADING_RESEARCH_MANDATE](TRADING_RESEARCH_MANDATE.md) |
| 종가베팅 통계 | 다음날 갭·MFE·MAE | market_intel.py | [TRADING_RESEARCH_MANDATE](TRADING_RESEARCH_MANDATE.md) |
| 눌림 통계 | 눌림폭·1/3/5일 MFE·MAE | pullback_stats.py | [TRADING_RESEARCH_MANDATE](TRADING_RESEARCH_MANDATE.md) |
| AI 진화 | 결정·아이디어·실험 | evolution.py | [EVOLUTION_RULES](EVOLUTION_RULES.md) |

## 데이터 흐름

Toss/시장 데이터 → Market Tape → 현재 장세.

현재 장세는 종가/눌림 통계와 일정·매크로 Risk Veto 양쪽으로 연결된다.

Risk Veto 결과는 다음날 갭 연구의 조건으로 다시 저장한다.

## 다음에 읽을 문서 추천 규칙

- 시장 장세를 읽었다면 → Risk Veto
- Risk Veto를 읽었다면 → 종가베팅 통계
- 종가베팅 통계를 읽었다면 → 데이터 명세
- 기능 변경 이유가 궁금하면 → 결정 원장
- 아직 안 넣은 기능이 궁금하면 → 아이디어 보드


## 안정성 문서

- [Overnight Risk Veto](RISK_VETO.md)
- [자동 회귀 탐지와 기능 단위 롤백](REGRESSION_GUARD.md)
- [토스증권 데이터 전환 계획](TOSS_DATA_PLAN.md)
- [자기진화 규칙](EVOLUTION_RULES.md)

권장 읽기 흐름: 현재 장세 → Risk Veto → 종가베팅 통계 → Regression Guard → 최근 AI 변경.
