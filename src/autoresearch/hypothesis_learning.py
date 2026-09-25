from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .question_learning import record_research_outcomes


FINAL = {"confirmed", "partially_confirmed", "falsified", "indeterminate"}


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def register_hypotheses(root: Path, hypotheses: list[dict[str, Any]], *, batch_id: str, created_at: str) -> dict[str, Any]:
    """1시간 AI가 만든 '나중에 틀렸다고 판정할 수 있는' 가설만 등록한다."""
    path = root / "data" / "supervisor" / "hypotheses.json"
    payload = _read(path) or {"schema_version": 1, "hypotheses": []}
    existing = {str(x.get("hypothesis_id")): x for x in payload.get("hypotheses", []) if isinstance(x, dict)}

    for raw in hypotheses:
        statement = str(raw.get("statement") or "").strip()
        question_ids = [str(x) for x in raw.get("question_ids", []) if x]
        checks = [str(x) for x in raw.get("verification_checks", []) if x]
        if not statement or not question_ids or not checks:
            continue
        key = statement + "|" + "|".join(sorted(question_ids))
        hid = "h-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        row = existing.get(hid) or {
            "hypothesis_id": hid,
            "created_at": created_at,
            "batch_id": batch_id,
            "status": "open",
            "verification_history": [],
        }
        row.update({
            "statement": statement,
            "question_ids": question_ids,
            "question_kinds": [str(x) for x in raw.get("question_kinds", []) if x],
            "subject": raw.get("subject"),
            "evidence_for": raw.get("evidence_for") or [],
            "evidence_against": raw.get("evidence_against") or [],
            "verification_checks": checks,
            "verify_after": raw.get("verify_after"),
            "expires_at": raw.get("expires_at"),
            "confidence": raw.get("confidence"),
        })
        existing[hid] = row

    rows = sorted(existing.values(), key=lambda x: str(x.get("created_at") or ""), reverse=True)[:500]
    output = {"schema_version": 1, "updated_at": created_at, "open_count": sum(x.get("status") == "open" for x in rows), "hypotheses": rows}
    _write(path, output)
    return output


def record_hypothesis_verdicts(root: Path, verdicts: list[dict[str, Any]], *, batch_id: str, processed_at: str) -> dict[str, Any]:
    """사후 관측으로 가설을 확인/부분확인/반증/판단불가하고 질문 학습에 환류한다."""
    path = root / "data" / "supervisor" / "hypotheses.json"
    payload = _read(path) or {"schema_version": 1, "hypotheses": []}
    by_id = {str(x.get("hypothesis_id")): x for x in payload.get("hypotheses", []) if isinstance(x, dict)}
    learning: list[dict[str, Any]] = []

    for verdict in verdicts:
        hid = str(verdict.get("hypothesis_id") or "")
        status = str(verdict.get("status") or "")
        if hid not in by_id or status not in FINAL:
            continue
        row = by_id[hid]
        history = list(row.get("verification_history") or [])
        history.append({
            "processed_at": processed_at,
            "batch_id": batch_id,
            "status": status,
            "evidence": verdict.get("evidence") or [],
            "reason": verdict.get("reason"),
        })
        row["verification_history"] = history[-20:]
        row["status"] = status
        row["verified_at"] = processed_at

        # 질문 품질은 '가설이 맞았나' 하나로만 평가하지 않는다.
        # 좋은 질문은 반증된 가설도 빠르게 걸러낼 수 있다.
        resolved = status in {"confirmed", "partially_confirmed", "falsified"}
        usefulness = 1.0 if resolved else 0.25
        evidence_quality = float(verdict.get("evidence_quality") or 0.0)
        kinds = list(row.get("question_kinds") or [])
        qids = list(row.get("question_ids") or [])
        for index, qid in enumerate(qids):
            learning.append({
                "question_id": qid,
                "kind": kinds[index] if index < len(kinds) else "unknown",
                "status": "answered" if resolved else "unresolved",
                "usefulness": usefulness,
                "evidence_quality": evidence_quality,
                "hypothesis_id": hid,
                "hypothesis_verdict": status,
            })

    payload["updated_at"] = processed_at
    payload["open_count"] = sum(x.get("status") == "open" for x in by_id.values())
    payload["hypotheses"] = list(by_id.values())
    _write(path, payload)
    if learning:
        record_research_outcomes(root, learning, batch_id=batch_id, processed_at=processed_at)
    return payload


def due_hypotheses(root: Path, now: str) -> list[dict[str, Any]]:
    payload = _read(root / "data" / "supervisor" / "hypotheses.json")
    try:
        current = datetime.fromisoformat(now)
    except ValueError:
        return []
    due = []
    for row in payload.get("hypotheses", []):
        if not isinstance(row, dict) or row.get("status") != "open":
            continue
        verify_after = row.get("verify_after")
        if not verify_after:
            continue
        try:
            when = datetime.fromisoformat(str(verify_after))
        except ValueError:
            continue
        if when <= current:
            due.append(row)
    return due
