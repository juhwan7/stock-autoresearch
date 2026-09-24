# 사용자 도움이 필요한 항목

AI가 혼자 해결할 수 없거나 사람이 명시적으로 설정해야 하는 항목을 적는다.

---

## [필수] OpenAI API Key 등록

상태: 사용자 작업 필요

이유: 10분 Continuous Loop에서 실제 웹 검색과 AI 판단을 실행하려면 API Key가 필요하다.

방법:

1. GitHub에서 `juhwan7/stock-autoresearch` 저장소를 연다.
2. `Settings`
3. `Secrets and variables`
4. `Actions`
5. `New repository secret`
6. Name: `OPENAI_API_KEY`
7. OpenAI API Key 입력 후 저장

키는 코드나 Markdown에 직접 적지 않는다.

## [권장] GitHub Pages 활성화

상태: 사용자 작업 필요

목적: 웹 대시보드를 GitHub Pages로 본다.

방법:

1. 저장소 `Settings`
2. `Pages`
3. Build and deployment의 Source를 `GitHub Actions`로 선택한다.

## [조건부] GitHub Actions 쓰기 권한 확인

상태: 자동 커밋이 실패할 때만 필요

확인 위치: `Settings → Actions → General → Workflow permissions`

현재 워크플로는 저장소 파일 쓰기에 필요한 최소 권한만 요청하도록 유지한다.


## [선택·fallback] 키움 REST API 읽기 전용 키 등록

상태: 선택 사항

목적: Toss Collector가 아직 연결되지 않았거나 KRX 정규장 중 일시적으로 사용할 수 없을 때 Market Tape의 fallback으로 사용한다.

현재 프로젝트는 **시세 조회만 사용하며 주문 기능은 구현하지 않는다.**

준비 방법:

1. 키움 REST API 사이트에서 사용신청을 한다.
2. 발급받은 App Key와 Secret Key를 확인한다.
3. GitHub 저장소 `Settings → Secrets and variables → Actions`로 이동한다.
4. 아래 두 Repository secret을 추가한다.

```
KIWOOM_APP_KEY
KIWOOM_SECRET_KEY
```

주의:
- 키 값 자체를 README, Issue, Markdown, 채팅 로그에 붙이지 않는다.
- 이 두 Secret이 없으면 프로젝트는 시장 분석 모듈을 실패시키지 않고 `needs_credentials` 상태로 기록한다.

현재 Provider Chain은 Toss-first이며 키움은 KRX 정규장 fallback이다.

## [구현 완료·운영 연결 필요] 분당 실제 체결대금

상태: Collector 코드 구현 완료 / 고정 IP 운영환경 연결 필요

canonical 구현인 `src/autoresearch/toss_collector.py`가 Toss `trade:kr` 체결을 받아 실제 `Σ(체결가 × 체결량)` 방식으로 1분 거래대금을 만든다.

Toss Collector가 연결되지 않은 키움 fallback에서는 기존처럼 분봉 종가×거래량 근사값을 사용하고 `amount_estimated=true`로 구분한다.


## [필수·Toss 실시간 운영] 고정 IP Collector 준비

상태: 사용자 작업 필요 — Collector/배포 코드 구현 완료

목적: KRX 종가 이후 NXT 20:00까지 포함한 실제 통합 체결을 토스증권 WebSocket으로 수집한다.

필요한 것:
1. 고정 공인 IP가 있는 실행환경.
2. 토스증권 Open API client_id / client_secret 발급.
3. 토스증권 Open API 설정에서 해당 고정 IP 허용.
4. Collector 환경에 TOSS_CLIENT_ID, TOSS_CLIENT_SECRET을 Secret으로 저장.

권장 실행환경:
- 고정 Elastic IP를 연결한 클라우드 VM
- 고정 IP VPS
- 고정 공인 IP 서버

GitHub-hosted Actions는 고정 IP 수집기의 대체로 사용하지 않는다.

현재 프로젝트의 기존 키움 수집기는 fallback/비교용으로 유지하며 신규 개발의 우선 공급자는 Toss로 전환한다.


## [Toss 연결 방식] 둘 중 하나만 선택

### A. 고정 IP self-hosted Runner

권장 구조다.

1. 고정 IP 서버에서 canonical Collector(`src/autoresearch/toss_collector.py`)를 systemd로 실행한다.
2. 같은 서버를 GitHub self-hosted runner로 등록한다.
3. runner label에 `stock-autoresearch-fixed-ip`를 추가한다.
4. Actions Variable `TOSS_FIXED_IP_RUNNER_ENABLED=true`를 등록한다.
5. 필요하면 `TOSS_SNAPSHOT_PATH`를 지정한다.

상세 절차: `docs/FIXED_IP_RUNNER.md`.

### B. HTTPS snapshot 전달

GitHub-hosted runner를 유지하고 싶을 때 사용한다.

1. 고정 IP Collector 서버의 최신 snapshot을 인증된 HTTPS endpoint로 노출한다.
2. GitHub Actions Secret에 `TOSS_SNAPSHOT_URL`, `TOSS_SNAPSHOT_TOKEN`을 등록한다.
3. `TOSS_FIXED_IP_RUNNER_ENABLED`는 켜지 않는다.

`continuous.yml`이 매 10분 snapshot을 받아 분석한다.

두 방식을 동시에 켜지 않는다.
