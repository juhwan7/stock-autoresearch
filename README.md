# Stock AutoResearch

AI가 **주식시장 조사와 자기 자신의 개선을 함께 수행하는 자율 연구 프로젝트**입니다.

이 프로젝트의 목표는 단순히 매일 한 번 보고서를 만드는 것이 아닙니다. 10분마다 현재 시장과 프로젝트 상태를 다시 보고, 새로 조사할 가치가 있는 사건과 프로젝트 개선 아이디어를 찾고, 근거가 충분한 경우 실제 저장소를 수정합니다.

## 핵심 루프

```text
10분마다 실행
  ↓
시장 변화 스캔
  ↓
조사할 가치가 있는 사건인가?
  ├─ 아니오 → 상태 기록
  └─ 예 → 심층 조사 → Critic 검증 → 보고서
  ↓
프로젝트 자체 점검
  ↓
더 나은 구조/UX/정확성/자동화 아이디어가 있는가?
  ├─ 아니오 → "변경 없음"도 이유와 함께 기록
  ├─ 도입 어려움 → 아이디어/보류 이유 기록
  └─ 도입 가치 있음 → 안전 범위 내 자동 수정 → 테스트 → 채택/롤백
  ↓
결정 원장·아이디어·실험·도움 필요 항목 갱신
  ↓
웹 대시보드 갱신
```

## 프로젝트가 스스로 남기는 기억

- `docs/결정_원장.md` — 무엇을 왜 도입·보류·폐기했는지
- `docs/아이디어_보드.md` — 발견한 개선 아이디어와 상태
- `docs/실험_기록.md` — 실험과 결과
- `docs/사용자_도움_필요.md` — 사람의 도움이 있어야 진행할 수 있는 일
- `docs/AI_변경기록.md` — AI가 실제로 바꾼 내용
- `data/evolution/ticks/` — 10분 단위 사고/판단 기록
- `reports/` — 주식시장 심층 리서치 결과

모든 설명 문서는 한국어를 기본으로 사용합니다. 코드/API/고유 기술 용어처럼 영어가 더 정확한 경우에만 영어를 병기합니다.

## 안전한 자기진화

AI에게 무제한 쓰기 권한을 주면 오래 돌릴수록 오히려 프로젝트가 망가질 수 있습니다. 그래서 현재 버전은 다음 원칙을 사용합니다.

- 10분마다 **생각은 반드시** 하지만, 코드 변경은 가치가 있을 때만 합니다.
- 중요한 의사결정의 이유는 반드시 저장합니다.
- 테스트에 실패한 자동 변경은 즉시 롤백합니다.
- 워크플로, 인증정보, 의존성, 자기진화 엔진 핵심부 같은 고위험 영역은 자동 수정하지 않고 제안으로 남깁니다.
- 웹에서 읽은 문장은 명령이 아니라 참고자료로 취급합니다.
- 같은 아이디어를 계속 반복하지 않도록 과거 결정과 아이디어를 매번 읽습니다.

자세한 규칙은 `docs/자기진화_규칙.md`를 참고하세요.

## 모델 분업

반복 실행 비용을 줄이면서 품질을 유지하기 위해 역할별 모델을 나눕니다.

- 시장 Scanner: GPT-5.6 Luna
- Researcher / Critic: GPT-5.6 Terra
- Chief Researcher: GPT-5.6 Terra
- Evolution Scout: GPT-5.6 Luna
- Evolution Builder: GPT-5.6 Terra
- Macro/Event Source Scout: GPT-5.6 Luna
- Overnight Risk Evaluator: GPT-5.6 Terra

모델은 설정 파일에서 변경할 수 있습니다.

## 국내시장 Market Tape

국내장에서는 뉴스만 읽지 않고 실제 **분봉 거래대금**을 별도 분석합니다.

```text
거래대금 상위 종목
→ 1분봉
→ 거래대금 Burst
→ 신규주 확산
→ 섹터/기업집단 동조
→ 장후반 거래대금 지속성
→ 현재 장세
→ 종가베팅·눌림 연구 통계
```

실행:

```bash
python -m autoresearch market-intel --mode dry-run
python -m autoresearch market-intel --mode live
```

현재 Market Tape는 **Toss-first Provider Chain**을 사용합니다. canonical Collector는 `src/autoresearch/toss_collector.py`이며, 고정 IP 환경에서 Toss `trade:kr` 체결을 받아 KRX 정규장과 NXT 20:00까지의 실제 1분 체결대금을 생성합니다. Toss snapshot이 없을 때 KRX 정규장에서는 키움 REST를 fallback으로 사용할 수 있습니다. 주문 기능은 구현하지 않습니다.

