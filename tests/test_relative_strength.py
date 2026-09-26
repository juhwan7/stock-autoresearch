from autoresearch.relative_strength import (
    parse_kospi_benchmark,
    parse_kospi_market_payload,
    parse_nasdaq_benchmark,
    parse_nasdaq_screener,
    summarize_market,
)


def test_relative_strength_is_stock_return_minus_index_return():
    result = summarize_market(
        {"name": "KOSPI", "change_pct": 1.0},
        [
            {"ticker": "A", "name": "강한종목", "change_pct": 3.0, "market_cap": 10},
            {"ticker": "B", "name": "약한종목", "change_pct": -1.0, "market_cap": 9},
        ],
        market="KOSPI",
        universe_label="test",
        source_urls=[],
    )
    assert result["strongest"][0]["relative_strength_pct"] == 2.0
    assert result["weakest"][0]["relative_strength_pct"] == -2.0
    assert result["above_benchmark_count"] == 1
    assert result["below_benchmark_count"] == 1


def test_empty_stock_universe_is_not_reported_as_ok():
    result = summarize_market(
        {"name": "KOSPI", "change_pct": 0.0},
        [],
        market="KOSPI",
        universe_label="test",
        source_urls=[],
    )
    assert result["status"] == "unavailable"
    assert result["universe_count"] == 0


def test_parse_nasdaq_payloads():
    stocks = parse_nasdaq_screener(
        {
            "data": {
                "rows": [
                    {
                        "symbol": "AAA",
                        "name": "Alpha",
                        "pctchange": "+2.50%",
                        "marketCap": "1000000000",
                        "lastsale": "$10.00",
                        "volume": "1,000",
                    },
                    {
                        "symbol": "ETF",
                        "name": "No cap",
                        "pctchange": "1.0%",
                        "marketCap": "",
                    },
                ]
            }
        }
    )
    assert [row["ticker"] for row in stocks] == ["AAA"]
    assert stocks[0]["change_pct"] == 2.5

    benchmark = parse_nasdaq_benchmark(
        {
            "data": {
                "primaryData": {
                    "percentageChange": "+0.48%",
                    "lastSalePrice": "27068.72",
                    "lastTradeTimestamp": "Sep 25, 2026",
                }
            }
        }
    )
    assert benchmark["change_pct"] == 0.48


def test_parse_kospi_json_list_and_benchmark():
    rows = parse_kospi_market_payload(
        {
            "stocks": [
                {
                    "itemCode": "005930",
                    "stockName": "삼성전자",
                    "closePrice": "100,000",
                    "fluctuationsRatio": "+2.50",
                    "marketSum": "5000000",
                    "accumulatedTradingVolume": "10,000,000",
                },
                {
                    "itemCode": "000660",
                    "stockName": "SK하이닉스",
                    "price": {
                        "currentPrice": "200,000",
                        "changeRate": "-1.25",
                        "tradingVolume": "2,000,000",
                    },
                    "marketValue": "4000000",
                },
            ]
        }
    )
    assert [row["ticker"] for row in rows] == ["005930", "000660"]
    assert rows[0]["change_pct"] == 2.5
    assert rows[0]["market_cap"] == 5000000
    assert rows[1]["change_pct"] == -1.25

    benchmark = parse_kospi_benchmark(
        {
            "domesticIndex": {
                "KOSPI": {
                    "itemCode": "KOSPI",
                    "price": {
                        "currentPrice": "7,080.92",
                        "changeRate": "+0.90",
                        "localTradedAt": "2026-09-23T15:30:00+09:00",
                    },
                }
            }
        }
    )
    assert benchmark["close"] == 7080.92
    assert benchmark["change_pct"] == 0.9
