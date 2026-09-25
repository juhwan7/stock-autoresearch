from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

KST = timezone(timedelta(hours=9))
LATEST = Path("data/providers/naver_batch/latest.json")
HISTORY = Path("data/providers/naver_batch/history.json")
USER_AGENT = "Mozilla/5.0 (compatible; StockAutoResearch/1.0; +https://github.com/juhwan7/stock-autoresearch)"


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


def _fetch_json(url: str, timeout: int = 12) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Referer": "https://stock.naver.com/",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if row.get(key) not in (None, ""):
            return row.get(key)
    return None


def _walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _normalize_code(value: Any) -> str:
    code = str(value or "").strip().upper()
    if code.startswith("A") and len(code) == 7:
        code = code[1:]
    return code


def extract_ranked_stocks(payload: Any, limit: int = 40) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in _walk_dicts(payload):
        code = _normalize_code(
            _first(row, "itemCode", "itemcode", "stockCode", "code", "cd")
        )
        if len(code) != 6 or code in seen:
            continue
        name = str(
            _first(row, "stockName", "itemName", "itemname", "name", "nm") or code
        ).strip()
        value = _number(
            _first(
                row,
                "accumulatedTradingValue",
                "tradingValue",
                "accumulatedTradeValue",
                "aa",
            )
        )
        rows.append(
            {
                "ticker": code,
                "name": name,
                "ranking_trading_value": value,
            }
        )
        seen.add(code)
        if len(rows) >= limit:
            break
    return rows


def extract_polling_quotes(payload: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in _walk_dicts(payload):
        code = _normalize_code(
            _first(row, "itemCode", "itemcode", "stockCode", "code", "cd")
        )
        if len(code) != 6:
            continue
        accumulated_value = _number(
            _first(
                row,
                "accumulatedTradingValue",
                "accumulatedTradeValue",
                "tradingValue",
                "aa",
            )
        )
        accumulated_volume = _number(
            _first(
                row,
                "accumulatedTradingVolume",
                "accumulatedTradeVolume",
                "tradingVolume",
                "aq",
            )
        )
        close = _number(
            _first(row, "closePrice", "currentPrice", "price", "nv")
        )
        if accumulated_value is None and accumulated_volume is None and close is None:
            continue
        result[code] = {
            "ticker": code,
            "name": str(
                _first(row, "stockName", "itemName", "itemname", "name", "nm") or ""
            ).strip()
            or None,
            "last_price": close,
            "day_return_pct": _number(
                _first(row, "fluctuationsRatio", "changeRate", "cr")
            ),
            "accumulated_trading_value": accumulated_value,
            "accumulated_trading_volume": accumulated_volume,
            "local_traded_at": _first(
                row, "localTradedAt", "localTradeTime", "tradeTime"
            ),
            "market_status": _first(row, "marketStatus", "ms"),
        }
    return result


def fetch_turnover_universe(limit: int = 40) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {
            "listingType": "tradingValueDesc",
            "exchangeType": "consolidated",
            "index": 0,
            "size": max(1, min(limit, 100)),
        }
    )
    url = (
        "https://stock.naver.com/api/stockSecurity/individual-stocks/v3/domestic?"
        + params
    )
    return extract_ranked_stocks(_fetch_json(url), limit=limit)


def _fetch_quotes_stock_naver(codes: list[str]) -> dict[str, dict[str, Any]]:
    if not codes:
        return {}
    params = urllib.parse.urlencode({"itemCodes": ",".join(codes)})
    payload = _fetch_json(
        "https://stock.naver.com/api/polling/domestic/stock?" + params
    )
    return extract_polling_quotes(payload)


def _fetch_quotes_legacy(codes: list[str]) -> dict[str, dict[str, Any]]:
    if not codes:
        return {}
    query = "SERVICE_ITEM:" + ",".join(codes)
    params = urllib.parse.urlencode({"query": query})
    payload = _fetch_json(
        "https://polling.finance.naver.com/api/realtime?" + params
    )
    return extract_polling_quotes(payload)


def fetch_quotes(codes: list[str], batch_size: int = 20) -> tuple[dict[str, dict[str, Any]], str]:
    all_quotes: dict[str, dict[str, Any]] = {}
    mode = "stock_naver_polling"
    for start in range(0, len(codes), batch_size):
        chunk = codes[start : start + batch_size]
        try:
            quotes = _fetch_quotes_stock_naver(chunk)
        except (
            OSError,
            TimeoutError,
            urllib.error.URLError,
            urllib.error.HTTPError,
            json.JSONDecodeError,
            ValueError,
        ):
            quotes = {}
        if not quotes:
            mode = "legacy_polling_fallback"
            try:
                quotes = _fetch_quotes_legacy(chunk)
            except (
                OSError,
                TimeoutError,
                urllib.error.URLError,
                urllib.error.HTTPError,
                json.JSONDecodeError,
                ValueError,
            ):
                quotes = {}
        all_quotes.update(quotes)
    return all_quotes, mode


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


