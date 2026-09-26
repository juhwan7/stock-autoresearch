# Stock AutoResearch

한국 주식시장의 **자금 흐름·뉴스·공시·이벤트를 계속 관측하고 검증하는 자율 시장 연구 프로젝트**입니다.

핵심 구조는 단순합니다.

```text
10분 비AI 센서
→ 시장 데이터·뉴스·공시·Health 관측
→ 10개 관측을 시간축으로 축적
→ 매시 정각 ChatGPT 심층 리서치·프로젝트 감독
→ 가설·반증·사후검증
→ 필요한 경우 기능 개선
→ 다음 관측에서 효과 재검증
```

GitHub Actions의 10분 센서는 OpenAI API를 호출하지 않습니다. AI 판단과 웹 심층조사는 :00/:30의 두 ChatGPT Supervisor이 담당합니다.

> 기존 `market-memo`와 독립된 프로젝트입니다. 주문·자동매매 기능은 구현하지 않습니다.


<!-- AUTO-USER-ACTION:START -->
## 사용자 확인 필요

- **Supervisor B 마지막 실행이 199분 전**
  - 영향: 정각/30분 AI 중 한 축이 장시간 정지
  - AI가 시도한 것: 상대 Supervisor와 복구감시가 stale 상태를 감지
  - 자동 해결 불가 이유: GitHub는 ChatGPT 예약 작업 자체를 켤 권한이 없음
  - 사용자가 할 일: ChatGPT 자동화 활성 상태를 확인하고 필요하면 다시 켜기
  - 해결 확인: 70분 이내의 새 batch 확인
<!-- AUTO-USER-ACTION:END -->

## 바로가기

- **대시보드:** https://juhwan7.github.io/stock-autoresearch/
- **이슈 추적:** https://juhwan7.github.io/stock-autoresearch/이슈추적.html
- **시스템/Kanban:** https://juhwan7.github.io/stock-autoresearch/시스템.html
- **지수 대비 상대강도:** https://juhwan7.github.io/stock-autoresearch/상대강도.html
- **시장 거대자금 흐름:** https://juhwan7.github.io/stock-autoresearch/거대자금.html
- [문서 지도](docs/문서_지도.md)
- [사용자 목적](docs/사용자_목적.md)
- [시스템 구조](docs/시스템_구조.md)
- [매매연구 원칙](docs/매매연구_원칙.md)
- [시장데이터 명세](docs/시장데이터_명세.md)
- [사용자 도움 필요](docs/사용자_도움_필요.md)

## 현재 운영 구조

### 1. 10분 시장 센서

`.github/workflows/연속연구와진화.yml`이 10분마다 시장과 프로젝트 상태를 관측합니다.

주요 입력은 네이버 공개 10분 배치, 연결된 Toss 데이터, 시장 discovery, DART·뉴스 단서, Risk, Health, Regression입니다. 센서는 AI 없이 객관적인 관측을 저장하고 판단·질문 생성은 :00/:30 Supervisor에 맡김합니다.

### 2. 국내 정량 데이터

기본 fallback은 고정 IP가 필요 없는 네이버 공개 데이터입니다. Toss 고정 IP REST 수집이 정상 연결된 경우 더 높은 우선순위의 데이터 공급자로 사용합니다.

Toss 수집은 현재 Top50만 보고 끝내지 않습니다. 당일 한 번이라도 Top50에 들어온 종목은 순위 밖으로 밀려나도 계속 추적합니다.

Toss 1분봉의 거래대금은 OHLCV 기반 `종가×거래량` 근사이며, 가능한 구간은 누적 거래대금 차분으로 보정합니다. 정확값과 근사값은 항상 구분합니다.

자세한 정의는 [시장데이터 명세](docs/시장데이터_명세.md), Toss 설정은 [고정 IP Toss 10분 러너](docs/고정IP_토스_러너.md)를 봅니다.

### 3. 매시간 AI 감독

매시 정각 AI는 최근 센서만 요약하지 않습니다.

- 시장 전체에서 실제 돈과 새 정보가 몰리는 트렌드를 동적으로 탐색
- 10분·1분 흐름과 뉴스·공시의 발생 순서를 비교
- 1차 자료 우선 검증과 반론 조사
- 종가베팅·눌림 연구
- Overnight Risk 확인
- 질문 → 가설 → 사후검증
- 데이터 누락·API 장애·파서 변화 등 다음 실패 가능성 선제 점검
- 실제 연구를 방해하는 기능 부족이 있으면 프로젝트 개선

새 외부 API가 필요하면 코드·테스트 등 인증 없이 가능한 부분을 먼저 준비하고, 필요한 Secret과 최소 권한만 사용자에게 요청합니다.

### 4. 데이터 누락 대응

Toss가 연결됐다는 사실만으로 데이터가 완전하다고 가정하지 않습니다.

장중에는 Top50 개수, 1분봉 공백, 종목별 fetch 오류, 보조 공급자와의 종목 차이, 10분 실행 지연, Top50 이탈 종목 추적 단절 등을 검사합니다.

누락 시 보조 공급자 값으로 조용히 덮어쓰지 않고 **출처와 exact/estimated 상태를 보존한 backfill**을 사용합니다.

### 5. 연구 전략

국내 단기 연구의 중심은 종가베팅과 눌림 단기스윙입니다.

중요하게 보는 것은 거래대금, 추세, 장후반 지속성, 섹터 동조, 앞선 대량거래 구간, 5·20일선, 다음 날 갭/MFE/MAE, 예정 이벤트와 Overnight Risk입니다. 성공 사례만 골라 통계를 만들지 않습니다.

## 주요 폴더

| 경로 | 역할 |
|---|---|
| `src/autoresearch/` | Python 연구·수집·검증 엔진 |
| `tests/` | 회귀·데이터·연구 로직 테스트 |
| `config/` | 운영 설정 |
| `prompts/` | AI 역할별 지시문 |
| `docs/` | 현재 운영 규칙과 설계 문서 |
| `data/` | 센서·상태·통계·런타임 데이터 |
| `reports/` | 사람이 읽는 시장 연구 결과 |
| `scripts/` | 자동화 보조 스크립트 |
| `site/` | GitHub Pages 대시보드 |
| `.github/workflows/` | 10분 센서·테스트·배포·알림 |

전체 문서는 [문서 지도](docs/문서_지도.md)에서 역할별로 찾을 수 있습니다.

## 안전 원칙

공시·거래소·정부·기업 IR 등 1차 자료를 우선합니다. 기사 하나만으로 중요한 사실을 확정하지 않고 사실·당사자 주장·분석·추정·미확인을 구분합니다.

데이터가 없으면 숫자를 만들지 않습니다. Secret을 저장소나 로그에 기록하지 않습니다. 주문·송금·결제 실행 권한은 자동 확장하지 않습니다.

잘못된 프로젝트 개선은 전체 저장소를 과거로 돌리는 대신 기능 단위 회귀검증과 롤백을 사용합니다.

## 로컬 검증

Python 3.11+:

```bash
pip install -e ".[dev]"
pytest -q
python -m autoresearch run --mode dry-run
python -m autoresearch market-intel --mode dry-run
python -m autoresearch risk-intel --mode dry-run
```

프로젝트의 세부 규칙은 README에 중복해서 쌓지 않고 `docs/`의 단일 기준 문서에서 관리합니다.
