from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Mapping


REGULAR = "regular"
TEST = "test"
RECOVERY = "recovery"
UNKNOWN = "unknown"
KNOWN_RUN_KINDS = {REGULAR, TEST, RECOVERY, UNKNOWN}


def supervisor_role(value: object) -> str | None:
    text = str(value or "").strip().upper()
    if text == "A" or text.endswith("-A") or text.startswith("A-"):
        return "A"
    if text == "B" or text.endswith("-B") or text.startswith("B-"):
        return "B"
    return None


def _parse_time(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _normalized_kind(value: object) -> str | None:
    text = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "regular": REGULAR,
        "supervisor_regular": REGULAR,
        "canonical": REGULAR,
        "test": TEST,
        "e2e": TEST,
        "diagnostic": TEST,
        "recovery": RECOVERY,
        "catchup": RECOVERY,
        "catch_up": RECOVERY,
    }
    return aliases.get(text)


def _contains_test_signal(payload: Mapping[str, Any]) -> bool:
    batch = str(payload.get("batch_id") or "").lower()
    summary = payload.get("summary")
    if isinstance(summary, list):
        summary_text = " ".join(str(x) for x in summary)
    else:
        summary_text = str(summary or "")
    summary_lower = summary_text.lower()

    if any(token in batch for token in ("-e2e", "e2e-", "-test", "test-", "telegram-format")):
        return True
    summary_stripped = summary_text.strip()
    if summary_stripped.startswith("[테스트]") or summary_lower.strip().startswith("test"):
        return True

    for item in payload.get("actions") or []:
        if not isinstance(item, Mapping):
            continue
        status = str(item.get("status") or "").lower()
        if status == "test":
            return True
    return False


def canonical_window_matches(payload: Mapping[str, Any]) -> bool:
    role = supervisor_role(payload.get("supervisor"))
    if role not in {"A", "B"}:
        return False

    end = _parse_time(payload.get("observation_window_end"))
    slots = [
        value
        for value in (_parse_time(x) for x in (payload.get("observation_slots") or []))
        if value is not None
    ]
    if end is None and slots:
        end = max(slots)
    if end is None:
        return False

    expected_minute = 0 if role == "A" else 30
    if end.minute != expected_minute or end.second != 0:
        return False

    expected_count = payload.get("expected_observation_count")
    if expected_count not in (None, "", 3, "3"):
        return False

    expected = [end - timedelta(minutes=20), end - timedelta(minutes=10), end]
    expected_iso = {x.isoformat() for x in expected}
    if any(x.isoformat() not in expected_iso for x in slots):
        return False

    start = _parse_time(payload.get("observation_window_start"))
    if start is not None and start != expected[0]:
        return False

    missing = [
        value
        for value in (_parse_time(x) for x in (payload.get("missing_observation_slots") or []))
        if value is not None
    ]
    if any(x.isoformat() not in expected_iso for x in missing):
        return False
    return True


def regular_window_complete(payload: Mapping[str, Any]) -> bool:
    if not canonical_window_matches(payload):
        return False
    explicit = payload.get("observation_window_complete")
    if explicit is not None:
        return bool(explicit)
    received = payload.get("received_observation_count")
    missing = payload.get("missing_observation_slots") or []
    if received is not None:
        try:
            return int(received) == 3 and not missing
        except (TypeError, ValueError):
            return False
    slots = payload.get("observation_slots") or []
    return len(slots) == 3 and not missing


def infer_run_kind(payload: Mapping[str, Any]) -> str:
    explicit = _normalized_kind(payload.get("run_kind")) or _normalized_kind(payload.get("result_type"))
    if explicit:
        return explicit

    batch = str(payload.get("batch_id") or "").strip().lower()
    supervisor_text = str(payload.get("supervisor") or "").strip().lower()

    if _contains_test_signal(payload):
        return TEST
    if batch.startswith("recovery-") or "recovery" in supervisor_text or "catchup" in supervisor_text:
        return RECOVERY

    role = supervisor_role(payload.get("supervisor"))
    if role in {"A", "B"} and canonical_window_matches(payload):
        return REGULAR

    # Backward compatibility for old regular files that predate explicit window metadata.
    if role in {"A", "B"} and re.fullmatch(
        r"supervisor-\d{8}t\d{4}[+-]\d{4}(?:-[ab]\d+)?",
        batch,
        flags=re.IGNORECASE,
    ):
        return REGULAR
    return UNKNOWN


def is_regular_supervisor_result(payload: Mapping[str, Any]) -> bool:
    return infer_run_kind(payload) == REGULAR and supervisor_role(payload.get("supervisor")) in {"A", "B"}
