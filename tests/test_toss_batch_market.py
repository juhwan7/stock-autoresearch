from datetime import datetime, timedelta

from autoresearch.toss_batch_market import (
    KST,
    _calibrate_interval,
    _daily_tracked_universe,
    _merge_rows,
)


def test_daily_union_keeps_former_top50_stock():
    now = datetime(2026, 9, 28, 10, 6, tzinfo=KST)
    previous = {
        "captured_at": (now - timedelta(minutes=6)).isoformat(),
        "ranking_fresh_today": True,
        "tracked_universe": [
            {
                "ticker": "005930",
                "name": "삼성전자",
                "last_top50_rank": 47,
                "in_current_top50": True,
                "current_rank": 47,
            }
        ],
    }
    current = [
        {"ticker": "000660", "name": "SK하이닉스"},
    ]
    rows = _daily_tracked_universe(
        current,
        previous,
        now,
        ranking_fresh_today=True,
    )
    samsung = next(row for row in rows if row["ticker"] == "005930")
    assert samsung["in_current_top50"] is False
    assert samsung["current_rank"] is None
    assert samsung["last_top50_rank"] == 47


def test_daily_union_resets_on_new_day():
    now = datetime(2026, 9, 29, 9, 6, tzinfo=KST)
    previous = {
        "captured_at": datetime(2026, 9, 28, 15, 30, tzinfo=KST).isoformat(),
        "ranking_fresh_today": True,
        "tracked_universe": [{"ticker": "005930", "name": "삼성전자"}],
    }
    rows = _daily_tracked_universe(
        [{"ticker": "000660", "name": "SK하이닉스"}],
        previous,
        now,
        ranking_fresh_today=True,
    )
    assert [row["ticker"] for row in rows] == ["000660"]


def test_stale_ranking_does_not_add_new_universe():
    now = datetime(2026, 9, 25, 11, 30, tzinfo=KST)
    rows = _daily_tracked_universe(
        [{"ticker": "005930", "name": "삼성전자"}],
        {},
        now,
        ranking_fresh_today=False,
    )
    assert rows == []


def test_calibration_matches_exact_interval_total():
    previous_at = datetime(2026, 9, 28, 10, 0, tzinfo=KST)
    rows = [
        {
            "timestamp": datetime(2026, 9, 28, 10, 1, tzinfo=KST).isoformat(),
            "amount": 100.0,
        },
        {
            "timestamp": datetime(2026, 9, 28, 10, 2, tzinfo=KST).isoformat(),
            "amount": 300.0,
        },
    ]
    _calibrate_interval(rows, previous_at=previous_at, interval_total=800.0)
    assert round(sum(row["amount"] for row in rows), 6) == 800.0
    assert all(row["calibrated_to_exact_interval_total"] for row in rows)


def test_merge_rows_deduplicates_same_minute():
    now = datetime(2026, 9, 28, 10, 6, tzinfo=KST)
    stamp = datetime(2026, 9, 28, 10, 5, tzinfo=KST).isoformat()
    merged = _merge_rows(
        [{"timestamp": stamp, "close": 100, "volume": 10}],
        [{"timestamp": stamp, "close": 101, "volume": 20}],
        now,
    )
    assert len(merged) == 1
    assert merged[0]["close"] == 101
