from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from autoresearch.feedback import (
    classify_feedback,
    feedback_fingerprint,
    stable_event_fingerprint,
)


KST = timezone(timedelta(hours=9))


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def append_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        if path.exists() and path.stat().st_size:
            handle.write("\n")
        handle.write(value.rstrip() + "\n")


def github_request(method: str, endpoint: str, payload: dict[str, Any] | None = None) -> Any:
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        raise RuntimeError("GITHUB_TOKEN/GITHUB_REPOSITORY가 필요합니다.")

    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        "https://api.github.com/repos/" + repo + endpoint,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {exc.code}: {detail[:800]}") from exc


def issue_comments(issue: int) -> list[dict[str, Any]]:
    return github_request("GET", f"/issues/{issue}/comments?per_page=100")


def already_notified(issue: int, fingerprint: str) -> bool:
    marker = f"<!-- stock-autoresearch-notify:{fingerprint} -->"
    return any(marker in str(item.get("body") or "") for item in issue_comments(issue))


def post_comment(issue: int, body: str) -> None:
    github_request("POST", f"/issues/{issue}/comments", {"body": body})


def git_names(base_sha: str) -> list[str]:
    if not base_sha:
        return []
    result = subprocess.run(
        ["git", "diff", "--name-only", base_sha, "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [x.strip() for x in result.stdout.splitlines() if x.strip()]


def latest_tick() -> dict[str, Any]:
    folder = ROOT / "data" / "evolution" / "ticks"
    if not folder.exists():
        return {}
    for path in sorted(folder.glob("*.jsonl"), reverse=True):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return {}


def latest_change() -> dict[str, Any]:
    folder = ROOT / "data" / "evolution" / "changes"
    if not folder.exists():
        return {}
    files = sorted(folder.glob("*.json"), reverse=True)
    return read_json(files[0]) if files else {}


def health_event() -> dict[str, Any] | None:
    data = read_json(ROOT / "data" / "health" / "latest.json")
    status = str(data.get("status") or "OK")
    if status not in {"WARN", "CRITICAL"}:
        return None
    issues = [
        {
            "component": item.get("component"),
            "code": item.get("code"),
            "severity": item.get("severity"),
            "message": item.get("message"),
        }
        for item in data.get("issues", [])
        if str(item.get("severity")) in {"WARN", "CRITICAL"}
    ]
    return {"type": "health", "status": status, "issues": issues}


def regression_event() -> dict[str, Any] | None:
    data = read_json(ROOT / "data" / "regression" / "latest.json")
    status = str(data.get("status") or "")
    if status not in {"QUARANTINED", "ROLLED_BACK"}:
        return None
    evaluations = [
        {
            "change_id": item.get("change_id"),
            "status": item.get("status"),
            "reason": item.get("reason"),
        }
        for item in data.get("evaluations", [])
        if item.get("status") in {"quarantined", "rolled_back"}
    ]
    return {
        "type": "regression",
        "status": status,
        "evaluations": evaluations[:5],
    }


def notify(args: argparse.Namespace) -> int:
    issue = int(args.issue)
    tick = latest_tick()
    change = latest_change()
    changed_files = git_names(args.base_sha)
    events: list[dict[str, Any]] = []

    outcome = str(tick.get("outcome") or "")
    scout = tick.get("scout") or {}
    if outcome == "applied" and change:
        events.append(
            {
                "type": "evolution_change",
                "change_id": change.get("change_id"),
                "title": change.get("title"),
                "risk": change.get("risk"),
                "reason": change.get("decision_basis"),
                "benefit": change.get("expected_benefit"),
                "paths": change.get("paths", []),
            }
        )
    elif outcome in {"proposal_only", "blocked", "validation_failed"}:
        if scout.get("needs_user") or outcome == "validation_failed":
            events.append(
                {
                    "type": "evolution_attention",
                    "outcome": outcome,
                    "title": scout.get("title"),
                    "risk": scout.get("risk"),
                    "reason": scout.get("decision_basis"),
                    "user_help": scout.get("user_help"),
                }
            )

    health = health_event()
    if health:
        events.append(health)
    regression = regression_event()
    if regression:
        events.append(regression)

    if not events:
        print("알림할 의미 있는 변화 없음")
        return 0

    fingerprint = stable_event_fingerprint({"events": events})
    if already_notified(issue, fingerprint):
        print("이미 알린 상태:", fingerprint)
        return 0

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    lines = [
        "@juhwan7 **Stock AutoResearch 변경 알림**",
        "",
        f"- 시간: {now}",
        f"- 커밋: [{sha[:8]}](https://github.com/{repo}/commit/{sha})",
    ]

    for event in events:
        etype = event["type"]
        if etype == "evolution_change":
            lines.extend(
                [
                    "",
                    "### ✅ AI 개선 적용",
                    f"- 제목: **{event.get('title') or '-'}**",
                    f"- change_id: {event.get('change_id') or '-'}",
                    f"- 위험도: {event.get('risk') or '-'}",
                    f"- 이유: {event.get('reason') or '-'}",
                    f"- 기대효과: {event.get('benefit') or '-'}",
                    "- 변경 파일:",
                ]
            )
            lines.extend(
                [f"  - {path}" for path in event.get("paths", [])[:12]]
            )
        elif etype == "evolution_attention":
            lines.extend(
                [
                    "",
                    "### 🟡 사용자 확인이 유용한 제안",
                    f"- 상태: {event.get('outcome')}",
                    f"- 제목: **{event.get('title') or '-'}**",
                    f"- 이유: {event.get('reason') or '-'}",
                    f"- 필요한 도움: {event.get('user_help') or '-'}",
                ]
            )
        elif etype == "health":
            lines.append("")
            lines.append(f"### ⚠️ Health {event.get('status')}")
            for item in event.get("issues", [])[:8]:
                lines.append(
                    f"- {item.get('component')}/{item.get('code')}: "
                    f"{item.get('message')}"
                )
        elif etype == "regression":
            lines.append("")
            lines.append(f"### 🛡️ Regression {event.get('status')}")
            for item in event.get("evaluations", [])[:5]:
                lines.append(
                    f"- {item.get('change_id') or '-'} · "
                    f"{item.get('status')} · {item.get('reason') or ''}"
                )

    if changed_files:
        lines.extend(
            [
                "",
                "<details><summary>이번 Tick 전체 변경 파일</summary>",
                "",
            ]
        )
        lines.extend([f"- {name}" for name in changed_files[:30]])
        lines.extend(["", "</details>"])

    lines.extend(
        [
            "",
            "### 바로 피드백하기",
            "이 Issue에 짧게 답하면 됩니다.",
            "",
            "- 좋아 / 유지 → 이 방향을 긍정적으로 기억",
            "- 보류 → 비슷한 개선을 우선 멈춤",
            "- 수정해줘: 원하는 방향 → 다음 자기진화 최우선 수정 요청",
            "- 되돌려줘: CHANGE_ID → 안전검사 후 롤백 요청",
            "- 아이디어: 내용 → 새 개선 아이디어",
            "- 그냥 자유롭게 적어도 사용자 피드백으로 저장",
            "",
            "자동 검증 단계를 통과한 뒤 이 알림이 작성됩니다.",
            f"<!-- stock-autoresearch-notify:{fingerprint} -->",
        ]
    )
    post_comment(issue, "\n".join(lines))
    print("GitHub Issue 알림 작성:", fingerprint)
    return 0


def ingest(args: argparse.Namespace) -> int:
    issue = int(args.issue)
    body = os.environ.get("COMMENT_BODY", "").strip()
    author = str(args.author)
    comment_id = str(args.comment_id)
    comment_url = str(args.comment_url or "")
    if not body:
        print("빈 피드백")
        return 0

    classification = classify_feedback(body)
    fingerprint = feedback_fingerprint(author, comment_id, body)
    log_path = ROOT / "data" / "feedback" / "사용자_피드백.jsonl"

    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            try:
                old = json.loads(line)
            except json.JSONDecodeError:
                continue
            if old.get("fingerprint") == fingerprint:
                print("이미 처리한 피드백")
                return 0

    now = datetime.now(KST)
    record = {
        "schema_version": 1,
        "fingerprint": fingerprint,
        "received_at": now.isoformat(),
        "issue_number": issue,
        "comment_id": comment_id,
        "comment_url": comment_url,
        "author": author,
        "kind": classification.kind,
        "priority": classification.priority,
        "change_id": classification.change_id,
        "body": body,
        "status": "pending_evolution_review",
    }
    append_jsonl(log_path, record)

    labels = {
        "positive": "긍정/유지",
        "hold": "보류",
        "modify_request": "수정 요청",
        "rollback_request": "롤백 요청",
        "idea": "새 아이디어",
        "freeform": "자유 피드백",
    }
    title = labels.get(classification.kind, classification.kind)
    block = (
        f"## {now.strftime('%Y-%m-%d %H:%M KST')} — {title}\n\n"
        f"- 우선순위: {classification.priority}\n"
        f"- change_id: {classification.change_id or '지정 없음'}\n"
        f"- GitHub 댓글: {comment_url or '링크 없음'}\n"
        f"- 내용: {body}\n\n"
        "처리 상태: 다음 자기진화 Tick의 최우선 사용자 피드백으로 전달\n"
    )
    append_text(ROOT / "docs" / "사용자_피드백.md", block)

    ack = {
        "positive": "✅ 긍정 피드백으로 저장했습니다. 비슷한 방향의 개선을 선호 신호로 사용합니다.",
        "hold": "⏸️ 보류 피드백으로 저장했습니다. 다음 자기진화부터 비슷한 변경을 우선 멈추고 재검토합니다.",
        "modify_request": "🛠️ 수정 요청으로 저장했습니다. 다음 자기진화 Tick에서 최우선으로 검토합니다.",
        "rollback_request": "↩️ 롤백 요청으로 저장했습니다. 다음 자기진화에서 해당 change_id와 이후 변경 충돌을 확인한 뒤 안전하게 처리합니다.",
        "idea": "💡 새 아이디어로 저장했습니다. 다음 자기진화 후보에 우선 포함합니다.",
        "freeform": "📝 사용자 피드백으로 저장했습니다. 다음 자기진화가 우선 컨텍스트로 읽습니다.",
    }[classification.kind]
    post_comment(issue, ack + f"\n\n<!-- feedback-ack:{comment_id} -->")
    print("피드백 저장:", classification.kind)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    notify_parser = sub.add_parser("notify")
    notify_parser.add_argument("--issue", default="1")
    notify_parser.add_argument("--base-sha", default="")

    ingest_parser = sub.add_parser("ingest")
    ingest_parser.add_argument("--issue", default="1")
    ingest_parser.add_argument("--comment-id", required=True)
    ingest_parser.add_argument("--author", required=True)
    ingest_parser.add_argument("--comment-url", default="")

    args = parser.parse_args()
    if args.command == "notify":
        raise SystemExit(notify(args))
    raise SystemExit(ingest(args))


if __name__ == "__main__":
    main()