def _same_kst_day(a: datetime, b: datetime) -> bool:
    return a.astimezone(KST).date() == b.astimezone(KST).date()


def build_interval_rows(
    current_quotes: dict[str, dict[str, Any]],
    previous: dict[str, Any],
    now: datetime,
) -> tuple[list[dict[str, Any]], float | None]:
    previous_at = _parse_time(previous.get("generated_at"))
    previous_quotes = {
        str(item.get("ticker") or ""): item
        for item in previous.get("stocks", [])
        if isinstance(item, dict) and item.get("ticker")
    }

    elapsed_minutes: float | None = None
    if previous_at and _same_kst_day(previous_at, now):
        elapsed_minutes = max(0.0, (now - previous_at).total_seconds() / 60.0)

    rows: list[dict[str, Any]] = []
    for code, current in current_quotes.items():
        item = dict(current)
        item["interval_trading_value"] = None
        item["interval_minutes"] = elapsed_minutes
        item["per_minute_average_trading_value"] = None
        item["interval_valid"] = False
        old = previous_quotes.get(code)
        current_value = _number(current.get("accumulated_trading_value"))
        old_value = _number((old or {}).get("accumulated_trading_value"))
        if (
            elapsed_minutes is not None
            and 2.0 <= elapsed_minutes <= 15.0
            and current_value is not None
            and old_value is not None
            and current_value >= old_value
        ):
            delta = current_value - old_value
            item["interval_trading_value"] = delta
            item["per_minute_average_trading_value"] = (
                delta / elapsed_minutes if elapsed_minutes > 0 else None
            )
            item["interval_valid"] = True
        rows.append(item)

    rows.sort(
        key=lambda item: float(item.get("interval_trading_value") or 0),
        reverse=True,
    )
    return rows, elapsed_minutes


def collect(root: Path, *, now: datetime | None = None, limit: int = 40) -> dict[str, Any]:
    now = now or datetime.now(KST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=KST)
    now = now.astimezone(KST)

    latest_path = root / LATEST
    history_path = root / HISTORY
    previous = _read_json(latest_path)

    source_status = "ok"
    error: str | None = None
    try:
        universe = fetch_turnover_universe(limit=limit)
    except Exception as exc:
        universe = []
        source_status = "ranking_error"
        error = type(exc).__name__

    codes = [item["ticker"] for item in universe]
    quotes: dict[str, dict[str, Any]] = {}
    polling_mode = "unavailable"
    if codes:
        try:
            quotes, polling_mode = fetch_quotes(codes)
        except Exception as exc:
            source_status = "polling_error"
            error = type(exc).__name__

    names = {item["ticker"]: item["name"] for item in universe}
    for code, quote in quotes.items():
        if not quote.get("name"):
            quote["name"] = names.get(code)

    interval_rows, elapsed_minutes = build_interval_rows(quotes, previous, now)
    valid_rows = [item for item in interval_rows if item.get("interval_valid")]

    if not universe:
        status = "unavailable"
    elif not quotes:
        status = "degraded"
    elif previous and not valid_rows:
        status = "warming_or_gap"
    else:
        status = "ok"

    snapshot = {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "status": status,
        "source_status": source_status,
        "error": error,
        "provider": "naver_public",
        "mode": "six_minute_batch",
        "polling_mode": polling_mode,
        "universe_method": "trading_value_desc",
        "universe_count": len(universe),
        "quote_count": len(quotes),
        "elapsed_minutes_from_previous": elapsed_minutes,
        "exact_1m_bars": False,
        "amount_method": "cumulative_trading_value_delta",
        "interpretation": (
            "직전 관측과 현재 누적 거래대금의 차이로 최근 약 6분 거래대금을 계산한다. "
            "per_minute_average_trading_value는 해당 구간의 분당 평균이며 정확한 1분봉 6개가 아니다."
        ),
        "stocks": interval_rows,
        "interval_leaders": valid_rows[:20],
        "limitations": [
            "네이버 공개 read-only 시세 기반으로 API 계약이 예고 없이 바뀔 수 있음",
            "GitHub Actions 실행 지연에 따라 관측 간격이 정확히 6분이 아닐 수 있음",
            "분당 평균 거래대금은 6분 구간 평균이며 개별 1분 Burst를 확정하지 않음",
        ],
    }
    _write_json(latest_path, snapshot)

    history = _read_json(history_path)
    snapshots = history.get("snapshots", [])
    if not isinstance(snapshots, list):
        snapshots = []
    snapshots.append(
        {
            "generated_at": snapshot["generated_at"],
            "status": status,
            "elapsed_minutes_from_previous": elapsed_minutes,
            "interval_leaders": valid_rows[:20],
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
        "status": status,
        "provider": "naver_public",
        "universe_count": len(universe),
        "quote_count": len(quotes),
        "valid_interval_count": len(valid_rows),
        "elapsed_minutes": elapsed_minutes,
        "latest": str(LATEST),
    }
