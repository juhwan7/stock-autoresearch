from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))
OUT = ROOT / "data" / "operations" / "status.json"
KANBAN = ROOT / "docs" / "운영_칸반.md"
README = ROOT / "README.md"

README_START = "<!-- AUTO-USER-ACTION:START -->"
README_END = "<!-- AUTO-USER-ACTION:END -->"


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def parse_time(value: object) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt.astimezone(KST)


def age_minutes(value: object, now: datetime) -> float | None:
    dt = parse_time(value)
    return None if dt is None else max(0.0, (now - dt).total_seconds() / 60)


def latest_supervisors() -> dict[str, dict]:
    result: dict[str, dict] = {}
    folder = ROOT / "data" / "supervisor" / "ai-results"
    for path in folder.glob("*.json"):
        data = read_json(path)
        supervisor = str(data.get("supervisor") or "").upper()
        if supervisor not in {"A", "B"}:
            continue
        current = result.get(supervisor)
        if current is None or str(data.get("processed_at") or "") > str(current.get("processed_at") or ""):
            result[supervisor] = {
                "processed_at": data.get("processed_at"),
                "batch_id": data.get("batch_id"),
                "status": data.get("status"),
                "path": str(path.relative_to(ROOT)),
            }
    return result


def card(card_id: str, title: str, state: str, impact: str, now: datetime, **extra: object) -> dict:
    value = {
        "card_id": card_id,
        "title": title,
        "state": state,
        "impact": impact,
        "last_checked": now.isoformat(),
    }
    value.update(extra)
    return value


def build_status(now: datetime | None = None) -> dict:
    now = (now or datetime.now(KST)).astimezone(KST)
    supervisors = latest_supervisors()
    discovery = read_json(ROOT / "data" / "discovery" / "latest.json")
    issue_digest = read_json(ROOT / "data" / "news" / "issue-digest.json")
    health = read_json(ROOT / "data" / "health" / "latest.json")
    state = read_json(ROOT / "data" / "supervisor" / "state.json")
    queue = read_json(ROOT / "data" / "supervisor" / "question_queue.json")
    site_state_path = ROOT / "site" / "data" / "상태.json"

    cards: list[dict] = []
    user_actions: list[dict] = []

    for name in ("A", "B"):
        row = supervisors.get(name) or {}
        age = age_minutes(row.get("processed_at"), now)
        if age is None:
            cards.append(card(f"supervisor-{name.lower()}-missing", f"Supervisor {name} 결과 없음", "사용자 확인 필요", "정각/30분 AI 연속성이 끊길 수 있음", now, owner="Recovery"))
            user_actions.append({
                "id": f"supervisor-{name.lower()}-missing",
                "problem": f"Supervisor {name} 결과 파일을 찾지 못함",
                "impact": "AI 시장 해석/이슈 갱신 누락 가능",
                "attempted": "다른 Supervisor와 Recovery가 상태를 이어받도록 설계",
                "why_blocked": "ChatGPT 예약 작업 자체의 계정 실행상태는 GitHub Action이 직접 재활성화할 수 없음",
                "action": "ChatGPT 자동화에서 해당 Supervisor가 활성화되어 있는지 확인",
                "verify": f"새 Supervisor {name} batch가 생성되고 canonical state에 반영",
            })
        elif age > 150:
            cards.append(card(f"supervisor-{name.lower()}-critical", f"Supervisor {name} {round(age)}분 정지", "사용자 확인 필요", "이슈 상태가 오래될 수 있음", now, owner="Recovery", verify_after="즉시"))
            user_actions.append({
                "id": f"supervisor-{name.lower()}-critical",
                "problem": f"Supervisor {name} 마지막 실행이 {round(age)}분 전",
                "impact": "정각/30분 AI 중 한 축이 장시간 정지",
                "attempted": "상대 Supervisor와 복구감시가 stale 상태를 감지",
                "why_blocked": "GitHub는 ChatGPT 예약 작업 자체를 켤 권한이 없음",
                "action": "ChatGPT 자동화 활성 상태를 확인하고 필요하면 다시 켜기",
                "verify": "70분 이내의 새 batch 확인",
            })
        elif age > 70:
            cards.append(card(f"supervisor-{name.lower()}-stale", f"Supervisor {name} {round(age)}분 지연", "조사 중", "다음 사이클 누락 가능", now, owner="Recovery", verify_after="다음 30분 사이클"))
        else:
            cards.append(card(f"supervisor-{name.lower()}-ok", f"Supervisor {name} 정상", "완료", f"마지막 {round(age)}분 전", now, owner=name))

    discovery_age = age_minutes(discovery.get("generated_at"), now)
    issue_age = age_minutes(issue_digest.get("updated_at"), now)
    if discovery_age is None or discovery_age > 20:
        cards.append(card("discovery-stale", "뉴스 discovery 신선도 저하", "조사 중", f"마지막 갱신 {discovery_age if discovery_age is not None else '미확인'}분 전", now, owner="6분 센서", verify_after="다음 6분"))
    else:
        cards.append(card("discovery-ok", "뉴스 discovery 정상", "완료", f"{round(discovery_age)}분 전 갱신", now, owner="6분 센서"))
    if issue_age is None or issue_age > 70:
        cards.append(card("issue-digest-stale", "이슈 원장 갱신 지연", "검증 대기", f"마지막 갱신 {issue_age if issue_age is not None else '미확인'}분 전", now, owner="A/B", verify_after="다음 :00/:30"))
    else:
        cards.append(card("issue-digest-ok", "이슈 원장 정상", "완료", f"{round(issue_age)}분 전 갱신 · {len(issue_digest.get('issues') or [])}개", now, owner="A/B"))

    if not site_state_path.exists() or site_state_path.stat().st_size == 0:
        cards.append(card("pages-data-empty", "Pages 상태 데이터 0 byte/누락", "수정 중", "대시보드가 비어 보일 수 있음", now, owner="6분 센서", verify_after="다음 대시보드 생성"))
    else:
        cards.append(card("pages-data-ok", "Pages 상태 데이터 정상", "완료", f"{site_state_path.stat().st_size} bytes", now, owner="Dashboard"))

    source_status = discovery.get("source_status") or {}
    needs_credentials = [name for name, value in source_status.items() if isinstance(value, dict) and value.get("status") == "needs_credentials"]
    if needs_credentials:
        user_actions.append({
            "id": "optional-news-credentials",
            "problem": "일부 보조 뉴스/공시 API 자격증명 없음",
            "impact": "Google RSS 등 fallback은 계속 작동하지만 탐색 범위가 줄어들 수 있음",
            "attempted": "키 없는 공개 소스와 broad fallback 유지",
            "why_blocked": "API Secret은 사용자가 GitHub Secrets에 직접 등록해야 함",
            "action": "필요 시 NAVER_CLIENT_ID/NAVER_CLIENT_SECRET/DART_API_KEY 등록",
            "verify": "source_status가 needs_credentials에서 ok로 전환",
        })

    for issue in health.get("issues") or []:
        if not isinstance(issue, dict):
            continue
        severity = str(issue.get("severity") or "").upper()
        if severity in {"CRITICAL", "WARN"}:
            cards.append(card(
                "health-" + re.sub(r"[^a-z0-9_-]", "-", str(issue.get("component") or "unknown").lower() + "-" + str(issue.get("code") or "issue").lower()),
                str(issue.get("component") or "system") + " · " + str(issue.get("message") or "Health 경고"),
                "조사 중" if severity == "WARN" else "수정 중",
                str(issue.get("recovery") or ""),
                now,
                owner="Recovery",
                verify_after="다음 Health 실행",
            ))

    return {
        "generated_at": now.isoformat(),
        "status": "needs_user_action" if user_actions else ("investigating" if any(x["state"] in {"조사 중", "수정 중", "검증 대기"} for x in cards) else "normal"),
        "supervisors": supervisors,
        "canonical": {
            "last_batch_id": state.get("last_batch_id"),
            "last_processed_at": state.get("last_processed_at"),
        },
        "news": {
            "discovery_generated_at": discovery.get("generated_at"),
            "candidate_count": discovery.get("item_count"),
            "issue_updated_at": issue_digest.get("updated_at"),
            "issue_count": len(issue_digest.get("issues") or []),
        },
        "question_queue": {
            "updated_at": queue.get("updated_at"),
            "open_count": queue.get("open_count"),
        },
        "cards": cards,
        "user_actions": user_actions,
    }


