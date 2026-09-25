import json
from datetime import datetime, timedelta, timezone

from autoresearch.naver_batch_market import (
    KST,
    build_interval_rows,
    extract_polling_quotes,
    extract_ranked_stocks,
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
