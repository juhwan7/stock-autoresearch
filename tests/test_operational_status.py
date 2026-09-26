import importlib.util
import json
from datetime import datetime
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "운영상태_생성.py"


def load_module():
    spec = importlib.util.spec_from_file_location("operations_status", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def prepare(module, tmp_path):
    module.ROOT = tmp_path
    module.OUT = tmp_path / "data/operations/status.json"
    module.KANBAN = tmp_path / "docs/운영_칸반.md"
    module.README = tmp_path / "README.md"
    module.README.write_text("# Test\n\n## 바로가기\n", encoding="utf-8")
    (tmp_path / "site/data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "site/data/상태.json").write_text("{}", encoding="utf-8")


def test_optional_credentials_are_not_user_action_when_public_coverage_is_healthy(tmp_path):
    module = load_module()
    prepare(module, tmp_path)
    write_json(tmp_path / "data/discovery/latest.json", {
        "generated_at": "2026-09-26T15:35:00+09:00",
        "item_count": 227,
        "source_status": {
            "naver_news_api": {"status": "needs_credentials"},
            "dart": {"status": "needs_credentials"},
        },
    })
    write_json(tmp_path / "data/news/issue-digest.json", {
        "updated_at": "2026-09-26T15:30:00+09:00",
        "issues": [{"issue_id": "a"}],
    })
    write_json(tmp_path / "data/health/latest.json", {"issues": []})
    write_json(tmp_path / "data/supervisor/state.json", {})
    write_json(tmp_path / "data/supervisor/question_queue.json", {})
    write_json(tmp_path / "data/supervisor/ai-results/a.json", {
        "supervisor": "A", "processed_at": "2026-09-26T15:00:00+09:00", "batch_id": "a"
    })
    write_json(tmp_path / "data/supervisor/ai-results/b.json", {
        "supervisor": "B", "processed_at": "2026-09-26T15:30:00+09:00", "batch_id": "b"
    })

    status = module.build_status(datetime.fromisoformat("2026-09-26T15:40:00+09:00"))
    assert status["user_actions"] == []
    optional = next(x for x in status["cards"] if x["card_id"] == "optional-news-credentials")
    assert optional["state"] == "완료"


def test_stale_supervisor_is_put_on_kanban_without_stopping_other_checks(tmp_path):
    module = load_module()
    prepare(module, tmp_path)
    write_json(tmp_path / "data/discovery/latest.json", {
        "generated_at": "2026-09-26T15:39:00+09:00", "item_count": 100, "source_status": {}
    })
    write_json(tmp_path / "data/news/issue-digest.json", {
        "updated_at": "2026-09-26T15:30:00+09:00", "issues": []
    })
    write_json(tmp_path / "data/health/latest.json", {"issues": []})
    write_json(tmp_path / "data/supervisor/state.json", {})
    write_json(tmp_path / "data/supervisor/question_queue.json", {})
    write_json(tmp_path / "data/supervisor/ai-results/a.json", {
        "supervisor": "A", "processed_at": "2026-09-26T15:00:00+09:00", "batch_id": "a"
    })
    write_json(tmp_path / "data/supervisor/ai-results/b.json", {
        "supervisor": "B", "processed_at": "2026-09-26T13:30:00+09:00", "batch_id": "b"
    })

    status = module.build_status(datetime.fromisoformat("2026-09-26T15:40:00+09:00"))
    stale = next(x for x in status["cards"] if x["card_id"] == "supervisor-b-stale")
    assert stale["state"] == "조사 중"
    assert any(x["card_id"] == "discovery-ok" for x in status["cards"])



def test_sensor_slot_coverage_uses_completed_six_slots(tmp_path):
    module = load_module()
    prepare(module, tmp_path)
    write_json(
        tmp_path / "data/supervisor/recent.json",
        {
            "schema_version": 2,
            "observations": [
                {
                    "observation_id": "obs-1500",
                    "observed_at": "2026-09-26T15:01:00+09:00",
                    "slot_at": "2026-09-26T15:00:00+09:00",
                    "slot_start_delay_seconds": 20,
                    "slot_delay_seconds": 60,
                    "source": {"event_name": "workflow_dispatch"},
                    "slot_source": "dispatch_input",
                },
                {
                    "observation_id": "obs-1510",
                    "observed_at": "2026-09-26T15:11:30+09:00",
                    "slot_at": "2026-09-26T15:10:00+09:00",
                    "slot_start_delay_seconds": 30,
                    "slot_delay_seconds": 90,
                    "source": {"event_name": "schedule"},
                    "slot_source": "workflow_start",
                },
                {
                    "observation_id": "obs-1530",
                    "observed_at": "2026-09-26T15:31:00+09:00",
                    "slot_at": "2026-09-26T15:30:00+09:00",
                    "slot_delay_seconds": 60,
                },
                {
                    "observation_id": "obs-1540",
                    "observed_at": "2026-09-26T15:41:00+09:00",
                    "slot_at": "2026-09-26T15:40:00+09:00",
                    "slot_delay_seconds": 60,
                },
                {
                    "observation_id": "obs-1550",
                    "observed_at": "2026-09-26T15:51:00+09:00",
                    "slot_at": "2026-09-26T15:50:00+09:00",
                    "slot_delay_seconds": 60,
                },
            ],
        },
    )
    coverage = module.sensor_slot_coverage(
        datetime.fromisoformat("2026-09-26T16:04:00+09:00")
    )
    assert coverage["window_start"] == "2026-09-26T15:00:00+09:00"
    assert coverage["window_end"] == "2026-09-26T15:50:00+09:00"
    assert coverage["received_slot_count"] == 5
    assert coverage["missing_slots"] == ["2026-09-26T15:20:00+09:00"]
    assert coverage["coverage_ratio"] == 0.833
    assert coverage["max_slot_start_delay_seconds"] == 60.0
    assert coverage["max_slot_delay_seconds"] == 90.0
    assert coverage["trigger_event_counts"]["workflow_dispatch"] == 1
    assert coverage["trigger_event_counts"]["schedule"] == 1


def test_build_status_surfaces_poor_sensor_slot_coverage(tmp_path):
    module = load_module()
    prepare(module, tmp_path)
    write_json(tmp_path / "data/discovery/latest.json", {
        "generated_at": "2026-09-26T15:59:00+09:00", "item_count": 100, "source_status": {}
    })
    write_json(tmp_path / "data/news/issue-digest.json", {
        "updated_at": "2026-09-26T15:30:00+09:00", "issues": []
    })
    write_json(tmp_path / "data/health/latest.json", {"issues": []})
    write_json(tmp_path / "data/supervisor/state.json", {})
    write_json(tmp_path / "data/supervisor/question_queue.json", {})
    write_json(tmp_path / "data/supervisor/recent.json", {
        "observations": [
            {
                "observation_id": "obs-1550",
                "observed_at": "2026-09-26T15:51:00+09:00",
                "slot_at": "2026-09-26T15:50:00+09:00",
                "slot_delay_seconds": 60,
            }
        ]
    })
    write_json(tmp_path / "data/supervisor/ai-results/a.json", {
        "supervisor": "A", "processed_at": "2026-09-26T16:00:00+09:00", "batch_id": "a"
    })
    write_json(tmp_path / "data/supervisor/ai-results/b.json", {
        "supervisor": "B", "processed_at": "2026-09-26T15:30:00+09:00", "batch_id": "b"
    })

    status = module.build_status(datetime.fromisoformat("2026-09-26T16:04:00+09:00"))
    card = next(x for x in status["cards"] if x["card_id"] == "sensor-slot-coverage-poor")
    assert card["state"] == "조사 중"
    assert status["sensor_slot_coverage"]["coverage_ratio"] == 0.167
