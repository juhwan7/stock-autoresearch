from autoresearch.memory import StateStore, normalize_title


def test_normalize_title():
    assert normalize_title("CXMT: DDR5 확대!") == normalize_title("CXMT DDR5 확대")


def test_state_round_trip(tmp_path):
    path = tmp_path / "state.json"
    store = StateStore(path)
    store.record_run(
        run_id="r1",
        generated_at="2026-01-01T00:00:00+00:00",
        topic_results=[
            {
                "topic": {"title": "Sample topic"},
                "final": {"title": "Sample topic"},
            }
        ],
    )
    reloaded = StateStore(path)
    assert reloaded.recent_titles() == ["Sample topic"]
    assert reloaded.previous_for("Sample topic") is not None
