# AI 연속 인수인계

이 문서는 새로운 ChatGPT/Supervisor가 이전 대화와 작업의 맥락을 잃지 않고 바로 이어서 작업하기 위한 **연속 인수인계 기준 문서**다.

## 읽기 순서

새 AI는 작업을 시작할 때 다음 순서로 확인한다.

1. `AGENTS.md`
2. `docs/문서_지도.md`
3. **이 문서**
4. `memory/INDEX.md`
5. `memory/current/현재상태.md`
6. `memory/current/다음확인사항.md`
7. `docs/자율진화_운영헌장.md`
8. `docs/사용자_목적.md`
9. `docs/사용자_피드백.md`
10. `docs/결정_원장.md`
11. `data/supervisor/latest-report.json`
12. `data/supervisor/state.json` 및 기존 Supervisor 큐/최근 관측

채팅 원문 전체를 GitHub에 복제하는 문서가 아니다. 프로젝트 판단에 필요한 사용자 요구, 결정 이유, 실패, 검증 결과, 미완료 작업과 다음 시작점을 손실 없이 구조화해 누적한다. Secret·토큰·개인정보는 기록하지 않는다.

## 사용자가 원하는 운영 방식

- Stock AutoResearch는 사용자가 매번 기능을 지시해야 움직이는 프로젝트가 아니라 AI가 시장과 프로젝트를 계속 관찰하고 스스로 개선 후보를 찾는 프로젝트다.
- 시장 연구와 프로젝트 개선은 같은 Supervisor 루프다.
- 현재 ChatGPT Supervisor는 정각과 30분에 번갈아 실행되어 하나의 연속 상태를 이어받는다.
- :00 작업과 :30 작업은 독립 연구가 아니다. 직전 사이클의 state/latest-report/queue, 미완료 작업과 검증 가설을 반드시 이어받는다.
- 시장 변화가 없어도 프로젝트 자율개선 검토는 생략하지 않는다.
- 의미 없는 커밋이나 문구 변경을 개선으로 취급하지 않는다.
- 안전하고 되돌릴 수 있으며 근거와 검증 계획이 있는 작은 변경을 우선한다.
- 사용자는 진행이 긴 작업에서 단계별 진행상황을 원한다.
- 사용자-facing 설명과 문서는 한국어를 기본으로 한다.
- 주문·자동매매 기능은 만들거나 활성화하지 않는다.

## 시장 데이터 핵심 요구

- 국내 단기 연구의 핵심은 종가베팅과 눌림 단기스윙이다.
- 시장→섹터→종목→비중의 구조와 실제 돈의 흐름을 중시한다.
- Toss를 신규 데이터 우선 공급자로 사용하지만 연결됐다는 사실만으로 완전하다고 가정하지 않는다.
- 10분마다 거래대금 상위 50종목을 관찰하고 해당 10분 구간의 1분 단위 데이터를 누적하는 방향이다.
- Top50에서 밀려난 종목도 당일 추적 Universe에서 즉시 버리지 않고 계속 관찰해야 한다.
- Top50 개수, 1분봉 공백, fetch 오류, 10분 지연, 공급자 종목 차이, Top50 이탈 추적을 검사한다.
- 누락 backfill은 provenance와 exact/estimated를 유지한다.
- 정확도 우선순위는 Toss/KRX/증권사 정확 체결합계 > Naver 누적 거래대금 차분 > 가격×거래량 근사다.
- 10분 센서는 OpenAI API 없이 동작해야 한다.

## 2026-09-26 10분 슬롯 window 계약

