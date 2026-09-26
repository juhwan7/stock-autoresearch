from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "장기기억_갱신.py"


def load_module():
    spec = importlib.util.spec_from_file_location("long_memory_refresh", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_memory_refresh_builds_hot_and_cold_layers(tmp_path):
    module = load_module()
    module.ROOT = tmp_path
    module.MEMORY = tmp_path / "memory"
    module.CURRENT = module.MEMORY / "current"
    module.REPORT = tmp_path / "data/supervisor/latest-report.json"
    module.OPERATIONS = tmp_path / "data/operations/status.json"
    module.HEALTH = tmp_path / "data/health/latest.json"
    module.QUEUE = tmp_path / "data/supervisor/question_queue.json"
    module.ISSUES = tmp_path / "data/news/issue-digest.json"
    module.AI_RESULTS = tmp_path / "data/supervisor/ai-results"

    for path in [module.REPORT, module.OPERATIONS, module.HEALTH, module.QUEUE, module.ISSUES]:
        path.parent.mkdir(parents=True, exist_ok=True)
    module.AI_RESULTS.mkdir(parents=True, exist_ok=True)

    report = {
        "batch_id": "supervisor-test-a",
        "processed_at": "2026-09-26T17:00:00+09:00",
        "supervisor": "A",
        "status": "verification_pending",
        "summary": ["시장 점검", "UI 점검"],
        "market_narrative": "시장 해설",
        "market_focus": [{"issue_id": "oil-risk", "reason": "유가"}],
        "work_axes_reviewed": [
            {"axis": "news", "status": "reviewed"},
            {"axis": "data_quality", "status": "reviewed"},
            {"axis": "bugs", "status": "reviewed"},
            {"axis": "ux", "status": "reviewed"},
            {"axis": "testing", "status": "reviewed"},
        ],
        "project_improvement_signals": [
            {"id": "x", "status": "verification_pending", "signal": "검증 필요"}
        ],
        "next_checks": ["다음 확인"],
        "changed_paths": ["site/index.html"],
    }
    module.REPORT.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    (module.AI_RESULTS / "a.json").write_text(
        json.dumps(report, ensure_ascii=False), encoding="utf-8"
    )
    module.OPERATIONS.write_text(
        json.dumps({"status": "normal", "cards": [], "user_actions": []}),
        encoding="utf-8",
    )
    module.HEALTH.write_text(json.dumps({"status": "OK"}), encoding="utf-8")
    module.QUEUE.write_text(
        json.dumps({"open_count": 1, "questions": []}), encoding="utf-8"
    )
    module.ISSUES.write_text(
        json.dumps(
            {"issues": [{"issue_id": "oil-risk", "status": "ACTIVE", "title": "유가"}]}
        ),
        encoding="utf-8",
    )

    assert module.main() == 0
    assert (module.MEMORY / "INDEX.md").exists()
    assert (module.CURRENT / "현재상태.md").exists()
    assert (module.CURRENT / "다음확인사항.md").exists()
    assert list((module.MEMORY / "supervisors" / "A").glob("*.md"))
    assert (module.MEMORY / "snapshots" / "daily" / "2026-09-26.md").exists()

    index = (module.MEMORY / "INDEX.md").read_text(encoding="utf-8")
    assert "이번 작업축: 5개" in index
    assert "oil-risk" in index


def test_memory_refresh_does_not_invent_when_report_missing(tmp_path):
    module = load_module()
    module.REPORT = tmp_path / "missing.json"
    assert module.main() == 0
