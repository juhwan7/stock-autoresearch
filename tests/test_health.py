import json
from datetime import datetime

import autoresearch.health as health
from autoresearch.health import KST, HealthWatchdog


def make_watchdog(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "health.yaml").write_text(
        """
thresholds:
  warn_consecutive: 2
  critical_consecutive: 4
  market_stale_minutes_during_session: 25
  risk_stale_minutes: 25
  macro_stale_minutes: 25
data:
  state_file: data/health/state.json
  latest_file: data/health/latest.json
components:
  market:
    runtime_file: data/market/runtime.json
  risk:
    runtime_file: data/risk/runtime.json
    latest_file: data/risk/latest.json
  macro:
    file: data/macro/current.json
""",
        encoding="utf-8",
    )
    return HealthWatchdog(tmp_path)


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 9, 25, 10, 0, tzinfo=KST)
        return value if tz is None else value.astimezone(tz)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_watchdog_detects_stale_market_and_macro(tmp_path, monkeypatch):
    watchdog = make_watchdog(tmp_path)
    old = "2026-09-25T09:00:00+09:00"
    write_json(
        tmp_path / "data/market/runtime.json",
        {"generated_at": old, "source_status": "ok"},
    )
    write_json(
        tmp_path / "data/risk/runtime.json",
        {"generated_at": "2026-09-25T09:55:00+09:00"},
    )
    write_json(
        tmp_path / "data/risk/latest.json",
        {"macro": {}, "upcoming_events": [{"title": "x"}]},
    )
    write_json(
        tmp_path / "data/macro/current.json",
        {"captured_at": old, "values": {}},
    )
    monkeypatch.setattr(health, "datetime", FixedDateTime)

    result = watchdog.run()
    codes = {x["code"] for x in result["issues"]}
    assert "stale" in codes
    assert result["status"] in {"NOTICE", "WARN", "CRITICAL"}


def test_repeated_failure_escalates(tmp_path, monkeypatch):
    watchdog = make_watchdog(tmp_path)
    write_json(
        tmp_path / "data/market/runtime.json",
        {
            "generated_at": "2026-09-25T09:59:00+09:00",
            "source_status": "needs_credentials",
        },
    )
    write_json(
        tmp_path / "data/risk/runtime.json",
        {"generated_at": "2026-09-25T09:59:00+09:00"},
    )
    write_json(
        tmp_path / "data/risk/latest.json",
        {"macro": {}, "upcoming_events": [{"title": "x"}]},
    )
    write_json(
        tmp_path / "data/macro/current.json",
        {"captured_at": "2026-09-25T09:59:00+09:00", "values": {}},
    )
    monkeypatch.setattr(health, "datetime", FixedDateTime)

    first = watchdog.run()
    second = watchdog.run()
    assert first["status"] == "NOTICE"
    assert second["status"] == "WARN"


def test_watchdog_identifies_toss_collector_outage(tmp_path, monkeypatch):
    watchdog = make_watchdog(tmp_path)
    write_json(
        tmp_path / "data/market/runtime.json",
        {
            "generated_at": "2026-09-25T09:59:00+09:00",
            "source_status": "toss_snapshot_unavailable",
            "provider": "toss",
        },
    )
    write_json(
        tmp_path / "data/risk/runtime.json",
        {"generated_at": "2026-09-25T09:59:00+09:00"},
    )
    write_json(
        tmp_path / "data/risk/latest.json",
        {"macro": {}, "upcoming_events": [{"title": "x"}]},
    )
    write_json(
        tmp_path / "data/macro/current.json",
        {"captured_at": "2026-09-25T09:59:00+09:00", "values": {}},
    )
    monkeypatch.setattr(health, "datetime", FixedDateTime)

    result = watchdog.run()
    codes = {x["code"] for x in result["issues"]}
    assert "toss-collector-unavailable" in codes


def test_watchdog_accepts_fresh_toss_snapshot(tmp_path, monkeypatch):
    watchdog = make_watchdog(tmp_path)
    write_json(
        tmp_path / "data/market/runtime.json",
        {
            "generated_at": "2026-09-25T09:59:00+09:00",
            "source_status": "ok",
            "provider": "toss",
            "fallback_used": False,
        },
    )
    write_json(
        tmp_path / "data/providers/toss/latest.json",
        {
            "captured_at": "2026-09-25T09:59:30+09:00",
            "collector": {
                "subscriptions": ["trade:kr:005930"],
                "rejected": [],
                "last_message_at": "2026-09-25T09:59:40+09:00",
            },
        },
    )
    write_json(
        tmp_path / "data/risk/runtime.json",
        {"generated_at": "2026-09-25T09:59:00+09:00"},
    )
    write_json(
        tmp_path / "data/risk/latest.json",
        {"macro": {}, "upcoming_events": [{"title": "x"}]},
    )
    write_json(
        tmp_path / "data/macro/current.json",
        {"captured_at": "2026-09-25T09:59:00+09:00", "values": {}},
    )
    monkeypatch.setattr(health, "datetime", FixedDateTime)

    result = watchdog.run()
    codes = {x["code"] for x in result["issues"]}
    assert "snapshot-missing" not in codes
    assert "snapshot-stale" not in codes
    assert "trade-stale" not in codes
    assert "subscription-empty" not in codes


