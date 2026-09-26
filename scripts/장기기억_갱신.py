from __future__ import annotations

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MEMORY = ROOT / "memory"
CURRENT = MEMORY / "current"
KST = timezone(timedelta(hours=9))

REPORT = ROOT / "data" / "supervisor" / "latest-report.json"
OPERATIONS = ROOT / "data" / "operations" / "status.json"
HEALTH = ROOT / "data" / "health" / "latest.json"
QUEUE = ROOT / "data" / "supervisor" / "question_queue.json"
ISSUES = ROOT / "data" / "news" / "issue-digest.json"
AI_RESULTS = ROOT / "data" / "supervisor" / "ai-results"


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def text_of(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        head = (
            value.get("title")
            or value.get("axis")
            or value.get("id")
            or value.get("issue_id")
            or value.get("signal")
            or value.get("question")
            or value.get("detail")
        )
        tail = (
            value.get("finding")
            or value.get("reason")
            or value.get("proposal")
            or value.get("action")
            or value.get("status")
        )
        if head and tail and str(head) != str(tail):
            return f"{head} — {tail}"
        if head or tail:
            return str(head or tail)
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def bullets(values: Any, empty: str = "없음") -> str:
    rows = [text_of(x) for x in as_list(values)]
    rows = [x for x in rows if x]
    return "\n".join(f"- {x}" for x in rows) if rows else f"- {empty}"


def slug(value: str) -> str:
    value = re.sub(r"[^0-9A-Za-z가-힣._+-]+", "-", value).strip("-")
    return value[:120] or "unknown"


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def parsed_time(value: Any) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        dt = datetime.now(KST)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt.astimezone(KST)


def supervisor_bucket(report: dict[str, Any]) -> str:
    name = str(report.get("supervisor") or "").upper()
    if name in {"A", "B"}:
        return name
    return "recovery"


def render_supervisor(report: dict[str, Any]) -> str:
    axes = as_list(report.get("work_axes_reviewed"))
    return f"""# {report.get('batch_id') or 'Supervisor 기록'}

- supervisor: {report.get('supervisor') or 'Recovery'}
- processed_at: {report.get('processed_at') or '미확인'}
- status: {report.get('status') or 'unknown'}
- work_axes_reviewed: {len(axes)}

## 시장 발견
{bullets(report.get('summary'))}

## 시장 해설
{text_of(report.get('market_narrative')) or '기록 없음'}

## 작업축 검토
{bullets(axes)}

## 프로젝트 개선 신호
{bullets(report.get('project_improvement_signals'))}

## 실제 처리
{bullets(report.get('actions'))}

## 실패/차단/변경된 가정
{bullets(report.get('failed_attempts') or report.get('blocked_items') or report.get('assumptions_changed'))}

## 상대 Supervisor 피드백
{bullets(report.get('feedback_to_other_supervisor') or report.get('supervisor_feedback'))}

## 다음 확인
{bullets(report.get('next_checks'))}

## 변경 경로
{bullets(report.get('changed_paths'))}
"""


def open_project_items(report: dict[str, Any], operations: dict[str, Any]) -> list[Any]:
    rows: list[Any] = []
    for item in as_list(report.get("project_improvement_signals")):
        if isinstance(item, dict) and str(item.get("status") or "").lower() in {
            "resolved",
            "normal",
            "complete",
            "completed",
        }:
            continue
        rows.append(item)
    for item in as_list(operations.get("cards")):
        if isinstance(item, dict) and str(item.get("state") or "") != "완료":
            rows.append(
                {
                    "title": item.get("title"),
                    "status": item.get("state"),
                    "finding": item.get("impact"),
                    "verify_after": item.get("verify_after"),
                }
            )
    return rows


def current_docs(
    report: dict[str, Any],
    operations: dict[str, Any],
    health: dict[str, Any],
    queue: dict[str, Any],
    issues: dict[str, Any],
) -> None:
    now = report.get("processed_at") or datetime.now(KST).isoformat()
    focus = as_list(report.get("market_focus"))
    active_issues = [
        x
        for x in as_list(issues.get("issues"))
        if isinstance(x, dict) and str(x.get("status") or "").upper() != "RESOLVED"
    ]
    open_items = open_project_items(report, operations)

    write(
        CURRENT / "현재상태.md",
        f"""# 현재 상태

> 갱신: {now}
> canonical batch: {report.get('batch_id') or '미확인'}

## 시장
{text_of(report.get('market_narrative')) or '시장 해설 없음'}

## 지금 먼저 볼 것
{bullets(focus[:8])}

## 운영
- status: {operations.get('status') or 'unknown'}
- health: {health.get('status') or 'unknown'}
- 뉴스 후보: {(operations.get('news') or {}).get('candidate_count', '미확인')}건
- 활성/관찰 이슈: {len(active_issues)}개
- 질문 큐 open: {queue.get('open_count', '미확인')}개

## 현재 열린 프로젝트 항목
{bullets(open_items[:15])}
""",
    )

    write(
        CURRENT / "다음확인사항.md",
        f"""# 다음 확인사항

> 갱신: {now}

## 다음 체크
{bullets(report.get('next_checks'))}

## 현재 해석을 바꿀 조건
{bullets(report.get('invalidation_checks'))}

## 실운영 검증 대기
{bullets([x for x in open_items if isinstance(x, dict) and str(x.get('status') or x.get('state') or '').lower() in {'verification_pending', '검증 대기'}])}
""",
    )

    open_questions = [
        q
        for q in as_list(queue.get("questions"))
        if isinstance(q, dict) and q.get("status") == "open"
    ]
    open_questions.sort(
        key=lambda q: (-int(q.get("priority") or 0), str(q.get("first_seen_at") or ""))
    )
    write(
        CURRENT / "열린문제.md",
        f"""# 열린 문제

> 갱신: {now}

## 프로젝트
{bullets(open_items[:30])}

## 사용자 행동이 기술적으로 필요한 항목
{bullets(operations.get('user_actions'))}

## 오래 열린 연구 질문 상위
{bullets(open_questions[:20])}
""",
    )

    hypotheses = as_list(report.get("hypotheses"))
    write(
        CURRENT / "현재가설.md",
        f"""# 현재 가설

> 갱신: {now}

## 구조화 가설
{bullets(hypotheses)}

## 반증·무효화 조건
{bullets(report.get('invalidation_checks'))}

구조화 가설이 없으면 임의로 만들지 않는다. 다음 Supervisor가 검증 가능한 가설을 만든 경우 이 파일에 자동 반영한다.
""",
    )

    write(
        CURRENT / "최근핵심변화.md",
        f"""# 최근 핵심 변화

> 갱신: {now}

## 요약
{bullets(report.get('summary'))}

## 처리
{bullets(report.get('actions'))}

## 작업축
{bullets(report.get('work_axes_reviewed'))}

## 변경 파일
{bullets(report.get('changed_paths'))}
""",
    )


def daily_snapshot(day: str) -> None:
    rows: list[dict[str, Any]] = []
    for path in AI_RESULTS.glob("*.json"):
        item = read_json(path)
        if str(item.get("processed_at") or "").startswith(day):
            rows.append(item)
    rows.sort(key=lambda x: str(x.get("processed_at") or ""))

    lines = [f"# {day} 일간 Supervisor 기억", "", f"- 실행 수: {len(rows)}", ""]
    for item in rows:
        summary = " / ".join(
            text_of(x) for x in as_list(item.get("summary"))[:2] if text_of(x)
        )
        axes = len(as_list(item.get("work_axes_reviewed")))
        lines += [
            f"## {item.get('processed_at') or '시각 미확인'} · {item.get('supervisor') or 'Recovery'}",
            f"- batch: {item.get('batch_id') or ''}",
            f"- status: {item.get('status') or 'unknown'}",
            f"- 작업축: {axes}",
            f"- 핵심: {summary or '요약 없음'}",
            "",
        ]
    write(MEMORY / "snapshots" / "daily" / f"{day}.md", "\n".join(lines))


def render_index(
    report: dict[str, Any],
    operations: dict[str, Any],
    health: dict[str, Any],
    queue: dict[str, Any],
    issues: dict[str, Any],
) -> None:
    focus = as_list(report.get("market_focus"))[:5]
    open_items = open_project_items(report, operations)[:10]
    resolved = [
        x
        for x in as_list(report.get("project_improvement_signals"))
        if isinstance(x, dict) and str(x.get("status") or "").lower() == "resolved"
    ][:8]
    active_issues = [
        x
        for x in as_list(issues.get("issues"))
        if isinstance(x, dict) and str(x.get("status") or "").upper() != "RESOLVED"
    ][:8]
    axes = as_list(report.get("work_axes_reviewed"))

    write(
        MEMORY / "INDEX.md",
        f"""# Stock AutoResearch Memory Index

> 자동 갱신: {report.get('processed_at') or '미확인'}
> latest batch: {report.get('batch_id') or '미확인'}
> Supervisor: {report.get('supervisor') or 'Recovery'} · 상태 {report.get('status') or 'unknown'}
> 이번 작업축: {len(axes)}개

## 시작할 때 읽기

1. 이 파일
2. memory/current/현재상태.md
3. memory/current/다음확인사항.md
4. 현재 문제에 관련된 WARM memory
5. 반복 문제/과거 비교가 필요할 때만 COLD memory

## 현재 가장 중요한 시장
{bullets(focus)}

## 활성 시장 이슈
{bullets(active_issues)}

## 현재 열린 프로젝트 문제
{bullets(open_items)}

## 최근 해결
{bullets(resolved)}

## 운영 품질
- operations: {operations.get('status') or 'unknown'}
- health: {health.get('status') or 'unknown'}
- open questions: {queue.get('open_count', '미확인')}
- 사용자 개입 필요: {len(as_list(operations.get('user_actions')))}건

## 기억 위치
- 현재 상태 → memory/current/
- A/B/Recovery 실행 → memory/supervisors/
- 실패/기능/삭제/공급자 → memory/project/
- 시장 이슈/regime/반응 → memory/market/
- 질문/가설/발견/반증 → memory/research/
- 재사용 교훈 → memory/lessons/
- 일/주/월 압축 → memory/snapshots/

canonical 사실은 data/ 원본을 우선한다.
""",
    )


def catalog(report: dict[str, Any]) -> None:
    value = {
        "schema_version": 1,
        "generated_at": report.get("processed_at") or datetime.now(KST).isoformat(),
        "latest_batch_id": report.get("batch_id"),
        "latest_supervisor": report.get("supervisor"),
        "hot": [
            "memory/INDEX.md",
            "memory/current/현재상태.md",
            "memory/current/다음확인사항.md",
            "memory/current/열린문제.md",
            "memory/current/현재가설.md",
            "memory/current/최근핵심변화.md",
            "docs/AI_연속_인수인계.md",
        ],
        "warm": [
            "memory/project/",
            "memory/market/",
            "memory/research/",
            "memory/lessons/",
        ],
        "cold": [
            "memory/supervisors/",
            "memory/snapshots/",
            "memory/archive/",
        ],
    }
    write(MEMORY / "catalog.json", json.dumps(value, ensure_ascii=False, indent=2))


def main() -> int:
    report = read_json(REPORT)
    if not report:
        print("장기기억 갱신 건너뜀: canonical Supervisor 결과 없음")
        return 0

    operations = read_json(OPERATIONS)
    health = read_json(HEALTH)
    queue = read_json(QUEUE)
    issues = read_json(ISSUES)

    dt = parsed_time(report.get("processed_at"))
    bucket = supervisor_bucket(report)
    stamp = dt.strftime("%Y-%m-%d-%H%M")
    batch = slug(str(report.get("batch_id") or stamp))

    write(
        MEMORY / "supervisors" / bucket / f"{stamp}-{batch}.md",
        render_supervisor(report),
    )
    current_docs(report, operations, health, queue, issues)
    daily_snapshot(dt.strftime("%Y-%m-%d"))
    render_index(report, operations, health, queue, issues)
    catalog(report)

    print(
        json.dumps(
            {
                "memory_updated": True,
                "batch_id": report.get("batch_id"),
                "supervisor": bucket,
                "hot_files": 7,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
