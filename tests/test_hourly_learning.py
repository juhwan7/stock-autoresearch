from pathlib import Path

from autoresearch.hourly_learning import apply_hourly_learning


def test_hourly_learning_closes_question_hypothesis_loop(tmp_path: Path):
    result = {
        "question_outcomes": [{
            "question_id": "q1", "kind": "flow", "status": "answered",
            "evidence_quality": 0.9, "usefulness": 0.9,
        }],
        "hypotheses": [{
            "statement": "관련 종목 동시 유입이 다음 관측에서도 유지된다.",
            "question_ids": ["q1"], "question_kinds": ["flow"],
            "subject": "로봇", "verification_checks": ["다음 6분 동시 유입 확인"],
            "verify_after": "2026-09-25T15:06:00+09:00",
        }],
        "follow_up_questions": [{
            "kind": "causality", "subject": "로봇",
            "question": "최초 자금 유입이 뉴스보다 먼저였는가?",
            "priority": 4, "parent_question_id": "q1",
            "reason": "선후관계 미확인",
        }],
    }
    summary = apply_hourly_learning(
        tmp_path, result, batch_id="hour-1",
        processed_at="2026-09-25T15:00:00+09:00",
    )
    assert summary["question_outcomes_recorded"] == 1
    assert summary["hypotheses_registered"] == 1
    assert summary["follow_up_questions_added"] == 1
    assert (tmp_path / "data/supervisor/hypotheses.json").exists()
    assert (tmp_path / "data/supervisor/question_queue.json").exists()
    assert (tmp_path / "data/supervisor/question_learning.json").exists()
