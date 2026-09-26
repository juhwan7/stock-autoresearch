import importlib.util
import json

import pytest
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
    module.TEST_REPORT = tmp_path / "latest-test-report.json"
    module.STATE = tmp_path / "state.json"
    module.ISSUES = tmp_path / "market-issues.json"
    module.RECENT_SESSIONS = tmp_path / "recent-sessions.json"
    module.POPULAR_REPORTS = tmp_path / "popular-reports.json"
    module.NEWS_ISSUES = tmp_path / "issue-digest.json"
    module.AI_RESULTS = tmp_path / "data/supervisor/ai-results"
    module.COLLABORATION = tmp_path / "collaboration.json"
    module.AI_RESULTS.mkdir(parents=True, exist_ok=True)
    module.STATE.write_text("{}", encoding="utf-8")

    result_path = tmp_path / "supervisor-result.json"
    result_path.write_text(
        json.dumps(
            {
                "batch_id": "supervisor-20260926T1500+0900",
                "processed_at": "2026-09-26T15:00:00+09:00",
                "supervisor": "A",
                "run_kind": "regular",
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
    module.AI_RESULTS = tmp_path / "data/supervisor/ai-results"
    module.COLLABORATION = tmp_path / "collaboration.json"
    module.AI_RESULTS.mkdir(parents=True, exist_ok=True)
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
    assert state["batch_size"] == 3
    assert state["sensor_interval_minutes"] == 10
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



def test_feedback_handoff_requires_receipt_of_previous_supervisor_feedback():
    module = load_module()
    warnings = []
    current = {
        "batch_id": "supervisor-b-1830",
        "supervisor": "B",
        "feedback_to_other_supervisor": ["A는 센서 누락 원인을 확인할 것"],
    }
    result = {
        "batch_id": "supervisor-a-1900",
        "supervisor": "A",
        "status": "changed",
        "feedback_received": [],
        "feedback_to_other_supervisor": ["B는 수정 결과를 검증할 것"],
    }
    handoff = module.validate_feedback_handoff(current, result, warnings)
    assert handoff["inbound_required"] is True
    assert handoff["inbound_recorded"] is False
    assert handoff["outgoing_recorded"] is True
    assert handoff["complete"] is False
    assert result["status"] == "verification_pending"
    assert any("feedback_received" in item for item in warnings)


def test_feedback_handoff_is_complete_when_both_directions_are_recorded():
    module = load_module()
    warnings = []
    current = {
        "batch_id": "supervisor-a-1900",
        "supervisor": "A",
        "feedback_to_other_supervisor": ["B는 독립 원기사 추정을 반증할 것"],
    }
    result = {
        "batch_id": "supervisor-b-1930",
        "supervisor": "B",
        "status": "changed",
        "feedback_received": ["A의 독립 원기사 추정 검증 요청을 이어받음"],
        "feedback_to_other_supervisor": ["A는 반증 결과를 다음 구현에 반영할 것"],
    }
    handoff = module.validate_feedback_handoff(current, result, warnings)
    assert handoff["source_batch_id"] == "supervisor-a-1900"
    assert handoff["source_supervisor"] == "A"
    assert handoff["target_supervisor"] == "B"
    assert handoff["complete"] is True
    assert result["status"] == "changed"
    assert warnings == []


def test_feedback_handoff_requires_outgoing_feedback_for_regular_supervisor():
    module = load_module()
    warnings = []
    result = {
        "batch_id": "supervisor-a-2000",
        "supervisor": "A",
        "status": "changed",
        "feedback_received": [],
        "feedback_to_other_supervisor": [],
    }
    handoff = module.validate_feedback_handoff({}, result, warnings)
    assert handoff["inbound_required"] is False
    assert handoff["outgoing_recorded"] is False
    assert handoff["complete"] is False
    assert result["status"] == "verification_pending"


def test_e2e_result_is_isolated_from_regular_canonical_state(tmp_path, monkeypatch):
    module = load_module()
    _configure_apply_paths(module, tmp_path)
    module.RECENT_OBSERVATIONS.write_text(
        json.dumps(_window_observations(), ensure_ascii=False),
        encoding="utf-8",
    )
    canonical = {
        "batch_id": "supervisor-20260926T1800+0900",
        "processed_at": "2026-09-26T18:00:00+09:00",
        "supervisor": "A",
        "run_kind": "regular",
        "notify": True,
        "summary": "정규 A",
        "feedback_to_other_supervisor": ["다음 B가 검증"],
    }
    module.REPORT.write_text(json.dumps(canonical, ensure_ascii=False), encoding="utf-8")
    module.STATE.write_text(
        json.dumps({"last_batch_id": canonical["batch_id"], "last_processed_at": canonical["processed_at"]}),
        encoding="utf-8",
    )
    result_path = tmp_path / "supervisor-writer-e2e-20260926T1831+0900.json"
    result_path.write_text(
        json.dumps(
            {
                "batch_id": "supervisor-writer-e2e-20260926T1831+0900",
                "processed_at": "2026-09-26T18:31:00+09:00",
                "supervisor": "B",
                "notify": True,
                "summary": "[테스트] 단일 writer E2E",
                "actions": [{"type": "writer_e2e", "status": "test"}],
                "feedback_to_other_supervisor": ["테스트 후속"],
                "observation_ids": ["obs-1810", "obs-1820", "obs-1830"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "argv", ["감독결과_적용.py", str(result_path)])
    assert module.main() == 0

    stored_canonical = json.loads(module.REPORT.read_text(encoding="utf-8"))
    stored_state = json.loads(module.STATE.read_text(encoding="utf-8"))
    stored_test = json.loads(module.TEST_REPORT.read_text(encoding="utf-8"))
    source = json.loads(result_path.read_text(encoding="utf-8"))

    assert stored_canonical["batch_id"] == canonical["batch_id"]
    assert stored_state["last_batch_id"] == canonical["batch_id"]
    assert stored_test["batch_id"] == "supervisor-writer-e2e-20260926T1831+0900"
    assert stored_test["run_kind"] == "test"
    assert source["run_kind"] == "test"


def test_reconcile_regular_windows_repairs_legacy_test_and_recovery_pointers(tmp_path):
    module = load_module()
    module.ROOT = tmp_path
    module.AI_RESULTS = tmp_path / "data/supervisor/ai-results"
    module.AI_RESULTS.mkdir(parents=True, exist_ok=True)

    regular_a = {
        "batch_id": "supervisor-20260926T2300+0900-a23",
        "processed_at": "2026-09-26T23:05:00+09:00",
        "supervisor": "A",
        "run_kind": "regular",
        "observation_ids": ["a1", "a2", "a3"],
        "observation_slots": [
            "2026-09-26T22:40:00+09:00",
            "2026-09-26T22:50:00+09:00",
            "2026-09-26T23:00:00+09:00",
        ],
        "observation_window_start": "2026-09-26T22:40:00+09:00",
        "observation_window_end": "2026-09-26T23:00:00+09:00",
        "expected_observation_count": 3,
        "received_observation_count": 3,
        "missing_observation_slots": [],
        "observation_window_complete": True,
    }
    regular_b = {
        "batch_id": "supervisor-20260926T2330+0900-b37",
        "processed_at": "2026-09-26T23:37:00+09:00",
        "supervisor": "B",
        "run_kind": "regular",
        "observation_ids": ["b1", "b2", "b3"],
        "observation_slots": [
            "2026-09-26T23:10:00+09:00",
            "2026-09-26T23:20:00+09:00",
            "2026-09-26T23:30:00+09:00",
        ],
        "observation_window_start": "2026-09-26T23:10:00+09:00",
        "observation_window_end": "2026-09-26T23:30:00+09:00",
        "expected_observation_count": 3,
        "received_observation_count": 3,
        "missing_observation_slots": [],
        "observation_window_complete": True,
    }
    test_b = {
        **regular_b,
        "batch_id": "supervisor-writer-e2e-20260926T2350+0900",
        "processed_at": "2026-09-26T23:50:00+09:00",
        "run_kind": "test",
    }
    recovery_a = {
        **regular_a,
        "batch_id": "recovery-20260926T2355+0900",
        "processed_at": "2026-09-26T23:55:00+09:00",
        "supervisor": "Recovery-A",
        "run_kind": "recovery",
    }
    for index, item in enumerate((regular_a, regular_b, test_b, recovery_a)):
        (module.AI_RESULTS / f"{index}.json").write_text(
            json.dumps(item, ensure_ascii=False), encoding="utf-8"
        )

    state = {
        "last_a_window": {"batch_id": recovery_a["batch_id"]},
        "last_b_window": {"batch_id": test_b["batch_id"]},
    }
    module._reconcile_regular_windows(state)

    assert state["last_a_window"]["batch_id"] == regular_a["batch_id"]
    assert state["last_b_window"]["batch_id"] == regular_b["batch_id"]
    assert state["last_a_window"]["complete"] is True
    assert state["last_b_window"]["complete"] is True


def test_window_state_from_legacy_regular_result_infers_complete_from_three_slots():
    module = load_module()
    legacy = {
        "batch_id": "supervisor-20260926T2300+0900-a23",
        "processed_at": "2026-09-26T23:05:50+09:00",
        "supervisor": "A",
        "observation_ids": ["a1", "a2", "a3"],
        "observation_slots": [
            "2026-09-26T22:40:00+09:00",
            "2026-09-26T22:50:00+09:00",
            "2026-09-26T23:00:00+09:00",
        ],
        "observation_window_start": "2026-09-26T22:40:00+09:00",
        "observation_window_end": "2026-09-26T23:00:00+09:00",
        "expected_observation_count": 3,
        "received_observation_count": 3,
        "missing_observation_slots": [],
    }
    state = module._window_state_from_result(legacy)
    assert state["complete"] is True


def test_apply_refuses_older_result_instead_of_silently_switching_batch(tmp_path, monkeypatch):
    module = load_module()
    _configure_apply_paths(module, tmp_path)
    module.RECENT_OBSERVATIONS.write_text(
        json.dumps(_window_observations(), ensure_ascii=False),
        encoding="utf-8",
    )
    module.REPORT.write_text(
        json.dumps(
            {
                "batch_id": "supervisor-20260927T0000+0900-a24",
                "processed_at": "2026-09-27T00:09:11+09:00",
                "supervisor": "A",
                "notify": True,
                "summary": "newer canonical",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    older = tmp_path / "older.json"
    older.write_text(
        json.dumps(
            {
                "batch_id": "supervisor-20260926T2330+0900-b37",
                "processed_at": "2026-09-26T23:37:00+09:00",
                "supervisor": "B",
                "notify": True,
                "summary": "older",
                "feedback_to_other_supervisor": ["next"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "argv", ["감독결과_적용.py", str(older)])
    with pytest.raises(SystemExit, match="stale Supervisor result refused"):
        module.main()

    canonical = json.loads(module.REPORT.read_text(encoding="utf-8"))
    assert canonical["batch_id"] == "supervisor-20260927T0000+0900-a24"



def test_collaboration_state_merges_sensor_aliases_and_keeps_history(tmp_path):
    module = load_module()
    module.COLLABORATION = tmp_path / "collaboration.json"
    first_path = tmp_path / "a.json"
    second_path = tmp_path / "b.json"

    first = {
        "batch_id": "supervisor-a-0000",
        "processed_at": "2026-09-27T00:09:11+09:00",
        "supervisor": "A",
        "status": "verification_pending",
        "summary": "00:00 슬롯 누락",
        "project_improvement_signals": [
            {
                "id": "sensor-slot-0000-missing",
                "status": "investigating",
                "signal": "00:00 canonical observation 누락",
                "verify_after": "다음 센서",
            },
            {
                "id": "issue-digest-apply-stale",
                "status": "verification_pending",
                "signal": "이슈 원장 전진 여부 확인 필요",
            },
        ],
        "changed_paths": ["data/supervisor/ai-results/supervisor-a-0000.json"],
        "next_checks": ["00:10 이후 확인"],
    }
    second = {
        "batch_id": "supervisor-b-0030",
        "processed_at": "2026-09-27T00:35:21+09:00",
        "supervisor": "B",
        "status": "verification_pending",
        "summary": "00:10/00:20/00:30도 누락",
        "project_improvement_signals": [
            {
                "id": "sensor-slot-0000-plus-continuity",
                "status": "investigating",
                "signal": "00:30까지 센서 연속성 이상",
                "verify_after": "Recovery 실행",
            },
            {
                "id": "issue-digest-apply-stale",
                "status": "resolved",
                "signal": "00:09:11까지 실제 전진 확인",
            },
        ],
        "changed_paths": ["data/supervisor/ai-results/supervisor-b-0030.json"],
        "next_checks": ["self-chain/heartbeat 확인"],
    }

    first_path.write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")
    second_path.write_text(json.dumps(second, ensure_ascii=False), encoding="utf-8")
    module.update_collaboration_state(first, first_path)
    module.update_collaboration_state(second, second_path)

    stored = json.loads(module.COLLABORATION.read_text(encoding="utf-8"))
    by_id = {x["incident_id"]: x for x in stored["incidents"]}
    assert set(by_id) == {"sensor-continuity", "issue-digest-apply"}
    assert by_id["sensor-continuity"]["status"] == "investigating"
    assert len(by_id["sensor-continuity"]["history"]) == 2
    assert by_id["issue-digest-apply"]["status"] == "resolved"
    assert stored["active_incident_count"] == 1
    assert stored["resolved_incident_count"] == 1
    assert stored["last_turn"]["batch_id"] == "supervisor-b-0030"
    assert stored["last_turn"]["change_kind"] == "result_only"


def test_collaboration_state_does_not_turn_no_change_into_active_incident(tmp_path):
    module = load_module()
    module.COLLABORATION = tmp_path / "collaboration.json"
    source = tmp_path / "result.json"
    result = {
        "batch_id": "supervisor-a-stable",
        "processed_at": "2026-09-27T01:00:00+09:00",
        "supervisor": "A",
        "status": "ok",
        "summary": "변경 필요 없음",
        "project_improvement_signals": [
            {
                "id": "ui-review-stable",
                "status": "no_change",
                "signal": "현재 UI 구조 유지가 더 안전",
            }
        ],
        "changed_paths": [],
        "next_checks": [],
    }
    source.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    module.update_collaboration_state(result, source)
    stored = json.loads(module.COLLABORATION.read_text(encoding="utf-8"))
    assert stored["active_incident_count"] == 0
    assert stored["resolved_incident_count"] == 1
    assert stored["status"] == "healthy"