def test_watchdog_flags_stale_toss_snapshot(tmp_path, monkeypatch):
    watchdog = make_watchdog(tmp_path)
    write_json(
        tmp_path / "data/market/runtime.json",
        {
            "generated_at": "2026-09-25T09:59:00+09:00",
            "source_status": "ok",
            "provider": "toss",
        },
    )
    write_json(
        tmp_path / "data/providers/toss/latest.json",
        {
            "captured_at": "2026-09-25T09:40:00+09:00",
            "collector": {
                "subscriptions": ["trade:kr:005930"],
                "rejected": [],
                "last_message_at": "2026-09-25T09:40:00+09:00",
            },
        },
    )
    write_json(
        tmp_path / "data/risk/runtime.json",
        {"generated_at": "2026-09-25T09:59:00+09:00"},
    )
    write_json(
        tmp_path / "data/risk/latest.json",
        {"macro": {}, "upcoming_events": [{"title": "x"}]},
    )
    write_json(
        tmp_path / "data/macro/current.json",
        {"captured_at": "2026-09-25T09:59:00+09:00", "values": {}},
    )
    monkeypatch.setattr(health, "datetime", FixedDateTime)

    result = watchdog.run()
    codes = {x["code"] for x in result["issues"]}
    assert "snapshot-stale" in codes
    assert "trade-stale" in codes


def test_watchdog_marks_kiwoom_as_toss_fallback(tmp_path, monkeypatch):
    watchdog = make_watchdog(tmp_path)
    write_json(
        tmp_path / "data/market/runtime.json",
        {
            "generated_at": "2026-09-25T09:59:00+09:00",
            "source_status": "ok",
            "provider": "kiwoom",
            "fallback_used": True,
        },
    )
    write_json(
        tmp_path / "data/risk/runtime.json",
        {"generated_at": "2026-09-25T09:59:00+09:00"},
    )
    write_json(
        tmp_path / "data/risk/latest.json",
        {"macro": {}, "upcoming_events": [{"title": "x"}]},
    )
    write_json(
        tmp_path / "data/macro/current.json",
        {"captured_at": "2026-09-25T09:59:00+09:00", "values": {}},
    )
    monkeypatch.setattr(health, "datetime", FixedDateTime)

    result = watchdog.run()
    codes = {x["code"] for x in result["issues"]}
    assert "toss-fallback-active" in codes


def test_watchdog_accepts_persisted_toss_summary_without_raw_snapshot(
    tmp_path, monkeypatch
):
    watchdog = make_watchdog(tmp_path)
    write_json(
        tmp_path / "data/market/runtime.json",
        {
            "generated_at": "2026-09-25T09:59:00+09:00",
            "source_status": "ok",
            "provider": "toss",
        },
    )
    write_json(
        tmp_path / "data/providers/toss/status.json",
        {
            "available": True,
            "captured_at": "2026-09-25T09:59:30+09:00",
            "collector": {
                "subscription_count": 80,
                "rejected_count": 0,
                "last_message_at": "2026-09-25T09:59:40+09:00",
            },
        },
    )
    write_json(
        tmp_path / "data/risk/runtime.json",
        {"generated_at": "2026-09-25T09:59:00+09:00"},
    )
    write_json(
        tmp_path / "data/risk/latest.json",
        {"macro": {}, "upcoming_events": [{"title": "x"}]},
    )
    write_json(
        tmp_path / "data/macro/current.json",
        {"captured_at": "2026-09-25T09:59:00+09:00", "values": {}},
    )
    monkeypatch.setattr(health, "datetime", FixedDateTime)

    result = watchdog.run()
    codes = {x["code"] for x in result["issues"]}
    assert "snapshot-missing" not in codes
    assert "snapshot-stale" not in codes
    assert "subscription-empty" not in codes
    assert "trade-stale" not in codes


