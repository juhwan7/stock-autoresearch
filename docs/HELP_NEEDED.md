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
