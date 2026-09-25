from pathlib import Path

from autoresearch.hypothesis_learning import (
    due_hypotheses,
    record_hypothesis_verdicts,
    register_hypotheses,
)


def test_hypothesis_is_registered_and_becomes_due(tmp_path: Path):
    payload = register_hypotheses(
        tmp_path,
        [{
            "statement": "로봇 관련 종목의 동시 자금 유입이 다음 관측에서도 유지된다.",
            "question_ids": ["q-flow"],
            "question_kinds": ["flow"],
            "verification_checks": ["다음 6분 관련 종목 거래대금 동시성 확인"],
            "verify_after": "2026-09-25T14:48:00+09:00",
            "expires_at": "2026-09-25T15:30:00+09:00",
        }],
        batch_id="b1",
        created_at="2026-09-25T14:42:00+09:00",
    )
    assert payload["open_count"] == 1
    assert due_hypotheses(tmp_path, "2026-09-25T14:47:00+09:00") == []
    assert len(due_hypotheses(tmp_path, "2026-09-25T14:48:00+09:00")) == 1


def test_falsified_hypothesis_still_teaches_question_quality(tmp_path: Path):
    payload = register_hypotheses(
        tmp_path,
        [{
            "statement": "관련 종목 확산이 다음 관측에서도 유지된다.",
            "question_ids": ["q-flow"],
            "question_kinds": ["flow"],
            "verification_checks": ["다음 관측 확인"],
            "verify_after": "2026-09-25T15:00:00+09:00",
        }],
        batch_id="b1",
        created_at="2026-09-25T14:00:00+09:00",
    )
    hid = payload["hypotheses"][0]["hypothesis_id"]
    result = record_hypothesis_verdicts(
        tmp_path,
        [{"hypothesis_id": hid, "status": "falsified", "evidence_quality": 0.9, "evidence": ["후속 6분에서 확산 소멸"]}],
        batch_id="b2",
        processed_at="2026-09-25T15:06:00+09:00",
    )
    assert result["hypotheses"][0]["status"] == "falsified"
    assert (tmp_path / "data/supervisor/question_learning.json").exists()
