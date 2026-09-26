from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .toss_collector import TossCollectorError, TossRestClient

KST = timezone(timedelta(hours=9))
LATEST = Path("data/providers/toss/latest.json")
HISTORY = Path("data/providers/toss/history.json")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


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


def _same_day(a: datetime | None, b: datetime) -> bool:
    return bool(a and a.astimezone(KST).date() == b.astimezone(KST).date())


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _session_of(ts: datetime) -> str | None:
    hhmm = ts.strftime("%H:%M")
    if "08:00" <= hhmm <= "08:50":
        return "pre"
    if "09:00" <= hhmm <= "15:30":
        return "regular"
    if "15:40" <= hhmm <= "20:00":
        return "post"
    return None


def _daily_tracked_universe(
    current_top50: list[dict[str, Any]],
    previous: dict[str, Any],
    now: datetime,
    *,
    ranking_fresh_today: bool,
) -> list[dict[str, Any]]:
    previous_at = _parse_time(previous.get("captured_at"))
    keep_previous = (
        _same_day(previous_at, now)
        and previous.get("ranking_fresh_today") is not False
    )
    tracked: dict[str, dict[str, Any]] = {}
    if keep_previous:
        for row in previous.get("tracked_universe", []):
            if not isinstance(row, dict):
                continue
            ticker = str(row.get("ticker") or "")
            if not ticker:
                continue
            tracked[ticker] = {
                **row,
                "ticker": ticker,
                "current_rank": None,
                "in_current_top50": False,
            }

    if ranking_fresh_today:
        for rank, row in enumerate(current_top50[:50], start=1):
            ticker = str(row.get("ticker") or "")
            if not ticker:
                continue
            old = tracked.get(ticker, {})
            tracked[ticker] = {
                **old,
                "ticker": ticker,
                "name": row.get("name") or old.get("name") or ticker,
                "first_top50_at": old.get("first_top50_at") or now.isoformat(),
                "last_top50_at": now.isoformat(),
                "current_rank": rank,
                "last_top50_rank": rank,
                "in_current_top50": True,
            }

    rows = list(tracked.values())
    rows.sort(
        key=lambda row: (
            0 if row.get("in_current_top50") else 1,
            int(row.get("current_rank") or row.get("last_top50_rank") or 9999),
            str(row.get("ticker") or ""),
        )
    )
    return rows


def _candles(client: TossRestClient, ticker: str, count: int = 12) -> list[dict[str, Any]]:
    payload = client.get_json(
        "/api/v1/candles",
        {
            "symbol": ticker,
            "interval": "1m",
            "count": min(max(count, 1), 200),
            "adjusted": True,
        },
    )
    result = payload.get("result") or {}
    rows: list[dict[str, Any]] = []
    for item in result.get("candles") or []:
        if not isinstance(item, dict):
            continue
        stamp = _parse_time(item.get("timestamp"))
        if stamp is None:
            continue
        op = _num(item.get("openPrice"))
        hi = _num(item.get("highPrice"))
        lo = _num(item.get("lowPrice"))
        cl = _num(item.get("closePrice"))
        vol = _num(item.get("volume"))
        if cl is None or vol is None:
            continue
        rows.append(
            {
                "timestamp": stamp.isoformat(),
                "open": op,
                "high": hi,
                "low": lo,
                "close": cl,
                "volume": vol,
                "amount": cl * vol,
                "amount_estimated": True,
                "amount_method": "close_x_volume",
            }
        )
    rows.sort(key=lambda row: str(row.get("timestamp") or ""))
    return rows


