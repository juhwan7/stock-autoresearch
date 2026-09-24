from datetime import datetime

from autoresearch.market_intel import KST, MarketIntelEngine, load_event_csv


def make_engine(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "market_intel.yaml").write_text(
        """
minute_analysis:
  baseline_window: 3
  burst_ratio: 2
  min_burst_amount_krw: 100
  close_watch_start: "14:30"
  continuous_end: "15:20"
data:
  stats_dir: data/market/stats
statistics:
  min_sample_size: 2
""",
        encoding="utf-8",
    )
    return MarketIntelEngine(tmp_path, "dry-run")


def signal_rows():
    return [
        {"time": "14:30", "open": 100, "high": 101, "low": 99, "close": 100, "amount": 1000},
        {"time": "15:20", "open": 104, "high": 106, "low": 103, "close": 105, "amount": 2000},
        {"time": "15:30", "open": 105, "high": 106, "low": 104, "close": 104, "amount": 1500},
    ]


def next_day_rows():
    return [
        {"time": "09:00", "open": 106, "high": 108, "low": 105, "close": 107, "amount": 1000},
        {"time": "12:00", "open": 107, "high": 110, "low": 102, "close": 103, "amount": 1000},
        {"time": "15:30", "open": 103, "high": 104, "low": 101, "close": 102, "amount": 1000},
    ]


def quantitative():
    return {
        "status": "ok",
        "stocks": [
            {
                "ticker": "A",
                "name": "테스트",
                "return_pct": 4.0,
                "total_amount": 4500,
                "close_watch_share": 0.7,
                "median_minute_amount": 600_000_000,
                "max_minute_amount": 2_500_000_000,
                "amount_threshold_counts": {
                    "500000000": 5,
                    "1000000000": 3,
                    "2000000000": 1,
                    "5000000000": 0,
                },
                "burst_count": 2,
                "positive_burst_times": ["14:30", "14:31"],
                "max_burst_ratio": 3.0,
                "minute_coverage_start": "09:00",
                "minute_coverage_end": "15:20",
                "full_regular_session": True,
                "high_position": 0.8,
                "group_id": "G",
                "sector": "S",
            }
        ],
        "recent_listings": {
            "positive_burst_count": 4,
            "threshold_event_counts": {"1000000000": 12},
        },
        "coflow_groups": [
            {
                "group": "G",
                "synchronized_burst_members": 3,
                "members": [{"ticker": "A", "name": "테스트"}],
            }
        ],
    }


def source_state():
    return {
        "turnover_rank_top10_share": 0.62,
        "market_overview": {
            "KOSPI": {"change_pct": 1.1, "advance_ratio": 0.58},
            "KOSDAQ": {"change_pct": 0.7, "advance_ratio": 0.55},
        },
    }


def test_close_bet_event_is_created_with_late_and_auction_moves(tmp_path):
    engine = make_engine(tmp_path)
    now = datetime(2026, 9, 25, 15, 31, tzinfo=KST)
    result = engine._update_close_bet_events(
        now,
        {"A": signal_rows()},
        quantitative(),
        source_state(),
    )
    assert result["created"] == 1

    rows = load_event_csv(tmp_path / "data/market/stats/종가베팅_이벤트.csv")
    assert len(rows) == 1
    assert float(rows[0]["late_return_pct"]) == 5.0
    assert round(float(rows[0]["closing_auction_pct"]), 4) == round((104 / 105 - 1) * 100, 4)
    assert rows[0]["minute_ge_10eok_count"] == "3"
    assert rows[0]["synchronized_coflow"] == "1"
    assert rows[0]["synchronized_group"] == "G"
    assert rows[0]["turnover_rank_top10_share"] == "0.62"
    assert rows[0]["recent_listing_10eok_event_count"] == "12"


def test_next_day_outcome_is_not_finalized_intraday(tmp_path):
    engine = make_engine(tmp_path)
    engine._update_close_bet_events(
        datetime(2026, 9, 25, 15, 31, tzinfo=KST),
        {"A": signal_rows()},
        quantitative(),
    )

    result = engine._update_close_bet_events(
        datetime(2026, 9, 28, 10, 0, tzinfo=KST),
        {"A": next_day_rows()},
        {"status": "ok", "stocks": []},
    )
    assert result["completed"] == 0
    rows = load_event_csv(tmp_path / "data/market/stats/종가베팅_이벤트.csv")
    assert rows[0]["next_date"] == ""


def test_next_day_outcome_is_finalized_after_close(tmp_path):
    engine = make_engine(tmp_path)
    engine._update_close_bet_events(
        datetime(2026, 9, 25, 15, 31, tzinfo=KST),
        {"A": signal_rows()},
        quantitative(),
    )

    result = engine._update_close_bet_events(
        datetime(2026, 9, 28, 15, 31, tzinfo=KST),
        {"A": next_day_rows()},
        {"status": "ok", "stocks": []},
    )
    assert result["completed"] == 1
    rows = load_event_csv(tmp_path / "data/market/stats/종가베팅_이벤트.csv")
    assert rows[0]["next_date"] == "2026-09-28"
    assert float(rows[0]["next_mfe_pct"]) > 0
    assert float(rows[0]["next_mae_pct"]) < 0


def test_next_day_outcome_is_also_measured_from_nxt_final_price(tmp_path):
    engine = make_engine(tmp_path)
    engine._update_close_bet_events(
        datetime(2026, 9, 25, 15, 31, tzinfo=KST),
        {"A": signal_rows()},
        quantitative(),
    )

    path = tmp_path / "data/market/stats/종가베팅_이벤트.csv"
    rows = load_event_csv(path)
    rows[0]["nxt_after_last_price"] = "108"
    from autoresearch.market_intel import CLOSE_EVENT_FIELDS, write_event_csv
    write_event_csv(path, rows, CLOSE_EVENT_FIELDS)

    result = engine._update_close_bet_events(
        datetime(2026, 9, 28, 15, 31, tzinfo=KST),
        {"A": next_day_rows()},
        {"status": "ok", "stocks": []},
    )
    assert result["completed"] == 1

    rows = load_event_csv(path)
    assert round(float(rows[0]["next_gap_from_nxt_pct"]), 4) == round((106 / 108 - 1) * 100, 4)
    assert round(float(rows[0]["next_mfe_from_nxt_pct"]), 4) == round((110 / 108 - 1) * 100, 4)
    assert round(float(rows[0]["next_mae_from_nxt_pct"]), 4) == round((101 / 108 - 1) * 100, 4)
