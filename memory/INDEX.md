# Stock AutoResearch Memory Index

> 이 파일은 scripts/장기기억_갱신.py가 Supervisor 결과 적용 시 자동 갱신한다.

## 시작 규칙

- 먼저 이 INDEX와 memory/current/만 읽는다.
- 관련 과거가 필요할 때만 supervisors/, project/, market/, research/, lessons/, snapshots/로 내려간다.
- canonical 사실은 data/ 원본을 우선한다.

## 현재 상태

초기 장기기억 계층 생성됨. 다음 Supervisor canonical 적용에서 실제 최신 상태로 자동 갱신된다.
