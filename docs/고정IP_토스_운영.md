# 고정 IP Toss Collector + GitHub self-hosted Runner

이 문서는 토스증권 실시간 체결을 Stock AutoResearch의 10분 GitHub 루프에 연결하는 운영 방법이다.

## 왜 같은 서버에 두나

토스증권 Open API는 허용 IP를 사용한다.

GitHub-hosted runner는 고정 공인 IP를 보장하지 않기 때문에 실시간 WebSocket Collector의 실행 장소로 적합하지 않다.

권장 구조:

고정 IP 서버
→ Toss WebSocket trade:kr
→ 실제 체결가×체결량 1분 집계
→ /var/lib/stock-autoresearch/toss/latest.json
→ 같은 서버의 GitHub self-hosted Runner
→ 10분마다 저장소 작업공간으로 스냅샷 복사
→ Market Tape / NXT / 통계 / 대시보드
→ GitHub commit

## 1. 서버 준비

Ubuntu 계열 예시:

1. 고정 공인 IP가 있는 VM/VPS를 준비한다.
2. 토스증권 WTS의 Open API 설정에서 해당 IP를 허용한다.
3. 서버에 Python 3.11+와 git을 설치한다.
4. 전용 사용자 stockresearch를 만든다.
5. 저장소를 /opt/stock-autoresearch에 clone한다.
6. 가상환경을 만들고 `pip install -e ".[dev]" -r collector/requirements.txt` 를 실행한다.
7. /var/lib/stock-autoresearch/toss 디렉터리를 만들고 stockresearch가 쓸 수 있게 한다.

## 2. 인증정보

/etc/stock-autoresearch/toss.env 파일에 다음 두 값만 둔다.

TOSS_CLIENT_ID
TOSS_CLIENT_SECRET

파일 권한은 600을 권장한다.

인증정보는 README, GitHub Issue, Markdown, 채팅 로그, latest.json에 기록하지 않는다.

## 3. Collector 서비스

canonical 구현은 `src/autoresearch/toss_collector.py`이다. `collector/toss_collector.py`는 호환용 진입점이며 동일 canonical 구현으로 위임한다.

`deploy/toss-collector.service.example`을 참고해 /etc/systemd/system/stock-autoresearch-toss.service를 만든다.

그 후:

sudo systemctl daemon-reload
sudo systemctl enable --now stock-autoresearch-toss
sudo systemctl status stock-autoresearch-toss

로그:

journalctl -u stock-autoresearch-toss -f

정상이라면 기본 설정에서 /var/lib/stock-autoresearch/toss/latest.json이 약 10초마다 갱신된다. 주기는 collector/config.json에서 바꿀 수 있다.

## 4. Collector가 하는 일

- OAuth2 Client Credentials 토큰 발급
- MARKET_TRADING_AMOUNT / KR / realtime 랭킹 조회
- 거래대금 상위 최대 100종목 선정
- 종목 메타데이터의 NXT 지원 여부를 함께 저장
- WebSocket `trade:kr` 구독
- KRX+NXT 통합 체결 수신
- 체결가×체결량을 실제 1분 거래대금으로 합산
- 08:00~08:50 프리마켓, 09:00~15:30 정규 구간, 15:40~20:00 NXT 애프터 구간을 분리 저장
- 연결 종료 시 지수 백오프로 재연결
- 구독 종목을 10분마다 다시 선정

주문, 계좌, 보유자산 API는 호출하지 않는다.

## 5. GitHub self-hosted Runner

저장소 Settings → Actions → Runners에서 Linux self-hosted runner를 이 서버에 등록한다.

추가 label:

stock-autoresearch-fixed-ip

GitHub의 runner 등록 토큰은 안내 명령에서만 사용하며 저장소에 기록하지 않는다.

Runner는 stockresearch 사용자 또는 이 프로젝트 전용 사용자로 운용하는 것을 권장한다.

## 6. Repository Variable

self-hosted Runner가 정상 동작한 뒤 저장소의 Actions variables에 다음 값을 등록한다.

TOSS_FIXED_IP_RUNNER_ENABLED=true

선택:

TOSS_SNAPSHOT_PATH=/var/lib/stock-autoresearch/toss/latest.json

변수를 켜기 전에는 fixed-ip workflow의 예약 job이 자동으로 skip된다.

## 7. Secret

fixed-ip Market Tape에서 AI 장세 해석까지 실행하려면 저장소 Actions Secret의 OPENAI_API_KEY가 필요하다.

TOSS_CLIENT_ID / TOSS_CLIENT_SECRET은 Collector 서버에만 두며 GitHub에 복제할 필요가 없다.

## 8. 장애 확인

Health Watchdog는 다음을 별도 구분한다.

- Toss snapshot 없음/오래됨
- API 인증/허용 IP 문제
- Risk/Macro stale
- 테스트 실패
- Regression quarantine/rollback

Collector가 멈추더라도 마지막 유효 Market Tape를 빈 데이터로 덮어쓰지 않는다.

## 관련 문서

- [토스증권 데이터 전환 계획](TOSS_DATA_PLAN.md)
- [시장 데이터 명세](MARKET_DATA_SPEC.md)
- [Overnight Risk Veto](RISK_VETO.md)
- [문서 지도](DOCS_MAP.md)


## 9. GitHub 연결 방식은 하나를 선택

### A. self-hosted Runner 방식

이 문서의 기본 권장 구조다.

- Collector와 GitHub Runner를 같은 고정 IP 서버에 둔다.
- `TOSS_FIXED_IP_RUNNER_ENABLED=true`
- `.github/workflows/fixed-ip-market.yml`이 로컬 snapshot을 읽는다.
- 별도의 공개 snapshot URL이 필요 없다.

### B. HTTPS snapshot 방식

GitHub-hosted runner를 계속 사용하고 싶을 때 사용한다.

- Collector 서버의 `collector/serve_snapshot.py`를 localhost로 실행한다.
- Caddy/nginx 등 HTTPS reverse proxy 뒤에 둔다.
- `TOSS_SNAPSHOT_EXPORT_TOKEN`으로 snapshot 조회를 보호한다.
- GitHub Actions Secret에 `TOSS_SNAPSHOT_URL`, `TOSS_SNAPSHOT_TOKEN`을 등록한다.
- continuous workflow가 매 10분 `scripts/fetch_toss_snapshot.py`로 가져온다.

두 방식을 동시에 활성화하지 않는 것을 권장한다. 같은 Market Tape를 중복 계산·커밋할 필요가 없기 때문이다.