- 센서는 `:00/:10/:20/:30/:40/:50` 10분 슬롯 기준으로 관측을 저장한다. 실제 실행이 몇 분 늦으면 `observed_at`과 `slot_at`을 분리하고 지연을 남긴다.
- workflow 시작 시 슬롯을 먼저 고정해 긴 수집이 다음 10분 경계를 넘어도 슬롯이 바뀌지 않게 한다. Recovery/heartbeat는 재실행할 슬롯을 `workflow_dispatch` 입력으로 명시하며 `slot_source`와 `slot_delay_seconds`로 지연 provenance를 남긴다.
- GitHub `schedule`은 실제 운영에서 수시간 공백이 관측됐고 GitHub 공식 문서상 고부하 때 지연·드롭될 수 있으므로 단독 트리거로 신뢰하지 않는다.
- 센서 run은 종료 전에 다음 10분 경계까지 대기한 뒤, 그 슬롯이 아직 없고 다른 센서도 실행/대기 중이 아닐 때 다음 센서를 `workflow_dispatch`로 연결하는 self-chain을 1차 연속성 경로로 사용한다. repo variable `SENSOR_SELF_CHAIN_DISABLED=true`이면 긴급 중지할 수 있다.
- 기본 cron을 놓치거나 self-chain이 끊긴 경우 `.github/workflows/10분센서_보조복구.yml`이 `:05/:15/:25/:35/:45/:55`에 현재 슬롯 저장 여부와 활성 센서를 확인한다. 이미 저장됐거나 실행 중이면 아무것도 하지 않고, 둘 다 아니면 해당 슬롯만 재실행한다.
- 늦게 도착한 workflow_dispatch 입력이 이미 지난 슬롯이면 과거 관측을 가장하지 않고 현재 10분 슬롯으로 재기준하며 `slot_source=dispatch_input_rebased`로 provenance를 남긴다. `slot_start_delay_seconds`는 실행 시작 지연, `slot_delay_seconds`는 수집 완료 지연으로 분리한다.
- 센서와 Recovery가 같은 main에 동시에 쓰면서 관측이 rebase 충돌로 폐기된 실운영 사례가 있었다. 운영 상태판 3개 파일(`data/operations/status.json`, `docs/운영_칸반.md`, `site/data/상태.json`)과 README 사용자조치 블록은 Recovery가 소유하며 센서는 로컬 검증에만 사용하고 commit하지 않는다. 핵심 observation commit의 rebase/push가 실패하면 성공으로 숨기지 않고 workflow failure로 남긴다.
- GitHub Recovery schedule은 A/B 실제 실행(:07/:37)과 직접 겹치지 않도록 `:03/:18/:33/:48`로 분리한다.
- B(:30)는 `:10/:20/:30`, A(:00)는 직전 `:40/:50/:00` 세 슬롯만 기본 입력으로 사용한다. 단순 최근 3개를 사용하지 않는다.
- 누락 슬롯은 과거 관측으로 채우지 않고 `missing_observation_slots`에 기록한다.
- 같은 슬롯 중복 관측은 validation과 성공 step이 더 좋은 하나를 canonical로 선택한다.
- AI 결과는 실제 사용한 `observation_ids`, `observation_slots`, window 시작/끝, 예상/수신 개수와 completeness를 남긴다.
- canonical apply는 ID가 queue에 존재하고 해당 3슬롯 window와 일치할 때만 처리 pointer를 전진시킨다.
- 상대 Supervisor 피드백 처리 상태와 A/B 의견충돌은 구조화해 다음 사이클에 넘긴다. 충돌은 후속 증거로 검증하기 전 임의로 삭제하지 않는다.
- 센서 뉴스의 `independent_story_count_estimate`는 제목 유사도 기반 복제 가능성 추정치일 뿐 독립 1차 출처 수 확정값이 아니다. 중요 이슈는 A/B가 원기사·공식 자료를 직접 검증한다.
- `data/operations/status.json`은 최근 1시간 완료 슬롯 6개의 수신률·누락 슬롯·최대 지연을 `sensor_slot_coverage`로 기록한다. 최신 timestamp 하나만 보지 말고 슬롯 커버리지로 GitHub schedule 누락을 감지한다.
- 직전 상대 Supervisor가 피드백을 남겼으면 다음 결과는 `feedback_received`로 실제 인수 사실을 남겨야 한다. 반대로 다음 상대에게 넘길 `feedback_to_other_supervisor`도 비우지 않는다. 둘 중 필요한 항목이 빠지면 canonical apply가 `verification_pending`으로 표시한다.

## 2026-09-26 자율진화·장기기억 운영 강화

- A(:00)는 탐색·개발형, B(:30)는 비판·검증·정리형으로 역할을 분리한다.
- 매 :00/:30 실행은 최소 5개의 서로 다른 작업축을 실제 검토한다. 변경 개수 자체는 목표가 아니며 no_change·삭제·통합·단순화도 정상 결과다.
- 결과 JSON에는 가능하면 `work_axes_reviewed`를 5개 이상 남기고, `feedback_to_other_supervisor`로 다음 상대 Supervisor가 이어받을 비판·질문을 구조화한다.
- 사용자가 기술적으로 반드시 개입해야 하는 Secret/OAuth/결제/계정권한 문제는 우회하지 않고 blocked로 기록한다. 그 blocker 때문에 나머지 시장 연구·개발을 멈추지 않는다.
- GitHub의 `memory/`를 A/B/Recovery의 외부 두뇌로 사용한다. 시작 시 HOT memory만 읽고, 필요한 과거만 WARM/COLD에서 검색한다.
- Supervisor canonical 결과 적용 시 `scripts/장기기억_갱신.py`가 INDEX, current, Supervisor 실행기록, 일간 snapshot, catalog를 갱신한다.
- 기능 삭제·실패·가설 반증도 장기학습 자산으로 취급한다.

