# Toss 실시간 Collector

이 디렉터리는 고정 IP 서버 배포를 위한 호환 파일과 보조 도구를 둔다.

**실제 Collector 구현의 단일 소스는 `src/autoresearch/toss_collector.py`다.**

따라서 새 기능·버그 수정은 패키지 구현 한 곳에만 적용한다. `collector/toss_collector.py`는 기존 실행 경로를 깨지 않기 위한 얇은 호환 래퍼다.

## 실행

저장소 루트에서:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .

export TOSS_CLIENT_ID="..."
export TOSS_CLIENT_SECRET="..."

python -m autoresearch toss-collector \
  --output /var/lib/stock-autoresearch/toss/latest.json \
  --top-n 80 \
  --ranking-refresh 600 \
  --snapshot-seconds 20
```

토스 WTS의 Open API 설정에서 **이 서버의 고정 공인 IP**를 허용해야 한다.

## 수집 방식

1. OAuth2 Client Credentials로 access token 발급.
2. `MARKET_TRADING_AMOUNT / KR / realtime` 랭킹에서 거래대금 상위 종목 선정.
3. 최대 100종목을 `trade:kr`로 구독.
4. 실시간 체결의 `price × volume`을 합산.
5. 실제 1분 OHLCV와 1분 거래대금 생성.
6. 08:00~08:50, 09:00~15:30, 15:40~20:00을 분리 저장.
7. 최신 스냅샷을 원자적으로 저장.
8. `toss_bridge.py`가 해당 스냅샷을 Market Tape에 연결.

주문·계좌·보유자산 API는 사용하지 않는다.

## 운영 방식

권장 방식은 고정 IP 서버에 Collector를 systemd로 상시 실행하고, 같은 서버를 GitHub self-hosted Runner로 연결하는 것이다.

자세한 설정:

- `../docs/FIXED_IP_RUNNER.md`
- `../deploy/toss-collector.service.example`
- `../deploy/toss-collector.env.example`

대안으로 `serve_snapshot.py`를 통해 인증된 HTTPS snapshot endpoint를 만들고 GitHub-hosted Actions에서 가져오는 경로도 유지한다.

## 중요 제약

토스 실시간 시세 채널은 최신 상태 우선의 스트림이므로 네트워크 단절이나 수신 지연 구간의 체결을 완벽하게 재구성할 수 있다고 가정하지 않는다.

Collector 재연결/장애 구간은 향후 데이터 품질 플래그와 함께 평가해야 한다.

모든 종목이 NXT 지원 종목이라고 가정하지 않으며, 종목 메타데이터의 `nxtSupported`를 보존한다.
