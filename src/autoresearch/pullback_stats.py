from __future__ import annotations

from datetime import datetime
from statistics import median
from typing import Any

from .market_stats import number, percent_change


PULLBACK_EVENT_FIELDS = [
    "signal_date",
    "ticker",
    "name",
    "sector",
    "group_id",
    "entry_price",
    "impulse_date",
    "impulse_return_pct",
    "impulse_amount",
    "impulse_amount_ratio",
    "peak_date",
    "peak_price",
    "drawdown_pct",
    "pullback_days",
    "amount_decay_pct",
    "ma5_distance_pct",
    "ma20_distance_pct",
    "first_positive_candle",
    "forward_1d_date",
    "forward_1d_mae_pct",
    "forward_1d_mfe_pct",
    "forward_3d_date",
    "forward_3d_mae_pct",
    "forward_3d_mfe_pct",
    "forward_5d_date",
    "forward_5d_mae_pct",
    "forward_5d_mfe_pct",
]


def _clean_daily(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    for row in rows:
        date = str(row.get("date") or row.get("dt") or "")
        close = abs(number(row.get("close") or row.get("cur_prc")))
        if len(date) != 8 or close <= 0:
            continue
        open_ = abs(number(row.get("open") or row.get("open_pric"))) or close
        high = abs(number(row.get("high") or row.get("high_pric"))) or close
        low = abs(number(row.get("low") or row.get("low_pric"))) or close
        amount = abs(number(row.get("amount") or row.get("trde_prica")))
        clean.append(
            {
                "date": date,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "amount": amount,
            }
        )
    clean.sort(key=lambda x: x["date"])
    return clean


def detect_pullback_event(
    ticker: str,
    rows: list[dict[str, Any]],
    meta: dict[str, Any] | None = None,
    *,
    min_impulse_return_pct: float = 5.0,
    min_impulse_amount_krw: float = 100_000_000_000,
    min_impulse_amount_ratio: float = 2.0,
    impulse_lookback_days: int = 25,
    min_drawdown_pct: float = 5.0,
    max_drawdown_pct: float = 35.0,
    min_amount_decay_pct: float = 30.0,
    max_pullback_days: int = 20,
) -> dict[str, Any] | None:
    """연구용 눌림 코호트를 탐지한다.

    이 조건은 매수 신호가 아니라 통계를 만들기 위한 초기 가설이다.
    """
    data = _clean_daily(rows)
    if len(data) < 25:
        return None

    latest_i = len(data) - 1
    latest = data[latest_i]
    start = max(20, latest_i - impulse_lookback_days)
    candidates: list[tuple[float, int, float, float]] = []

    for i in range(start, latest_i):
        previous = data[i - 1]["close"]
        day_return = percent_change(previous, data[i]["close"])
        baseline_values = [
            x["amount"] for x in data[max(0, i - 20):i] if x["amount"] > 0
        ]
        baseline = median(baseline_values) if baseline_values else 0.0
        amount_ratio = data[i]["amount"] / baseline if baseline > 0 else 0.0
        if (
            day_return >= min_impulse_return_pct
            and data[i]["amount"] >= min_impulse_amount_krw
            and amount_ratio >= min_impulse_amount_ratio
        ):
            score = day_return * amount_ratio
            candidates.append((score, i, day_return, amount_ratio))

    if not candidates:
        return None

    _, impulse_i, impulse_return, impulse_amount_ratio = max(candidates)
    post = data[impulse_i:latest_i + 1]
    peak_rel = max(range(len(post)), key=lambda j: post[j]["high"])
    peak_i = impulse_i + peak_rel

    # 같은 날 고점 직후는 아직 "눌림" 표본으로 보지 않는다.
    pullback_days = latest_i - peak_i
    if pullback_days < 1 or pullback_days > max_pullback_days:
        return None

    peak_price = data[peak_i]["high"]
    drawdown = percent_change(peak_price, latest["close"])
    drawdown_abs = abs(min(drawdown, 0.0))
    if not (min_drawdown_pct <= drawdown_abs <= max_drawdown_pct):
        return None

    impulse_amount = data[impulse_i]["amount"]
    if impulse_amount <= 0:
        return None
    amount_decay = (1.0 - latest["amount"] / impulse_amount) * 100.0
    if amount_decay < min_amount_decay_pct:
        return None

    ma5_values = [x["close"] for x in data[max(0, latest_i - 4):latest_i + 1]]
    ma20_values = [x["close"] for x in data[max(0, latest_i - 19):latest_i + 1]]
    ma5 = sum(ma5_values) / len(ma5_values)
    ma20 = sum(ma20_values) / len(ma20_values)

    previous = data[latest_i - 1]
    first_positive = (
        latest["close"] > latest["open"]
        and latest["close"] > previous["close"]
        and previous["close"] <= previous["open"]
    )

    meta = meta or {}
    return {
        "signal_date": latest["date"],
        "ticker": ticker,
        "name": meta.get("name") or ticker,
        "sector": meta.get("sector") or "",
        "group_id": meta.get("group_id") or "",
        "entry_price": round(latest["close"], 4),
        "impulse_date": data[impulse_i]["date"],
        "impulse_return_pct": round(impulse_return, 4),
        "impulse_amount": round(impulse_amount, 2),
        "impulse_amount_ratio": round(impulse_amount_ratio, 4),
        "peak_date": data[peak_i]["date"],
        "peak_price": round(peak_price, 4),
        "drawdown_pct": round(drawdown, 4),
        "pullback_days": pullback_days,
        "amount_decay_pct": round(amount_decay, 4),
        "ma5_distance_pct": round(percent_change(ma5, latest["close"]), 4),
        "ma20_distance_pct": round(percent_change(ma20, latest["close"]), 4),
        "first_positive_candle": "1" if first_positive else "0",
    }


def complete_pullback_event(
    event: dict[str, Any],
    rows: list[dict[str, Any]],
    horizons: tuple[int, ...] = (1, 3, 5),
) -> bool:
    """신호 이후 실제 거래일의 MFE/MAE를 채운다.

    반환값은 최소 한 필드가 새로 완결됐는지 여부다.
    """
    data = _clean_daily(rows)
    signal_date = str(event.get("signal_date") or "").replace("-", "")
    entry = number(event.get("entry_price"))
    if not signal_date or entry <= 0:
        return False

    indices = [i for i, row in enumerate(data) if row["date"] == signal_date]
    if not indices:
        return False
    signal_i = indices[-1]
    changed = False

    for horizon in horizons:
        date_key = f"forward_{horizon}d_date"
        if event.get(date_key):
            continue
        future = data[signal_i + 1: signal_i + 1 + horizon]
        if len(future) < horizon:
            continue
        low = min(x["low"] for x in future)
        high = max(x["high"] for x in future)
        event[date_key] = future[-1]["date"]
        event[f"forward_{horizon}d_mae_pct"] = round(percent_change(entry, low), 4)
        event[f"forward_{horizon}d_mfe_pct"] = round(percent_change(entry, high), 4)
        changed = True

    return changed


def cooldown_allows(
    existing_events: list[dict[str, Any]],
    ticker: str,
    signal_date: str,
    *,
    calendar_days: int = 7,
) -> bool:
    try:
        current = datetime.strptime(signal_date, "%Y%m%d").date()
    except ValueError:
        return True
    for event in reversed(existing_events):
        if str(event.get("ticker") or "") != ticker:
            continue
        raw = str(event.get("signal_date") or "").replace("-", "")
        try:
            prior = datetime.strptime(raw, "%Y%m%d").date()
        except ValueError:
            continue
        if 0 <= (current - prior).days <= calendar_days:
            return False
        if (current - prior).days > calendar_days:
            break
    return True
