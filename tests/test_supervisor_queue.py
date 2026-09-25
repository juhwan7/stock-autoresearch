import json
from datetime import datetime, timedelta, timezone

from autoresearch.supervisor_queue import (
    BATCH_SIZE,
    append_observation,
    build_observation,
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
            "topic_counts": {"market": 4, "semiconductor_ai": 8},
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
    assert state["batch_size"] == 10
    assert state["last_processed_observation_id"] is None


def test_processed_pointer_excludes_old_observations(tmp_path):
    state_path = tmp_path / "data/supervisor/state.json"
    write_json(
        state_path,
        {
            "schema_version": 1,
            "batch_size": 10,
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
