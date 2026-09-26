from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_observer_pins_slot_at_workflow_start_and_accepts_recovery_input():
    workflow = read(".github/workflows/연속연구와진화.yml")
    assert "slot_at:" in workflow
    assert "Pin observation slot at workflow start" in workflow
    assert "SENSOR_SLOT_AT=" in workflow
    assert "SENSOR_SLOT_SOURCE=" in workflow


def test_lightweight_heartbeat_runs_five_minutes_after_each_slot():
    workflow = read(".github/workflows/10분센서_보조복구.yml")
    assert 'cron: "5,15,25,35,45,55 * * * *"' in workflow
    assert 'ACTIVE_SENSOR_RUNS=$(gh run list' in workflow
    assert '-f slot_at="$EXPECTED_SLOT"' in workflow
    assert "pip install" not in workflow
    assert "actions/checkout" not in workflow


def test_heavy_recovery_dispatches_with_explicit_slot():
    workflow = read(".github/workflows/자동복구_감시.yml")
    assert "RECOVERY_SLOT_AT=" in workflow
    assert '-f slot_at="$RECOVERY_SLOT_AT"' in workflow
