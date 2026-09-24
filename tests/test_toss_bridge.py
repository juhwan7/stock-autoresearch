import json
from datetime import datetime, timedelta

import pytest

from autoresearch.market_intel import KST, MarketIntelEngine, in_domestic_monitor_window
from autoresearch.toss_bridge import TossCollectorBridge, TossSnapshotError


def write_snapshot(tmp_path, captured_at):
    path = tmp_path / "data/providers/toss/latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "captured_at": captured_at,
                "minute_amount_method": "exact_trade_sum",
                "market_overview": {
                    "KOSPI": {"change_pct": 1.0, "rising": 500, "falling": 300}
                },
                "turnover_rank_top10_share": 0.55,
                "ranking": [
                    {
                        "ticker": "005930",
                        "name": "삼성전자",
                        "day_return_pct": 1.2,
                        "trading_value": 500000000000,
                    }
                ],
                "metadata": {
                    "005930": {
                        "name": "삼성전자",
                        "krx_close": 70000,
                        "listing_age_days": 10000,
                    }
                },
                "minute_by_ticker": {
                    "005930": [
                        {
                            "time": "15:20",
                            "open": 69900,
                            "high": 70100,
                            "low": 69800,
                            "close": 70000,
                            "volume": 10000,
                            "amount": 700000000,
                        }
                    ]
                },
                "postmarket_by_ticker": {
                    "005930": [
                        {
                            "time": "15:40",
                            "open": 70000,
                            "high": 70100,
                            "low": 69900,
                            "close": 70000,
                            "volume": 20000,
                            "amount": 1400000000,
                        },
                        {
                            "time": "19:59",
                            "open": 70600,
                            "high": 70800,
                            "low": 70500,
                            "close": 70700,
                            "volume": 30000,
                            "amount": 2121000000,
                        },
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def make_engine(tmp_path):
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "market_intel.yaml").write_text(
        """
providers:
  primary: toss_collector
  toss_snapshot: data/providers/toss/latest.json
  toss_max_age_minutes: 20
minute_analysis:
  baseline_window: 3
  burst_ratio: 2
  min_burst_amount_krw: 100
data:
  stats_dir: data/market/stats
statistics:
  min_sample_size: 20
pullback_research:
  enabled: false
models: {}
""",
        encoding="utf-8",
    )
    return MarketIntelEngine(tmp_path, "live")


def test_toss_bridge_preserves_exact_minute_amount_and_postmarket(tmp_path):
    now = datetime(2026, 9, 25, 19, 59, tzinfo=KST)
    write_snapshot(tmp_path, now.isoformat())
    bridge = TossCollectorBridge(tmp_path, max_age_minutes=20)

    minute, metadata, source = bridge.market_payload(now)

    assert source["provider"] == "toss"
    assert source["minute_amount_method"] == "exact_trade_sum"
    assert minute["005930"][0]["amount"] == 700000000
    assert minute["005930"][0]["amount_estimated"] is False
    assert metadata["005930"]["day_return_pct"] == 1.2

    post = source["postmarket"]["stocks"][0]
    assert post["minute_ge_10eok_count"] == 2
    assert round(post["krx_close_premium_pct"], 2) == 1.0
    assert post["amount_estimated"] is False


def test_toss_bridge_rejects_stale_snapshot(tmp_path):
    now = datetime(2026, 9, 25, 19, 59, tzinfo=KST)
    write_snapshot(tmp_path, (now - timedelta(minutes=40)).isoformat())
    bridge = TossCollectorBridge(tmp_path, max_age_minutes=20)

    with pytest.raises(TossSnapshotError):
        bridge.load(now)


def test_domestic_monitor_window_extends_to_20_10():
    assert in_domestic_monitor_window(
        datetime(2026, 9, 25, 19, 59, tzinfo=KST)
    )
    assert in_domestic_monitor_window(
        datetime(2026, 9, 25, 20, 10, tzinfo=KST)
    )
    assert not in_domestic_monitor_window(
        datetime(2026, 9, 25, 20, 11, tzinfo=KST)
    )


def test_nxt_after_data_is_written_to_close_bet_event(tmp_path):
    engine = make_engine(tmp_path)
    path = tmp_path / "data/market/stats/종가베팅_이벤트.csv"
    path.parent.mkdir(parents=True, exist_ok=True)

    from autoresearch.market_intel import CLOSE_EVENT_FIELDS, write_event_csv

    write_event_csv(
        path,
        [{"signal_date": "2026-09-25", "ticker": "005930", "name": "삼성전자"}],
        CLOSE_EVENT_FIELDS,
    )

    source_state = {
        "provider": "toss",
        "postmarket": {
            "stocks": [
                {
                    "ticker": "005930",
                    "name": "삼성전자",
                    "last_price": 70700,
                    "return_pct": 1.0,
                    "krx_close_premium_pct": 1.0,
                    "amount": 3521000000,
                    "max_minute_amount": 2121000000,
                    "minute_ge_10eok_count": 2,
                    "minute_ge_20eok_count": 1,
                    "amount_estimated": False,
                }
            ]
        },
    }

    result = engine._update_nxt_after_events(
        datetime(2026, 9, 25, 19, 59, tzinfo=KST),
        source_state,
    )
    assert result["updated"] == 1

    import csv
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle))

    assert row["nxt_eligible"] == "1"
    assert row["nxt_after_last_price"] == "70700"
    assert row["nxt_after_10eok_count"] == "2"
    assert row["nxt_amount_estimated"] == "0"
