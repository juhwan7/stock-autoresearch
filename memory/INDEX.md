# Stock AutoResearch Memory Index

> 자동 갱신: 2026-09-28T07:09:13+09:00
> latest batch: supervisor-20260928T0700+0900-a50
> Supervisor: A · 상태 verification_pending
> 이번 작업축: 7개

## 시작할 때 읽기

1. 이 파일
2. memory/current/현재상태.md
3. memory/current/다음확인사항.md
4. 현재 문제에 관련된 WARM memory
5. 반복 문제/과거 비교가 필요할 때만 COLD memory

## 현재 가장 중요한 시장
- A/B regular-result transport/apply 단절
- issue-digest lifecycle 지연
- degraded 7개 고정 뉴스축
- 다음 거래 가능 구간 macro 실값

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
- supervisor-result-transport — investigating
- Supervisor A 178분 정규 결과 공백 — 단일 stale 결과만으로 사용자 조치를 요구하거나 Supervisor를 끄지 않음
- Supervisor B 2012분 정규 결과 공백 — 단일 stale 결과만으로 사용자 조치를 요구하거나 Supervisor를 끄지 않음
- 이슈 원장 갱신 지연 — 마지막 갱신 2037.7392159833332분 전
- 장기 AI 기억 갱신 지연 — 마지막 기억 갱신 177.70588265분 전
- macro · 매크로 runtime은 생성됐지만 실제 시장값이 비어 있음 — provider 연결을 재시도하고 지속되면 1시간 AI 감독이 소스 경로를 수정

## 최근 해결
- 없음

## 운영 품질
- operations: investigating
- health: CRITICAL
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
