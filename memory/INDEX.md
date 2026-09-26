# Stock AutoResearch Memory Index

> 자동 갱신: 2026-09-27T00:35:21+09:00
> latest batch: supervisor-20260927T0030+0900-b35
> Supervisor: B · 상태 verification_pending
> 이번 작업축: 7개

## 시작할 때 읽기

1. 이 파일
2. memory/current/현재상태.md
3. memory/current/다음확인사항.md
4. 현재 문제에 관련된 WARM memory
5. 반복 문제/과거 비교가 필요할 때만 COLD memory

## 현재 가장 중요한 시장
- 00:10/00:20/00:30 센서 연속 누락 원인과 self-chain/heartbeat 복구
- 미·이란 공식 답변과 호르무즈 실제 통항
- 한국 수입규제 241건의 다음 거래일 업종 가격·수급 반응
- macro runtime 실값의 다음 거래 가능 구간 검증

## 활성 시장 이슈
- 이란 전쟁 여파로 EU 에너지 가격 위기 경고 — NEW
- 한국산 제품 수입규제 241건·신규조사 증가 — NEW
- 텍사스 데이터센터 신규 허가 중단·전력망 감사 — NEW
- 미국·이란 협상과 호르무즈 해협 재개방 — ACTIVE
- Fed 추가 인상 압력과 끈적한 인플레이션 — ACTIVE
- 글로벌 장기채 매도와 미국 30년물 고점 — ACTIVE
- 호르무즈 우회 수송과 초고가 유조선 운임 — ACTIVE
- AI 강세와 고금리·에너지 부담의 줄다리기 — ACTIVE

## 현재 열린 프로젝트 문제
- sensor-slot-0000-plus-continuity — investigating
- macro-runtime-empty — verification_pending
- Supervisor A 정규 window 검증 대기 — 최근 정규 결과 2/3 슬롯 · 누락 슬롯은 과거값으로 보충하지 않음
- Supervisor B 정규 window 검증 대기 — 최근 정규 결과 0/3 슬롯 · 누락 슬롯은 과거값으로 보충하지 않음
- 10분 센서 슬롯 커버리지 낮음 — 0/6 슬롯 · GitHub schedule/저장 경로 점검 필요

## 최근 해결
- issue-digest-apply-stale — resolved

## 운영 품질
- operations: investigating
- health: NOTICE
- open questions: 24
- 사용자 개입 필요: 0건

## 기억 위치
- 현재 상태 → memory/current/
- A/B/Recovery 실행 → memory/supervisors/
- 실패/기능/삭제/공급자 → memory/project/
- 시장 이슈/regime/반응 → memory/market/
- 질문/가설/발견/반증 → memory/research/
- 재사용 교훈 → memory/lessons/
- 일/주/월 압축 → memory/snapshots/

canonical 사실은 data/ 원본을 우선한다.
