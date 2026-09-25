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


KST = timezone(timedelta(hours=9))
BATCH_SIZE = 10
RECENT_LIMIT = 120


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
    discovery = _read_json(root / "data" / "discovery" / "latest.json")
    toss = _read_json(root / "data" / "providers" / "toss" / "status.json")
    if not toss:
        toss = _read_json(root / "data" / "providers" / "toss" / "latest.json")

    feedback_count, latest_feedback_comment_id = _pending_feedback(root)
    validation_status = str(env.get("VALIDATION_STATUS") or "unknown")
    run_id = str(env.get("GITHUB_RUN_ID") or "")
    run_attempt = str(env.get("GITHUB_RUN_ATTEMPT") or "1")
    head_sha = str(env.get("GITHUB_SHA") or "")
    suffix = (run_id + "-" + run_attempt) if run_id else (head_sha[:10] or "local")
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

    market_source_status = str(market.get("source_status") or "")
    if market_source_status and market_source_status not in {"ok", "idle"}:
        signals.append("market:" + market_source_status)

    previous_run = _recent_workflow_run(env)
    if previous_run.get("conclusion") in {"failure", "cancelled", "timed_out"}:
        signals.append("previous_workflow:" + str(previous_run.get("conclusion")))

    pending_before = _pending_after(recent, str(last_processed_id) if last_processed_id else None)

    return {
        "schema_version": 1,
        "observation_id": observation_id,
        "observed_at": now.isoformat(),
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
            "sector_selection": discovery.get("sector_selection"),
            "naver_indices": discovery.get("naver_indices"),
            "source_summary": discovery.get("source_summary"),
            "top_new_items": (discovery.get("new_items") or [])[:10],
            "handoff_queries": discovery.get("handoff_queries"),
        },
        "market": {
            "generated_at": market.get("generated_at"),
            "source_status": market.get("source_status"),
            "provider": market.get("provider"),
            "fallback_used": market.get("fallback_used"),
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

    stamp = datetime.fromisoformat(str(observation["observed_at"]))
    queue_path = supervisor_dir / "queue" / (stamp.astimezone(KST).strftime("%Y-%m-%d") + ".jsonl")
    _append_jsonl(queue_path, observation)

    recent.append(observation)
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
            "schema_version": 1,
            "updated_at": observation["observed_at"],
            "batch_size": BATCH_SIZE,
            "observations": recent,
        },
    )

    if not state:
        _write_json(
            state_path,
            {
                "schema_version": 1,
                "batch_size": BATCH_SIZE,
                "last_processed_observation_id": None,
                "last_processed_at": None,
                "last_batch_id": None,
                "last_processed_feedback_comment_id": None,
            },
        )

    return {
        "status": "appended",
        "observation_id": observation_id,
        "queue_file": str(queue_path.relative_to(root)),
        "recent_count": len(recent),
        "pending_after_append": pending_after,
    }


def observe(root: Path, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    observation = build_observation(root, env=env)
    return append_observation(root, observation)
