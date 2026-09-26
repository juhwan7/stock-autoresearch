from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "data/supervisor/latest-report.json"
STATE = ROOT / "data/supervisor/state.json"
ISSUES = ROOT / "data/supervisor/market-issues.json"
RECENT_SESSIONS = ROOT / "data/market/recent-sessions.json"
POPULAR_REPORTS = ROOT / "data/research/popular-reports.json"
NEWS_ISSUES = ROOT / "data/news/issue-digest.json"

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


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/supervisor_result_apply.py <result.json>")
    src = Path(sys.argv[1])
    result = json.loads(src.read_text(encoding="utf-8"))

    # The workflow historically selected by filesystem mtime. Checkout mtimes are
    # not a reliable ordering signal, so an older result could be applied again.
    # If that happens, recover by choosing the newest valid immutable result by
    # its explicit processed_at timestamp. Never let canonical state move backward.
    current = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {}
    current_at = str(current.get("processed_at") or "")
    if str(result.get("processed_at") or "") <= current_at:
        candidates = []
        for path in (ROOT / "data/supervisor/ai-results").glob("*.json"):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if item.get("notify") is True and str(item.get("processed_at") or "") > current_at:
                candidates.append((str(item.get("processed_at")), path, item))
        if candidates:
            _, src, result = max(candidates, key=lambda row: row[0])
        else:
            raise SystemExit("no newer Supervisor result to apply")

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
    if not isinstance(result.get("changed_paths"), list) or not result.get("changed_paths"):
        try:
            source_path = str(src.relative_to(ROOT))
        except ValueError:
            source_path = str(src)
        result["changed_paths"] = [source_path]
        warnings.append("changed_paths 누락을 현재 Supervisor 결과 경로로 복구")
    if warnings:
        result["validation_warnings"] = warnings
    observation_ids = result.get("observation_ids") or []
    update_issue_lifecycle(result)
    update_market_session_history(result)
    update_popular_reports(result)
    update_news_issue_digest(result)
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["last_batch_id"] = result["batch_id"]
    state["last_processed_at"] = result["processed_at"]
    if observation_ids:
        state["last_processed_observation_id"] = observation_ids[-1]
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("applied", result["batch_id"])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
