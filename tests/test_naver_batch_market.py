import json
from datetime import datetime, timedelta, timezone

from autoresearch.naver_batch_market import (
    KST,
    archive_session_snapshot,
    build_daily_tracked_universe,
    build_interval_rows,
    calibrate_minute_samples,
    extract_polling_quotes,
    extract_ranked_stocks,
    parse_time_quote_rows,
)


def test_extract_ranked_stocks_from_nested_payload():
    payload = {
        "result": {
            "items": [
                {
                    "itemCode": "005930",
                    "stockName": "삼성전자",
                    "accumulatedTradingValue": "123,456,789",
                },
                {
                    "itemCode": "000660",
                    "stockName": "SK하이닉스",
                    "tradingValue": 987654321,
                },
            ]
        }
    }
    rows = extract_ranked_stocks(payload, limit=10)
    assert [row["ticker"] for row in rows] == ["005930", "000660"]
    assert rows[0]["ranking_trading_value"] == 123456789


def test_extract_polling_quotes_supports_new_and_legacy_fields():
    payload = {
        "items": [
            {
                "itemCode": "005930",
                "stockName": "삼성전자",
                "closePrice": "100,000",
                "accumulatedTradingValue": "5,000,000,000",
                "accumulatedTradingVolume": "50,000",
                "fluctuationsRatio": "2.5",
            },
            {
                "cd": "000660",
                "nm": "SK하이닉스",
                "nv": 200000,
                "aa": 7000000000,
                "aq": 35000,
                "cr": 1.5,
            },
        ]
    }
    quotes = extract_polling_quotes(payload)
    assert quotes["005930"]["accumulated_trading_value"] == 5000000000
    assert quotes["000660"]["last_price"] == 200000
    assert quotes["000660"]["accumulated_trading_value"] == 7000000000


def test_build_interval_rows_calculates_six_minute_delta():
    now = datetime(2026, 9, 28, 10, 6, tzinfo=KST)
    previous = {
        "generated_at": (now - timedelta(minutes=6)).isoformat(),
        "stocks": [
            {
                "ticker": "005930",
                "accumulated_trading_value": 10_000_000_000,
            }
        ],
    }
    current = {
        "005930": {
            "ticker": "005930",
            "name": "삼성전자",
            "accumulated_trading_value": 13_600_000_000,
        }
    }
    rows, elapsed = build_interval_rows(current, previous, now)
    assert elapsed == 6
    assert rows[0]["interval_trading_value"] == 3_600_000_000
    assert rows[0]["per_minute_average_trading_value"] == 600_000_000
    assert rows[0]["interval_valid"] is True


def test_interval_gap_is_not_misreported_as_six_minutes():
    now = datetime(2026, 9, 28, 11, 0, tzinfo=KST)
    previous = {
        "generated_at": (now - timedelta(minutes=40)).isoformat(),
        "stocks": [
            {
                "ticker": "005930",
                "accumulated_trading_value": 10_000_000_000,
            }
        ],
    }
    current = {
        "005930": {
            "ticker": "005930",
            "accumulated_trading_value": 20_000_000_000,
        }
    }
    rows, elapsed = build_interval_rows(current, previous, now)
    assert elapsed == 40
    assert rows[0]["interval_valid"] is False
    assert rows[0]["interval_trading_value"] is None


def test_ranking_turnover_can_backfill_polling_turnover():
    universe = [
        {"ticker": "005930", "name": "삼성전자", "ranking_trading_value": 15_000_000_000}
    ]
    quotes = {
        "005930": {
            "ticker": "005930",
            "name": "삼성전자",
            "accumulated_trading_value": None,
        }
    }
    universe_by_code = {item["ticker"]: item for item in universe}
    for code, quote in quotes.items():
        if quote.get("accumulated_trading_value") is None:
            quote["accumulated_trading_value"] = universe_by_code[code]["ranking_trading_value"]
    assert quotes["005930"]["accumulated_trading_value"] == 15_000_000_000


def test_parse_time_quote_rows_builds_minute_volume_and_amount():
    html = """
    <table>
      <tr onmouseover="mouseOver(this)">
        <td><span>10:06</span></td><td><span>10,000</span></td><td><span>0</span></td>
        <td><span>10,010</span></td><td><span>9,990</span></td><td><span>1,600</span></td><td><span>600</span></td>
      </tr>
      <tr onmouseover="mouseOver(this)">
        <td><span>10:05</span></td><td><span>9,900</span></td><td><span>0</span></td>
        <td><span>9,910</span></td><td><span>9,890</span></td><td><span>1,000</span></td><td><span>400</span></td>
      </tr>
    </table>
    """
    rows = parse_time_quote_rows(html)
    assert [row["time"] for row in rows] == ["10:05", "10:06"]
    assert rows[-1]["minute_volume"] == 600
    assert rows[-1]["raw_trading_value_estimate"] == 6_000_000