def test_persisted_summary_uses_longer_cross_runner_threshold(
    tmp_path, monkeypatch
):
    watchdog = make_watchdog(tmp_path)
    write_json(
        tmp_path / "data/market/runtime.json",
        {
            "generated_at": "2026-09-25T09:59:00+09:00",
            "source_status": "ok",
            "provider": "toss",
        },
    )
    write_json(
        tmp_path / "data/providers/toss/status.json",
        {
            "available": True,
            "captured_at": "2026-09-25T09:48:00+09:00",
            "collector": {
                "subscription_count": 80,
                "rejected_count": 0,
                "last_message_at": "2026-09-25T09:48:00+09:00",
            },
        },
    )
    write_json(
        tmp_path / "data/risk/runtime.json",
        {"generated_at": "2026-09-25T09:59:00+09:00"},
    )
    write_json(
        tmp_path / "data/risk/latest.json",
        {"macro": {}, "upcoming_events": [{"title": "x"}]},
    )
    write_json(
        tmp_path / "data/macro/current.json",
        {"captured_at": "2026-09-25T09:59:00+09:00", "values": {}},
    )
    monkeypatch.setattr(health, "datetime", FixedDateTime)

    result = watchdog.run()
    codes = {x["code"] for x in result["issues"]}
    assert "snapshot-stale" not in codes
    assert "trade-stale" not in codes


def test_raw_snapshot_keeps_strict_local_freshness_threshold(
    tmp_path, monkeypatch
):
    watchdog = make_watchdog(tmp_path)
    write_json(
        tmp_path / "data/market/runtime.json",
        {
            "generated_at": "2026-09-25T09:59:00+09:00",
            "source_status": "ok",
            "provider": "toss",
        },
    )
    write_json(
        tmp_path / "data/providers/toss/latest.json",
        {
            "captured_at": "2026-09-25T09:48:00+09:00",
            "collector": {
                "subscriptions": ["trade:kr:005930"],
                "rejected": [],
                "last_message_at": "2026-09-25T09:48:00+09:00",
            },
        },
    )
    write_json(
        tmp_path / "data/risk/runtime.json",
        {"generated_at": "2026-09-25T09:59:00+09:00"},
    )
    write_json(
        tmp_path / "data/risk/latest.json",
        {"macro": {}, "upcoming_events": [{"title": "x"}]},
    )
    write_json(
        tmp_path / "data/macro/current.json",
        {"captured_at": "2026-09-25T09:59:00+09:00", "values": {}},
    )
    monkeypatch.setattr(health, "datetime", FixedDateTime)

    result = watchdog.run()
    codes = {x["code"] for x in result["issues"]}
    assert "snapshot-stale" in codes
    assert "trade-stale" in codes


def test_macro_empty_is_notice_outside_market_window(tmp_path, monkeypatch):
    watchdog = make_watchdog(tmp_path)

    class WeekendDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2026, 9, 26, 10, 0, tzinfo=KST)
            return value if tz is None else value.astimezone(tz)

    write_json(
        tmp_path / "data/market/runtime.json",
        {"generated_at": "2026-09-26T09:59:00+09:00", "source_status": "outside_domestic_monitor_window"},
    )
    write_json(
        tmp_path / "data/risk/runtime.json",
        {"generated_at": "2026-09-26T09:59:00+09:00"},
    )
    write_json(
        tmp_path / "data/risk/latest.json",
        {"macro": {}, "upcoming_events": [{"title": "x"}]},
    )
    write_json(
        tmp_path / "data/macro/current.json",
        {"captured_at": "2026-09-26T09:59:00+09:00", "values": {}},
    )
    monkeypatch.setattr(health, "datetime", WeekendDateTime)

    result = watchdog.run()
    macro_issue = next(x for x in result["issues"] if x["code"] == "unavailable")
    assert macro_issue["severity"] == "NOTICE"


def test_google_news_fallback_success_stays_notice(tmp_path):
    watchdog = make_watchdog(tmp_path)
    source_status = {
        "google_news:a": {"status": "empty"},
        "google_news:b": {"status": "empty"},
        "google_news:c": {"status": "error"},
        "google_news:d": {"status": "empty"},
        "google_news:e": {"status": "empty"},
        "google_news:f": {"status": "ok"},
        "google_news:broad_fallback": {"status": "ok", "count": 30},
    }
    write_json(
        tmp_path / "data/discovery/latest.json",
        {"source_status": source_status},
    )

    issues = watchdog._check_discovery()
    issue = next(x for x in issues if x["code"] == "google-news-degraded")
    assert issue["severity"] == "NOTICE"
