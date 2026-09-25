import json
from datetime import datetime, timedelta, timezone

from autoresearch.regression import RegressionDetector, _hash_text


UTC = timezone.utc


def make_detector(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "regression.yaml").write_text(
        """
windows:
  baseline_7d_days: 7
  baseline_30d_days: 30
  post_change_hours: 24
  grace_hours: 1
minimum_samples:
  baseline_7d: 3
  baseline_30d: 3
  post_change: 3
thresholds:
  overall_drop_7d: 8
  overall_drop_30d: 8
  research_quality_drop: 8
  severe_overall_drop: 15
rollback:
  enabled: true
  max_per_tick: 1
  require_both_baselines: true
  require_research_quality_drop: true
  block_on_later_path_overlap: true
  block_on_current_hash_mismatch: true
quality:
  weights:
    research_quality: 0.5
    health: 0.3
    data_completeness: 0.2
data:
  history_dir: data/regression/history
  latest_file: data/regression/latest.json
  quarantine_file: data/regression/quarantine.json
  changes_dir: data/evolution/changes
""",
        encoding="utf-8",
    )
    return RegressionDetector(tmp_path)


def snapshot(at, overall, research):
    return {
        "timestamp": at.isoformat(),
        "overall_quality": overall,
        "research_quality": research,
        "health_score": overall,
        "data_completeness": overall,
    }


def manifest(change_id, applied, path, before, after):
    return {
        "change_id": change_id,
        "applied_at": applied.isoformat(),
        "title": "테스트 기능",
        "risk": "medium",
        "paths": [path],
        "files": [
            {
                "path": path,
                "before_content": before,
                "after_content": after,
                "before_hash": _hash_text(before),
                "after_hash": _hash_text(after),
            }
        ],
        "status": "active",
    }


def test_regression_rolls_back_only_target_feature(tmp_path):
    detector = make_detector(tmp_path)
    now = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
    applied = now - timedelta(hours=8)

    target = tmp_path / "src/feature.py"
    target.parent.mkdir(parents=True)
    target.write_text("after", encoding="utf-8")
    unrelated = tmp_path / "src/unrelated.py"
    unrelated.write_text("keep-me", encoding="utf-8")

    man = manifest("c1", applied, "src/feature.py", "before", "after")
    man_path = tmp_path / "data/evolution/changes/c1.json"
    man_path.parent.mkdir(parents=True)
    man_path.write_text(json.dumps(man), encoding="utf-8")

    history = [
        snapshot(applied - timedelta(hours=6), 92, 94),
        snapshot(applied - timedelta(hours=4), 93, 95),
        snapshot(applied - timedelta(hours=2), 91, 93),
        snapshot(applied + timedelta(hours=2), 70, 72),
        snapshot(applied + timedelta(hours=4), 71, 73),
        snapshot(applied + timedelta(hours=6), 69, 71),
    ]

    result = detector._evaluate_change(
        man_path,
        man,
        history,
        now,
        [(man_path, man)],
    )

    assert result["status"] == "rolled_back"
    assert target.read_text(encoding="utf-8") == "before"
    assert unrelated.read_text(encoding="utf-8") == "keep-me"

    updated = json.loads(man_path.read_text(encoding="utf-8"))
    assert updated["status"] == "rolled_back_regression"


def test_later_overlap_blocks_automatic_rollback(tmp_path):
    detector = make_detector(tmp_path)
    now = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
    applied = now - timedelta(hours=8)

    target = tmp_path / "src/feature.py"
    target.parent.mkdir(parents=True)
    target.write_text("later-version", encoding="utf-8")

    first = manifest("c1", applied, "src/feature.py", "before", "after")
    first_path = tmp_path / "data/evolution/changes/c1.json"
    first_path.parent.mkdir(parents=True)
    first_path.write_text(json.dumps(first), encoding="utf-8")

    later = manifest(
        "c2",
        applied + timedelta(hours=2),
        "src/feature.py",
        "after",
        "later-version",
    )
    later_path = tmp_path / "data/evolution/changes/c2.json"
    later_path.write_text(json.dumps(later), encoding="utf-8")

    history = [
        snapshot(applied - timedelta(hours=6), 92, 94),
        snapshot(applied - timedelta(hours=4), 93, 95),
        snapshot(applied - timedelta(hours=2), 91, 93),
        snapshot(applied + timedelta(hours=2), 70, 72),
        snapshot(applied + timedelta(hours=4), 71, 73),
        snapshot(applied + timedelta(hours=6), 69, 71),
    ]

    result = detector._evaluate_change(
        first_path,
        first,
        history,
        now,
        [(first_path, first), (later_path, later)],
    )

    assert result["status"] == "quarantined"
    assert "경로 겹침" in result["reason"]
    assert target.read_text(encoding="utf-8") == "later-version"


def test_small_quality_change_is_not_regression(tmp_path):
    detector = make_detector(tmp_path)
    now = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
    applied = now - timedelta(hours=8)

    target = tmp_path / "src/feature.py"
    target.parent.mkdir(parents=True)
    target.write_text("after", encoding="utf-8")

    man = manifest("c1", applied, "src/feature.py", "before", "after")
    man_path = tmp_path / "data/evolution/changes/c1.json"
    man_path.parent.mkdir(parents=True)
    man_path.write_text(json.dumps(man), encoding="utf-8")

    history = [
        snapshot(applied - timedelta(hours=6), 92, 94),
        snapshot(applied - timedelta(hours=4), 93, 95),
        snapshot(applied - timedelta(hours=2), 91, 93),
        snapshot(applied + timedelta(hours=2), 89, 91),
        snapshot(applied + timedelta(hours=4), 90, 92),
        snapshot(applied + timedelta(hours=6), 88, 90),
    ]

    result = detector._evaluate_change(
        man_path,
        man,
        history,
        now,
        [(man_path, man)],
    )

    assert result["status"] == "no_regression"
    assert target.read_text(encoding="utf-8") == "after"


def test_evaluated_change_becomes_learning_memory(tmp_path):
    detector = make_detector(tmp_path)
    manifest_data = {
        "change_id": "learn-1",
        "title": "학습 연결 테스트",
        "expected_benefit": "품질 개선",
        "paths": ["src/feature.py"],
    }
    evaluation = {
        "status": "no_regression",
        "baseline_7d": 90.0,
        "post_overall": 91.0,
    }

    detector._record_learning(evaluation, manifest_data)

    text = (tmp_path / "docs/실험_기록.md").read_text(encoding="utf-8")
    assert "LEARN-learn-1" in text
    assert "판정: 유지" in text
    assert manifest_data["learning_recorded"] is True

    detector._record_learning(evaluation, manifest_data)
    assert (tmp_path / "docs/실험_기록.md").read_text(encoding="utf-8").count(
        "LEARN-learn-1"
    ) == 1