def render_kanban(status: dict) -> str:
    columns = ["발견", "조사 중", "수정 중", "검증 대기", "사용자 확인 필요", "완료"]
    groups = {name: [] for name in columns}
    for item in status.get("cards") or []:
        groups.setdefault(item.get("state") or "발견", []).append(item)
    lines = ["# 운영 Kanban", "", f"> 자동 갱신: {status.get('generated_at')}", ""]
    for name in columns:
        lines += [f"## {name}", ""]
        rows = groups.get(name) or []
        if not rows:
            lines += ["- 없음", ""]
            continue
        for item in rows:
            lines.append(f"- **{item.get('title')}**")
            lines.append(f"  - 영향: {item.get('impact')}")
            lines.append(f"  - 담당: {item.get('owner','자동화')}")
            if item.get("verify_after"):
                lines.append(f"  - 다음 확인: {item.get('verify_after')}")
            lines.append(f"  - 최근 확인: {item.get('last_checked')}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def update_readme(status: dict) -> None:
    try:
        text = README.read_text(encoding="utf-8")
    except OSError:
        return
    actions = status.get("user_actions") or []
    if actions:
        body = ["## 사용자 확인 필요", ""]
        for item in actions:
            body += [
                f"- **{item.get('problem')}**",
                f"  - 영향: {item.get('impact')}",
                f"  - AI가 시도한 것: {item.get('attempted')}",
                f"  - 자동 해결 불가 이유: {item.get('why_blocked')}",
                f"  - 사용자가 할 일: {item.get('action')}",
                f"  - 해결 확인: {item.get('verify')}",
            ]
    else:
        body = ["## 사용자 확인 필요", "", "- 현재 사람이 직접 처리해야 하는 필수 항목은 없습니다."]
    block = README_START + "\n" + "\n".join(body) + "\n" + README_END
    if README_START in text and README_END in text:
        text = re.sub(re.escape(README_START) + r".*?" + re.escape(README_END), block, text, flags=re.S)
    else:
        insert_at = text.find("\n## 바로가기")
        text = (text[:insert_at] + "\n\n" + block + "\n" + text[insert_at:]) if insert_at >= 0 else text + "\n\n" + block + "\n"
    README.write_text(text, encoding="utf-8")


def main() -> None:
    status = build_status()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    KANBAN.write_text(render_kanban(status), encoding="utf-8")
    update_readme(status)
    print(json.dumps({"status": status["status"], "cards": len(status["cards"]), "user_actions": len(status["user_actions"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
