from __future__ import annotations

from autoresearch.supervisor_result import (
    canonical_window_matches,
    infer_run_kind,
    regular_window_complete,
)


def regular_b(**extra):
    value = {
        "batch_id": "supervisor-20260926T1630+0900",
        "processed_at": "2026-09-26T16:30:00+09:00",
        "supervisor": "B",
        "observation_window_start": "2026-09-26T16:10:00+09:00",
        "observation_window_end": "2026-09-26T16:30:00+09:00",
        "observation_slots": [
            "2026-09-26T16:10:00+09:00",
            "2026-09-26T16:20:00+09:00",
            "2026-09-26T16:30:00+09:00",
        ],
        "expected_observation_count": 3,
        "received_observation_count": 3,
        "missing_observation_slots": [],
        "observation_window_complete": True,
    }
    value.update(extra)
    return value


def test_regular_result_requires_canonical_ab_window_or_explicit_kind():
    item = regular_b()
    assert canonical_window_matches(item) is True
    assert regular_window_complete(item) is True
    assert infer_run_kind(item) == "regular"


def test_incomplete_regular_window_is_still_regular_but_not_complete():
    item = regular_b(
        observation_slots=["2026-09-26T16:10:00+09:00", "2026-09-26T16:20:00+09:00"],
        received_observation_count=2,
        missing_observation_slots=["2026-09-26T16:30:00+09:00"],
        observation_window_complete=False,
    )
    assert infer_run_kind(item) == "regular"
    assert regular_window_complete(item) is False


def test_writer_e2e_is_test_even_when_it_uses_a_perfect_b_window():
    item = regular_b(
        batch_id="supervisor-writer-e2e-20260926T1631+0900",
        summary="[테스트] Supervisor writer E2E",
        actions=[{"type": "writer_e2e", "status": "test"}],
    )
    assert canonical_window_matches(item) is True
    assert infer_run_kind(item) == "test"


def test_recovery_never_counts_as_regular_ab_liveness():
    item = regular_b(
        batch_id="recovery-20260926T1635+0900",
        supervisor="Recovery-B",
        run_kind="recovery",
    )
    assert infer_run_kind(item) == "recovery"


def test_explicit_run_kind_is_forward_compatible_contract():
    assert infer_run_kind({"supervisor": "A", "run_kind": "regular"}) == "regular"
    assert infer_run_kind({"supervisor": "B", "run_kind": "test"}) == "test"
    assert infer_run_kind({"supervisor": "Recovery", "run_kind": "recovery"}) == "recovery"
