import csv

from autoresearch.market_intel import MarketIntelEngine
from autoresearch.pullback_stats import PULLBACK_EVENT_FIELDS


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def make_engine(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "market_intel.yaml").write_text(
        """
minute_analysis:
  baseline_window: 3
  burst_ratio: 2
  min_burst_amount_krw: 100
data:
  stats_dir: data/market/stats
statistics:
  min_sample_size: 2
pullback_research:
  cohort_version: "v1"
""",
        encoding="utf-8",
    )
    return MarketIntelEngine(tmp_path, "dry-run")


def test_strategy_rates_and_rebound_drawdown(tmp_path):
    engine = make_engine(tmp_path)
    stats_dir = tmp_path / "data/market/stats"

    close_fields = [
        "signal_date", "ticker", "next_date", "next_gap_pct",
        "next_mae_pct", "next_mfe_pct", "late_return_pct",
        "closing_auction_pct", "late_amount_share", "high_position",
        "burst_count",
    ]
    write_csv(
        stats_dir / "close_bet_events.csv",
        close_fields,
        [
            {
                "signal_date": "20260920",
                "ticker": "A",
                "next_date": "20260921",
                "next_gap_pct": "1",
                "next_mae_pct": "-6",
                "next_mfe_pct": "6",
                "late_return_pct": "2",
                "closing_auction_pct": "0.5",
                "late_amount_share": "0.4",
                "high_position": "0.9",
                "burst_count": "3",
            },
            {
                "signal_date": "20260920",
                "ticker": "B",
                "next_date": "20260921",
                "next_gap_pct": "-1",
                "next_mae_pct": "-2",
                "next_mfe_pct": "4",
                "late_return_pct": "-1",
                "closing_auction_pct": "-0.5",
                "late_amount_share": "0.2",
                "high_position": "0.6",
                "burst_count": "0",
            },
        ],
    )

    pullback_rows = [
        {
            "cohort_version": "v1",
            "signal_date": "20260910",
            "ticker": "A",
            "drawdown_pct": "-20",
            "pullback_days": "5",
            "amount_decay_pct": "60",
            "ma20_distance_pct": "2",
            "first_positive_candle": "1",
            "forward_5d_date": "20260917",
            "forward_5d_mae_pct": "-3",
            "forward_5d_mfe_pct": "8",
        },
        {
            "cohort_version": "v1",
            "signal_date": "20260910",
            "ticker": "B",
            "drawdown_pct": "-10",
            "pullback_days": "3",
            "amount_decay_pct": "40",
            "ma20_distance_pct": "8",
            "first_positive_candle": "0",
            "forward_5d_date": "20260917",
            "forward_5d_mae_pct": "-7",
            "forward_5d_mfe_pct": "2",
        },
    ]
    write_csv(stats_dir / "pullback_events.csv", PULLBACK_EVENT_FIELDS, pullback_rows)

    stats = engine._strategy_stats()

    assert stats["close_bet"]["rates"]["mfe_ge_5"] == 0.5
    assert stats["close_bet"]["rates"]["mae_le_minus5"] == 0.5
    assert stats["pullback"]["rates"]["mfe_ge_5"] == 0.5
    assert stats["pullback"]["rates"]["mae_le_minus5"] == 0.5

    rebound = stats["pullback"]["rebound_drawdown"]["mfe_ge_5"]
    assert rebound["summary"]["sample_size"] == 1
    assert rebound["summary"]["fields"]["drawdown_pct"]["median"] == -20.0
