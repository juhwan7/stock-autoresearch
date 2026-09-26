import json
from datetime import datetime, timedelta, timezone

from autoresearch.supervisor_queue import (
    BATCH_SIZE,
    append_observation,
    build_observation,
    build_supervisor_window,
    expected_supervisor_slots,
    sensor_slot_start,
)


KST = timezone(timedelta(hours=9))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_build_observation_collects_health_and_feedback(tmp_path):
    write_json(
        tmp_path / "data/health/latest.json",
        {
            "status": "WARN",
            "generated_at": "2026-09-25T08:10:00+09:00",
            "issues": [
                {
                    "component": "market",
                    "code": "stale",
                    "severity": "WARN",
                    "message": "시장 데이터가 오래됨",
                }
            ],
        },
    )
    write_json(
        tmp_path / "data/discovery/latest.json",
        {
            "generated_at": "2026-09-25T08:19:00+09:00",
            "item_count": 12,
            "new_item_count": 3,
            "topic_counts": {"kr_market_broad": 8, "global_market": 4},
            "trending_terms": [{"term": "조선", "count": 4, "score": 11}],
            "sector_selection": {"mode": "dynamic", "fixed_sector_whitelist": False},
            "naver_indices": {"KOSPI": "7000.00"},
            "source_summary": {"ok_or_partial": 3, "failed": 0},
            "new_items": [{"title": "새 뉴스", "url": "https://example.com/news"}],
            "handoff_queries": ["코스피 코스닥 증시"],
        },
    )
    feedback = tmp_path / "data/feedback/사용자_피드백.jsonl"
    feedback.parent.mkdir(parents=True)
    feedback.write_text(
        json.dumps(
            {
                "comment_id": "101",
                "status": "pending_evolution_review",
                "body": "수정해줘",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    observation = build_observation(
        tmp_path,
        now=datetime(2026, 9, 25, 8, 20, tzinfo=KST),
        env={
            "GITHUB_RUN_ID": "77",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_SHA": "abcdef123456",
            "GITHUB_REPOSITORY": "juhwan7/stock-autoresearch",
            "GITHUB_REF_NAME": "main",
            "VALIDATION_STATUS": "failed",
        },
    )

    assert observation["queue"]["batch_size"] == BATCH_SIZE
    assert observation["health"]["status"] == "WARN"
    assert observation["user_feedback"]["pending_count"] == 1
    assert observation["market_discovery"]["new_item_count"] == 3
    assert observation["market_discovery"]["top_new_items"][0]["title"] == "새 뉴스"
    assert observation["market_discovery"]["trending_terms"][0]["term"] == "조선"
    assert observation["market_discovery"]["sector_selection"]["mode"] == "dynamic"
    assert "health:WARN" in observation["signals"]
    assert "validation:failed" in observation["signals"]


def test_append_observation_is_idempotent_and_tracks_pending(tmp_path):
    fixed = datetime(2026, 9, 25, 8, 20, tzinfo=KST)
    first = build_observation(
        tmp_path,
        now=fixed,
        env={"GITHUB_RUN_ID": "88", "GITHUB_RUN_ATTEMPT": "1"},
    )

    result = append_observation(tmp_path, first)
    duplicate = append_observation(tmp_path, first)

    assert result["status"] == "appended"
    assert result["pending_after_append"] == 1
    assert duplicate["status"] == "duplicate"

    recent = json.loads(
        (tmp_path / "data/supervisor/recent.json").read_text(encoding="utf-8")
    )
    assert len(recent["observations"]) == 1

    state = json.loads(
        (tmp_path / "data/supervisor/state.json").read_text(encoding="utf-8")
    )
    assert state["batch_size"] == BATCH_SIZE
    assert state["last_processed_observation_id"] is None


def test_processed_pointer_excludes_old_observations(tmp_path):
    state_path = tmp_path / "data/supervisor/state.json"
    write_json(
        state_path,
        {
            "schema_version": 1,
            "batch_size": BATCH_SIZE,
            "last_processed_observation_id": "obs-old",
        },
    )
    write_json(
        tmp_path / "data/supervisor/recent.json",
        {
            "schema_version": 1,
            "observations": [
                {"observation_id": "obs-old"},
                {"observation_id": "obs-new"},
            ],
        },
    )

    observation = build_observation(
        tmp_path,
        now=datetime(2026, 9, 25, 9, 0, tzinfo=KST),
        env={"GITHUB_RUN_ID": "99", "GITHUB_RUN_ATTEMPT": "1"},
    )
    assert observation["queue"]["pending_before_append"] == 1


def test_recent_sessions_feed_supervisor_and_suppress_offhours_false_alarm(tmp_path):
    write_json(
        tmp_path / "data/market/runtime.json",
        {
            "generated_at": "2026-09-26T14:15:00+09:00",
            "source_status": "outside_domestic_monitor_window",
            "provider": "provider_chain",
        },
    )
    write_json(
        tmp_path / "data/market/recent-sessions.json",
        {
            "updated_at": "2026-09-26T12:50:00+09:00",
            "basis": "verified_close",
            "korea": [
                {
                    "date": "2026-09-23",
                    "kospi": {"close": 7080.92, "change_pct": 0.90},
                    "kosdaq": {"close": 844.48, "change_pct": 1.21},
                    "flows_krw_100m": {"foreign": -5047, "institution": 3169},
                },
                {"date": "2026-09-22"},
                {"date": "2026-09-21"},
            ],
            "us": [{"date": "2026-09-25"}],
            "holiday_notes": [{"market": "KR", "reason": "추석 연휴"}],
        },
    )

    observation = build_observation(
        tmp_path,
        now=datetime(2026, 9, 26, 14, 20, tzinfo=KST),
        env={"GITHUB_RUN_ID": "100", "GITHUB_RUN_ATTEMPT": "1"},
    )

    assert observation["market"]["historical_fallback_available"] is True
    assert len(observation["market_recent_sessions"]["korea"]) == 3
    assert observation["market_recent_sessions"]["korea"][0]["date"] == "2026-09-23"
    assert "market:outside_domestic_monitor_window" not in observation["signals"]



def test_sensor_slot_floor_and_supervisor_windows():
    delayed = datetime(2026, 9, 26, 18, 22, 45, tzinfo=KST)
    assert sensor_slot_start(delayed) == datetime(2026, 9, 26, 18, 20, tzinfo=KST)

    b_slots = expected_supervisor_slots(
        datetime(2026, 9, 26, 18, 30, tzinfo=KST),
        "B",
    )
    assert [slot.strftime("%H:%M") for slot in b_slots] == ["18:10", "18:20", "18:30"]

    a_slots = expected_supervisor_slots(
        datetime(2026, 9, 26, 19, 0, tzinfo=KST),
        "A",
    )
    assert [slot.strftime("%H:%M") for slot in a_slots] == ["18:40", "18:50", "19:00"]


def test_supervisor_window_does_not_backfill_missing_slot():
    observations = [
        {
            "observation_id": "obs-1810",
            "observed_at": "2026-09-26T18:12:00+09:00",
            "slot_at": "2026-09-26T18:10:00+09:00",
            "validation": {"status": "ok"},
        },
        {
            "observation_id": "obs-1830",
            "observed_at": "2026-09-26T18:31:00+09:00",
            "slot_at": "2026-09-26T18:30:00+09:00",
            "validation": {"status": "ok"},
        },
        {
            "observation_id": "obs-1800-old",
            "observed_at": "2026-09-26T18:01:00+09:00",
            "slot_at": "2026-09-26T18:00:00+09:00",
            "validation": {"status": "ok"},
        },
    ]
    manifest = build_supervisor_window(
        observations,
        processed_at=datetime(2026, 9, 26, 18, 30, tzinfo=KST),
        supervisor="B",
    )
    assert manifest["observation_ids"] == ["obs-1810", "obs-1830"]
    assert manifest["missing_slots"] == ["2026-09-26T18:20:00+09:00"]
    assert manifest["received_observation_count"] == 2
    assert manifest["complete"] is False


def test_duplicate_slot_uses_better_canonical_observation():
    observations = [
        {
            "observation_id": "obs-1820-bad",
            "observed_at": "2026-09-26T18:20:30+09:00",
            "slot_at": "2026-09-26T18:20:00+09:00",
            "validation": {"status": "failed"},
            "steps": {"market": "failure"},
        },
        {
            "observation_id": "obs-1820-good",
            "observed_at": "2026-09-26T18:23:00+09:00",
            "slot_at": "2026-09-26T18:20:00+09:00",
            "validation": {"status": "ok"},
            "steps": {"market": "success", "discovery": "success"},
        },
        {
            "observation_id": "obs-1810",
            "observed_at": "2026-09-26T18:11:00+09:00",
            "slot_at": "2026-09-26T18:10:00+09:00",
            "validation": {"status": "ok"},
        },
        {
            "observation_id": "obs-1830",
            "observed_at": "2026-09-26T18:31:00+09:00",
            "slot_at": "2026-09-26T18:30:00+09:00",
            "validation": {"status": "ok"},
        },
    ]
    manifest = build_supervisor_window(
        observations,
        processed_at=datetime(2026, 9, 26, 18, 30, tzinfo=KST),
        supervisor="B",
    )
    assert manifest["observation_ids"] == ["obs-1810", "obs-1820-good", "obs-1830"]
    assert manifest["complete"] is True


def test_append_observation_writes_window_manifest_on_half_hour(tmp_path):
    for minute, run_id in [(10, "10"), (20, "20"), (30, "30")]:
        observation = build_observation(
            tmp_path,
            now=datetime(2026, 9, 26, 18, minute, 10, tzinfo=KST),
            env={
                "GITHUB_RUN_ID": run_id,
                "GITHUB_RUN_ATTEMPT": "1",
                "VALIDATION_STATUS": "ok",
            },
        )
        append_observation(tmp_path, observation)

    manifest = json.loads(
        (tmp_path / "data/supervisor/windows/latest-B.json").read_text(encoding="utf-8")
    )
    assert manifest["complete"] is True
    assert manifest["observation_slots"] == [
        "2026-09-26T18:10:00+09:00",
        "2026-09-26T18:20:00+09:00",
        "2026-09-26T18:30:00+09:00",
    ]



def test_pending_count_recovers_from_processed_slot_when_id_was_replaced(tmp_path):
    write_json(
        tmp_path / "data/supervisor/state.json",
        {
            "schema_version": 2,
            "batch_size": BATCH_SIZE,
            "last_processed_observation_id": "obs-1830-old",
            "last_processed_slot": "2026-09-26T18:30:00+09:00",
        },
    )
    write_json(
        tmp_path / "data/supervisor/recent.json",
        {
            "schema_version": 2,
            "observations": [
                {
                    "observation_id": "obs-1830-replacement",
                    "observed_at": "2026-09-26T18:33:00+09:00",
                    "slot_at": "2026-09-26T18:30:00+09:00",
                },
                {
                    "observation_id": "obs-1840",
                    "observed_at": "2026-09-26T18:41:00+09:00",
                    "slot_at": "2026-09-26T18:40:00+09:00",
                },
            ],
        },
    )
    observation = build_observation(
        tmp_path,
        now=datetime(2026, 9, 26, 18, 50, tzinfo=KST),
        env={"GITHUB_RUN_ID": "pending-slot", "GITHUB_RUN_ATTEMPT": "1"},
    )
    assert observation["queue"]["pending_before_append"] == 1



def test_build_observation_keeps_workflow_start_slot_after_long_collection(tmp_path):
    observation = build_observation(
        tmp_path,
        now=datetime(2026, 9, 26, 18, 31, 30, tzinfo=KST),
        env={
            "GITHUB_RUN_ID": "slot-pin",
            "GITHUB_RUN_ATTEMPT": "1",
            "SENSOR_SLOT_AT": "2026-09-26T18:20:00+09:00",
            "SENSOR_SLOT_SOURCE": "workflow_start",
        },
    )
    assert observation["slot_at"] == "2026-09-26T18:20:00+09:00"
    assert observation["slot_source"] == "workflow_start"
    assert observation["slot_delay_seconds"] == 690.0


def test_equal_quality_duplicate_slot_prefers_lower_delay():
    observations = [
        {
            "observation_id": "obs-late",
            "observed_at": "2026-09-26T18:28:00+09:00",
            "slot_at": "2026-09-26T18:20:00+09:00",
            "slot_delay_seconds": 480,
            "validation": {"status": "ok"},
            "steps": {"market": "success"},
        },
        {
            "observation_id": "obs-ontime",
            "observed_at": "2026-09-26T18:21:00+09:00",
            "slot_at": "2026-09-26T18:20:00+09:00",
            "slot_delay_seconds": 60,
            "validation": {"status": "ok"},
            "steps": {"market": "success"},
        },
        {
            "observation_id": "obs-1810",
            "observed_at": "2026-09-26T18:11:00+09:00",
            "slot_at": "2026-09-26T18:10:00+09:00",
            "validation": {"status": "ok"},
        },
        {
            "observation_id": "obs-1830",
            "observed_at": "2026-09-26T18:31:00+09:00",
            "slot_at": "2026-09-26T18:30:00+09:00",
            "validation": {"status": "ok"},
        },
    ]
    manifest = build_supervisor_window(
        observations,
        processed_at=datetime(2026, 9, 26, 18, 30, tzinfo=KST),
        supervisor="B",
    )
    assert manifest["observation_ids"] == ["obs-1810", "obs-ontime", "obs-1830"]



def test_observation_records_start_delay_trigger_and_ten_minute_samples(tmp_path):
    write_json(
        tmp_path / "data/providers/naver_batch/latest.json",
        {
            "generated_at": "2026-09-26T18:20:00+09:00",
            "minute_samples_by_ticker": {
                "005930": [
                    {"time": f"18:{minute:02d}", "minute_trading_value": minute}
                    for minute in range(9, 21)
                ]
            },
        },
    )
    observation = build_observation(
        tmp_path,
        now=datetime(2026, 9, 26, 18, 21, 30, tzinfo=KST),
        env={
            "GITHUB_RUN_ID": "slot-delay",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "SENSOR_SLOT_AT": "2026-09-26T18:20:00+09:00",
            "SENSOR_SLOT_SOURCE": "dispatch_input",
            "SENSOR_SLOT_START_DELAY_SECONDS": "20.5",
        },
    )
    assert observation["slot_start_delay_seconds"] == 20.5
    assert observation["slot_delay_seconds"] == 90.0
    assert observation["source"]["event_name"] == "workflow_dispatch"
    samples = observation["public_batch_market"]["minute_samples_by_ticker"]["005930"]
    assert len(samples) == 10
    assert samples[0]["time"] == "18:11"
    assert samples[-1]["time"] == "18:20"


def test_equal_quality_duplicate_prefers_lower_start_delay_before_completion_delay():
    observations = [
        {
            "observation_id": "obs-start-late",
            "observed_at": "2026-09-26T18:21:00+09:00",
            "slot_at": "2026-09-26T18:20:00+09:00",
            "slot_start_delay_seconds": 180,
            "slot_delay_seconds": 60,
            "validation": {"status": "ok"},
            "steps": {"market": "success"},
        },
        {
            "observation_id": "obs-start-ontime",
            "observed_at": "2026-09-26T18:24:00+09:00",
            "slot_at": "2026-09-26T18:20:00+09:00",
            "slot_start_delay_seconds": 20,
            "slot_delay_seconds": 240,
            "validation": {"status": "ok"},
            "steps": {"market": "success"},
        },
        {
            "observation_id": "obs-1810",
            "observed_at": "2026-09-26T18:11:00+09:00",
            "slot_at": "2026-09-26T18:10:00+09:00",
            "validation": {"status": "ok"},
        },
        {
            "observation_id": "obs-1830",
            "observed_at": "2026-09-26T18:31:00+09:00",
            "slot_at": "2026-09-26T18:30:00+09:00",
            "validation": {"status": "ok"},
        },
    ]
    manifest = build_supervisor_window(
        observations,
        processed_at=datetime(2026, 9, 26, 18, 30, tzinfo=KST),
        supervisor="B",
    )
    assert manifest["observation_ids"] == [
        "obs-1810",
        "obs-start-ontime",
        "obs-1830",
    ]
