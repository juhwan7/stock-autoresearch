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
                "burst_count": 2,
                "max_burst_ratio": 3.0,
                "high_position": 0.8,
                "group_id": "G",
                "sector": "S",
            }
        ],
    }


def test_close_bet_event_is_created_with_late_and_auction_moves(tmp_path):
    engine = make_engine(tmp_path)
    now = datetime(2026, 9, 25, 15, 31, tzinfo=KST)
    result = engine._update_close_bet_events(now, {"A": signal_rows()}, quantitative())
    assert result["created"] == 1

    rows = load_event_csv(tmp_path / "data/market/stats/close_bet_events.csv")
    assert len(rows) == 1
    assert float(rows[0]["late_return_pct"]) == 5.0
    assert round(float(rows[0]["closing_auction_pct"]), 4) == round((104 / 105 - 1) * 100, 4)


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
    rows = load_event_csv(tmp_path / "data/market/stats/close_bet_events.csv")
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
    rows = load_event_csv(tmp_path / "data/market/stats/close_bet_events.csv")
    assert rows[0]["next_date"] == "2026-09-28"
    assert float(rows[0]["next_mfe_pct"]) > 0
    assert float(rows[0]["next_mae_pct"]) < 0
