from autoresearch.relative_strength import (
    parse_kospi_benchmark,
    parse_kospi_market_payload,
    parse_nasdaq_benchmark,
    parse_yahoo_spark,
    build_period_summary,
    build_consistency,
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
                    "itemcode": "005930",
                    "itemname": "삼성전자",
                    "nowPrice": "100,000",
                    "prevChangeRate": "+2.50",
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



def test_parse_yahoo_spark_and_period_return_summary():
    payload = {
        "spark": {
            "result": [
                {
                    "symbol": "AAA",
                    "response": [
                        {
                            "timestamp": list(range(1, 23)),
                            "indicators": {
                                "quote": [
                                    {"close": [100 + i for i in range(22)]}
                                ]
                            },
                        }
                    ],
                },
                {
                    "symbol": "^TEST",
                    "response": [
                        {
                            "timestamp": list(range(1, 23)),
                            "indicators": {
                                "quote": [
                                    {"close": [200 + i for i in range(22)]}
                                ]
                            },
                        }
                    ],
                },
            ],
            "error": None,
        }
    }
    histories = parse_yahoo_spark(payload)
    assert len(histories["AAA"]) == 22

    base = summarize_market(
        {"name": "TEST", "change_pct": 1.0},
        [{"ticker": "AAA", "name": "Alpha", "change_pct": 2.0, "market_cap": 100}],
        market="NASDAQ",
        universe_label="test",
        source_urls=[],
    )
    period = build_period_summary(
        base,
        histories,
        market="NASDAQ",
        benchmark_symbol="^TEST",
        sessions=5,
    )
    assert period["status"] == "ok"
    assert period["universe_count"] == 1
    assert period["strongest"][0]["ticker"] == "AAA"
    assert period["requested_universe_count"] == 1


def test_consistency_classifies_persistent_and_turning_names():
    base = summarize_market(
        {"name": "IDX", "change_pct": 0.0},
        [
            {"ticker": "A", "name": "Always Strong", "change_pct": 2.0},
            {"ticker": "B", "name": "Turning Strong", "change_pct": 1.0},
            {"ticker": "C", "name": "Always Weak", "change_pct": -1.0},
            {"ticker": "D", "name": "Turning Weak", "change_pct": -2.0},
        ],
        market="NASDAQ",
        universe_label="test",
        source_urls=[],
    )
    base["periods"] = {
        "5D": summarize_market(
            {"name": "IDX", "change_pct": 0.0},
            [
                {"ticker": "A", "name": "Always Strong", "change_pct": 3.0},
                {"ticker": "B", "name": "Turning Strong", "change_pct": -1.0},
                {"ticker": "C", "name": "Always Weak", "change_pct": -2.0},
                {"ticker": "D", "name": "Turning Weak", "change_pct": 1.0},
            ],
            market="NASDAQ",
            universe_label="test",
            source_urls=[],
        ),
        "20D": summarize_market(
            {"name": "IDX", "change_pct": 0.0},
            [
                {"ticker": "A", "name": "Always Strong", "change_pct": 4.0},
                {"ticker": "B", "name": "Turning Strong", "change_pct": -2.0},
                {"ticker": "C", "name": "Always Weak", "change_pct": -3.0},
                {"ticker": "D", "name": "Turning Weak", "change_pct": 2.0},
            ],
            market="NASDAQ",
            universe_label="test",
            source_urls=[],
        ),
    }
    result = build_consistency(base)
    assert result["status"] == "ok"
    assert result["persistent_strong"][0]["ticker"] == "A"
    assert result["persistent_weak"][0]["ticker"] == "C"
    assert result["turning_strong"][0]["ticker"] == "B"
    assert result["turning_weak"][0]["ticker"] == "D"
