from __future__ import annotations

from pathlib import Path
from typing import Any

from .hypothesis_learning import register_hypotheses, record_hypothesis_verdicts
from .question_engine import merge_follow_up_questions
from .question_learning import record_research_outcomes


def apply_hourly_learning(root: Path, result: dict[str, Any], *, batch_id: str, processed_at: str) -> dict[str, Any]:
    """1시간 AI의 구조화 결과를 질문/가설 장기학습 상태에 원자적으로 반영한다."""
    outcomes = [x for x in result.get("question_outcomes", []) if isinstance(x, dict)]
    hypotheses = [x for x in result.get("hypotheses", []) if isinstance(x, dict)]
    verdicts = [x for x in result.get("hypothesis_verdicts", []) if isinstance(x, dict)]
    follow_ups = [x for x in result.get("follow_up_questions", []) if isinstance(x, dict)]

    learning = record_research_outcomes(root, outcomes, batch_id=batch_id, processed_at=processed_at) if outcomes else {}
    registered = register_hypotheses(root, hypotheses, batch_id=batch_id, created_at=processed_at) if hypotheses else {}
    verified = record_hypothesis_verdicts(root, verdicts, batch_id=batch_id, processed_at=processed_at) if verdicts else {}
    queue = merge_follow_up_questions(root, follow_ups, observed_at=processed_at, batch_id=batch_id) if follow_ups else {}

    return {
        "question_outcomes_recorded": len(outcomes),
        "hypotheses_registered": len(hypotheses),
        "hypothesis_verdicts_recorded": len(verdicts),
        "follow_up_questions_added": len(follow_ups),
        "open_hypotheses": (verified or registered).get("open_count"),
        "open_questions": queue.get("open_count"),
        "learning_updated_at": learning.get("updated_at"),
    }