def test_calibrate_minute_samples_matches_six_minute_total():
    rows = [
        {"time": "10:01", "raw_trading_value_estimate": 100.0},
        {"time": "10:02", "raw_trading_value_estimate": 200.0},
        {"time": "10:03", "raw_trading_value_estimate": 300.0},
    ]
    calibrated = calibrate_minute_samples(rows, 1_200.0)
    assert round(sum(x["minute_trading_value"] for x in calibrated), 6) == 1_200.0
    assert all(x["calibrated_to_interval_total"] for x in calibrated)
    assert all(x["amount_estimated"] for x in calibrated)


def test_daily_tracked_universe_keeps_stock_after_it_drops_below_top50():
    now = datetime(2026, 9, 28, 10, 6, tzinfo=KST)
    previous = {
        "generated_at": (now - timedelta(minutes=6)).isoformat(),
        "tracked_universe": [
            {
                "ticker": "005930",
                "name": "삼성전자",
                "first_top50_at": (now - timedelta(minutes=30)).isoformat(),
                "last_top50_at": (now - timedelta(minutes=6)).isoformat(),
                "last_top50_rank": 47,
                "in_current_top50": True,
                "current_rank": 47,
            }
        ],
    }
    current_top = [
        {"ticker": "000660", "name": "SK하이닉스", "ranking_trading_value": 100}
    ]
    tracked = build_daily_tracked_universe(current_top, previous, now)
    samsung = next(x for x in tracked if x["ticker"] == "005930")
    assert samsung["in_current_top50"] is False
    assert samsung["current_rank"] is None
    assert samsung["last_top50_rank"] == 47


def test_daily_tracked_universe_resets_on_new_day():
    now = datetime(2026, 9, 29, 9, 6, tzinfo=KST)
    previous = {
        "generated_at": datetime(2026, 9, 28, 15, 30, tzinfo=KST).isoformat(),
        "tracked_universe": [
            {"ticker": "005930", "name": "삼성전자", "last_top50_rank": 47}
        ],
    }
    current_top = [
        {"ticker": "000660", "name": "SK하이닉스", "ranking_trading_value": 100}
    ]
    tracked = build_daily_tracked_universe(current_top, previous, now)
    assert [x["ticker"] for x in tracked] == ["000660"]


def test_stale_same_day_universe_is_not_carried_forward():
    now = datetime(2026, 9, 25, 11, 45, tzinfo=KST)
    previous = {
        "generated_at": (now - timedelta(minutes=6)).isoformat(),
        "ranking_fresh_today": False,
        "tracked_universe": [
            {"ticker": "005930", "name": "삼성전자", "last_top50_rank": 1}
        ],
    }
    tracked = build_daily_tracked_universe([], previous, now)
    assert tracked == []


def test_archive_session_snapshot_keeps_only_recent_actual_sessions(tmp_path):
    for day in [21, 22, 23, 28, 29, 30]:
        now = datetime(2026, 9, day, 15, 30, tzinfo=KST)
        snapshot = {
            "generated_at": now.isoformat(),
            "ranking_fresh_today": True,
            "tracked_universe": [{"ticker": "005930"}],
            "current_top50": [{"ticker": "005930", "current_rank": 1}],
            "stocks": [{"ticker": "005930", "day_return_pct": 1.0}],
            "minute_samples_by_ticker": {"005930": [{"time": "15:29"}]},
        }
        archive_session_snapshot(tmp_path, snapshot, now, keep=5)

    folder = tmp_path / "data/providers/naver_batch/sessions"
    files = sorted(x.name for x in folder.glob("*.json"))
    assert files == [
        "2026-09-22.json",
        "2026-09-23.json",
        "2026-09-28.json",
        "2026-09-29.json",
        "2026-09-30.json",
    ]
    saved = json.loads((folder / "2026-09-30.json").read_text(encoding="utf-8"))
    assert saved["current_top50"][0]["ticker"] == "005930"


def test_archive_session_snapshot_ignores_holiday_stale_ranking(tmp_path):
    now = datetime(2026, 9, 26, 15, 30, tzinfo=KST)
    result = archive_session_snapshot(
        tmp_path,
        {
            "generated_at": now.isoformat(),
            "ranking_fresh_today": False,
            "tracked_universe": [],
        },
        now,
    )
    assert result is None
    assert not (tmp_path / "data/providers/naver_batch/sessions").exists()
