# 토스증권 데이터 전환 계획

사용 증권사 기준은 **토스증권**으로 잡는다.

현재 Market Tape의 기존 키움 코드는 즉시 삭제하지 않고 fallback/비교용으로 남겨두되, 신규 개발의 우선 데이터 공급자는 Toss Open API로 전환한다.

## 토스에서 활용할 기능

- 국내·미국 현재가
- 최근 체결
- 1분봉·일봉
- 거래대금·등락률 랭킹
- KRX·NXT 장 운영시간
- KRW/USD 환율
- 국내 지수·국채
- 개인·외국인·기관 수급
- 프로그램매매
- 공매도
- 신용
- 대차
- 국내 통합 실시간 체결 WebSocket

## 왜 별도 Collector가 필요한가

토스 Open API는 허용 IP 등록이 필요하다.

GitHub-hosted Actions는 실행마다 고정 IP를 보장하지 않으므로 장중 실시간 체결 수집기의 주 실행 장소로 적합하지 않다.

권장 구조:

고정 IP Collector → Toss WebSocket(KRX+NXT 통합) → 실제 체결가×체결량 → 정확한 1분 거래대금 → provider_current.json/분봉 저장 → GitHub 10분 분석 Loop.

## 거래시간

Toss의 국내 실시간 WebSocket은 KRX+NXT 통합 시세를 사용한다.

프로젝트는 15:30을 “분석 종료”로 보지 않는다.

- KRX 종가까지의 흐름
- NXT 대상 종목의 15:40~20:00 애프터마켓
- 20:00 이후 Overnight Macro

를 서로 다른 구간으로 저장하고 비교한다.

모든 종목이 NXT 대상이라고 가정하지 않는다.

## 보안 원칙

- 주문 API는 사용하지 않는다.
- 계좌 헤더가 필요한 기능은 현재 연구 범위에서 제외한다.
- 토큰·client secret은 Secret으로만 저장한다.
- 대시보드나 Markdown에 인증정보를 기록하지 않는다.

## 사용자 도움이 필요한 것

실시간 Toss Collector를 실제 가동하려면 고정 공인 IP가 있는 실행환경이 필요하다.

예:
- 고정 IP VPS
- 고정 Elastic IP를 붙인 클라우드 VM
- 고정 공인 IP가 있는 개인 서버

환경이 준비되면 TOSS_CLIENT_ID, TOSS_CLIENT_SECRET을 Secret으로 등록하고 토스증권 Open API 설정에서 해당 IP를 허용한다.

## 관련 문서

- [시장 데이터 명세](MARKET_DATA_SPEC.md)
- [Risk Veto](RISK_VETO.md)
- [문서 지도](DOCS_MAP.md)