def _merge_rows(old_rows: list[dict[str, Any]], new_rows: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    by_ts: dict[str, dict[str, Any]] = {}
    for row in [*old_rows, *new_rows]:
        if not isinstance(row, dict):
            continue
        stamp = _parse_time(row.get("timestamp") or row.get("time"))
        if not _same_day(stamp, now):
            continue
        by_ts[stamp.isoformat()] = {**row, "timestamp": stamp.isoformat()}
    return [by_ts[key] for key in sorted(by_ts)][-500:]


def _calibrate_interval(
    rows: list[dict[str, Any]],
    *,
    previous_at: datetime | None,
    interval_total: float | None,
) -> None:
    if previous_at is None or interval_total is None or interval_total < 0:
        return
    interval_rows = [
        row
        for row in rows
        if (_parse_time(row.get("timestamp")) or previous_at) > previous_at
    ]
    raw_sum = sum(float(row.get("amount") or 0) for row in interval_rows)
    if raw_sum <= 0:
        return
    scale = interval_total / raw_sum
    for row in interval_rows:
        row["amount"] = float(row.get("amount") or 0) * scale
        row["amount_estimated"] = True
        row["amount_method"] = "close_x_volume_scaled_to_exact_ranking_delta"
        row["calibrated_to_exact_interval_total"] = True


def collect(root: Path, *, now: datetime | None = None, limit: int = 50) -> dict[str, Any]:
    now = (now or datetime.now(KST)).astimezone(KST)
    client_id = os.getenv("TOSS_CLIENT_ID", "").strip()
    client_secret = os.getenv("TOSS_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise TossCollectorError("TOSS_CLIENT_ID/TOSS_CLIENT_SECRET이 없음")

    client = TossRestClient(client_id, client_secret)
    latest_path = root / LATEST
    previous = _read_json(latest_path)
    previous_at = _parse_time(previous.get("captured_at"))

    top_n = min(max(int(limit), 1), 100)
    ranking = client.rankings(top_n)
    ranked_at = _parse_time(ranking[0].get("ranked_at")) if ranking else None
    ranking_fresh_today = bool(ranked_at and ranked_at.date() == now.date())

    metadata = dict(previous.get("metadata") or {})
    current_top50 = ranking[:top_n] if ranking_fresh_today else []
    current_codes = [str(row.get("ticker") or "") for row in current_top50 if row.get("ticker")]
    if current_codes:
        metadata.update(client.stocks(current_codes))

    tracked_universe = _daily_tracked_universe(
        current_top50,
        previous,
        now,
        ranking_fresh_today=ranking_fresh_today,
    )
    codes = [str(row.get("ticker") or "") for row in tracked_universe if row.get("ticker")]

    previous_rank = {
        str(row.get("ticker") or ""): row
        for row in previous.get("ranking", [])
        if isinstance(row, dict) and row.get("ticker")
    }
    current_rank = {
        str(row.get("ticker") or ""): row
        for row in current_top50
        if isinstance(row, dict) and row.get("ticker")
    }

    regular: dict[str, list[dict[str, Any]]] = {}
    premarket: dict[str, list[dict[str, Any]]] = {}
    postmarket: dict[str, list[dict[str, Any]]] = {}
    errors: dict[str, str] = {}

    for ticker in codes:
        try:
            recent = _candles(client, ticker, count=12)
            recent = [
                row for row in recent
                if _same_day(_parse_time(row.get("timestamp")), now)
            ]
            if ticker in current_rank and ticker in previous_rank and previous_at and _same_day(previous_at, now):
                current_value = _num(current_rank[ticker].get("trading_value"))
                old_value = _num(previous_rank[ticker].get("trading_value"))
                elapsed = (now - previous_at).total_seconds() / 60.0
                if (
                    current_value is not None
                    and old_value is not None
                    and current_value >= old_value
                    and 2.0 <= elapsed <= 15.0
                ):
                    _calibrate_interval(
                        recent,
                        previous_at=previous_at,
                        interval_total=current_value - old_value,
                    )

            buckets = {"regular": [], "pre": [], "post": []}
            for row in recent:
                stamp = _parse_time(row.get("timestamp"))
                session = _session_of(stamp) if stamp else None
                if session:
                    buckets[session].append(row)

            regular[ticker] = _merge_rows(
                (previous.get("minute_by_ticker") or {}).get(ticker, []),
                buckets["regular"],
                now,
            )
            premarket[ticker] = _merge_rows(
                (previous.get("premarket_by_ticker") or {}).get(ticker, []),
                buckets["pre"],
                now,
            )
            postmarket[ticker] = _merge_rows(
                (previous.get("postmarket_by_ticker") or {}).get(ticker, []),
                buckets["post"],
                now,
            )
        except Exception as exc:
            errors[ticker] = type(exc).__name__
        time.sleep(0.06)

    regular = {k: v for k, v in regular.items() if v}
    premarket = {k: v for k, v in premarket.items() if v}
    postmarket = {k: v for k, v in postmarket.items() if v}

    snapshot = {
        "schema_version": 1,
        "captured_at": now.isoformat(),
        "provider": "toss",
        "source_mode": "rest_10m_batch",
        "ranking_fresh_today": ranking_fresh_today,
        "minute_amount_method": "close_x_volume; current Top50 interval may be scaled to exact ranking tradingAmount delta",
        "minute_amount_exact": False,
        "ranking": current_top50,
        "metadata": metadata,
        "market_overview": {},
        "tracked_universe": tracked_universe,
        "current_top50_count": len(current_top50),
        "tracked_universe_count": len(tracked_universe),
        "dropped_from_current_top50_count": sum(
            1 for row in tracked_universe if not row.get("in_current_top50")
        ),
        "minute_by_ticker": regular,
        "premarket_by_ticker": premarket,
        "postmarket_by_ticker": postmarket,
        "fetch_errors": errors,
        "collector": {
            "mode": "rest_10m_batch",
            "last_universe_refresh": now.isoformat(),
            "last_message_at": now.isoformat() if (regular or premarket or postmarket) else None,
            "subscriptions": [],
            "rejected": [],
        },
        "session": {
            "pre_market": {"start": "08:00", "end": "08:50"},
            "krx_regular": {"start": "09:00", "end": "15:30"},
            "nxt_after": {"start": "15:40", "end": "20:00"},
        },
        "limitations": [
            "Toss REST 1분봉은 OHLCV를 제공하므로 1분 거래대금은 close×volume 근사치",
            "현재 Top50이 직전 관측에도 Top50이었다면 Toss ranking tradingAmount 차분으로 해당 관측구간 합계를 보정",
            "Top50 밖으로 밀린 종목도 당일 추적 Universe에 남아 1분봉 조회를 계속함",
        ],
    }
    _write_json(latest_path, snapshot)

    history_path = root / HISTORY
    history = _read_json(history_path)
    snapshots = history.get("snapshots", [])
    if not isinstance(snapshots, list):
        snapshots = []
    snapshots.append(
        {
            "captured_at": now.isoformat(),
            "ranking_fresh_today": ranking_fresh_today,
            "current_top50_count": len(current_top50),
            "tracked_universe_count": len(tracked_universe),
            "dropped_from_current_top50_count": snapshot["dropped_from_current_top50_count"],
            "regular_ticker_count": len(regular),
            "error_count": len(errors),
        }
    )
    _write_json(
        history_path,
        {
            "schema_version": 1,
            "updated_at": now.isoformat(),
            "snapshots": snapshots[-120:],
        },
    )

    return {
        "status": "ok" if ranking_fresh_today else "idle_or_holiday",
        "provider": "toss",
        "source_mode": "rest_10m_batch",
        "current_top50_count": len(current_top50),
        "tracked_universe_count": len(tracked_universe),
        "regular_ticker_count": len(regular),
        "error_count": len(errors),
    }
