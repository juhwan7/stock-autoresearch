# Stock AutoResearch Memory Index

> 자동 갱신: 2026-09-28T18:36:17+09:00
> latest batch: supervisor-20260928T1830+0900-b1836
> Supervisor: B · 상태 verification_pending
> 이번 작업축: 7개

## 시작할 때 읽기

1. 이 파일
2. memory/current/현재상태.md
3. memory/current/다음확인사항.md
4. 현재 문제에 관련된 WARM memory
5. 반복 문제/과거 비교가 필요할 때만 COLD memory

## 현재 가장 중요한 시장
- Issue Fast Path 실운영 전진·dedup 검증
- 18:00 A result transport 복구
- 주요 글로벌/국내 뉴스의 독립근거 확인
- 가격·금리·유가·환율은 live 근거 없이 단일 원인 확정 금지

## 활성 시장 이슈
- "피규어 AI, 인간 행동 데이터로 휴머노이드 ‘제로샷’ 성능 높여" — WATCHING
- 고려아연 "핵심광물 공급망 재편되는 때…MBK·영풍도 동참했으면" | — WATCHING
- 남아공-짐바브웨, 산업단지용 5억 달러 댐 논의 중 — WATCHING
- 美클래러티법 지연에도 규제 속도…"韓도 미래 금융 대비해야" — WATCHING
- 美 전문가들 "미중 정상회담, 무역·AI 합의에도 전략적 갈등 여전" — WATCHING
- 이 대통령 지지율 37.9%로 2주째 반등‥"순방외교·인적 쇄신 영향" — WATCHING
- 美국채 10년물 5.34%, 24년래 최고…세계 채권시장 왜 또 흔들리나 — WATCHING
- 국채 금리 상승 속 PCE 물가·고용지표 주목…마이크론 실적 발표[이번주 美 증시는] - 머니투데이 — WATCHING

## 현재 열린 프로젝트 문제
- supervisor-a-result-continuity — investigating
- issue-fast-path-live — verification_pending
- Supervisor A 14519분 정규 결과 공백 — 단일 stale 결과만으로 사용자 조치를 요구하거나 Supervisor를 끄지 않음
- Supervisor B 13832분 정규 결과 공백 — 단일 stale 결과만으로 사용자 조치를 요구하거나 Supervisor를 끄지 않음
- 장기 AI 기억 갱신 지연 — 마지막 기억 갱신 13831.75851895분 전
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
