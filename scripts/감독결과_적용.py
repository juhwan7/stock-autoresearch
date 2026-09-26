from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "data/supervisor/latest-report.json"
STATE = ROOT / "data/supervisor/state.json"
ISSUES = ROOT / "data/supervisor/market-issues.json"
RECENT_SESSIONS = ROOT / "data/market/recent-sessions.json"

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

    required = ("batch_id", "processed_at", "notify", "summary", "actions", "changed_paths", "next_checks")
    missing = [k for k in required if k not in result]
    if missing:
        raise SystemExit("missing fields: " + ", ".join(missing))
    if result.get("notify") is not True:
        raise SystemExit("Supervisor result must have notify=true")
    observation_ids = result.get("observation_ids") or []
    update_issue_lifecycle(result)
    update_market_session_history(result)
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