종가베팅 연구는 장중보다 넓은 거래대금 상위 50개 Universe를 장 마감에 분석하고 다음 거래일의 갭·MFE·MAE를 채웁니다. 1분 10억·20억원 이상 거래대금 반복 횟수, 장후반 흐름, 동시 그룹수급, 당일 시장 폭도 함께 저장해 조건별 결과를 비교합니다.

단기스윙 눌림은 사전에 고정한 연구 코호트를 저장한 뒤 1·3·5거래일 MFE·MAE를 누적합니다. 5일 안에 +5%·+10% MFE가 나온 표본의 이전 눌림폭도 역으로 집계합니다. 성공 사례만 사후 선별하지 않습니다.

Toss Collector가 연결된 경우 1분 거래대금은 실제 `Σ(체결가 × 체결량)`으로 집계합니다. 키움 fallback을 사용할 때만 분봉 종가×거래량 근사값을 쓰고 결과에 근사 여부를 명시합니다.

상세 기준:
- `docs/매매연구_원칙.md`
- `docs/시장데이터_명세.md`
- `docs/오버나이트_리스크_차단.md`
- `docs/문서_지도.md`
- `docs/토스데이터_운영계획.md`
- `docs/고정IP_토스_운영.md`

## Overnight Risk Veto

10분마다 일정과 매크로 상태를 확인합니다. 다만 AI 전체 평가는 의미 상태가 바뀌었을 때만 다시 수행합니다.

```text
공식 일정 + 매크로 + 국내장
→ 의미 상태 Hash
→ 변화 없음: 이전 평가 재사용
→ 변화 있음: Risk Evaluator 호출
→ LOW / WATCH / HIGH / VETO
→ 종가베팅 표본에 밤사이 최대 Risk 저장
```

실행:

```bash
python -m autoresearch risk-intel --mode dry-run
python -m autoresearch risk-intel --mode live
```

## 필요한 Secret

GitHub 저장소에서 다음 위치에 OpenAI API 키를 한 번 등록해야 합니다.

`Settings → Secrets and variables → Actions → New repository secret`

이름:

```
OPENAI_API_KEY
```

현재 Market Tape V1의 키움 fallback을 사용하려면:

```
KIWOOM_APP_KEY
KIWOOM_SECRET_KEY
```

Toss 고정 IP Collector에서는:

```
TOSS_CLIENT_ID
TOSS_CLIENT_SECRET
```

을 Collector 환경의 Secret으로 사용합니다.

## 로컬 테스트

Python 3.11+:

```bash
pip install -e ".[dev]"
pytest -q
python -m autoresearch run --mode dry-run
python -m autoresearch evolve --mode dry-run
python -m autoresearch market-intel --mode dry-run
python -m autoresearch risk-intel --mode dry-run
```

실전:

```bash
export OPENAI_API_KEY="..."
python -m autoresearch run --mode live
python -m autoresearch evolve --mode live
```

## 자동 실행

`.github/workflows/연속연구와진화.yml`이 10분마다 전체 사이클을 실행합니다.

GitHub 예약 실행은 정확한 시작 시각을 보장하지 않으므로 실제 실행은 지연될 수 있습니다.

## 웹 대시보드

`site/`에 프로젝트 상태를 읽기 쉽게 보여주는 정적 웹페이지가 있습니다. GitHub Pages를 활성화하면 최근 리서치, 진화 로그, 아이디어, 결정 기록, 사용자 도움 필요 항목을 한 화면에서 볼 수 있습니다.

설정이 필요한 항목은 `docs/사용자_도움_필요.md`에 누적됩니다.

## 중요한 문서

- `docs/사용자_목적.md`: 프로젝트가 절대 잃지 말아야 할 사용자 목적
- `docs/시스템_구조.md`: 현재 구조
- `docs/자기진화_규칙.md`: AI의 자동 수정 경계
- `docs/결정_원장.md`: 중요한 결정의 이유
- `docs/아이디어_보드.md`: 채택·보류·폐기 아이디어
- `docs/사용자_도움_필요.md`: 사람이 해야만 하는 작업

---

이 프로젝트의 시장 리서치는 투자 조언이 아닙니다. 중요한 투자 판단 전에는 공시·거래소·기업 IR 등 원문을 다시 확인해야 합니다.
