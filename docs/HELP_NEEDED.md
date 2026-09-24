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


## [권장·국내시장 실데이터] 키움 REST API 읽기 전용 키 등록

상태: 사용자 작업 필요

목적: 국내시장 거래대금 상위 종목과 1분봉을 10분마다 실제로 수집해 장세·동조수급·종가베팅 통계를 만들기 위함이다.

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

현재 수집기는 키움의 거래대금 상위 조회와 1분봉 조회를 사용하도록 구현되어 있다.

## [향후 데이터 정밀화] 분당 실제 체결대금

상태: AI 개선 과제

현재 키움 1분봉은 OHLC·거래량을 사용하므로 분당 거래대금은 우선 `분봉 종가 × 분 거래량`으로 근사한다.

이는 실제 체결가격별 거래대금 합계와 차이가 날 수 있다. 이후 체결 데이터 또는 더 적합한 데이터 소스를 이용해 실제 분당 거래대금으로 교체해야 한다.


## [향후 필수·Toss 실시간] 고정 IP Collector 준비

상태: 사용자 작업 필요

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
