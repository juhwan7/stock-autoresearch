import importlib.util
import json
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "감독결과_적용.py"


def load_module():
    spec = importlib.util.spec_from_file_location("supervisor_result_apply", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_news_issue_digest_keeps_active_and_recent_resolved_for_seven_days(tmp_path):
    module = load_module()
    module.NEWS_ISSUES = tmp_path / "issue-digest.json"
    module.NEWS_ISSUES.parent.mkdir(parents=True, exist_ok=True)
    module.NEWS_ISSUES.write_text(
        json.dumps(
            {
                "issues": [
                    {
                        "issue_id": "old-active",
                        "title": "오래됐지만 지속 중",
                        "status": "ACTIVE",
                        "last_updated": "2026-09-01T00:00:00+09:00",
                    },
                    {
                        "issue_id": "old-resolved",
                        "title": "오래된 해소",
                        "status": "RESOLVED",
                        "last_updated": "2026-09-10T00:00:00+09:00",
                    },
                    {
                        "issue_id": "recent-resolved",
                        "title": "최근 해소",
                        "status": "RESOLVED",
                        "last_updated": "2026-09-24T00:00:00+09:00",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    module.update_news_issue_digest(
        {
            "processed_at": "2026-09-26T15:00:00+09:00",
            "news_issue_digest": {
                "issues": [
                    {
                        "issue_id": "new-meeting",
                        "title": "새 정상회담",
                        "status": "NEW",
                        "severity": "MEDIUM",
                        "summary": "새 이슈",
                    }
                ]
            },
        }
    )

    stored = json.loads(module.NEWS_ISSUES.read_text(encoding="utf-8"))
    ids = {x["issue_id"] for x in stored["issues"]}
    assert "old-active" in ids
    assert "recent-resolved" in ids
    assert "new-meeting" in ids
    assert "old-resolved" not in ids
    assert stored["retention_days"] == 7
    assert stored["max_issues"] == 100


def test_news_issue_digest_caps_at_100_and_tracks_status_change(tmp_path):
    module = load_module()
    module.NEWS_ISSUES = tmp_path / "issue-digest.json"
    issues = [
        {
            "issue_id": f"issue-{i:03d}",
            "title": f"이슈 {i}",
            "status": "ACTIVE",
            "severity": "LOW",
            "last_updated": "2026-09-26T12:00:00+09:00",
        }
        for i in range(105)
    ]
    issues[0]["status"] = "WATCHING"
    module.NEWS_ISSUES.write_text(
        json.dumps({"issues": issues}, ensure_ascii=False),
        encoding="utf-8",
    )

    module.update_news_issue_digest(
        {
            "processed_at": "2026-09-26T15:30:00+09:00",
            "news_issue_digest": {
                "issues": [
                    {
                        "issue_id": "issue-000",
                        "title": "이슈 0",
                        "status": "ESCALATING",
                        "severity": "HIGH",
                        "change_reason": "새 근거로 강화",
                    }
                ]
            },
        }
    )

    stored = json.loads(module.NEWS_ISSUES.read_text(encoding="utf-8"))
    assert len(stored["issues"]) == 100
    changed = next(x for x in stored["issues"] if x["issue_id"] == "issue-000")
    assert changed["status"] == "ESCALATING"
    assert changed["history"][-1]["from"] == "WATCHING"
    assert changed["history"][-1]["to"] == "ESCALATING"


def test_main_recovers_missing_changed_paths_without_blocking_apply(tmp_path, monkeypatch):
    module = load_module()
    module.REPORT = tmp_path / "latest-report.json"
    module.STATE = tmp_path / "state.json"
    module.ISSUES = tmp_path / "market-issues.json"
    module.RECENT_SESSIONS = tmp_path / "recent-sessions.json"
    module.POPULAR_REPORTS = tmp_path / "popular-reports.json"
    module.NEWS_ISSUES = tmp_path / "issue-digest.json"
    module.STATE.write_text("{}", encoding="utf-8")

    result_path = tmp_path / "supervisor-result.json"
    result_path.write_text(
        json.dumps(
            {
                "batch_id": "supervisor-test",
                "processed_at": "2026-09-26T15:00:00+09:00",
                "notify": True,
                "summary": ["변화 적음"],
                "actions": ["검증"],
                "next_checks": ["다음 확인"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "argv", ["감독결과_적용.py", str(result_path)])
    assert module.main() == 0

    applied = json.loads(module.REPORT.read_text(encoding="utf-8"))
    assert applied["changed_paths"] == [str(result_path)]
    assert any("changed_paths" in x for x in applied["validation_warnings"])
