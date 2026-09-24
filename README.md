# Stock AutoResearch

완전자율형 주식 리서치 실험 프로젝트입니다.

사용자는 큰 목적만 정합니다.

```
stocks
```

시스템은 스스로 다음 루프를 수행합니다.

```
시장 스캔
→ 사건/변화 후보 추출
→ 중요도 점수화
→ 연구 주제 선정
→ 연구 질문 생성
→ 웹/1차 자료 조사
→ Evidence 저장
→ Critic 반론·누락 검토
→ 필요 시 재조사
→ 산업·종목 연결
→ 최종 리포트
→ 상태 저장
```

## V1 원칙

- 기존 `market-memo`와 완전히 독립적입니다.
- 한국·미국 주식시장을 기본 범위로 둡니다.
- 공식 문서·정부·거래소·기업 IR 등 1차 자료를 우선합니다.
- 기사만 존재하는 내용을 확정 사실로 승격하지 않습니다.
- 사실, 당사자 주장, 분석, 추정을 구분합니다.
- 같은 내용을 반복 수집하지 않고 새 변화와 새 근거를 우선합니다.
- 매수·매도 추천기가 아니라 조사 시스템입니다.

## 빠른 실행

Python 3.11+가 필요합니다.

```bash
pip install -e .
python -m autoresearch run --mode dry-run
```

`dry-run`은 API 키 없이 전체 파이프라인을 검증합니다.

실전 웹 리서치:

```bash
export OPENAI_API_KEY="..."
python -m autoresearch run --mode live
```

기본 모델은 `config/research.yaml` 또는 `OPENAI_MODEL` 환경변수로 변경할 수 있습니다.

## GitHub Actions

`.github/workflows/autoresearch.yml`은 수동 실행과 평일 아침 자동 실행을 지원합니다. 실전 자동 실행 전 저장소 Settings → Secrets and variables → Actions에 `OPENAI_API_KEY`를 등록하세요.

## 결과

- `data/runs/`: 각 실행의 구조화된 JSON
- `data/state/`: 이전 연구와 비교하기 위한 상태
- `reports/`: 사람이 읽는 Markdown 리포트

> 이 프로젝트의 산출물은 투자 조언이 아니라 조사 결과입니다. 시장 데이터와 공시는 원문을 다시 확인해야 합니다.