## 2026-09-25 현재 연속 Supervisor 구조

- 정각: `AutoResearch 동적 트렌드 AI 심층리서치`
- 30분: `AutoResearch 연속 감독 30분`
- 목표 흐름: 15:00 A → 15:30 B → 16:00 A → 16:30 B처럼 같은 상태를 교대로 이어받는다.
- 각 실행은 A 시장 연구와 B 프로젝트 자율개선을 모두 수행한다.
- Telegram Supervisor 결과는 정각(:00)과 30분(:30) AI 사이클에서만 시간당 2회 보낸다. 10분 센서는 관측·큐 적재만 하며 Telegram 결과 알림을 보내지 않는다.
- 시장·코드 변화가 없어도 :00/:30 사이클 결과 자체를 새 batch_id와 notify=true로 latest-report에 저장해 결과를 보고한다.
- 종료 전 `data/supervisor/latest-report.json`과 `data/supervisor/state.json`을 최신 SHA 기준으로 순차 갱신하고 다시 읽어 일치 여부를 검증해야 한다.
- `latest-report.json`에는 고유 batch_id, processed_at, notify=true와 summary/actions/changed_paths/next_checks를 남긴다.
- state의 처리 포인터는 실제 마지막 처리 관측 및 batch와 일치해야 한다.
- 파일 쓰기 충돌이면 최신 SHA를 다시 읽고 재시도한다.
- 별도의 평행 Supervisor 상태를 만들지 않는다.

## Telegram 알림 경로와 최근 장애

목표 경로는 다음과 같다.

`Supervisor 실행 → latest-report/state 저장 → 감독 결과 즉시 알림 workflow → Telegram`

2026-09-25 확인된 문제:
- `latest-report.json`은 11:59 배치를 가리키는데 `state.json` 처리 포인터가 08:43에 남아 있는 불일치가 발견됐다.
- 15:30 Supervisor 실행은 있었지만 새 latest-report가 GitHub에 저장되지 않아 Telegram workflow가 발동하지 않았다.
- Telegram 스크립트가 GitHub Issue 댓글 성공 뒤에만 Telegram을 호출하던 결합도 발견됐다.

적용한 개선:
- Telegram 전송을 GitHub Issue 댓글 성공 여부와 분리했다. Issue가 실패해도 Telegram 전송을 독립적으로 시도한다.
- 정각/30분 Supervisor 프롬프트에 최신 blob SHA 재조회 → 순차 저장 → 재조회 검증 규칙을 추가했다.
- `감독결과_즉시알림.yml`에는 기존 latest-report push 트리거를 유지하면서 보조 알림 트리거 기반을 추가했다.

주의:
- 위 개선이 실제 다음 Supervisor 배치에서 end-to-end로 성공하는지는 반드시 운영 실행으로 사후검증한다.
- Telegram Secret 값은 어떤 문서/로그에도 저장하지 않는다.

## Toss/10분 센서 운영 의도

- 진짜 1분 실시간 스트리밍 자체가 목적은 아니다.
- 10분마다 상위 50종목을 확인하면서 직전 10분의 1분 데이터 10개를 확보하는 구조가 핵심이다.
- 상위 50위에서 54위 등으로 밀린 종목도 이미 추적 대상이었다면 계속 갱신한다.
- Toss 고정 IP Collector와 공개/보조 provider를 함께 사용하되 공급자 누락을 숨기지 않는다.
- 휴장일·장외시간을 장애나 실제 장중 흐름으로 오판하지 않는다.

## AI가 프로젝트를 개선할 때 기억할 것

