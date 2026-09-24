# Toss Collector 출력 위치

고정 IP 환경의 Toss Collector는 최신 정규화 스냅샷을 이 폴더의 latest.json으로 전달한다.

Stock AutoResearch는 이 파일이 신선하면 키움보다 먼저 사용한다.

필수 최상위 필드:

- captured_at: ISO 8601 KST
- minute_by_ticker: KRX 정규장 1분 데이터
- postmarket_by_ticker: NXT 애프터마켓 15:40~20:00 데이터
- metadata
- ranking
- market_overview
- session
- minute_amount_method

1분 row 권장 필드:

- timestamp 또는 time
- open / high / low / close
- volume
- amount

WebSocket 체결가×체결량을 합산했다면 amount는 실제 1분 체결대금이며 minute_amount_method는 exact_trade_sum으로 기록한다.

주문·계좌 정보는 이 스냅샷에 넣지 않는다.
