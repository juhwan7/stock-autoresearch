from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from autoresearch.supervisor_result import infer_run_kind, regular_window_complete

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))
OUT = ROOT / "data" / "operations" / "status.json"
KANBAN = ROOT / "docs" / "운영_칸반.md"
README = ROOT / "README.md"
MEMORY_CATALOG = ROOT / "memory" / "catalog.json"

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


def sensor_slot_coverage(now: datetime, *, slot_count: int = 6) -> dict:
    recent = read_json(ROOT / "data" / "supervisor" / "recent.json")
    observations = recent.get("observations") or []
    if not isinstance(observations, list):
        observations = []

    current_slot = now.replace(
        minute=(now.minute // 10) * 10,
        second=0,
        microsecond=0,
    )
    end_slot = current_slot - timedelta(minutes=10)
    expected = [
        end_slot - timedelta(minutes=10 * offset)
        for offset in range(slot_count - 1, -1, -1)
    ]
    expected_keys = {slot.isoformat() for slot in expected}

    received: dict[str, dict] = {}
    for item in observations:
        if not isinstance(item, dict):
            continue
        stamp = parse_time(item.get("slot_at") or item.get("observed_at"))
        if stamp is None:
            continue
        slot = stamp.replace(
            minute=(stamp.minute // 10) * 10,
            second=0,
            microsecond=0,
        )
        key = slot.isoformat()
        if key not in expected_keys:
            continue
        current = received.get(key)
        current_start_delay = float(
            (current or {}).get("slot_start_delay_seconds")
            or (current or {}).get("slot_delay_seconds")
            or 999999
        )
        candidate_start_delay = float(
            item.get("slot_start_delay_seconds")
            or item.get("slot_delay_seconds")
            or 0
        )
        if current is None or candidate_start_delay < current_start_delay:
            received[key] = item

    received_slots = [slot.isoformat() for slot in expected if slot.isoformat() in received]
    missing_slots = [slot.isoformat() for slot in expected if slot.isoformat() not in received]
    start_delays = [
        float(
            (received.get(slot) or {}).get("slot_start_delay_seconds")
            or (received.get(slot) or {}).get("slot_delay_seconds")
            or 0
        )
        for slot in received_slots
    ]
    completion_delays = [
        float((received.get(slot) or {}).get("slot_delay_seconds") or 0)
        for slot in received_slots
    ]
    event_counts: dict[str, int] = {}
    slot_source_counts: dict[str, int] = {}
    for slot in received_slots:
        item = received.get(slot) or {}
        event_name = str((item.get("source") or {}).get("event_name") or "unknown")
        slot_source = str(item.get("slot_source") or "legacy")
        event_counts[event_name] = event_counts.get(event_name, 0) + 1
        slot_source_counts[slot_source] = slot_source_counts.get(slot_source, 0) + 1
    ratio = round(len(received_slots) / slot_count, 3) if slot_count else 0.0
    return {
        "window_start": expected[0].isoformat() if expected else None,
        "window_end": expected[-1].isoformat() if expected else None,
        "expected_slot_count": slot_count,
        "received_slot_count": len(received_slots),
        "received_slots": received_slots,
        "missing_slots": missing_slots,
        "coverage_ratio": ratio,
        "max_slot_start_delay_seconds": (
            round(max(start_delays), 1) if start_delays else None
        ),
        "max_slot_delay_seconds": (
            round(max(completion_delays), 1) if completion_delays else None
        ),
        "trigger_event_counts": event_counts,
        "slot_source_counts": slot_source_counts,
    }


def latest_supervisors() -> dict[str, dict]:
    """Return only real regular A/B runs; test/E2E/Recovery never count as liveness."""
    result: dict[str, dict] = {}
    folder = ROOT / "data" / "supervisor" / "ai-results"
    for path in folder.glob("*.json"):
        data = read_json(path)
        if infer_run_kind(data) != "regular":
            continue
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
                "run_kind": "regular",
                "window_complete": regular_window_complete(data),
                "expected_observation_count": data.get("expected_observation_count", 3),
                "received_observation_count": data.get("received_observation_count"),
                "missing_observation_slots": data.get("missing_observation_slots") or [],
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
    memory_catalog = read_json(MEMORY_CATALOG)
    slot_coverage = sensor_slot_coverage(now)
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
            cards.append(card(f"supervisor-{name.lower()}-stale", f"Supervisor {name} {round(age)}분 지연", "조사 중", "다음 정규 사이클 누락 가능", now, owner="Recovery", verify_after="다음 30분 사이클"))
        elif not row.get("window_complete"):
            expected = int(row.get("expected_observation_count") or 3)
            received = row.get("received_observation_count")
            received_text = "미확인" if received is None else str(received)
            cards.append(card(
                f"supervisor-{name.lower()}-window-incomplete",
                f"Supervisor {name} 정규 window 검증 대기",
                "검증 대기",
                f"최근 정규 결과 {received_text}/{expected} 슬롯 · 누락 슬롯은 과거값으로 보충하지 않음",
                now,
                owner=name,
                verify_after="다음 정규 A/B 사이클",
            ))
        else:
            cards.append(card(f"supervisor-{name.lower()}-ok", f"Supervisor {name} 정상", "완료", f"마지막 정규 실행 {round(age)}분 전 · 3/3 window", now, owner=name))

    coverage_ratio = float(slot_coverage.get("coverage_ratio") or 0)
    coverage_text = (
        f"{slot_coverage.get('received_slot_count')}/{slot_coverage.get('expected_slot_count')} 슬롯"
    )
    if coverage_ratio >= 0.83:
        cards.append(card(
            "sensor-slot-coverage-ok",
            "10분 센서 슬롯 커버리지 정상",
            "완료",
            coverage_text,
            now,
            owner="10분 센서",
        ))
    elif coverage_ratio >= 0.5:
        cards.append(card(
            "sensor-slot-coverage-degraded",
            "10분 센서 슬롯 일부 누락",
            "검증 대기",
            coverage_text + " · 누락 " + ", ".join(slot_coverage.get("missing_slots") or []),
            now,
            owner="Recovery",
            verify_after="다음 10분 슬롯",
        ))
    else:
        cards.append(card(
            "sensor-slot-coverage-poor",
            "10분 센서 슬롯 커버리지 낮음",
            "조사 중",
            coverage_text + " · GitHub schedule/저장 경로 점검 필요",
            now,
            owner="Recovery",
            verify_after="다음 Recovery 또는 10분 센서",
        ))

    discovery_age = age_minutes(discovery.get("generated_at"), now)
    issue_age = age_minutes(issue_digest.get("updated_at"), now)
    if discovery_age is None or discovery_age > 25:
        cards.append(card("discovery-stale", "뉴스 discovery 신선도 저하", "조사 중", f"마지막 갱신 {discovery_age if discovery_age is not None else '미확인'}분 전", now, owner="10분 센서", verify_after="다음 10분 슬롯"))
    else:
        cards.append(card("discovery-ok", "뉴스 discovery 정상", "완료", f"{round(discovery_age)}분 전 갱신", now, owner="10분 센서"))
    if issue_age is None or issue_age > 70:
        cards.append(card("issue-digest-stale", "이슈 원장 갱신 지연", "검증 대기", f"마지막 갱신 {issue_age if issue_age is not None else '미확인'}분 전", now, owner="A/B", verify_after="다음 :00/:30"))
    else:
        cards.append(card("issue-digest-ok", "이슈 원장 정상", "완료", f"{round(issue_age)}분 전 갱신 · {len(issue_digest.get('issues') or [])}개", now, owner="A/B"))

    if not site_state_path.exists() or site_state_path.stat().st_size == 0:
        cards.append(card("pages-data-empty", "Pages 상태 데이터 0 byte/누락", "수정 중", "대시보드가 비어 보일 수 있음", now, owner="10분 센서", verify_after="다음 대시보드 생성"))
    else:
        cards.append(card("pages-data-ok", "Pages 상태 데이터 정상", "완료", f"{site_state_path.stat().st_size} bytes", now, owner="Dashboard"))

    memory_age = age_minutes(memory_catalog.get("generated_at"), now)
    if not memory_catalog:
        cards.append(card(
            "long-memory-missing",
            "장기 AI 기억 미생성",
            "수정 중",
            "A/B가 과거 시행착오를 빠르게 이어받지 못할 수 있음",
            now,
            owner="Memory",
            verify_after="다음 Supervisor canonical 적용",
        ))
    elif memory_age is None or memory_age > 90:
        cards.append(card(
            "long-memory-stale",
            "장기 AI 기억 갱신 지연",
            "검증 대기",
            f"마지막 기억 갱신 {memory_age if memory_age is not None else '미확인'}분 전",
            now,
            owner="Memory",
            verify_after="다음 :00/:30 또는 Recovery",
        ))
    else:
        cards.append(card(
            "long-memory-ok",
            "장기 AI 기억 정상",
            "완료",
            f"{round(memory_age)}분 전 갱신 · {memory_catalog.get('latest_supervisor') or 'Recovery'}",
            now,
            owner="Memory",
        ))

    source_status = discovery.get("source_status") or {}
    needs_credentials = [name for name, value in source_status.items() if isinstance(value, dict) and value.get("status") == "needs_credentials"]
    candidate_count = int(discovery.get("item_count") or 0)
    if needs_credentials and candidate_count < 20:
        user_actions.append({
            "id": "news-credentials-required",
            "problem": "뉴스/공시 탐색 커버리지가 낮고 일부 보조 API 자격증명도 없음",
            "impact": "핵심 이슈 누락 가능성이 커짐",
            "attempted": "키 없는 Google RSS·공개 소스와 broad fallback 사용",
            "why_blocked": "추가 API Secret은 사용자가 GitHub Secrets에 직접 등록해야 함",
            "action": "NAVER_CLIENT_ID/NAVER_CLIENT_SECRET/DART_API_KEY 중 필요한 자격증명 등록",
            "verify": "후보 뉴스가 20건 이상 안정적으로 수집되고 source coverage가 회복",
        })
    elif needs_credentials:
        cards.append(card(
            "optional-news-credentials",
            "선택형 뉴스·공시 API 미연결",
            "완료",
            f"현재 공개 fallback으로 후보 {candidate_count}건 확보되어 필수 조치 아님",
            now,
            owner="Discovery",
        ))

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
        "sensor_slot_coverage": slot_coverage,
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
        "memory": {
            "generated_at": memory_catalog.get("generated_at"),
            "latest_batch_id": memory_catalog.get("latest_batch_id"),
            "latest_supervisor": memory_catalog.get("latest_supervisor"),
            "age_minutes": None if memory_age is None else round(memory_age, 1),
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
    """README는 프로젝트 소개 문서다. 실시간 장애 상세는 시스템/운영 Kanban에서만 표시한다."""
    return None


def main() -> None:
    status = build_status()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    KANBAN.write_text(render_kanban(status), encoding="utf-8")
    print(json.dumps({"status": status["status"], "cards": len(status["cards"]), "user_actions": len(status["user_actions"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
