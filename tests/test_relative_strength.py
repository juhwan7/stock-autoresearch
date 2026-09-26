from autoresearch.relative_strength import (
    parse_kospi_benchmark,
    parse_kospi_market_sum,
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


def test_parse_kospi_market_sum_and_benchmark():
    html = """
    <table>
      <tr>
        <td>1</td>
        <td><a class="tltle" href="/item/main.naver?code=005930">삼성전자</a></td>
        <td>100,000</td><td>1,000</td><td>+2.50%</td><td>100</td>
        <td>5,000,000</td><td>1,000,000</td><td>50.0</td><td>10,000,000</td>
      </tr>
    </table>
    """
    rows = parse_kospi_market_sum(html)
    assert rows[0]["ticker"] == "005930"
    assert rows[0]["change_pct"] == 2.5
    assert rows[0]["market_cap"] == 5000000 * 100_000_000

    index_html = """
      <span id="now_value">7,080.92</span>
      <span id="change_value_and_rate">63.01 +0.90%</span>
      <span id="time">2026.09.23 15:30</span>
    """
    benchmark = parse_kospi_benchmark(index_html)
    assert benchmark["close"] == 7080.92
    assert benchmark["change_pct"] == 0.9
