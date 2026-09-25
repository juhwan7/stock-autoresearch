from datetime import datetime
from zoneinfo import ZoneInfo

from autoresearch.provider_gap_guard import audit_toss_snapshot


def test_detects_missing_toss_ranking_and_minute_bars():
    toss = {
        "ranking": [{"ticker": "005930"}],
        "minute_by_ticker": {},
        "fetch_errors": {},
    }
    fallback = {
        "ranking": [{"ticker": "005930"}, {"ticker": "000660"}],
    }
    now = datetime(2026, 9, 28, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    result = audit_toss_snapshot(toss, fallback, now)
    assert result["status"] == "degraded"
    assert "000660" in result["missing_vs_fallback"]
    assert result["recommended_action"] == "fallback_provider_and_backfill"


def test_holiday_or_after_hours_does_not_flag_empty_ranking():
    now = datetime(2026, 9, 25, 13, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    result = audit_toss_snapshot({}, {}, now)
    assert result["status"] == "ok"
