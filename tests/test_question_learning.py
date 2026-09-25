from pathlib import Path

from autoresearch.question_learning import learned_priority_bonus, record_research_outcomes


def test_question_learning_requires_enough_samples(tmp_path: Path):
    rows = [{"question_id": f"q{i}", "kind": "flow", "status": "answered", "usefulness": 1.0, "evidence_quality": 1.0} for i in range(9)]
    record_research_outcomes(tmp_path, rows, batch_id="b1", processed_at="2026-09-25T11:00:00+09:00")
    assert learned_priority_bonus(tmp_path) == {}


def test_question_learning_boosts_only_after_evidence(tmp_path: Path):
    rows = [{"question_id": f"q{i}", "kind": "flow", "status": "answered", "usefulness": 0.9, "evidence_quality": 0.9} for i in range(10)]
    payload = record_research_outcomes(tmp_path, rows, batch_id="b1", processed_at="2026-09-25T11:00:00+09:00")
    assert payload["by_kind"]["flow"]["total"] == 10
    assert learned_priority_bonus(tmp_path)["flow"] == 1


def test_low_value_question_kind_is_deprioritized(tmp_path: Path):
    rows = [{"question_id": f"q{i}", "kind": "news", "status": "unresolved", "usefulness": 0.1, "evidence_quality": 0.2} for i in range(10)]
    record_research_outcomes(tmp_path, rows, batch_id="b2", processed_at="2026-09-25T12:00:00+09:00")
    assert learned_priority_bonus(tmp_path)["news"] == -1
