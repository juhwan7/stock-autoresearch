from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from .hypothesis_learning import due_hypotheses


KST = timezone(timedelta(hours=9))
BATCH_SIZE = 3
RECENT_LIMIT = 120
SENSOR_INTERVAL_MINUTES = 10
SUPERVISOR_WINDOW_SIZE = 3


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")


def sensor_slot_start(value: datetime) -> datetime:
    """Return the canonical 10-minute KST slot for an observation."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=KST)
    value = value.astimezone(KST)
    minute = (value.minute // SENSOR_INTERVAL_MINUTES) * SENSOR_INTERVAL_MINUTES
    return value.replace(minute=minute, second=0, microsecond=0)


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


def _observation_slot(item: Mapping[str, Any]) -> datetime | None:
    explicit = _parse_datetime(item.get("slot_at"))
    if explicit is not None:
        return sensor_slot_start(explicit)
    observed = _parse_datetime(item.get("observed_at"))
    return sensor_slot_start(observed) if observed is not None else None


def _supervisor_anchor(processed_at: datetime, supervisor: str) -> datetime:
    if processed_at.tzinfo is None:
        processed_at = processed_at.replace(tzinfo=KST)
    processed_at = processed_at.astimezone(KST)
    role = "B" if "B" in supervisor.upper() else "A"
    if role == "A":
        return processed_at.replace(minute=0, second=0, microsecond=0)
    if processed_at.minute >= 30:
        return processed_at.replace(minute=30, second=0, microsecond=0)
    previous_hour = processed_at - timedelta(hours=1)
    return previous_hour.replace(minute=30, second=0, microsecond=0)


def expected_supervisor_slots(
    processed_at: datetime,
    supervisor: str,
) -> list[datetime]:
    anchor = _supervisor_anchor(processed_at, supervisor)
    return [
        anchor - timedelta(minutes=SENSOR_INTERVAL_MINUTES * offset)
        for offset in range(SUPERVISOR_WINDOW_SIZE - 1, -1, -1)
    ]


def _observation_quality(item: Mapping[str, Any]) -> tuple[int, datetime]:
    validation = str((item.get("validation") or {}).get("status") or "")
    steps = item.get("steps") or {}
    successful_steps = sum(1 for value in steps.values() if value == "success")
    observed = _parse_datetime(item.get("observed_at")) or datetime.min.replace(tzinfo=KST)
    return ((100 if validation == "ok" else 0) + successful_steps, observed)


def build_supervisor_window(
    observations: list[dict[str, Any]],
    *,
    processed_at: datetime,
    supervisor: str,
) -> dict[str, Any]:
    expected = expected_supervisor_slots(processed_at, supervisor)
    expected_keys = {slot.isoformat(): slot for slot in expected}
    canonical: dict[str, dict[str, Any]] = {}

    for item in observations:
        if not isinstance(item, dict):
            continue
        slot = _observation_slot(item)
        if slot is None:
            continue
        key = slot.isoformat()
        if key not in expected_keys:
            continue
        current = canonical.get(key)
        if current is None or _observation_quality(item) > _observation_quality(current):
            canonical[key] = item

    ordered = [canonical.get(slot.isoformat()) for slot in expected]
    received = [item for item in ordered if item is not None]
    missing = [
        slot.isoformat()
        for slot, item in zip(expected, ordered)
        if item is None
    ]
    anchor = expected[-1]
    return {
        "schema_version": 1,
        "supervisor": "B" if "B" in supervisor.upper() else "A",
        "anchor_at": anchor.isoformat(),
        "window_start": expected[0].isoformat(),
        "window_end": anchor.isoformat(),
        "expected_observation_count": SUPERVISOR_WINDOW_SIZE,
        "received_observation_count": len(received),
        "completeness_ratio": round(len(received) / SUPERVISOR_WINDOW_SIZE, 3),
        "complete": len(received) == SUPERVISOR_WINDOW_SIZE,
        "expected_slots": [slot.isoformat() for slot in expected],
        "observation_slots": [
            slot.isoformat()
            for slot, item in zip(expected, ordered)
            if item is not None
        ],
        "observation_ids": [
            str(item.get("observation_id"))
            for item in received
            if item.get("observation_id")
        ],
        "missing_slots": missing,
    }


def _write_window_manifest(
    root: Path,
    observations: list[dict[str, Any]],
    slot: datetime,
) -> dict[str, Any] | None:
    if slot.minute not in {0, 30}:
        return None
    role = "A" if slot.minute == 0 else "B"
    manifest = build_supervisor_window(
        observations,
        processed_at=slot,
        supervisor=role,
    )
    folder = root / "data" / "supervisor" / "windows"
    dated = folder / slot.strftime("%Y-%m-%d")
    _write_json(folder / f"latest-{role}.json", manifest)
    _write_json(dated / (slot.strftime("%H%M") + f"-{role}.json"), manifest)
    return manifest


def _latest_changed_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "show", "--pretty=", "--name-only", "HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()][:30]


def _pending_feedback(root: Path) -> tuple[int, str | None]:
    rows = _read_jsonl(root / "data" / "feedback" / "사용자_피드백.jsonl")
    pending = [
        row
        for row in rows
        if str(row.get("status") or "").startswith("pending")
    ]
    latest_comment_id: str | None = None
    if pending:
        latest_comment_id = str(pending[-1].get("comment_id") or "") or None
    return len(pending), latest_comment_id


def _pending_after(
    observations: list[dict[str, Any]],
    last_processed_id: str | None,
) -> int:
    if not last_processed_id:
        return len(observations)
    for index, item in enumerate(observations):
        if item.get("observation_id") == last_processed_id:
            return len(observations) - index - 1
    return len(observations)


def _recent_workflow_run(env: Mapping[str, str]) -> dict[str, Any]:
    token = str(env.get("GITHUB_TOKEN") or "").strip()
    repo = str(env.get("GITHUB_REPOSITORY") or "").strip()
    if not token or not repo:
        return {}

    branch = str(env.get("GITHUB_REF_NAME") or "main")
    query = urllib.parse.urlencode({"branch": branch, "per_page": 10})
    request = urllib.request.Request(
        "https://api.github.com/repos/" + repo + "/actions/runs?" + query,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
    ):
        return {}

    current_run_id = str(env.get("GITHUB_RUN_ID") or "")
    for run in payload.get("workflow_runs", []):
        if str(run.get("id") or "") == current_run_id:
            continue
        return {
            "id": run.get("id"),
            "name": run.get("name"),
            "event": run.get("event"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "created_at": run.get("created_at"),
            "updated_at": run.get("updated_at"),
            "html_url": run.get("html_url"),
            "head_sha": run.get("head_sha"),
        }
    return {}


def build_observation(
    root: Path,
    *,
    now: datetime | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    env = env or os.environ
    now = now or datetime.now(KST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=KST)
    now = now.astimezone(KST)

    supervisor_dir = root / "data" / "supervisor"
    recent = _read_json(supervisor_dir / "recent.json").get("observations", [])
    if not isinstance(recent, list):
        recent = []
    state = _read_json(supervisor_dir / "state.json")
    last_processed_id = state.get("last_processed_observation_id")

    health = _read_json(root / "data" / "health" / "latest.json")
    regression = _read_json(root / "data" / "regression" / "latest.json")
    market = _read_json(root / "data" / "market" / "runtime.json")
    recent_sessions = _read_json(root / "data" / "market" / "recent-sessions.json")
    discovery = _read_json(root / "data" / "discovery" / "latest.json")
    public_batch = _read_json(
        root / "data" / "providers" / "naver_batch" / "latest.json"
    )
    toss = _read_json(root / "data" / "providers" / "toss" / "status.json")
    if not toss:
        toss = _read_json(root / "data" / "providers" / "toss" / "latest.json")

    feedback_count, latest_feedback_comment_id = _pending_feedback(root)
    validation_status = str(env.get("VALIDATION_STATUS") or "unknown")
    run_id = str(env.get("GITHUB_RUN_ID") or "")
    run_attempt = str(env.get("GITHUB_RUN_ATTEMPT") or "1")
    head_sha = str(env.get("GITHUB_SHA") or "")
    suffix = (run_id + "-" + run_attempt) if run_id else (head_sha[:10] or "local")
    slot_at = sensor_slot_start(now)
    observation_id = now.strftime("obs-%Y%m%dT%H%M%S%z-") + suffix

    health_issues = []
    for item in health.get("issues", [])[:12]:
        if not isinstance(item, dict):
            continue
        health_issues.append(
            {
                "component": item.get("component"),
                "code": item.get("code"),
                "severity": item.get("severity"),
                "message": item.get("message"),
            }
        )

    signals: list[str] = []
    health_status = str(health.get("status") or "MISSING")
    if health_status in {"WARN", "CRITICAL"}:
        signals.append("health:" + health_status)
    regression_status = str(regression.get("status") or "MISSING")
    if regression_status in {"QUARANTINED", "ROLLED_BACK"}:
        signals.append("regression:" + regression_status)
    if validation_status != "ok":
        signals.append("validation:" + validation_status)
    if feedback_count:
        signals.append("user_feedback:" + str(feedback_count))

    discovery_sources = discovery.get("source_summary", {}) if isinstance(discovery, dict) else {}
    if discovery and not int(discovery_sources.get("ok_or_partial") or 0):
        signals.append("discovery:unavailable")
    if int(discovery_sources.get("degraded") or 0):
        signals.append("discovery:degraded")

    market_source_status = str(market.get("source_status") or "")
    has_recent_sessions = bool(
        isinstance(recent_sessions.get("korea"), list)
        and recent_sessions.get("korea")
    )
    normal_historical_fallback = (
        market_source_status in {
            "outside_domestic_monitor_window",
            "outside_regular_session",
        }
        and has_recent_sessions
    )
    if (
        market_source_status
        and market_source_status not in {"ok", "idle"}
        and not normal_historical_fallback
    ):
        signals.append("market:" + market_source_status)

    previous_run = _recent_workflow_run(env)
    if previous_run.get("conclusion") in {"failure", "cancelled", "timed_out"}:
        signals.append("previous_workflow:" + str(previous_run.get("conclusion")))

    pending_before = _pending_after(recent, str(last_processed_id) if last_processed_id else None)

    return {
        "schema_version": 2,
        "observation_id": observation_id,
        "observed_at": now.isoformat(),
        "slot_at": slot_at.isoformat(),
        "slot_key": slot_at.strftime("%Y-%m-%dT%H:%M%z"),
        "sensor_interval_minutes": SENSOR_INTERVAL_MINUTES,
        "slot_delay_seconds": max(0.0, (now - slot_at).total_seconds()),
        "source": {
            "repository": env.get("GITHUB_REPOSITORY"),
            "workflow": env.get("GITHUB_WORKFLOW"),
            "run_id": run_id or None,
            "run_attempt": run_attempt,
            "head_sha": head_sha or None,
            "ref_name": env.get("GITHUB_REF_NAME"),
        },
        "queue": {
            "batch_size": BATCH_SIZE,
            "pending_before_append": pending_before,
            "last_processed_observation_id": last_processed_id,
        },
        "validation": {
            "status": validation_status,
            "compile": env.get("COMPILE_STATUS"),
            "pytest": env.get("PYTEST_STATUS"),
            "diff_check": env.get("DIFF_STATUS"),
        },
        "steps": {
            "toss_fetch": env.get("TOSS_FETCH_STATUS"),
            "toss_summary": env.get("TOSS_SUMMARY_STATUS"),
            "health": env.get("HEALTH_STEP_STATUS"),
            "dashboard": env.get("DASHBOARD_STEP_STATUS"),
            "market_discovery": env.get("DISCOVERY_STEP_STATUS"),
            "public_batch_market": env.get("PUBLIC_BATCH_STATUS"),
            "market_sensor_repair": env.get("MARKET_SENSOR_STATUS"),
            "risk_sensor_repair": env.get("RISK_SENSOR_STATUS"),
            "regression_refresh": env.get("REGRESSION_STEP_STATUS"),
        },
        "health": {
            "status": health_status,
            "generated_at": health.get("generated_at"),
            "issues": health_issues,
        },
        "regression": {
            "status": regression_status,
            "generated_at": regression.get("generated_at"),
            "quarantine_count": regression.get("quarantine_count"),
            "rolled_back_count": regression.get("rolled_back_count"),
        },
        "market_discovery": {
            "generated_at": discovery.get("generated_at"),
            "item_count": discovery.get("item_count"),
            "new_item_count": discovery.get("new_item_count"),
            "topic_counts": discovery.get("topic_counts"),
            "trending_terms": discovery.get("trending_terms"),
            "new_dart_filings": discovery.get("new_dart_filings"),
            "official_web_candidates": discovery.get("official_web_candidates"),
            "toss_market": discovery.get("toss_market"),
            "sector_selection": discovery.get("sector_selection"),
            "naver_indices": discovery.get("naver_indices"),
            "source_summary": discovery.get("source_summary"),
            "top_new_items": (discovery.get("new_items") or [])[:10],
            "handoff_queries": discovery.get("handoff_queries"),
        },
        "public_batch_market": {
            "generated_at": public_batch.get("generated_at"),
            "status": public_batch.get("status"),
            "provider": public_batch.get("provider"),
            "exact_1m_bars": public_batch.get("exact_1m_bars"),
            "elapsed_minutes_from_previous": public_batch.get(
                "elapsed_minutes_from_previous"
            ),
            "interval_leaders": (public_batch.get("interval_leaders") or [])[:20],
            "one_minute_samples_available": public_batch.get("one_minute_samples_available"),
            "minute_amount_exact": public_batch.get("minute_amount_exact"),
            "minute_amount_method": public_batch.get("minute_amount_method"),
            "minute_sample_ticker_count": public_batch.get("minute_sample_ticker_count"),
            "current_top50_count": public_batch.get("current_top50_count"),
            "tracked_universe_count": public_batch.get("tracked_universe_count"),
            "dropped_from_current_top50_count": public_batch.get("dropped_from_current_top50_count"),
            "tracked_outside_top50_with_samples": public_batch.get("tracked_outside_top50_with_samples"),
            "minute_samples_by_ticker": {
                str(ticker): rows[-6:]
                for ticker, rows in (public_batch.get("minute_samples_by_ticker") or {}).items()
                if isinstance(rows, list)
            },
            "limitations": public_batch.get("limitations") or [],
        },
        "market": {
            "generated_at": market.get("generated_at"),
            "source_status": market.get("source_status"),
            "provider": market.get("provider"),
            "fallback_used": market.get("fallback_used"),
            "historical_fallback_available": has_recent_sessions,
        },
        "market_recent_sessions": {
            "updated_at": recent_sessions.get("updated_at"),
            "basis": recent_sessions.get("basis"),
            "korea": (recent_sessions.get("korea") or [])[:3],
            "us": (recent_sessions.get("us") or [])[:3],
            "holiday_notes": recent_sessions.get("holiday_notes") or [],
        },
        "toss": {
            "available": toss.get("available"),
            "captured_at": toss.get("captured_at"),
            "collector": toss.get("collector"),
        },
        "user_feedback": {
            "pending_count": feedback_count,
            "latest_pending_comment_id": latest_feedback_comment_id,
        },
        "git": {
            "head_sha": head_sha or None,
            "latest_commit_changed_files": _latest_changed_files(root),
        },
        "previous_workflow_run": previous_run,
        "hypothesis_verification": {
            "due": due_hypotheses(root, now.isoformat())[:30],
        },
        "signals": signals,
    }


def append_observation(
    root: Path,
    observation: dict[str, Any],
) -> dict[str, Any]:
    supervisor_dir = root / "data" / "supervisor"
    recent_path = supervisor_dir / "recent.json"
    state_path = supervisor_dir / "state.json"

    recent_payload = _read_json(recent_path)
    recent = recent_payload.get("observations", [])
    if not isinstance(recent, list):
        recent = []

    observation_id = observation.get("observation_id")
    if any(item.get("observation_id") == observation_id for item in recent):
        return {
            "status": "duplicate",
            "observation_id": observation_id,
            "recent_count": len(recent),
        }

    new_slot = _observation_slot(observation)
    same_slot_index = None
    for index, item in enumerate(recent):
        if new_slot is not None and _observation_slot(item) == new_slot:
            same_slot_index = index

    stamp = datetime.fromisoformat(str(observation["observed_at"]))
    queue_path = supervisor_dir / "queue" / (stamp.astimezone(KST).strftime("%Y-%m-%d") + ".jsonl")

    if same_slot_index is not None:
        existing = recent[same_slot_index]
        if _observation_quality(observation) <= _observation_quality(existing):
            return {
                "status": "duplicate_slot",
                "observation_id": observation_id,
                "slot_at": new_slot.isoformat() if new_slot else None,
                "canonical_observation_id": existing.get("observation_id"),
                "recent_count": len(recent),
            }
        observation["supersedes_observation_id"] = existing.get("observation_id")
        recent[same_slot_index] = observation
        _append_jsonl(queue_path, observation)
        append_status = "replaced_slot"
    else:
        _append_jsonl(queue_path, observation)
        recent.append(observation)
        append_status = "appended"

    recent = recent[-RECENT_LIMIT:]
    state = _read_json(state_path)
    last_processed = state.get("last_processed_observation_id")
    pending_after = _pending_after(
        recent,
        str(last_processed) if last_processed else None,
    )
    observation["queue"]["pending_after_append"] = pending_after

    _write_json(
        recent_path,
        {
            "schema_version": 2,
            "updated_at": observation["observed_at"],
            "batch_size": BATCH_SIZE,
            "sensor_interval_minutes": SENSOR_INTERVAL_MINUTES,
            "observations": recent,
        },
    )

    window_manifest = (
        _write_window_manifest(root, recent, new_slot)
        if new_slot is not None
        else None
    )

    if not state:
        _write_json(
            state_path,
            {
                "schema_version": 1,
                "batch_size": BATCH_SIZE,
                "last_processed_observation_id": None,
                "last_processed_slot": None,
                "processed_observation_ids_recent": [],
                "last_a_window": None,
                "last_b_window": None,
                "last_processed_at": None,
                "last_batch_id": None,
                "last_processed_feedback_comment_id": None,
            },
        )

    return {
        "status": append_status,
        "observation_id": observation_id,
        "slot_at": new_slot.isoformat() if new_slot else None,
        "queue_file": str(queue_path.relative_to(root)),
        "recent_count": len(recent),
        "pending_after_append": pending_after,
        "window_manifest": window_manifest,
    }


def observe(root: Path, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Record facts only.

    The ten-minute sensor is deliberately not a reasoning layer. It collects
    observable market/system state and leaves questions, hypotheses, bug
    diagnosis, and project-improvement decisions to the :00/:30 Supervisor.
    """
    observation = build_observation(root, env=env)
    return append_observation(root, observation)
