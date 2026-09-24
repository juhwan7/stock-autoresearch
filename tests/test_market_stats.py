from autoresearch.market_stats import MarketStats, describe_event_sample


CFG = {
    "minute_analysis": {
        "baseline_window": 3,
        "burst_ratio": 2.0,
        "min_burst_amount_krw": 100,
        "close_watch_start": "14:30",
        "continuous_end": "15:20",
    },
    "universe": {"recent_listing_calendar_days": 90},
    "coflow": {"minimum_members": 2},
}


def rows(mult=1):
    return [
        {"time": "14:28", "open": 100, "high": 101, "low": 99, "close": 100, "amount": 100 * mult},
        {"time": "14:29", "open": 100, "high": 101, "low": 99, "close": 100, "amount": 100 * mult},
        {"time": "14:30", "open": 100, "high": 102, "low": 100, "close": 101, "amount": 500 * mult},
        {"time": "14:31", "open": 101, "high": 104, "low": 101, "close": 103, "amount": 600 * mult},
    ]


def test_turnover_burst_and_close_share():
    engine = MarketStats(CFG)
    result = engine.summarize_stock("A", rows(), {"name": "A"})
    assert result is not None
    assert result.burst_count >= 1
    assert result.close_watch_share > 0.5
    assert result.return_pct > 0


def test_group_coflow():
    engine = MarketStats(CFG)
    result = engine.summarize_market(
        {"A": rows(), "B": rows(2)},
        {
            "A": {"name": "A", "group_id": "한화"},
            "B": {"name": "B", "group_id": "한화"},
        },
    )
    assert result["status"] == "ok"
    assert result["coflow_groups"][0]["group"] == "한화"


def test_event_distribution_uses_median():
    stats = describe_event_sample(
        [{"mae": -2}, {"mae": -4}, {"mae": -20}],
        ["mae"],
    )
    assert stats["sample_size"] == 3
    assert stats["fields"]["mae"]["median"] == -4.0