매 사이클 최소 한 개 개선 후보를 검토한다. 우선순위:
1. 데이터 누락/stale/provider 불일치/fallback/backfill
2. API 401/403/429/5xx/schema/rate limit
3. 10분 센서 지연·공백·Top50 이탈 추적
4. Health/Regression/Pages/Actions/Telegram
5. 질문→가설→반증→사후검증
6. 테스트와 실제 실행경로 불일치
7. 중복·구형 코드/문서
8. 가치 있는 새 데이터·속보·외부 서비스/API

개선 전 evidence, expected_benefit, risk, validation_plan을 명시한다. due hypothesis는 실제 후속 관측으로 판정한다.

## 대화에서 나온 내용을 앞으로 보존하는 규칙

프로젝트와 관련된 새 사용자 요구나 중요한 결정이 나오면 다음 중 적절한 위치에 기록한다.

- 장기 목적/선호 변화 → 이 문서 + `사용자_목적.md`
- 새로운 설계 결정과 이유 → `결정_원장.md`
- 사용자의 수정/보류/아이디어 → `사용자_피드백.md`
- 실제 AI 변경 → `AI_변경기록.md`
- 실험과 검증 → `실험_기록.md`
- 다음 AI가 즉시 알아야 할 현재 상태/미완료 작업 → 이 문서 + Supervisor state/queue/latest-report

매 정각/30분 Supervisor는 실행 종료 전에 **이번 사이클에서 새로 생긴 장기 맥락이 있는지 판단**하고, 있으면 기존 문서에 중복 없이 반영한다. 단순 시장 숫자나 일회성 로그까지 이 문서에 계속 붙이지 않는다.

## 다음 AI의 첫 질문

새 AI는 작업을 시작할 때 스스로 다음을 확인한다.

- 직전 Supervisor는 어디까지 처리했는가?
- state와 latest-report가 같은 batch를 가리키는가?
- 직전 사이클의 미완료 작업과 검증 가설은 무엇인가?
- 사용자의 가장 최근 요구가 canonical 문서에 반영됐는가?
- 최근 변경의 CI와 실제 운영 사후검증이 끝났는가?
- Telegram/latest-report 경로가 실제 end-to-end로 동작했는가?
- Toss/Top50/1분 데이터에 조용한 누락이 없는가?

이 질문에 답한 뒤 새 작업을 시작한다.

## 문제 종료와 재검증 규칙

사용자의 핵심 요구: 같은 문제를 계속 관찰하지 않는다. 먼저 정상/장애를 구분하고, 장애라면 원인 조사 → 수정 → 테스트 → 실제 운영 검증까지 스스로 진행한 뒤 상태를 기록하고 다음 문제로 넘어간다.

상태는 최소 normal / investigating / verification_pending / resolved / blocked로 구분한다.

- normal: 휴장·장외시간 등 정상 이유가 확인됨. 조건 변화 전 재조사 금지.
- investigating: 실제 장애 가능성이 있어 현재 해결 중.
- verification_pending: 수정은 완료됐고 실제 검증시각/조건을 기다림. verify_after 전 재조사 금지.
- resolved: 실제 운영 검증까지 통과. 새로운 반증 증거가 생기기 전 재조사 금지.
- blocked: 서로 다른 안전한 해결법을 충분히 시도했으나 현재 환경에서 해결 불가. 반복 시도하지 않고 다른 유용한 작업을 계속함.

한국 휴장 중 국내 신규 체결 부재는 휴장 확인 후 normal로 닫고 다음 개장일을 verify_after로 둘 수 있다. 그 사이 Supervisor는 미국장·글로벌 시장과 다른 프로젝트 개선을 계속한다.

미국장 관측은 한국장 종료 후에만 수행하지 않는다. 한국장 중에도 최신 미국장 종가·시간외·선물과 관련 종목 정보를 국내시장과 함께 보고, 미국 정규장 중에는 거래대금 상위·순위 변화·섹터 집중도를 계속 관찰한다. 미국 신호가 실제 한국장 거래대금과 연결됐는지는 이후 사후검증한다.

## Telegram 자율개발 보고 요구

정각/30분 Supervisor는 시장 리서치뿐 아니라 프로젝트 자율개발 결과도 같은 Telegram 보고에 포함한다.

