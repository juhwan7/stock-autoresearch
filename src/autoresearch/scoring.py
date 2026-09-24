from __future__ import annotations

from typing import Any

COMPONENTS = (
    "novelty",
    "market_impact",
    "evidence_strength",
    "followup_value",
    "official_source_signal",
    "price_action_signal",
)


def _clamp(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(100.0, number))


def score_candidate(candidate: dict[str, Any], weights: dict[str, float]) -> float:
    scores = candidate.get("scores", {})
    total = 0.0
    weight_total = 0.0
    for component in COMPONENTS:
        weight = float(weights.get(component, 0.0))
        total += _clamp(scores.get(component, 0)) * weight
        weight_total += weight
    if weight_total <= 0:
        return 0.0
    return round(total / weight_total, 2)


def rank_candidates(
    candidates: list[dict[str, Any]], weights: dict[str, float]
) -> list[dict[str, Any]]:
    ranked = []
    for candidate in candidates:
        item = dict(candidate)
        item["priority_score"] = score_candidate(candidate, weights)
        ranked.append(item)
    return sorted(ranked, key=lambda x: x["priority_score"], reverse=True)


def quality_average(final: dict[str, Any]) -> float:
    values = final.get("quality_score", {})
    if not values:
        return 0.0
    nums = [_clamp(v) for v in values.values()]
    return round(sum(nums) / len(nums), 2) if nums else 0.0
