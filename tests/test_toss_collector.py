from autoresearch.toss_collector import CollectorState, TossRestClient


def test_trade_ticks_aggregate_exact_amount_and_sessions():
    state = CollectorState(top_n=80)

    assert state.add_trade(
        symbol="005930",
        price="72000",
        volume="100",
        timestamp="2026-09-25T14:30:10+09:00",
    )
    assert state.add_trade(
        symbol="005930",
        price="72100",
        volume="50",
        timestamp="2026-09-25T14:30:40+09:00",
    )
    assert state.add_trade(
        symbol="005930",
        price="72500",
        volume="20",
        timestamp="2026-09-25T15:45:00+09:00",
    )

    regular = state._rows(state.regular)["005930"][0]
    assert regular["open"] == 72000
    assert regular["high"] == 72100
    assert regular["low"] == 72000
    assert regular["close"] == 72100
    assert regular["volume"] == 150
    assert regular["amount"] == 10805000
    assert regular["trade_count"] == 2
    assert regular["amount_estimated"] is False

    post = state._rows(state.postmarket)["005930"][0]
    assert post["amount"] == 1450000
    assert post["trade_count"] == 1


def test_subscription_codes_are_capped_at_100():
    state = CollectorState(top_n=100)
    state.ranking = [
        {"ticker": f"{i:06d}", "trading_value": 1000 - i}
        for i in range(120)
    ]
    assert len(state.codes()) == 100
    assert state.codes()[0] == "000000"
    assert state.codes()[-1] == "000099"


def test_rankings_normalize_change_rate_to_percent(monkeypatch):
    client = TossRestClient("id", "secret")

    def fake_get_json(path, params=None, retry_auth=True):
        assert path == "/api/v1/rankings"
        assert params["type"] == "MARKET_TRADING_AMOUNT"
        assert params["marketCountry"] == "KR"
        assert params["duration"] == "realtime"
        return {
            "result": {
                "rankedAt": "2026-09-25T14:30:00+09:00",
                "rankings": [
                    {
                        "rank": 1,
                        "symbol": "005930",
                        "currency": "KRW",
                        "price": {
                            "lastPrice": "72000",
                            "basePrice": "71000",
                            "changeRate": "0.0140845",
                        },
                        "tradingVolume": "1000000",
                        "tradingAmount": "72000000000",
                    }
                ],
            }
        }

    monkeypatch.setattr(client, "get_json", fake_get_json)
    rows = client.rankings(80)

    assert rows[0]["ticker"] == "005930"
    assert round(rows[0]["day_return_pct"], 3) == 1.408
    assert rows[0]["trading_value"] == 72000000000


def test_stock_metadata_keeps_nxt_support(monkeypatch):
    client = TossRestClient("id", "secret")

    def fake_get_json(path, params=None, retry_auth=True):
        return {
            "result": [
                {
                    "symbol": "005930",
                    "name": "삼성전자",
                    "market": "KOSPI",
                    "listDate": "1975-06-11",
                    "securityType": "STOCK",
                    "koreanMarketDetail": {
                        "nxtSupported": True,
                        "krxTradingSuspended": False,
                        "nxtTradingSuspended": False,
                    },
                }
            ]
        }

    monkeypatch.setattr(client, "get_json", fake_get_json)
    meta = client.stocks(["005930"])["005930"]

    assert meta["name"] == "삼성전자"
    assert meta["nxt_supported"] is True
    assert meta["krx_trading_suspended"] is False
