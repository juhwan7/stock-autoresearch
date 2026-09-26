from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from autoresearch.supervisor_queue import build_supervisor_window
from autoresearch.supervisor_result import infer_run_kind, is_regular_supervisor_result, regular_window_complete, supervisor_role as classified_supervisor_role

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "data/supervisor/latest-report.json"
TEST_REPORT = ROOT / "data/supervisor/latest-test-report.json"
STATE = ROOT / "data/supervisor/state.json"
ISSUES = ROOT / "data/supervisor/market-issues.json"
RECENT_SESSIONS = ROOT / "data/market/recent-sessions.json"
POPULAR_REPORTS = ROOT / "data/research/popular-reports.json"
NEWS_ISSUES = ROOT / "data/news/issue-digest.json"
RECENT_OBSERVATIONS = ROOT / "data/supervisor/recent.json"
DISAGREEMENTS = ROOT / "data/supervisor/disagreements.json"
DISCOVERY = ROOT / "data/discovery/latest.json"
AI_RESULTS = ROOT / "data/supervisor/ai-results"
COLLABORATION = ROOT / "data/supervisor/collaboration.json"


def _read_json_dict(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _parse_result_time(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("processed_at must include timezone")
    return parsed


def normalize_observation_window(result: dict, warnings: list[str]) -> dict:
    recent_payload = _read_json_dict(RECENT_OBSERVATIONS)
    observations = recent_payload.get("observations") or []
    if not isinstance(observations, list):
        observations = []
    processed_at = _parse_result_time(result.get("processed_at"))
    supervisor = str(result.get("supervisor") or "A")
    manifest = build_supervisor_window(
        [x for x in observations if isinstance(x, dict)],
        processed_at=processed_at,
        supervisor=supervisor,
    )

    known = {
        str(item.get("observation_id")): item
        for item in observations
        if isinstance(item, dict) and item.get("observation_id")
    }
    provided = result.get("observation_ids")
    if not isinstance(provided, list):
        provided = []
    provided = [str(x) for x in provided if str(x).strip()]
    unknown = [item_id for item_id in provided if item_id not in known]

    if unknown:
        warnings.append(
            "queue에 없는 observation_ids가 있어 처리 포인터를 이동하지 않음: "
            + ", ".join(unknown[:5])
        )
        valid_ids: list[str] = []
    elif provided:
        valid_ids = provided
    else:
        valid_ids = list(manifest.get("observation_ids") or [])
        if valid_ids:
            warnings.append("observation_ids 누락을 10분 슬롯 window에서 복구")

    manifest_id_to_slot = {
        str(item_id): str(slot)
        for item_id, slot in zip(
            manifest.get("observation_ids") or [],
            manifest.get("observation_slots") or [],
        )
    }
    actual_slots: list[str] = []
    for item_id in valid_ids:
        item = known.get(item_id) or {}
        slot = item.get("slot_at") or manifest_id_to_slot.get(item_id)
        if slot:
            actual_slots.append(str(slot))

    expected_slots = list(manifest.get("expected_slots") or [])
    manifest_slots = list(manifest.get("observation_slots") or [])
    ids_match_window = bool(valid_ids) and (
        len(valid_ids) == len(manifest.get("observation_ids") or [])
        and actual_slots == manifest_slots
    )
    if valid_ids and not ids_match_window:
        warnings.append(
            "Supervisor가 사용한 observation_ids가 정해진 3개 슬롯 window와 일치하지 않음"
        )

    selected_slots = actual_slots or manifest_slots
    selected_slot_set = set(selected_slots)
    selected_missing = [
        slot for slot in expected_slots
        if slot not in selected_slot_set
    ]
    expected_count = int(manifest.get("expected_observation_count") or 3)
    selected_expected_count = sum(
        1 for slot in selected_slots
        if slot in set(expected_slots)
    )

    result["observation_ids"] = valid_ids
    result["observation_slots"] = selected_slots
    result["observation_window_start"] = manifest.get("window_start")
    result["observation_window_end"] = manifest.get("window_end")
    result["expected_observation_count"] = expected_count
    result["received_observation_count"] = len(valid_ids)
    result["missing_observation_slots"] = selected_missing
    result["observation_completeness_ratio"] = round(
        selected_expected_count / expected_count,
        3,
    ) if expected_count else 0.0
    result["observation_window_complete"] = (
        bool(manifest.get("complete"))
        and not unknown
        and ids_match_window
        and not selected_missing
    )

    if not result["observation_window_complete"]:
        warnings.append(
            "정해진 10분 슬롯 3개가 모두 준비되지 않아 결과를 verification_pending으로 유지"
        )
        if str(result.get("status") or "") not in {"blocked"}:
            result["status"] = "verification_pending"

    return manifest


def _supervisor_role(value: object) -> str | None:
    return classified_supervisor_role(value)


def _latest_regular_result(
    *,
    role: str | None = None,
    before_at: str | None = None,
    exclude_batch_id: str | None = None,
) -> dict:
    folder = AI_RESULTS
    rows: list[tuple[str, dict]] = []
    for path in folder.glob("*.json"):
        item = _read_json_dict(path)
        if not is_regular_supervisor_result(item):
            continue
        if role and _supervisor_role(item.get("supervisor")) != role:
            continue
        batch_id = str(item.get("batch_id") or "")
        processed_at = str(item.get("processed_at") or "")
        if exclude_batch_id and batch_id == exclude_batch_id:
            continue
        if before_at and processed_at >= before_at:
            continue
        rows.append((processed_at, item))
    return max(rows, key=lambda row: row[0])[1] if rows else {}


def _window_state_from_result(item: dict) -> dict:
    return {
        "batch_id": item.get("batch_id"),
        "window_start": item.get("observation_window_start"),
        "window_end": item.get("observation_window_end"),
        "observation_ids": list(item.get("observation_ids") or []),
        "missing_slots": list(item.get("missing_observation_slots") or []),
        "complete": regular_window_complete(item),
    }


def _reconcile_regular_windows(state: dict) -> None:
    """Repair A/B pointers from immutable regular results, never from test/Recovery."""
    for role in ("A", "B"):
        item = _latest_regular_result(role=role)
        if not item:
            continue
        state["last_a_window" if role == "A" else "last_b_window"] = _window_state_from_result(item)


def validate_feedback_handoff(
    current: dict,
    result: dict,
    warnings: list[str],
) -> dict:
    previous_role = _supervisor_role(current.get("supervisor"))
    current_role = _supervisor_role(result.get("supervisor"))
    previous_feedback = current.get("feedback_to_other_supervisor") or []
    if not isinstance(previous_feedback, list):
        previous_feedback = [previous_feedback] if previous_feedback else []
    received = result.get("feedback_received") or []
    outgoing = result.get("feedback_to_other_supervisor") or []

    inbound_required = bool(
        previous_role
        and current_role
        and previous_role != current_role
        and previous_feedback
    )
    inbound_recorded = bool(received)
    outgoing_recorded = bool(outgoing)

    if inbound_required and not inbound_recorded:
        warnings.append(
            "직전 상대 Supervisor의 feedback_to_other_supervisor가 있으나 "
            "feedback_received가 비어 있어 상호 피드백 연속성을 검증할 수 없음"
        )
        if str(result.get("status") or "") != "blocked":
            result["status"] = "verification_pending"

    if current_role and not outgoing_recorded:
        warnings.append(
            "다음 상대 Supervisor에 넘길 feedback_to_other_supervisor가 비어 있음"
        )
        if str(result.get("status") or "") != "blocked":
            result["status"] = "verification_pending"

    handoff = {
        "source_batch_id": current.get("batch_id") if inbound_required else None,
        "source_supervisor": previous_role if inbound_required else None,
        "target_supervisor": current_role,
        "inbound_required": inbound_required,
        "inbound_recorded": inbound_recorded,
        "outgoing_recorded": outgoing_recorded,
        "complete": (not inbound_required or inbound_recorded) and (
            not current_role or outgoing_recorded
        ),
    }
    result["feedback_handoff"] = handoff
    return handoff


def update_supervisor_disagreements(result: dict) -> None:
    incoming = result.get("supervisor_disagreements") or []
    if not isinstance(incoming, list) or not incoming:
        return
    store = _read_json_dict(DISAGREEMENTS)
    existing = {
        str(item.get("disagreement_id")): item
        for item in (store.get("items") or [])
        if isinstance(item, dict) and item.get("disagreement_id")
    }
    now = str(result.get("processed_at") or "")
    supervisor = str(result.get("supervisor") or "")
    batch_id = str(result.get("batch_id") or "")

    for raw in incoming:
        if not isinstance(raw, dict):
            continue
        disagreement_id = str(raw.get("disagreement_id") or "").strip()
        topic = str(raw.get("topic") or "").strip()
        if not disagreement_id or not topic:
            continue
        current = existing.get(disagreement_id, {"disagreement_id": disagreement_id, "history": []})
        previous_status = current.get("status")
        current.update(
            {
                "topic": topic,
                "a_position": raw.get("a_position", current.get("a_position")),
                "b_position": raw.get("b_position", current.get("b_position")),
                "status": raw.get("status") or current.get("status") or "open",
                "evidence_needed": raw.get("evidence_needed") or current.get("evidence_needed") or [],
                "verify_after": raw.get("verify_after") or current.get("verify_after"),
                "resolution": raw.get("resolution") or current.get("resolution"),
                "updated_at": now,
                "updated_by": supervisor,
                "last_batch_id": batch_id,
            }
        )
        if not current.get("first_seen"):
            current["first_seen"] = now
        history = current.setdefault("history", [])
        history.append(
            {
                "at": now,
                "by": supervisor,
                "batch_id": batch_id,
                "status_from": previous_status,
                "status_to": current.get("status"),
                "note": raw.get("note") or raw.get("resolution") or "",
            }
        )
        current["history"] = history[-30:]
        existing[disagreement_id] = current

    items = sorted(
        existing.values(),
        key=lambda item: str(item.get("updated_at") or ""),
        reverse=True,
    )[:100]
    DISAGREEMENTS.parent.mkdir(parents=True, exist_ok=True)
    DISAGREEMENTS.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": now,
                "open_count": sum(1 for item in items if item.get("status") not in {"resolved", "discarded"}),
                "items": items,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def update_issue_lifecycle(result: dict) -> None:
    """Persist explicit market issue state transitions without deleting history."""
    store = json.loads(ISSUES.read_text(encoding="utf-8")) if ISSUES.exists() else {"issues": []}
    issues = {str(x.get("issue_id")): x for x in store.get("issues", []) if x.get("issue_id")}
    now = str(result.get("processed_at") or "")
    for change in result.get("issue_lifecycle_updates") or []:
        issue_id = str(change.get("issue_id") or "").strip()
        title = str(change.get("title") or "").strip()
        status = str(change.get("status") or "WATCHING").upper()
        if not issue_id or not title:
            continue
        current = issues.get(issue_id)
        if current is None:
            current = {
                "issue_id": issue_id,
                "title": title,
                "first_seen": change.get("event_time") or now,
                "first_detected": now,
                "promoted_at": now if status in {"ACTIVE", "ESCALATING"} else None,
                "resolved_at": None,
                "history": [],
            }
            issues[issue_id] = current
        previous = current.get("status")
        current.update({
            "title": title,
            "status": status,
            "severity": change.get("severity", current.get("severity", "WATCH")),
            "direction": change.get("direction", current.get("direction", "neutral")),
            "last_seen": now,
            "event_time": change.get("event_time") or current.get("event_time"),
            "reason": change.get("reason") or current.get("reason"),
            "evidence": change.get("evidence") or current.get("evidence", []),
            "affected_assets": change.get("affected_assets") or current.get("affected_assets", []),
            "invalidation_conditions": change.get("invalidation_conditions") or current.get("invalidation_conditions", []),
        })
        if status in {"ACTIVE", "ESCALATING"} and not current.get("promoted_at"):
            current["promoted_at"] = now
        if status == "RESOLVED":
            current["resolved_at"] = change.get("resolved_at") or now
            current["resolution_reason"] = change.get("resolution_reason") or change.get("reason")
        elif previous == "RESOLVED" and status != "RESOLVED":
            current["resolved_at"] = None
            current["resolution_reason"] = None
        if previous != status or change.get("note"):
            current.setdefault("history", []).append({
                "at": now,
                "event_time": change.get("event_time"),
                "from": previous,
                "to": status,
                "note": change.get("note") or change.get("reason") or "",
            })
            current["history"] = current["history"][-100:]
    store["updated_at"] = now
    store["issues"] = sorted(
        issues.values(),
        key=lambda x: (x.get("status") == "RESOLVED", str(x.get("last_seen") or "")),
    )
    ISSUES.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_market_session_history(result: dict) -> None:
    updates = result.get("market_session_history") or {}
    if not isinstance(updates, dict):
        return
    store = json.loads(RECENT_SESSIONS.read_text(encoding="utf-8")) if RECENT_SESSIONS.exists() else {}
    changed = False
    for market in ("korea", "us"):
        rows = updates.get(market)
        if not isinstance(rows, list) or not rows:
            continue
        merged = {
            str(item.get("date")): item
            for item in store.get(market, [])
            if isinstance(item, dict) and item.get("date")
        }
        for item in rows:
            if isinstance(item, dict) and item.get("date"):
                merged[str(item["date"])] = item
                changed = True
        store[market] = sorted(merged.values(), key=lambda x: str(x.get("date") or ""), reverse=True)[:3]
    if changed:
        store["updated_at"] = str(result.get("processed_at") or "")
        RECENT_SESSIONS.parent.mkdir(parents=True, exist_ok=True)
        RECENT_SESSIONS.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_popular_reports(result: dict) -> None:
    payload = result.get("popular_reports")
    if not isinstance(payload, dict):
        return
    incoming = payload.get("items")
    if not isinstance(incoming, list) or not incoming:
        return

    store = json.loads(POPULAR_REPORTS.read_text(encoding="utf-8")) if POPULAR_REPORTS.exists() else {}
    existing = store.get("items") if isinstance(store.get("items"), list) else []

    def item_key(item: dict) -> str:
        return "|".join([
            str(item.get("report_date") or ""),
            str(item.get("broker") or ""),
            str(item.get("company") or ""),
            str(item.get("title") or ""),
        ])

    merged: dict[str, dict] = {}
    for item in existing + incoming:
        if not isinstance(item, dict):
            continue
        if not item.get("title") or not item.get("broker") or not item.get("report_date"):
            continue
        key = item_key(item)
        previous = merged.get(key, {})
        candidate = dict(previous)
        candidate.update(item)
        if previous:
            candidate["views"] = max(int(previous.get("views") or 0), int(item.get("views") or 0))
        analysis = candidate.get("analysis") if isinstance(candidate.get("analysis"), dict) else {}
        if analysis.get("status") == "ready_source_read":
            required_analysis = ("core", "evidence", "market_link", "countercheck", "source_url", "analyzed_at")
            if any(not analysis.get(field) for field in required_analysis):
                analysis = dict(analysis)
                analysis["status"] = "pending_source_read"
                candidate["analysis"] = analysis
        merged[key] = candidate

    items = sorted(
        merged.values(),
        key=lambda x: (
            str(x.get("report_date") or ""),
            int(x.get("views") or 0),
            str(x.get("title") or ""),
        ),
        reverse=True,
    )[:30]
    for index, item in enumerate(items, 1):
        item["display_order"] = index

    next_store = dict(store)
    next_store.update({k: v for k, v in payload.items() if k != "items"})
    next_store["items"] = items
    next_store["max_items"] = 30
    next_store["sort_mode"] = "report_date_desc_then_views_desc"
    next_store["updated_at"] = str(result.get("processed_at") or payload.get("updated_at") or "")
    POPULAR_REPORTS.parent.mkdir(parents=True, exist_ok=True)
    POPULAR_REPORTS.write_text(json.dumps(next_store, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def update_news_issue_digest(result: dict) -> None:
    payload = result.get("news_issue_digest")
    if not isinstance(payload, dict):
        return
    incoming = payload.get("issues")
    if not isinstance(incoming, list):
        return

    store = json.loads(NEWS_ISSUES.read_text(encoding="utf-8")) if NEWS_ISSUES.exists() else {"issues": []}
    existing = {
        str(item.get("issue_id")): item
        for item in store.get("issues", [])
        if isinstance(item, dict) and item.get("issue_id")
    }
    now = str(result.get("processed_at") or payload.get("updated_at") or "")

    for item in incoming:
        if not isinstance(item, dict):
            continue
        issue_id = str(item.get("issue_id") or "").strip()
        title = str(item.get("title") or "").strip()
        if not issue_id or not title:
            continue
        previous = existing.get(issue_id, {})
        merged = dict(previous)
        merged.update(item)

        # 같은 사건의 후속 기사/공식자료는 URL 기준으로 합치고 중복을 제거한다.
        source_map: dict[str, dict] = {}
        for source in list(previous.get("sources") or []) + list(item.get("sources") or []):
            if not isinstance(source, dict):
                continue
            key = str(source.get("url") or "").strip() or (
                str(source.get("publisher") or "") + "|" + str(source.get("title") or "")
            )
            if key:
                source_map[key] = source
        if source_map:
            merged["sources"] = list(source_map.values())[-60:]
            merged["source_count"] = len({
                str(source.get("publisher") or source.get("url") or "")
                for source in merged["sources"]
                if source.get("publisher") or source.get("url")
            })
            if not item.get("article_count"):
                merged["article_count"] = max(
                    int(previous.get("article_count") or 0),
                    len(merged["sources"]),
                )
        if not merged.get("first_detected"):
            merged["first_detected"] = now
        merged["last_updated"] = now
        history = list(previous.get("history") or [])
        before = str(previous.get("status") or "")
        after = str(merged.get("status") or "")
        if not previous:
            merged["status_changed_at"] = now
            history.append({"at": now, "from": None, "to": after or "WATCHING", "note": "first_detected"})
        elif before != after:
            merged["status_changed_at"] = now
            history.append({"at": now, "from": before, "to": after, "note": str(item.get("change_reason") or "")})
        else:
            changed_update = (
                str(item.get("latest_update") or "").strip()
                and str(item.get("latest_update") or "").strip() != str(previous.get("latest_update") or "").strip()
            ) or (
                str(item.get("summary") or "").strip()
                and str(item.get("summary") or "").strip() != str(previous.get("summary") or "").strip()
            )
            if changed_update:
                history.append({
                    "at": now,
                    "from": before or after or "WATCHING",
                    "to": after or before or "WATCHING",
                    "note": "추가 소식 · " + str(item.get("latest_update") or item.get("change_reason") or "내용 갱신"),
                })
            if not merged.get("status_changed_at"):
                merged["status_changed_at"] = previous.get("last_updated") or previous.get("first_detected") or now

        reference = merged.get("event_time") or merged.get("first_detected") or now
        try:
            ref_dt = datetime.fromisoformat(str(reference).replace("Z", "+00:00"))
            now_dt_for_age = datetime.fromisoformat(str(now).replace("Z", "+00:00"))
            if ref_dt.tzinfo is None:
                ref_dt = ref_dt.replace(tzinfo=now_dt_for_age.tzinfo)
            if now_dt_for_age.tzinfo is None:
                now_dt_for_age = now_dt_for_age.replace(tzinfo=ref_dt.tzinfo)
            merged["age_hours"] = round(max(0.0, (now_dt_for_age - ref_dt).total_seconds() / 3600.0), 1)
        except (TypeError, ValueError):
            merged["age_hours"] = None

        merged["history"] = history[-120:]
        existing[issue_id] = merged

    def parse_time(value: object) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return parsed

    now_dt = parse_time(now) or datetime.now().astimezone()
    cutoff = now_dt - timedelta(days=7)

    def keep_issue(item: dict) -> bool:
        status = str(item.get("status") or "").upper()
        if status != "RESOLVED":
            return True
        reference = (
            parse_time(item.get("last_updated"))
            or parse_time(item.get("resolved_at"))
            or parse_time(item.get("event_time"))
            or parse_time(item.get("first_detected"))
        )
        return bool(reference and reference >= cutoff)

    def issue_rank(item: dict) -> tuple:
        status_rank = {"ESCALATING": 0, "NEW": 1, "ACTIVE": 2, "WATCHING": 3, "EASING": 4, "RESOLVED": 5}
        severity_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        updated = (
            parse_time(item.get("last_updated"))
            or parse_time(item.get("event_time"))
            or parse_time(item.get("first_detected"))
        )
        updated_score = -updated.timestamp() if updated else 0
        return (
            status_rank.get(str(item.get("status") or "").upper(), 9),
            severity_rank.get(str(item.get("severity") or "").upper(), 9),
            updated_score,
        )

    items = sorted((x for x in existing.values() if keep_issue(x)), key=issue_rank)
    store.update({k: v for k, v in payload.items() if k != "issues"})
    store["updated_at"] = now
    store["issues"] = items[:100]
    store["max_issues"] = 100
    store["retention_days"] = 7
    store["retention_rule"] = "active/easing issues persist; resolved issues remain visible for at least 7 days"
    NEWS_ISSUES.parent.mkdir(parents=True, exist_ok=True)
    NEWS_ISSUES.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _collaboration_incident_id(raw: dict) -> str:
    raw_id = str(raw.get("id") or raw.get("incident_id") or raw.get("disagreement_id") or "").strip()
    key = raw_id.lower().replace("_", "-")
    topic = str(raw.get("topic") or raw.get("type") or "").lower().replace("_", "-")
    combined = f"{key} {topic}"
    if "issue-digest" in combined or "news-issue-digest" in combined:
        return "issue-digest-apply"
    if "macro-runtime" in combined or ("macro" in combined and ("empty" in combined or "data" in combined)):
        return "macro-runtime-data"
    if "sensor" in combined and any(token in combined for token in ("slot", "continuity", "heartbeat", "self-chain", "chain")):
        return "sensor-continuity"
    return raw_id


def _collaboration_incident_title(incident_id: str, raw: dict) -> str:
    explicit = str(raw.get("title") or "").strip()
    if explicit:
        return explicit
    known = {
        "sensor-continuity": "센서 연속성 장애",
        "issue-digest-apply": "이슈 원장 갱신 지연",
        "macro-runtime-data": "거시 데이터 실값 공백",
    }
    if incident_id in known:
        return known[incident_id]
    summary = str(
        raw.get("signal")
        or raw.get("finding")
        or raw.get("topic")
        or raw.get("detail")
        or ""
    ).strip()
    if summary:
        return summary.split("·", 1)[0][:72]
    return incident_id or "협업 확인 항목"


def _collaboration_status(value: object) -> str:
    raw = str(value or "investigating").strip().lower().replace("-", "_")
    if raw in {"resolved", "done", "completed", "fixed", "closed"}:
        return "resolved"
    if raw in {"open", "active", "tracking"}:
        return "investigating"
    if raw in {"verification_pending", "investigating", "blocked", "degraded", "stale"}:
        return raw
    return raw or "investigating"


def update_collaboration_state(result: dict, src: Path) -> None:
    """Merge A/B work into one shared incident state without inventing evidence."""
    store = _read_json_dict(COLLABORATION)
    existing_items = store.get("incidents") or []
    if not isinstance(existing_items, list):
        existing_items = []
    incidents = {
        str(item.get("incident_id")): item
        for item in existing_items
        if isinstance(item, dict) and item.get("incident_id")
    }

    now = str(result.get("processed_at") or "")
    batch_id = str(result.get("batch_id") or "")
    supervisor = str(result.get("supervisor") or "").upper()
    try:
        source_file = str(src.relative_to(ROOT))
    except ValueError:
        source_file = str(src)

    def upsert(raw: dict, *, source_kind: str) -> None:
        incident_id = _collaboration_incident_id(raw)
        if not incident_id:
            return
        status = _collaboration_status(raw.get("status"))
        summary = str(
            raw.get("signal")
            or raw.get("finding")
            or raw.get("detail")
            or raw.get("resolution")
            or raw.get("topic")
            or ""
        ).strip()
        evidence_raw = raw.get("evidence") or raw.get("evidence_needed") or []
        if isinstance(evidence_raw, str):
            evidence = [evidence_raw]
        elif isinstance(evidence_raw, list):
            evidence = [str(x) for x in evidence_raw if str(x).strip()]
        else:
            evidence = []

        current = incidents.get(incident_id, {"incident_id": incident_id, "history": []})
        current["title"] = _collaboration_incident_title(incident_id, raw)
        current["status"] = status
        current["summary"] = summary
        current["owner"] = supervisor or current.get("owner")
        current["verify_after"] = raw.get("verify_after") or current.get("verify_after")
        current["evidence"] = evidence or current.get("evidence") or []
        current["source_kind"] = source_kind
        current["source_batch_id"] = batch_id
        current["source_file"] = source_file
        current["updated_at"] = now
        if not current.get("first_seen"):
            current["first_seen"] = now

        history = current.get("history") or []
        if not isinstance(history, list):
            history = []
        if not any(
            isinstance(item, dict) and str(item.get("batch_id") or "") == batch_id
            for item in history
        ):
            history.append(
                {
                    "at": now,
                    "by": supervisor,
                    "batch_id": batch_id,
                    "status": status,
                    "summary": summary,
                }
            )
        current["history"] = history[-40:]
        incidents[incident_id] = current

    for raw in result.get("project_improvement_signals") or []:
        if isinstance(raw, dict):
            upsert(raw, source_kind="project_improvement_signal")
    for raw in result.get("supervisor_disagreements") or []:
        if isinstance(raw, dict):
            upsert(raw, source_kind="supervisor_disagreement")

    resolved_statuses = {"resolved", "discarded", "closed", "completed"}
    ordered = sorted(
        incidents.values(),
        key=lambda item: (
            str(item.get("status") or "").lower() in resolved_statuses,
            str(item.get("updated_at") or ""),
        ),
        reverse=False,
    )
    # active first, and newest first inside each group
    ordered = sorted(
        ordered,
        key=lambda item: (
            str(item.get("status") or "").lower() in resolved_statuses,
            -_parse_result_time(item.get("updated_at") or now).timestamp() if (item.get("updated_at") or now) else 0,
        ),
    )[:100]

    active = [
        item for item in ordered
        if str(item.get("status") or "").lower() not in resolved_statuses
    ]
    resolved = [
        item for item in ordered
        if str(item.get("status") or "").lower() in resolved_statuses
    ]

    changed_paths = [
        str(x) for x in (result.get("changed_paths") or []) if str(x).strip()
    ]
    result_only = bool(changed_paths) and all(
        path.startswith("data/supervisor/ai-results/")
        for path in changed_paths
    )
    last_turn = {
        "batch_id": batch_id,
        "processed_at": now,
        "supervisor": supervisor,
        "status": result.get("status"),
        "summary": result.get("summary"),
        "feedback_received": result.get("feedback_received") or [],
        "feedback_resolved": result.get("feedback_resolved") or [],
        "feedback_disagreed": result.get("feedback_disagreed") or [],
        "feedback_deferred": result.get("feedback_deferred") or [],
        "feedback_to_other_supervisor": result.get("feedback_to_other_supervisor") or [],
        "changed_paths": changed_paths,
        "change_kind": "result_only" if result_only else ("project_change" if changed_paths else "no_change"),
        "next_checks": result.get("next_checks") or [],
        "source_file": source_file,
    }

    timeline = store.get("timeline") or []
    if not isinstance(timeline, list):
        timeline = []
    timeline = [
        item for item in timeline
        if not (isinstance(item, dict) and str(item.get("batch_id") or "") == batch_id)
    ]
    timeline.append(last_turn)
    timeline.sort(key=lambda item: str(item.get("processed_at") or ""), reverse=True)

    if active:
        headline = f"A와 B가 {active[0].get('title') or '운영 문제'}를 공동 추적 중입니다."
        if resolved:
            headline += f" 최근 해결: {resolved[0].get('title')}."
    else:
        headline = "현재 열린 협업 incident가 없습니다. A와 B가 다음 관측과 개선 후보를 교차검증 중입니다."

    active_statuses = {str(item.get("status") or "").lower() for item in active}
    if "blocked" in active_statuses:
        overall_status = "blocked"
    elif "investigating" in active_statuses or "degraded" in active_statuses or "stale" in active_statuses:
        overall_status = "investigating"
    elif active:
        overall_status = "verification_pending"
    else:
        overall_status = "healthy"

    store = {
        "schema_version": 1,
        "updated_at": now,
        "status": overall_status,
        "headline": headline,
        "active_incident_count": len(active),
        "resolved_incident_count": len(resolved),
        "incidents": ordered,
        "last_turn": last_turn,
        "timeline": timeline[:80],
    }
    COLLABORATION.parent.mkdir(parents=True, exist_ok=True)
    COLLABORATION.write_text(
        json.dumps(store, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/supervisor_result_apply.py <result.json>")
    src = Path(sys.argv[1])
    result = json.loads(src.read_text(encoding="utf-8"))

    # 입력 파일과 실제 적용 batch를 몰래 바꾸지 않는다.
    # push 단계가 정확한 immutable result를 선택하고 apply는 그 batch만 검증·적용한다.
    # canonical보다 오래된 결과는 뒤로 되감지 않으며, 동일 batch 재적용만 idempotent하게 허용한다.
    current = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {}
    current_at = str(current.get("processed_at") or "")
    current_batch = str(current.get("batch_id") or "")
    result_at = str(result.get("processed_at") or "")
    result_batch = str(result.get("batch_id") or "")
    if current_at and result_at < current_at:
        raise SystemExit(
            f"stale Supervisor result refused: {result_batch} ({result_at}) < "
            f"{current_batch} ({current_at})"
        )
    if current_at and result_at == current_at and current_batch and result_batch != current_batch:
        raise SystemExit(
            f"same-time Supervisor result conflicts with canonical: "
            f"{result_batch} != {current_batch}"
        )

    required = ("batch_id", "processed_at", "notify", "summary")
    missing = [k for k in required if k not in result]
    if missing:
        raise SystemExit("missing fields: " + ", ".join(missing))
    if result.get("notify") is not True:
        raise SystemExit("Supervisor result must have notify=true")

    # 보조 필드 하나가 빠졌다는 이유로 canonical 적용과 Telegram 전체를 중단하지 않는다.
    # 핵심 식별/시간/알림/요약은 엄격히 검증하되, 실행 메타데이터는 안전한 기본값으로 복구한다.
    warnings = list(result.get("validation_warnings") or [])
    if not isinstance(result.get("actions"), list):
        result["actions"] = []
        warnings.append("actions 누락/형식오류를 빈 목록으로 복구")
    if not isinstance(result.get("next_checks"), list):
        result["next_checks"] = []
        warnings.append("next_checks 누락/형식오류를 빈 목록으로 복구")
    if not isinstance(result.get("work_axes_reviewed"), list):
        result["work_axes_reviewed"] = []
        warnings.append("work_axes_reviewed 누락/형식오류를 빈 목록으로 복구")
    if len(result.get("work_axes_reviewed") or []) < 5:
        warnings.append("work_axes_reviewed가 운영헌장 기준 5개 미만 - 다음 Supervisor가 보완")
    if not isinstance(result.get("feedback_to_other_supervisor"), list):
        value = result.get("feedback_to_other_supervisor")
        result["feedback_to_other_supervisor"] = [value] if value else []
    for key in (
        "feedback_received",
        "feedback_resolved",
        "feedback_disagreed",
        "feedback_deferred",
    ):
        if not isinstance(result.get(key), list):
            result[key] = []
    if not isinstance(result.get("supervisor_disagreements"), list):
        result["supervisor_disagreements"] = []
    if not isinstance(result.get("changed_paths"), list) or not result.get("changed_paths"):
        try:
            source_path = str(src.relative_to(ROOT))
        except ValueError:
            source_path = str(src)
        result["changed_paths"] = [source_path]
        warnings.append("changed_paths 누락을 현재 Supervisor 결과 경로로 복구")
    # 과거 정규 결과는 window 메타가 비어 있고 apply 단계에서 복구되는 경우가 있다.
    # 먼저 정규 3슬롯을 정규화한 뒤 run_kind를 판정한다.
    window_manifest = normalize_observation_window(result, warnings)
    run_kind = infer_run_kind(result)
    result["run_kind"] = run_kind
    if run_kind == "unknown":
        warnings.append("Supervisor result run_kind를 정규/test/recovery로 확정하지 못함")

    previous_regular = (
        _latest_regular_result(
            before_at=str(result.get("processed_at") or ""),
            exclude_batch_id=str(result.get("batch_id") or ""),
        )
        if run_kind == "regular"
        else {}
    )
    if run_kind == "regular":
        feedback_handoff = validate_feedback_handoff(previous_regular, result, warnings)
    else:
        feedback_handoff = {
            "source_batch_id": None,
            "source_supervisor": None,
            "target_supervisor": _supervisor_role(result.get("supervisor")),
            "inbound_required": False,
            "inbound_recorded": bool(result.get("feedback_received")),
            "outgoing_recorded": bool(result.get("feedback_to_other_supervisor")),
            "complete": True,
            "run_kind": run_kind,
        }
        result["feedback_handoff"] = feedback_handoff

    # discovery가 실제 새 기사 입력을 확보했는데 정규 A/B가 issue lifecycle
    # payload를 생략하면 digest가 조용히 멈춘다. timestamp를 조작하지 않고
    # 해당 Supervisor 결과 자체를 미완료로 표시해 다음 사이클이 원인을 이어받게 한다.
    discovery = _read_json_dict(DISCOVERY)
    discovery_has_new_news = (
        int(discovery.get("item_count") or 0) > 0
        and int(discovery.get("new_item_count") or 0) > 0
        and int((discovery.get("source_summary") or {}).get("ok_or_partial") or 0) > 0
    )
    is_regular_result = is_regular_supervisor_result(result)
    if discovery_has_new_news and is_regular_result and not isinstance(result.get("news_issue_digest"), dict):
        warnings.append(
            "최신 discovery에 새 뉴스가 있으나 news_issue_digest가 없어 뉴스 lifecycle 적용이 누락됨"
        )
        if str(result.get("status") or "") != "blocked":
            result["status"] = "verification_pending"
    if warnings:
        result["validation_warnings"] = warnings
    observation_ids = list(result.get("observation_ids") or [])

    # 테스트/E2E는 writer·Telegram 경로를 검증할 수 있지만 시장 canonical,
    # A/B 피드백, 이슈 원장과 정규 생존 상태를 오염시키면 안 된다.
    if run_kind == "test":
        warnings.append("test/E2E 결과는 정규 canonical과 A/B 실행 이력을 전진시키지 않음")
        result["validation_warnings"] = warnings
        TEST_REPORT.parent.mkdir(parents=True, exist_ok=True)
        TEST_REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        src.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("applied test", result["batch_id"])
        return 0

    update_supervisor_disagreements(result)
    update_issue_lifecycle(result)
    update_market_session_history(result)
    update_popular_reports(result)
    update_news_issue_digest(result)
    update_collaboration_state(result, src)
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    src.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    state = _read_json_dict(STATE)
    state["schema_version"] = max(int(state.get("schema_version") or 1), 2)
    state["batch_size"] = 3
    state["sensor_interval_minutes"] = 10
    state.setdefault("last_processed_slot", None)
    state.setdefault("processed_observation_ids_recent", [])
    state.setdefault("last_a_window", None)
    state.setdefault("last_b_window", None)
    state["last_batch_id"] = result["batch_id"]
    state["last_processed_at"] = result["processed_at"]
    processed_recent = [
        str(x)
        for x in (state.get("processed_observation_ids_recent") or [])
        if str(x).strip()
    ]
    if result.get("observation_window_complete"):
        for item_id in observation_ids:
            if item_id not in processed_recent:
                processed_recent.append(item_id)
    state["processed_observation_ids_recent"] = processed_recent[-120:]

    role = _supervisor_role(result.get("supervisor"))
    is_regular_supervisor = is_regular_supervisor_result(result)
    if is_regular_supervisor:
        state["last_feedback_handoff"] = {
            "batch_id": result["batch_id"],
            **feedback_handoff,
        }
    elif run_kind == "recovery":
        state["last_recovery_batch"] = {
            "batch_id": result["batch_id"],
            "processed_at": result.get("processed_at"),
        }
    # 과거 test/Recovery 오염이 남아 있어도 immutable 정규 결과를 기준으로
    # A/B window 포인터를 다시 계산한다. Recovery 자체가 포인터를 전진시키는 것은 아니다.
    _reconcile_regular_windows(state)
    if is_regular_supervisor:
        state["last_a_window" if role == "A" else "last_b_window"] = _window_state_from_result(result)
    else:
        warnings.append(f"{run_kind} 결과는 정규 A/B window 포인터를 전진시키지 않음")
        result["validation_warnings"] = warnings
        REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if observation_ids and result.get("observation_window_complete"):
        state["last_processed_observation_id"] = observation_ids[-1]
        slots = result.get("observation_slots") or []
        state["last_processed_slot"] = slots[-1] if slots else result.get("observation_window_end")
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("applied", result["batch_id"])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