- 새 버그·오탐·데이터 누락·비효율을 스스로 탐지한다.
- 실제 장애면 원인 조사에서 멈추지 않고 수정·테스트·가능한 실운영 검증까지 진행한다.
- 연구 품질에 도움이 되는 새 기능을 발견하면 안전하고 되돌릴 수 있는 범위에서 직접 구현하고 검증한다.
- Telegram에는 버그의 사용자 영향, 원인, 수정 내용, 테스트 결과, 해결 상태를 쉬운 말로 설명한다.
- 새 기능은 추가 이유, 실제로 달라진 점, 테스트 여부, 남은 검증을 설명한다.
- 변경 파일 수나 commit 정보만으로 개선을 설명하지 않는다.
- 변경할 실익이 없으면 억지로 기능을 추가하지 않고 그 판단을 보고한다.


## 10분 센서와 두 Supervisor의 역할 분리

2026-09-25 사용자 결정에 따라 10분 계층에서 질문 생성과 프로젝트 판단을 제거했다.

- 10분 센서 = 눈/녹화기. 시장·공급자·Health·Regression 등 확인 가능한 사실을 수집하고 저장한다.
- :00 Supervisor = 첫 번째 두뇌. 최근 관측과 이전 상태를 읽고 의문 생성 → 조사 → 수정/기능 개선 → 테스트 → 후속 의문 생성까지 수행한다.
- :30 Supervisor = 두 번째 두뇌. :00의 결론·미해결 질문·수정 결과를 그대로 이어받아 같은 순환을 계속한다.
- 두 Supervisor는 독립 프로젝트가 아니며 하나의 연속 연구 상태를 교대로 발전시킨다.
- question_queue는 더 이상 10분 규칙 엔진이 채우지 않는다. Supervisor가 연구 과정에서 가치 있는 질문과 후속 질문만 기록한다.
- 해결된 문제에서 새로운 의문을 만들 수 있지만, resolved/normal 또는 verify_after 전 verification_pending 문제를 다시 처음부터 조사하지 않는다.
- 새 기능은 실제 시장 연구의 정확도·속도·안정성·가독성을 높이는 근거가 있을 때 직접 구현하고 테스트한다. 기능 개수 자체를 목표로 하지 않는다.

목표 순환: `10분 사실 수집 → :00 두뇌 → 조사/수정/테스트 → 새 의문 → :30 두뇌 → 추가 조사/수정/테스트 → 새 의문 → 다음 :00`.


## GitHub 쓰기 실패 자동복구 규칙

Supervisor의 GitHub 쓰기 요청 하나가 실패하거나 실행 전 안전검사에서 차단됐다는 이유만으로 전체 사이클을 중단하거나 Supervisor를 비활성화하지 않는다. 저장소 권한 장애와 개별 요청 실패를 구분한다.

복구 순서는 다음과 같다.

1. 대상 파일을 main에서 다시 읽어 최신 blob SHA와 현재 내용을 확보한다.
2. 전체 파일을 크게 다시 쓰기보다 필요한 필드·문단·코드만 바꾸는 최소 변경으로 재시도한다.
3. 여러 파일 또는 큰 JSON/문서 변경이면 서로 독립적인 작은 커밋으로 분할한다.
4. 같은 요청을 그대로 반복하지 않는다. 실패 원인을 SHA 충돌, 스키마/내용 크기, 경로, 일시적 도구 실패, 권한 문제로 나눠 확인한다.
5. 허용된 다른 정상 GitHub 쓰기 방식이 있으면 최소 권한 범위에서 대체 경로를 사용한다. Secret 추가, 권한 확대, 보호 설정 우회는 자동으로 하지 않는다.
6. 쓰기 성공 응답만 믿지 않고 대상 파일을 다시 읽어 의도한 내용이 실제 main에 존재하는지 확인한다.
7. 관련 GitHub Actions가 있다면 실행 여부와 conclusion까지 확인한다. 실제 운영 확인이 필요한 수정은 verification_pending과 verify_after를 남긴다.
8. 서로 다른 안전한 방법을 충분히 시도해도 실패하면 blocked로 기록하되 다른 시장 연구·프로젝트 개선 작업은 계속한다.
9. 다음 Supervisor는 실패 횟수와 이미 시도한 방법을 이어받아 같은 실패 방법을 처음부터 반복하지 않는다.

특히 ChatGPT 연결 도구 단계의 개별 차단을 GitHub 저장소 전체의 쓰기 권한 장애로 단정하지 않는다. 다른 작은 쓰기가 실제로 성공하는지 확인해 범위를 판별한다.


## 최근 7일 대량 이슈 추적 화면

사용자는 이슈 생명주기를 매우 세밀하게 본다. `data/news/issue-digest.json`과 `site/이슈추적.html`을 핵심 사용자 화면으로 취급한다.

