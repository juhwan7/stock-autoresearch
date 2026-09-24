from autoresearch.pullback_stats import (
    complete_pullback_event,
    cooldown_allows,
    detect_pullback_event,
)


def make_rows():
    rows = []
    price = 100.0
    for day in range(30):
        date = f"202609{day + 1:02d}" if day < 29 else "20261001"
        amount = 20_000_000_000
        open_ = price
        close = price * 1.002
        high = max(open_, close) * 1.01
        low = min(open_, close) * 0.99
        if day == 20:
            open_ = price
            close = price * 1.10
            high = close * 1.03
            low = price * 0.99
            amount = 150_000_000_000
        elif day > 20:
            close = 106 - (day - 21) * 0.45
            open_ = close * 1.003
            high = close * 1.01
            low = close * 0.99
            amount = 35_000_000_000
        price = close
        rows.append(
            {
                "date": date,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "amount": amount,
            }
        )
    return rows


def test_detect_research_pullback():
    event = detect_pullback_event("A", make_rows(), {"name": "테스트"})
    assert event is not None
    assert event["ticker"] == "A"
    assert event["drawdown_pct"] < 0
    assert event["amount_decay_pct"] >= 30


def test_complete_future_outcomes():
    rows = make_rows()
    event = detect_pullback_event("A", rows[:-5], {"name": "테스트"})
    assert event is not None
    changed = complete_pullback_event(event, rows)
    assert changed
    assert event["forward_1d_date"]
    assert event["forward_3d_date"]
    assert event["forward_5d_date"]


def test_cooldown_blocks_duplicates():
    assert not cooldown_allows(
        [{"signal_date": "20260920", "ticker": "A"}],
        "A",
        "20260925",
        calendar_days=7,
    )
    assert cooldown_allows(
        [{"signal_date": "20260901", "ticker": "A"}],
        "A",
        "20260925",
        calendar_days=7,
    )
