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



def test_sensor_commit_excludes_recovery_owned_status_files():
    workflow = read(".github/workflows/연속연구와진화.yml")
    assert "git add data/operations" not in workflow
    assert "git add README.md docs/운영_칸반.md" not in workflow
    assert "git restore --staged site/data/상태.json" in workflow
    assert "data/operations/status.json" in workflow
    assert "docs/운영_칸반.md" in workflow
    assert "site/data/상태.json" in workflow


def test_sensor_persist_conflict_is_a_real_workflow_failure():
    workflow = read(".github/workflows/연속연구와진화.yml")
    assert "observation 저장 실패를 숨기지 않고 workflow를 실패 처리합니다." in workflow
    assert "핵심 observation 저장에 실패했습니다." in workflow
    assert workflow.count("exit 1") >= 2


def test_heavy_recovery_schedule_avoids_a_b_execution_minutes():
    workflow = read(".github/workflows/자동복구_감시.yml")
    assert 'cron: "3,18,33,48 * * * *"' in workflow
    assert 'cron: "7,22,37,52 * * * *"' not in workflow



def test_sensor_self_chain_dispatches_next_slot_without_cron_dependency():
    workflow = read(".github/workflows/연속연구와진화.yml")
    assert "Keep 10-minute sensor chain alive" in workflow
    assert "actions: write" in workflow
    assert "SENSOR_SELF_CHAIN_DISABLED" in workflow
    assert 'gh workflow run "연속연구와진화.yml"' in workflow
    assert '-f slot_at="$NEXT_SLOT"' in workflow
    assert "ACTIVE_OTHER_RUNS" in workflow
    assert "NEXT_SLOT=" in workflow


def test_stale_dispatch_is_rebased_instead_of_backfilling_old_slot():
    workflow = read(".github/workflows/연속연구와진화.yml")
    assert 'source = "dispatch_input_rebased"' in workflow
    assert "requested_slot == current_slot" in workflow
    assert "SENSOR_SLOT_START_DELAY_SECONDS=" in workflow



def test_sensor_push_race_retries_only_nonconflicting_updates():
    workflow = read(".github/workflows/연속연구와진화.yml")
    assert "for ATTEMPT in 1 2 3" in workflow
    assert "git pull --rebase" in workflow
    assert "3회 재동기화 후에도 핵심 observation 저장에 실패했습니다." in workflow
    assert "git rebase --abort || true" in workflow
    assert "sleep $((ATTEMPT * 2))" in workflow



def test_self_chain_catches_up_current_slot_after_long_sensor_run():
    workflow = read(".github/workflows/연속연구와진화.yml")
    assert 'raw_source_slot = (os.getenv("SENSOR_SLOT_AT") or "").strip()' in workflow
    assert "expected_next = (" in workflow
    assert "next_slot = max(expected_next, current_slot)" in workflow
    assert "과거 슬롯을 backfill하지 않고 현재 슬롯을 즉시 이어" in workflow


def test_supervisor_result_workflow_has_dispatch_single_writer_fallback():
    workflow = read(".github/workflows/감독결과_적용과_텔레그램.yml")
    assert "workflow_dispatch:" in workflow
    assert "supervisor_result:" in workflow
    assert "Receive or find Supervisor result" in workflow
    assert 'payload.get("notify") is not True' in workflow
    assert 'supervisor not in {"A", "B"}' in workflow
    assert 'git add "${{ steps.result.outputs.path }}"' in workflow
    assert "Commit result and canonical state as one writer" in workflow
    assert "Verify persisted result on main" in workflow
    assert "if [ -f data/supervisor/disagreements.json ]" in workflow


def test_supervisor_result_writer_retries_conflicts_and_fails_closed():
    workflow = read(".github/workflows/감독결과_적용과_텔레그램.yml")
    assert "for ATTEMPT in 1 2 3" in workflow
    assert "git pull --rebase origin main" in workflow
    assert "Supervisor result/canonical 저장에 3회 실패했습니다." in workflow
    assert "exit 1" in workflow
    assert "supervisor-result-apply" in workflow


def test_supervisor_result_workflow_has_owner_only_issue_dispatch_bridge():
    workflow = read(".github/workflows/감독결과_적용과_텔레그램.yml")
    assert "issues:" in workflow
    assert "types: [opened]" in workflow
    assert "startsWith(github.event.issue.title, '[Supervisor Result]')" in workflow
    assert "github.actor == github.repository_owner" in workflow
    assert "ISSUE_RESULT:" in workflow
    assert "Close consumed dispatch issue" in workflow
    assert 'gh issue close "$ISSUE_NUMBER"' in workflow
