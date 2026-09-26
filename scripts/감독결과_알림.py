from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from autoresearch.feedback import build_telegram_payload


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "data" / "supervisor" / "latest-report.json"
ISSUE_NUMBER = 1


def read_report() -> dict[str, Any]:
    try:
        value = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def github_request(method: str, endpoint: str, payload: dict[str, Any] | None = None) -> Any:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repo:
        raise RuntimeError("GITHUB_TOKEN/GITHUB_REPOSITORY가 필요합니다.")

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
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
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def already_notified(batch_id: str) -> bool:
    marker = "<!-- hourly-supervisor:" + batch_id + " -->"
    try:
        comments = github_request("GET", "/issues/" + str(ISSUE_NUMBER) + "/comments?per_page=100")
    except (RuntimeError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False
    return any(marker in str(item.get("body") or "") for item in comments)


def post_issue(report: dict[str, Any]) -> bool:
    batch_id = str(report.get("batch_id") or "").strip()
    if not batch_id or already_notified(batch_id):
        return False

    lines = [
        "@juhwan7 **1시간 감독 배치 처리 결과**",
        "",
        "- batch_id: " + batch_id,
        "- 처리 관측: " + str(len(report.get("observation_ids") or [])) + "개",
        "- 상태: **" + str(report.get("status") or "unknown") + "**",
        "",
        "### 핵심 요약",
    ]
    for item in (report.get("summary") or [])[:8]:
        lines.append("- " + str(item))

    actions = report.get("actions") or []
    if actions:
        lines.extend(["", "### 처리한 작업"])
        for item in actions[:10]:
            lines.append("- " + str(item))

    changed = report.get("changed_paths") or []
    if changed:
        lines.extend(["", "### 변경 파일"])
        for item in changed[:15]:
            lines.append("- " + str(item))

    next_checks = report.get("next_checks") or []
    if next_checks:
        lines.extend(["", "### 다음 6분 관측에서 확인"])
        for item in next_checks[:8]:
            lines.append("- " + str(item))

    lines.extend(
        [
            "",
            "### 바로 피드백",
            "이 Issue에 좋아, 보류, 수정해줘: ..., 되돌려줘: CHANGE_ID, 아이디어: ... 또는 자유문장으로 답하면 다음 1시간 감독 배치가 우선 처리합니다.",
            "",
            "<!-- hourly-supervisor:" + batch_id + " -->",
        ]
    )
    try:
        github_request(
            "POST",
            "/issues/" + str(ISSUE_NUMBER) + "/comments",
            {"body": "\n".join(lines)},
        )
        return True
    except (RuntimeError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        print("GitHub Issue 감독 알림 실패:", type(exc).__name__)
        return False


def send_telegram(report: dict[str, Any]) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("Telegram Secret이 없어 감독 알림은 건너뜀")
        return False

    supervisor = str(report.get("supervisor") or "Recovery")
    processed = str(report.get("processed_at") or "")
    axes = report.get("work_axes_reviewed") or []
    telegram_report = report.get("telegram_report") or []

    lines = [
        f"Stock AutoResearch · Supervisor {supervisor}",
        (processed + " · " if processed else "") + "상태 " + str(report.get("status") or "unknown"),
        f"검토 작업축 {len(axes)}개 · 처리 관측 {len(report.get('observation_ids') or [])}개",
    ]

    if telegram_report:
        lines.append("")
        for item in telegram_report[:10]:
            lines.append(str(item))
    else:
        lines.extend(["", "시장·프로젝트 핵심"])
        for item in (report.get("summary") or [])[:6]:
            lines.append("- " + str(item))

    signals = report.get("project_improvement_signals") or []
    if signals:
        resolved = sum(
            1 for x in signals
            if isinstance(x, dict) and str(x.get("status") or "").lower() == "resolved"
        )
        pending = len(signals) - resolved
        lines.extend(
            [
                "",
                f"프로젝트 개선: {len(signals)}건 · 해결 {resolved} · 추적 {pending}",
            ]
        )

    changed = report.get("changed_paths") or []
    if changed:
        lines.append("실제 변경: " + str(len(changed)) + "개 경로")

    feedback = report.get("feedback_to_other_supervisor") or []
    if feedback:
        lines.extend(["", "다음 상대 Supervisor"])
        for item in feedback[:4]:
            lines.append("- " + str(item))

    actions_needed = report.get("required_user_actions") or []
    if actions_needed:
        lines.extend(["", "사용자 개입 필요"])
        for item in actions_needed[:3]:
            if isinstance(item, dict):
                lines.append("- " + str(item.get("action") or item.get("why") or item))
            else:
                lines.append("- " + str(item))
    else:
        lines.extend(["", "사용자 개입 필요: 없음"])

    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[:3870].rstrip() + "\n…(상세 내용은 대시보드/GitHub에서 확인)"

    payload = build_telegram_payload(
        chat_id=chat_id,
        text=text,
        feedback_url="https://github.com/juhwan7/stock-autoresearch/issues/1",
        dashboard_url="https://juhwan7.github.io/stock-autoresearch/",
    )
    request = urllib.request.Request(
        "https://api.telegram.org/bot" + token + "/sendMessage",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        return bool(data.get("ok"))
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
    ) as exc:
        print("Telegram 감독 알림 실패:", type(exc).__name__)
        return False


def main() -> int:
    report = read_report()
    if not report:
        print("감독 결과 파일 없음")
        return 0
    if not bool(report.get("notify")):
        print("이번 감독 배치는 알림 대상 아님")
        return 0

    batch_id = str(report.get("batch_id") or "").strip()
    if not batch_id:
        print("batch_id 없음")
        return 0
    if already_notified(batch_id):
        print("이미 알린 감독 배치:", batch_id)
        return 0

    # 이 marker는 Telegram 성공 뒤에만 생성한다.
    # 따라서 Telegram 실패 시 같은 batch를 다음 실행에서 다시 시도할 수 있다.
    telegram_ok = send_telegram(report)
    if not telegram_ok:
        print("Telegram 감독 알림 미전송 - 다음 실행에서 재시도 가능")
        return 1

    issue_ok = post_issue(report)
    if not issue_ok:
        print("Telegram 전송은 성공했지만 GitHub Issue 기록은 미전송")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