- :00/:30 Supervisor는 매 사이클 최신 뉴스 후보를 폭넓게 다시 보고 중복·재탕·광고성·시장무관 항목을 제거한 뒤 사건 단위 이슈로 병합한다. 10분 센서 후보 목표는 최대 500건이다.
- 최근 7일 이슈는 몇 개만 압축하지 말고 수십 개를 유지할 수 있어야 하며 저장 한도는 최대 100개다.
- 활성/관찰/완화 이슈는 오래됐어도 상황이 살아 있으면 유지한다. 해소 이슈도 최소 7일간 화면에 남긴다.
- 정상회담, 해외 순방, 국빈방문, 다자회의, 고위급 협의, 관세·제재·투자·방산·에너지·공급망 협상은 직접적인 주가 반응이 아직 없어도 후속 발표 가능성이 있으면 누락검사를 한다.
- 정치적 평가나 인물 평가를 하지 않고 사실·공식 발표·시장 전달 경로만 기록한다.
- 클릭 상세에는 현재 요약, 왜 중요한가, 진행 상황, 다음 확인, 전달 경로, 영향 자산, 확인된 사실, 미확인/반증 조건, 상태 변경 history, 출처 링크가 보여야 한다.
- 같은 사건의 사전 일정→회담→공동성명→후속 실무협의는 같은 issue_id로 누적한다.
- 홈은 상위 이슈만 요약하고, 전체 내용은 전용 `이슈 추적` 화면에서 확인한다.

## 1년 이상 무인 운영 기준

- 이슈 화면 기본 정렬은 최근 발생/업데이트순이다. event_time, first_detected, last_updated, status_changed_at을 분리하고 최근 24시간은 상대시간, 이후는 시작일+추적일수를 표시한다.
- discovery는 고정 검색축만 사용하지 않고 직전 주기의 다매체 급증 키워드를 다음 10분 독립 검색축으로 확장한다. 일반 단어·숫자·시장과 무관한 기사·스팸은 센서 단계에서 줄인다.
- 이슈는 기사 단위가 아니라 사건 단위다. 후속 기사는 같은 issue_id의 sources/latest_update/history에 `추가 소식`으로 병합한다.
- `data/discovery/archive/`에는 10분 뉴스 커버리지·핫키워드 통계를, `data/news/archive/`에는 Supervisor 이슈 상태 변화를 일별 JSONL로 보존한다.
- A(:00), B(:30)는 서로의 직전 실행·canonical 적용·Telegram workflow를 시작 시점에 검사하고 누락 구간을 이어받는다.
- 별도 ChatGPT Recovery(:15)는 A/B 공백을 감시하고, GitHub `자동복구 감시` workflow는 discovery·Pages·운영상태를 15분 단위로 확인해 stale 센서를 재실행한다.
- `data/operations/status.json`, `docs/운영_칸반.md`, README `사용자 확인 필요`를 장기 운영의 사용자-facing 상태판으로 쓴다.
- 공개 fallback으로 충분히 운영되는 선택형 API 미연결은 사용자 필수조치로 올리지 않는다. 실제 권한·Secret·결제·계정 UI 조치가 필요할 때만 올린다.


## GitHub Pages 시장 중요도 우선 원칙

- Pages의 기본 정보 순서는 `시장 영향 이슈 → 다음 변동 트리거 → 심층 리서치 → 시장 데이터/보조 분석 → 시스템 상태 → A/B AI 대화`다.
- 상단 메뉴에서 `이슈 추적`과 `리서치`를 홈 바로 뒤에 둔다. 시스템 내부 상태와 AI 협업 기록은 뒤로 보낸다.
- 홈 첫 화면은 시스템 설명보다 현재 시장 해설, 핵심 이슈, 앞으로의 트리거, 연결 리서치를 먼저 보여준다.
- 이슈 목록의 기본 우선순위는 단순 최신순이 아니라 상태·심각도·시장 영향 가능성·가격 반영 여부·다음 트리거를 함께 본다.
- `AI 대화`는 실제 `data/supervisor/ai-results/*.json`의 A/B/Recovery 필드만 렌더링하며 가짜 대화 문장을 생성하지 않는다.
- A/B Supervisor는 UI를 자기진화 대상으로 보되 기능 수를 늘리는 것보다 사용자가 시장 핵심을 더 빨리 찾는지를 우선 검증한다.
