# Toss 실시간 Collector

이 디렉터리는 고정 IP 서버에서 08:00~20:00 국내 통합 체결을 모으는 **읽기 전용** Collector다.

주문 API는 호출하지 않는다.

## 왜 별도 서버인가

토스증권 Open API는 허용 IP 등록이 필요하고, 국내 WebSocket은 KRX+NXT 통합 체결을 제공한다.

GitHub-hosted runner는 고정 IP 상시 WebSocket 수집기로 사용하지 않는다.

## 수집 흐름

1. OAuth2 Client Credentials로 access token 발급.
2. 시장 전체 거래대금 랭킹에서 상위 종목을 구성.
3. 최대 100개 이내에서 `trade:kr` 실시간 체결 구독.
4. 체결마다 실제 `체결가 × 체결량`을 합산.
5. 1분 OHLCV + 실제 1분 거래대금 생성.
6. 정규장과 NXT 애프터마켓을 별도 저장.
7. 10초마다 원자적으로 latest.json 갱신.
8. AutoResearch의 `toss_bridge.py`가 최신 스냅샷을 읽는다.

## 설치

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r collector/requirements.txt

cp collector/config.example.json collector/config.json
```

환경변수:

```bash
TOSS_CLIENT_ID=...
TOSS_CLIENT_SECRET=...
TOSS_COLLECTOR_CONFIG=/opt/stock-autoresearch/collector/config.json
TOSS_SNAPSHOT_PATH=/var/lib/stock-autoresearch/toss/latest.json
```

토스 WTS의 Open API 설정에서 **이 서버의 고정 공인 IP**를 허용해야 한다.

## systemd

`stock-autoresearch-toss.service.example`을 환경에 맞게 복사해서 사용한다.

## 주의

- 국내 WebSocket은 KRX+NXT 통합 시세다.
- 실시간 시세 채널은 중간 프레임 유실이 가능한 구조이므로 Collector는 수신 지연/재연결 횟수를 diagnostics에 남긴다.
- 연결당 구독은 100건 이하로 유지한다.
- 서버로부터 데이터를 받는 중에도 keepalive를 위해 60초 주기로 PING을 보낸다.
- Collector 재시작/네트워크 단절 구간은 정확한 체결대금이 비므로 데이터 품질에서 별도 취급해야 한다.
- `unknown_trade_keys`가 생기면 토스 WebSocket Trade payload 스키마 변경 여부를 확인한다.

## GitHub와 연결

Collector의 출력은 현재 `data/providers/toss/latest.json` 계약과 동일하다.

운영 환경에서는 다음 중 하나로 연결한다.

1. 고정 IP 서버를 GitHub **self-hosted runner**로 사용해 같은 서버의 snapshot을 읽게 한다.
2. 인증된 내부/HTTPS snapshot endpoint를 만들고 10분 workflow가 가져온다.

대량 체결 데이터를 매 10초마다 Git commit 하는 방식은 사용하지 않는다.

## 공식 문서

- https://developers.tossinvest.com/
- https://developers.tossinvest.com/docs/market-data
