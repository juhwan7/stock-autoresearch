from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any

from .market_stats import number, percent_change


KST = timezone(timedelta(hours=9))


class TossSnapshotError(RuntimeError):
    pass


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


def _time_label(value: Any) -> str:
    text = str(value or "")
    parsed = _parse_time(text)
    if parsed is not None:
        return parsed.strftime("%H:%M")
    if len(text) >= 5 and ":" in text:
        return text[-5:]
    return text


def _normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        close = abs(number(row.get("close") or row.get("closePrice")))
        volume = abs(number(row.get("volume")))
        amount_value = row.get("amount")
        amount = (
            abs(number(amount_value))
            if amount_value not in (None, "")
            else close * volume
        )
        if close <= 0:
            continue
        result.append(
            {
                "time": _time_label(row.get("time") or row.get("timestamp")),
                "open": abs(number(row.get("open") or row.get("openPrice"))) or close,
                "high": abs(number(row.get("high") or row.get("highPrice"))) or close,
                "low": abs(number(row.get("low") or row.get("lowPrice"))) or close,
                "close": close,
                "volume": volume,
                "amount": amount,
                "amount_estimated": amount_value in (None, ""),
            }
        )
    result.sort(key=lambda x: x["time"])
    return result


class TossCollectorBridge:
    """고정 IP Toss Collector가 만든 정규화 스냅샷을 읽는다.

    이 모듈은 주문/계좌 API를 사용하지 않는다.
    """

    def __init__(
        self,
        root: Path,
        *,
        snapshot_path: str = "data/providers/toss/latest.json",
        max_age_minutes: int = 20,
    ):
        self.root = root
        self.path = root / snapshot_path
        self.max_age_minutes = max_age_minutes

    def load(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now(KST)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise TossSnapshotError("토스 Collector 스냅샷이 없음") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise TossSnapshotError("토스 Collector 스냅샷을 읽을 수 없음") from exc

        captured = _parse_time(data.get("captured_at"))
        if captured is None:
            raise TossSnapshotError("captured_at이 없거나 잘못됨")
        age = (now - captured).total_seconds() / 60.0
        if age < -5:
            raise TossSnapshotError("토스 스냅샷 시각이 미래로 크게 벗어남")
        if age > self.max_age_minutes:
            raise TossSnapshotError(
                f"토스 스냅샷이 오래됨: {age:.0f}분"
            )

        if not isinstance(data.get("minute_by_ticker"), dict):
            raise TossSnapshotError("minute_by_ticker가 없음")
        return data

    def market_payload(
        self,
        now: datetime | None = None,
    ) -> tuple[
        dict[str, list[dict[str, Any]]],
        dict[str, dict[str, Any]],
        dict[str, Any],
    ]:
        data = self.load(now)
        minute = {
            str(ticker): _normalize_rows(rows)
            for ticker, rows in data.get("minute_by_ticker", {}).items()
            if isinstance(rows, list)
        }
        metadata = {
            str(ticker): dict(item)
            for ticker, item in data.get("metadata", {}).items()
            if isinstance(item, dict)
        }

        for row in data.get("ranking", []):
            if not isinstance(row, dict):
                continue
            ticker = str(row.get("ticker") or row.get("symbol") or "")
            if not ticker:
                continue
            meta = metadata.setdefault(ticker, {})
            meta.setdefault("name", row.get("name") or ticker)
            if row.get("day_return_pct") not in (None, ""):
                meta["day_return_pct"] = number(row.get("day_return_pct"))
            if row.get("trading_value") not in (None, ""):
                meta["ranking_trading_value_raw"] = abs(
                    number(row.get("trading_value"))
                )

        source = {
            "source": "toss_collector",
            "provider": "toss",
            "status": "ok" if minute else "no_rows",
            "captured_at": data.get("captured_at"),
            "market_overview": data.get("market_overview", {}),
            "turnover_rank_top10_share": data.get(
                "turnover_rank_top10_share"
            ),
            "detail_count": len(minute),
            "minute_amount_method": data.get(
                "minute_amount_method",
                "exact_trade_sum",
            ),
            "session": data.get("session", {}),
            "postmarket": self._postmarket_summary(data, metadata),
        }
        return minute, metadata, source

    def _postmarket_summary(
        self,
        data: dict[str, Any],
        metadata: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        summaries = []
        for ticker, raw_rows in data.get("postmarket_by_ticker", {}).items():
            if not isinstance(raw_rows, list):
                continue
            rows = _normalize_rows(raw_rows)
            if not rows:
                continue
            amounts = [float(x.get("amount") or 0) for x in rows]
            first = float(rows[0]["close"])
            last = float(rows[-1]["close"])
            meta = metadata.get(str(ticker), {})
            krx_close = number(
                meta.get("krx_close")
                or meta.get("regular_close")
            )
            summaries.append(
                {
                    "ticker": str(ticker),
                    "name": meta.get("name") or str(ticker),
                    "nxt_eligible": True,
                    "start_time": rows[0]["time"],
                    "last_time": rows[-1]["time"],
                    "last_price": last,
                    "return_pct": round(percent_change(first, last), 4),
                    "krx_close_premium_pct": (
                        round(percent_change(krx_close, last), 4)
                        if krx_close > 0
                        else None
                    ),
                    "amount": round(sum(amounts), 2),
                    "median_minute_amount": round(median(amounts), 2)
                    if amounts
                    else 0.0,
                    "max_minute_amount": round(max(amounts), 2)
                    if amounts
                    else 0.0,
                    "minute_ge_10eok_count": sum(
                        1 for x in amounts if x >= 1_000_000_000
                    ),
                    "minute_ge_20eok_count": sum(
                        1 for x in amounts if x >= 2_000_000_000
                    ),
                    "amount_estimated": any(
                        bool(x.get("amount_estimated")) for x in rows
                    ),
                }
            )

        summaries.sort(
            key=lambda x: float(x.get("amount") or 0),
            reverse=True,
        )
        return {
            "count": len(summaries),
            "total_amount": round(
                sum(float(x.get("amount") or 0) for x in summaries),
                2,
            ),
            "stocks": summaries[:50],
        }
