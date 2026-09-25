from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def record_research_outcomes(root: Path, outcomes: list[dict[str, Any]], *, batch_id: str, processed_at: str) -> dict[str, Any]:
    """1시간 AI가 검증한 질문 결과를 장기 성능 통계로 누적한다.

    outcome은 question_id/kind/status/evidence_quality/usefulness를 가진다.
    방향성 예측 정확도가 아니라 질문이 연구에 실제 도움이 됐는지를 먼저 학습한다.
    """
    path = root / "data" / "supervisor" / "question_learning.json"
    payload = _read(path) or {"schema_version": 1, "by_kind": {}, "recent_outcomes": []}
    by_kind = payload.setdefault("by_kind", {})
    recent = list(payload.get("recent_outcomes") or [])

    for row in outcomes:
        kind = str(row.get("kind") or "unknown")
        status = str(row.get("status") or "unresolved")
        usefulness = float(row.get("usefulness") or 0.0)
        quality = float(row.get("evidence_quality") or 0.0)
        stats = by_kind.setdefault(kind, {"total": 0, "answered": 0, "partial": 0, "unresolved": 0, "usefulness_sum": 0.0, "evidence_quality_sum": 0.0})
        stats["total"] += 1
        if status == "answered":
            stats["answered"] += 1
        elif status == "partially_answered":
            stats["partial"] += 1
        else:
            stats["unresolved"] += 1
        stats["usefulness_sum"] += max(0.0, min(1.0, usefulness))
        stats["evidence_quality_sum"] += max(0.0, min(1.0, quality))
        stats["answer_rate"] = round((stats["answered"] + 0.5 * stats["partial"]) / stats["total"], 4)
        stats["avg_usefulness"] = round(stats["usefulness_sum"] / stats["total"], 4)
        stats["avg_evidence_quality"] = round(stats["evidence_quality_sum"] / stats["total"], 4)
        recent.append({**row, "batch_id": batch_id, "processed_at": processed_at})

    payload["updated_at"] = processed_at
    payload["recent_outcomes"] = recent[-300:]
    _write(path, payload)
    return payload


def learned_priority_bonus(root: Path) -> dict[str, int]:
    """충분한 표본이 쌓인 질문 종류에만 작은 우선순위 보정을 준다.

    학습이 원래 시장 신호를 압도하지 않도록 보정폭은 -1~+1이다.
    """
    payload = _read(root / "data" / "supervisor" / "question_learning.json")
    result: dict[str, int] = {}
    for kind, stats in (payload.get("by_kind") or {}).items():
        total = int(stats.get("total") or 0)
        if total < 10:
            continue
        usefulness = float(stats.get("avg_usefulness") or 0.0)
        quality = float(stats.get("avg_evidence_quality") or 0.0)
        answer_rate = float(stats.get("answer_rate") or 0.0)
        score = 0.45 * usefulness + 0.35 * quality + 0.20 * answer_rate
        if score >= 0.75:
            result[str(kind)] = 1
        elif score <= 0.35:
            result[str(kind)] = -1
    return result
