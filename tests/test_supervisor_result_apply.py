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


def test_issue_merge_deduplicates_sources_and_records_additional_update(tmp_path):
    module = load_module()
    module.NEWS_ISSUES = tmp_path / "issue-digest.json"
    module.NEWS_ISSUES.write_text(
        json.dumps(
            {
                "issues": [
                    {
                        "issue_id": "north-korea-missile",
                        "title": "북한 탄도미사일",
                        "status": "ACTIVE",
                        "summary": "최초 발사 보도",
                        "latest_update": "합참 확인",
                        "first_detected": "2026-09-26T10:00:00+09:00",
                        "last_updated": "2026-09-26T10:00:00+09:00",
                        "status_changed_at": "2026-09-26T10:00:00+09:00",
                        "sources": [
                            {"publisher": "연합뉴스", "title": "합참 확인", "url": "https://example.com/a"}
                        ],
                        "history": [],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    module.update_news_issue_digest(
        {
            "processed_at": "2026-09-26T12:00:00+09:00",
            "news_issue_digest": {
                "issues": [
                    {
                        "issue_id": "north-korea-missile",
                        "title": "북한 탄도미사일",
                        "status": "ACTIVE",
                        "summary": "일본 방위성이 비행거리 정보를 추가 발표",
                        "latest_update": "일본 방위성 비행거리 발표",
                        "sources": [
                            {"publisher": "연합뉴스", "title": "합참 확인", "url": "https://example.com/a"},
                            {"publisher": "Reuters", "title": "Japan adds flight details", "url": "https://example.com/b"},
                        ],
                    }
                ]
            },
        }
    )

    stored = json.loads(module.NEWS_ISSUES.read_text(encoding="utf-8"))
    issue = next(x for x in stored["issues"] if x["issue_id"] == "north-korea-missile")
    assert len(issue["sources"]) == 2
    assert issue["source_count"] == 2
    assert issue["status_changed_at"] == "2026-09-26T10:00:00+09:00"
    assert issue["age_hours"] == 2.0
    assert "추가 소식" in issue["history"][-1]["note"]



def _configure_apply_paths(module, tmp_path):
    module.REPORT = tmp_path / "latest-report.json"
    module.STATE = tmp_path / "state.json"
    module.ISSUES = tmp_path / "market-issues.json"
    module.RECENT_SESSIONS = tmp_path / "recent-sessions.json"
    module.POPULAR_REPORTS = tmp_path / "popular-reports.json"
    module.NEWS_ISSUES = tmp_path / "issue-digest.json"
    module.RECENT_OBSERVATIONS = tmp_path / "recent.json"
    module.DISAGREEMENTS = tmp_path / "disagreements.json"
    module.STATE.write_text("{}", encoding="utf-8")


def _window_observations():
    return {
        "schema_version": 2,
        "observations": [
            {
                "observation_id": "obs-1810",
                "observed_at": "2026-09-26T18:11:00+09:00",
                "slot_at": "2026-09-26T18:10:00+09:00",
                "validation": {"status": "ok"},
            },
            {
                "observation_id": "obs-1820",
                "observed_at": "2026-09-26T18:22:00+09:00",
                "slot_at": "2026-09-26T18:20:00+09:00",
                "validation": {"status": "ok"},
            },
            {
                "observation_id": "obs-1830",
                "observed_at": "2026-09-26T18:31:00+09:00",
                "slot_at": "2026-09-26T18:30:00+09:00",
                "validation": {"status": "ok"},
            },
        ],
    }


def test_main_recovers_missing_observation_ids_from_complete_slot_window(tmp_path, monkeypatch):
    module = load_module()
    _configure_apply_paths(module, tmp_path)
    module.RECENT_OBSERVATIONS.write_text(
        json.dumps(_window_observations(), ensure_ascii=False),
        encoding="utf-8",
    )
    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "batch_id": "supervisor-b-1830",
                "processed_at": "2026-09-26T18:30:00+09:00",
                "supervisor": "B",
                "notify": True,
                "summary": "3슬롯 검증",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "argv", ["감독결과_적용.py", str(result_path)])
    assert module.main() == 0

    applied = json.loads(module.REPORT.read_text(encoding="utf-8"))
    state = json.loads(module.STATE.read_text(encoding="utf-8"))
    assert applied["observation_ids"] == ["obs-1810", "obs-1820", "obs-1830"]
    assert applied["observation_window_complete"] is True
    assert applied["observation_completeness_ratio"] == 1.0
    assert state["last_processed_observation_id"] == "obs-1830"
    assert state["last_processed_slot"] == "2026-09-26T18:30:00+09:00"
    assert state["last_b_window"]["complete"] is True


def test_main_does_not_advance_pointer_for_ids_outside_window(tmp_path, monkeypatch):
    module = load_module()
    _configure_apply_paths(module, tmp_path)
    payload = _window_observations()
    payload["observations"].insert(
        0,
        {
            "observation_id": "obs-1800",
            "observed_at": "2026-09-26T18:01:00+09:00",
            "slot_at": "2026-09-26T18:00:00+09:00",
            "validation": {"status": "ok"},
        },
    )
    module.RECENT_OBSERVATIONS.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    module.STATE.write_text(
        json.dumps(
            {
                "last_processed_observation_id": "obs-prev",
                "processed_observation_ids_recent": ["obs-prev"],
            }
        ),
        encoding="utf-8",
    )
    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "batch_id": "supervisor-b-wrong-window",
                "processed_at": "2026-09-26T18:30:00+09:00",
                "supervisor": "B",
                "notify": True,
                "summary": "잘못된 슬롯",
                "observation_ids": ["obs-1800"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "argv", ["감독결과_적용.py", str(result_path)])
    assert module.main() == 0

    applied = json.loads(module.REPORT.read_text(encoding="utf-8"))
    state = json.loads(module.STATE.read_text(encoding="utf-8"))
    assert applied["observation_window_complete"] is False
    assert applied["status"] == "verification_pending"
    assert applied["observation_completeness_ratio"] == 0.0
    assert state["last_processed_observation_id"] == "obs-prev"
    assert state["processed_observation_ids_recent"] == ["obs-prev"]


def test_supervisor_disagreement_is_preserved_for_followup(tmp_path, monkeypatch):
    module = load_module()
    _configure_apply_paths(module, tmp_path)
    module.RECENT_OBSERVATIONS.write_text(
        json.dumps(_window_observations(), ensure_ascii=False),
        encoding="utf-8",
    )
    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "batch_id": "supervisor-b-disagreement",
                "processed_at": "2026-09-26T18:30:00+09:00",
                "supervisor": "B",
                "notify": True,
                "summary": "A 판단 반증 대기",
                "observation_ids": ["obs-1810", "obs-1820", "obs-1830"],
                "supervisor_disagreements": [
                    {
                        "disagreement_id": "news-independence-1",
                        "topic": "기사 급증을 독립근거 증가로 볼 수 있는가",
                        "a_position": "중요도 상승",
                        "b_position": "재전송 가능성 검증 필요",
                        "status": "open",
                        "evidence_needed": ["원기사 계열 확인"],
                        "verify_after": "다음 B",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "argv", ["감독결과_적용.py", str(result_path)])
    assert module.main() == 0

    stored = json.loads(module.DISAGREEMENTS.read_text(encoding="utf-8"))
    assert stored["open_count"] == 1
    item = stored["items"][0]
    assert item["disagreement_id"] == "news-independence-1"
    assert item["a_position"] == "중요도 상승"
    assert item["b_position"] == "재전송 가능성 검증 필요"
