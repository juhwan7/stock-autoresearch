from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Any


def number(value: Any) -> float:
    if value is None:
        return 0.0
    text = str(value).strip().replace(",", "")
    if not text:
        return 0.0
    sign = -1.0 if text.startswith("-") else 1.0
    text = text.lstrip("+-")
    try:
        return sign * float(text)
    except ValueError:
        return 0.0


def percent_change(a: float, b: float) -> float:
    if not a:
        return 0.0
    return (b / a - 1.0) * 100.0


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * p
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    weight = pos - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def normalize_time(value: str) -> str:
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if len(digits) >= 6:
        return f"{digits[-6:-4]}:{digits[-4:-2]}"
    if len(digits) >= 4:
        return f"{digits[-4:-2]}:{digits[-2:]}"
    return str(value)


@dataclass
class MinuteSummary:
    ticker: str
    name: str
    first_price: float
    last_price: float
    return_pct: float
    total_amount: float
    close_watch_amount: float
    close_watch_share: float
    close_watch_return_pct: float
    median_minute_amount: float
    max_minute_amount: float
    amount_threshold_counts: dict[str, int]
    burst_count: int
    max_burst_ratio: float
    rise_without_burst: bool
    high_position: float
    last_minute_amount: float
    last_minute_burst_ratio: float
    group_id: str
    sector: str
    listing_age_days: int | None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class MarketStats:
    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        minute = cfg.get("minute_analysis", {})
        self.baseline_window = int(minute.get("baseline_window", 20))
        self.burst_ratio = float(minute.get("burst_ratio", 2.5))
        self.min_burst_amount = float(minute.get("min_burst_amount_krw", 500_000_000))
        self.amount_thresholds = [
            float(x)
            for x in minute.get(
                "absolute_amount_thresholds_krw",
                [500_000_000, 1_000_000_000, 2_000_000_000, 5_000_000_000],
            )
        ]
        self.close_watch_start = str(minute.get("close_watch_start", "14:30"))
        self.continuous_end = str(minute.get("continuous_end", "15:20"))

    def summarize_stock(
        self,
        ticker: str,
        rows: list[dict[str, Any]],
        meta: dict[str, Any] | None = None,
    ) -> MinuteSummary | None:
        if not rows:
            return None
        meta = meta or {}
        clean = []
        for raw in rows:
            close = abs(number(raw.get("close") or raw.get("cur_prc")))
            volume = abs(number(raw.get("volume") or raw.get("trde_qty")))
            amount = abs(number(raw.get("amount") or raw.get("trde_prica")))
            if amount <= 0 and close > 0 and volume > 0:
                amount = close * volume
            tm = normalize_time(str(raw.get("time") or raw.get("cntr_tm") or ""))
            high = abs(number(raw.get("high") or raw.get("high_pric"))) or close
            low = abs(number(raw.get("low") or raw.get("low_pric"))) or close
            open_ = abs(number(raw.get("open") or raw.get("open_pric"))) or close
            if close <= 0 or not tm:
                continue
            clean.append({
                "time": tm,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "amount": amount,
            })
        clean.sort(key=lambda x: x["time"])
        clean = [x for x in clean if "09:00" <= x["time"] <= self.continuous_end]
        if not clean:
            return None

        amounts: list[float] = []
        burst_count = 0
        max_ratio = 0.0
        ratios: list[float] = []
        for row in clean:
            baseline = median(amounts[-self.baseline_window:]) if amounts else 0.0
            ratio = row["amount"] / baseline if baseline > 0 else 0.0
            ratios.append(ratio)
            if row["amount"] >= self.min_burst_amount and ratio >= self.burst_ratio:
                burst_count += 1
            max_ratio = max(max_ratio, ratio)
            amounts.append(row["amount"])

        first = clean[0]["open"] or clean[0]["close"]
        last = clean[-1]["close"]
        total_amount = sum(x["amount"] for x in clean)
        close_watch_rows = [
            x for x in clean
            if self.close_watch_start <= x["time"] <= self.continuous_end
        ]
        close_watch_amount = sum(x["amount"] for x in close_watch_rows)
        close_watch_return = (
            percent_change(
                close_watch_rows[0]["open"] or close_watch_rows[0]["close"],
                close_watch_rows[-1]["close"],
            )
            if close_watch_rows
            else 0.0
        )
        median_minute_amount = median(amounts) if amounts else 0.0
        max_minute_amount = max(amounts) if amounts else 0.0
        threshold_counts = {
            str(int(threshold)): sum(1 for amount in amounts if amount >= threshold)
            for threshold in self.amount_thresholds
        }
        stock_return = percent_change(first, last)
        day_high = max(x["high"] for x in clean)
        day_low = min(x["low"] for x in clean)
        high_position = 0.5 if day_high == day_low else (last - day_low) / (day_high - day_low)

        return MinuteSummary(
            ticker=ticker,
            name=str(meta.get("name") or ticker),
            first_price=first,
            last_price=last,
            return_pct=round(stock_return, 3),
            total_amount=round(total_amount, 2),
            close_watch_amount=round(close_watch_amount, 2),
            close_watch_share=round(close_watch_amount / total_amount, 4) if total_amount else 0.0,
            close_watch_return_pct=round(close_watch_return, 3),
            median_minute_amount=round(median_minute_amount, 2),
            max_minute_amount=round(max_minute_amount, 2),
            amount_threshold_counts=threshold_counts,
            burst_count=burst_count,
            max_burst_ratio=round(max_ratio, 3),
            rise_without_burst=stock_return >= 2.0 and burst_count == 0,
            high_position=round(high_position, 4),
            last_minute_amount=round(clean[-1]["amount"], 2),
            last_minute_burst_ratio=round(ratios[-1], 3) if ratios else 0.0,
            group_id=str(meta.get("group_id") or ""),
            sector=str(meta.get("sector") or ""),
            listing_age_days=meta.get("listing_age_days"),
        )

    def summarize_market(
        self,
        minute_by_ticker: dict[str, list[dict[str, Any]]],
        metadata: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        metadata = metadata or {}
        stocks = []
        for ticker, rows in minute_by_ticker.items():
            summary = self.summarize_stock(ticker, rows, metadata.get(ticker))
            if summary:
                stocks.append(summary)

        if not stocks:
            return {
                "status": "insufficient_data",
                "stock_count": 0,
                "reason": "분봉 데이터가 없음",
            }

        advancers = sum(1 for s in stocks if s.return_pct > 0)
        decliners = sum(1 for s in stocks if s.return_pct < 0)
        total_amount = sum(s.total_amount for s in stocks)
        ranked = sorted(stocks, key=lambda s: s.total_amount, reverse=True)
        top10_amount = sum(s.total_amount for s in ranked[:10])
        burst_leaders = sorted(
            stocks,
            key=lambda s: (s.burst_count, s.max_burst_ratio, s.total_amount),
            reverse=True,
        )[:10]

        recent = [
            s for s in stocks
            if s.listing_age_days is not None
            and s.listing_age_days <= int(self.cfg.get("universe", {}).get("recent_listing_calendar_days", 90))
        ]

        groups: dict[str, list[MinuteSummary]] = defaultdict(list)
        for s in stocks:
            key = s.group_id or s.sector
            if key:
                groups[key].append(s)

        coflow = []
        min_members = int(self.cfg.get("coflow", {}).get("minimum_members", 3))
        for key, members in groups.items():
            positive = [s for s in members if s.return_pct > 0 and s.burst_count > 0]
            if len(positive) >= min_members:
                coflow.append({
                    "group": key,
                    "member_count": len(members),
                    "positive_burst_members": len(positive),
                    "members": [
                        {
                            "ticker": s.ticker,
                            "name": s.name,
                            "return_pct": s.return_pct,
                            "burst_count": s.burst_count,
                            "max_burst_ratio": s.max_burst_ratio,
                            "max_minute_amount": s.max_minute_amount,
                            "total_amount": s.total_amount,
                        }
                        for s in sorted(positive, key=lambda x: x.total_amount, reverse=True)
                    ],
                })
        coflow.sort(key=lambda x: (x["positive_burst_members"], x["member_count"]), reverse=True)

        return {
            "status": "ok",
            "stock_count": len(stocks),
            "breadth": {
                "advancers": advancers,
                "decliners": decliners,
                "flat": len(stocks) - advancers - decliners,
                "advance_ratio": round(advancers / len(stocks), 4),
            },
            "turnover": {
                "total_amount": round(total_amount, 2),
                "top10_share": round(top10_amount / total_amount, 4) if total_amount else 0.0,
            },
            "burst_leaders": [s.as_dict() for s in burst_leaders],
            "rise_without_burst": [
                s.as_dict()
                for s in sorted(
                    [x for x in stocks if x.rise_without_burst],
                    key=lambda x: x.return_pct,
                    reverse=True,
                )[:10]
            ],
            "recent_listings": {
                "count": len(recent),
                "positive_burst_count": sum(1 for s in recent if s.return_pct > 0 and s.burst_count > 0),
                "stocks": [s.as_dict() for s in sorted(recent, key=lambda x: x.total_amount, reverse=True)[:15]],
            },
            "coflow_groups": coflow[:10],
            "stocks": [s.as_dict() for s in ranked],
        }


def describe_event_sample(events: list[dict[str, Any]], fields: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {"sample_size": len(events), "fields": {}}
    for field in fields:
        values = [number(x.get(field)) for x in events if x.get(field) not in (None, "")]
        out["fields"][field] = {
            "count": len(values),
            "mean": round(sum(values) / len(values), 4) if values else None,
            "median": round(median(values), 4) if values else None,
            "p25": round(percentile(values, 0.25), 4) if values else None,
            "p75": round(percentile(values, 0.75), 4) if values else None,
        }
    return out
