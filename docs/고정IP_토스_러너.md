# EC2 Toss 10분 수집기 연결

목표는 Raspberry Pi와 상시 WebSocket 없이, 고정 공인 IP가 있는 EC2가 10분마다 Toss REST API를 직접 호출하도록 만드는 것이다.

## 최종 구조

```
EC2 Elastic IP
→ GitHub self-hosted runner
→ 10분마다 Toss OAuth
→ 거래대금 현재 Top50
→ 당일 Top50 진입 종목 합집합 유지
→ 각 추적 종목 최근 1분봉 조회
→ data/providers/toss/latest.json
→ main commit
→ 기존 10분 감독 workflow와 30분 간격 A/B Supervisor가 사용
```

Toss Client ID/Secret은 EC2 파일에 저장하지 않는다. GitHub Repository Secret의 `TOSS_CLIENT_ID`, `TOSS_CLIENT_SECRET`을 self-hosted runner job에만 주입한다.

## 1. EC2에 Elastic IP 연결

AWS Console에서:

1. EC2
2. 왼쪽 `Elastic IP addresses`
3. `Allocate Elastic IP address`
4. 생성된 Elastic IP 선택
5. `Actions → Associate Elastic IP address`
6. stock-autoresearch용 EC2 인스턴스를 선택
7. 연결

EC2 일반 Public IPv4는 인스턴스 중지/시작 후 달라질 수 있으므로 Toss 허용 IP에는 Elastic IP를 등록하는 것을 권장한다.

## 2. Toss 허용 IP 등록

Toss WTS:

`설정 → Open API → 허용 IP 관리`

방금 EC2에 연결한 Elastic IP를 등록한다.

등록되지 않은 IP의 REST/WebSocket 요청은 Toss에서 403으로 거부된다.

## 3. GitHub self-hosted runner 등록 토큰 받기

GitHub 저장소:

`Settings → Actions → Runners → New self-hosted runner → Linux → x64`

화면에 표시되는 임시 등록 토큰을 복사한다.

이 토큰은 runner 등록용 일회성/단기 토큰이며 `TOSS_CLIENT_SECRET`과 다른 값이다.

## 4. EC2에서 bootstrap 실행

저장소를 clone한 뒤:

```bash
cd stock-autoresearch
chmod +x scripts/ec2_toss_runner_bootstrap.sh
RUNNER_TOKEN='GitHub에서 방금 받은 runner 등록 토큰' \
bash scripts/ec2_toss_runner_bootstrap.sh
```

성공하면 GitHub `Settings → Actions → Runners`에:

`stock-autoresearch-ec2`

가 Online으로 표시되고 label에:

`stock-autoresearch-fixed-ip`

가 포함된다.

## 5. GitHub 설정

Repository Secrets:

```
TOSS_CLIENT_ID
TOSS_CLIENT_SECRET
```

Repository Variables:

```
TOSS_FIXED_IP_RUNNER_ENABLED=true
```

Toss Secret 값은 로그나 코드에 붙이지 않는다.

## 6. 연결 테스트

GitHub:

`Actions → 고정 IP 토스 10분 시장 데이터 → Run workflow`

정상일 때 주요 단계:

- Install: success
- Collect Toss Top50 and recent 1-minute candles: success
- Summarize Toss provider state: success
- Validate Toss batch code: success
- Commit Toss market state: success

그리고 다음 파일이 갱신된다.

```
data/providers/toss/latest.json
data/providers/toss/status.json
data/providers/toss/history.json
```

## 수집 규칙

매 10분:

1. Toss 거래대금 현재 Top50을 조회한다.
2. 당일 한 번이라도 Top50에 들어온 종목은 합집합에 계속 남긴다.
3. 현재 54위, 80위로 밀려나도 당일에는 계속 1분봉을 조회한다.
4. 각 추적 종목의 최근 1분봉을 가져온다.
5. 새로운 1분봉을 당일 시계열에 병합한다.
6. 다음 거래일에는 추적 Universe를 초기화한다.

Toss 1분봉 REST 응답은 OHLCV이므로 1분 거래대금은 기본적으로 `종가×거래량` 근사값이다. 현재 Top50 종목이 직전 관측에도 Top50이었다면 Toss ranking의 누적 `tradingAmount` 차분을 이용해 해당 10분 구간 합계를 보정한다.

## 흔한 오류

### 403

Toss 허용 IP와 EC2 실제 egress IP가 다르다.

- EC2 Elastic IP가 실제 연결됐는지 확인
- Toss 허용 IP에 같은 Elastic IP가 등록됐는지 확인

### Runner Offline

EC2에서:

```bash
cd /opt/actions-runner
sudo ./svc.sh status
sudo ./svc.sh start
```

### TOSS_CLIENT_ID/TOSS_CLIENT_SECRET 없음

GitHub 저장소의 `Settings → Secrets and variables → Actions`에 두 Repository Secret을 등록한다.

### workflow가 계속 skipped

Repository Variable `TOSS_FIXED_IP_RUNNER_ENABLED=true`를 추가한다.

