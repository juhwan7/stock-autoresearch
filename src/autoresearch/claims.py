from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


VALID_STATUSES = {
    "verified_fact",
    "official_claim",
    "analysis",
    "inference",
    "unverified",
}
VALID_CONFIDENCE = {"high", "medium", "low"}


def normalize_claim(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).lower()


def claim_id(value: str) -> str:
    normalized = normalize_claim(value)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]
    return "clm_" + digest


def _source_snapshot(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": source.get("id"),
        "title": source.get("title"),
        "publisher": source.get("publisher"),
        "url": source.get("url"),
        "published_at": source.get("published_at"),
        "tier": source.get("tier"),
        "primary": source.get("primary"),
    }


def build_claim_records(
    *,
    run_id: str,
    generated_at: str,
    mode: str,
    topic: dict[str, Any],
    research: dict[str, Any],
    critic: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    critic = critic or {}
    source_map = {
        str(item.get("id")): item
        for item in research.get("sources", [])
        if isinstance(item, dict) and item.get("id")
    }
    downgraded = {str(x) for x in critic.get("claims_to_downgrade", [])}
    supported = {str(x) for x in critic.get("claims_supported", [])}
    topic_title = str(topic.get("title") or research.get("topic") or "")
    records: list[dict[str, Any]] = []

    for raw in research.get("claims", []):
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("claim") or "").strip()
        if not text:
            continue

        status = str(raw.get("status") or "unverified")
        if status not in VALID_STATUSES:
            status = "unverified"
        confidence = str(raw.get("confidence") or "low")
        if confidence not in VALID_CONFIDENCE:
            confidence = "low"

        source_ids = [
            str(value)
            for value in raw.get("source_ids", [])
            if value not in (None, "")
        ]
        resolved = [
            _source_snapshot(source_map[source_id])
            for source_id in source_ids
            if source_id in source_map
        ]
        missing = [source_id for source_id in source_ids if source_id not in source_map]

        disposition = "not_explicitly_classified"
        if text in downgraded:
            disposition = "downgrade_requested"
        elif text in supported:
            disposition = "supported"

        records.append(
            {
                "schema_version": 1,
                "claim_id": claim_id(text),
                "run_id": run_id,
                "observed_at": generated_at,
                "mode": mode,
                "topic": topic_title,
                "claim": text,
                "status": status,
                "confidence": confidence,
                "source_ids": source_ids,
                "sources": resolved,
                "missing_source_ids": missing,
                "critic_verdict": critic.get("verdict"),
                "critic_disposition": disposition,
            }
        )

    return records


def append_claim_records(
    root: Path,
    *,
    run_id: str,
    generated_at: str,
    mode: str,
    topic_results: list[dict[str, Any]],
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for item in topic_results:
        records.extend(
            build_claim_records(
                run_id=run_id,
                generated_at=generated_at,
                mode=mode,
                topic=item.get("topic", {}),
                research=item.get("research", {}),
                critic=item.get("critic", {}),
            )
        )

    if not records:
        return {"path": None, "appended": 0}

    day = generated_at[:10]
    path = root / "data" / "research" / "claims" / (day + ".jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)

    existing: set[tuple[str, str]] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            existing.add((str(item.get("run_id")), str(item.get("claim_id"))))

    appended = 0
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            key = (str(record["run_id"]), str(record["claim_id"]))
            if key in existing:
                continue
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            existing.add(key)
            appended += 1

    return {
        "path": str(path.relative_to(root)),
        "appended": appended,
        "records": len(records),
    }
