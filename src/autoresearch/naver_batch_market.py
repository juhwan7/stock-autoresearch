from __future__ import annotations

import json
import math
import re
import time
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


def _fetch_text(url: str, timeout: int = 12) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,*/*;q=0.8",
            "Referer": "https://finance.naver.com/",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset()
    for encoding in [charset, "euc-kr", "cp949", "utf-8"]:
        if not encoding:
            continue
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&#39;", "'")
        .replace("&quot;", '"')
    )
    return re.sub(r"\s+", " ", text).strip()


def parse_time_quote_rows(html_text: str) -> list[dict[str, Any]]:
    """네이버 시간별 시세 표를 최근 1분 표본으로 정규화한다.

    표의 '거래량'은 누적 거래량으로 취급하고, 마지막 열에 분당 변동량이 있으면
    우선 사용한다. 없으면 인접 누적 거래량 차이로 복원한다.
    """
    rows: list[dict[str, Any]] = []
    blocks = re.findall(
        r"<tr[^>]*onmouseover=[\"']mouseOver\(this\)[\"'][^>]*>(.*?)</tr>",
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for block in blocks:
        cells = [
            _strip_html(x)
            for x in re.findall(
                r"<td[^>]*>(.*?)</td>",
                block,
                flags=re.IGNORECASE | re.DOTALL,
            )
        ]
        if len(cells) < 6:
            continue
        tm = cells[0].strip()
        if not re.fullmatch(r"\d{2}:\d{2}", tm):
            continue
        price = _number(cells[1])
        cumulative_volume = _number(cells[5]) if len(cells) >= 6 else None
        reported_delta_volume = _number(cells[6]) if len(cells) >= 7 else None
        if price is None:
            continue
        rows.append(
            {
                "time": tm,
                "price": price,
                "accumulated_volume": cumulative_volume,
                "reported_minute_volume": (
                    abs(reported_delta_volume)
                    if reported_delta_volume is not None
                    else None
                ),
            }
        )

    # 화면은 보통 최신→과거 순서다. 누적 거래량 차이로 분당 거래량을 보완한다.
    for idx, row in enumerate(rows):
        minute_volume = row.get("reported_minute_volume")
        if minute_volume is None and idx + 1 < len(rows):
            current_total = _number(row.get("accumulated_volume"))
            older_total = _number(rows[idx + 1].get("accumulated_volume"))
            if (
                current_total is not None
                and older_total is not None
                and current_total >= older_total
            ):
                minute_volume = current_total - older_total
        row["minute_volume"] = minute_volume
        row["raw_trading_value_estimate"] = (
            float(row["price"]) * float(minute_volume)
            if minute_volume is not None
            else None
        )

    rows.sort(key=lambda item: str(item.get("time") or ""))
    return rows


def fetch_recent_minute_samples(
    ticker: str,
    now: datetime,
    *,
    limit: int = 6,
) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {
            "code": ticker,
            "thistime": now.astimezone(KST).strftime("%Y%m%d%H%M%S"),
            "page": 1,
        }
    )
    html_text = _fetch_text(
        "https://finance.naver.com/item/sise_time.naver?" + params
    )
    rows = parse_time_quote_rows(html_text)
    return rows[-max(1, limit):]


def _quote_traded_today(quote: dict[str, Any], now: datetime) -> bool:
    traded = _parse_time(quote.get("local_traded_at"))
    return bool(traded and traded.date() == now.astimezone(KST).date())


def calibrate_minute_samples(
    samples: list[dict[str, Any]],
    interval_total: float | None,
) -> list[dict[str, Any]]:
    """1분 가격×거래량 근사치를 6분 누적 거래대금 차분에 맞춰 보정한다."""
    rows = [dict(item) for item in samples]
    raw_sum = sum(
        float(item.get("raw_trading_value_estimate") or 0)
        for item in rows
    )
    scale = (
        float(interval_total) / raw_sum
        if interval_total is not None and interval_total >= 0 and raw_sum > 0
        else None
    )
    for item in rows:
        raw = item.get("raw_trading_value_estimate")
        item["minute_trading_value"] = (
            float(raw) * scale
            if raw is not None and scale is not None
            else raw
        )
        item["amount_estimated"] = True
        item["calibrated_to_interval_total"] = scale is not None
    return rows


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


def extract_ranked_stocks(payload: Any, limit: int = 50) -> list[dict[str, Any]]:
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


def fetch_turnover_universe(limit: int = 50) -> list[dict[str, Any]]:
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


def build_daily_tracked_universe(
    current_top: list[dict[str, Any]],
    previous: dict[str, Any],
    now: datetime,
) -> list[dict[str, Any]]:
    """오늘 한 번이라도 거래대금 Top50에 들어온 종목을 장 마감까지 유지한다."""
    previous_at = _parse_time(previous.get("generated_at"))
    same_day = bool(previous_at and _same_kst_day(previous_at, now))

    prior_rows = (
        previous.get("tracked_universe", [])
        if same_day and isinstance(previous.get("tracked_universe"), list)
        else []
    )
    tracked: dict[str, dict[str, Any]] = {}
    for row in prior_rows:
        if not isinstance(row, dict):
            continue
        code = _normalize_code(row.get("ticker"))
        if len(code) != 6:
            continue
        tracked[code] = dict(row)
        tracked[code]["ticker"] = code
        tracked[code]["in_current_top50"] = False
        tracked[code]["current_rank"] = None

    for rank, row in enumerate(current_top[:50], start=1):
        code = _normalize_code(row.get("ticker"))
        if len(code) != 6:
            continue
        existing = tracked.get(code, {})
        first_seen = (
            existing.get("first_top50_at")
            or now.isoformat()
        )
        tracked[code] = {
            **existing,
            "ticker": code,
            "name": row.get("name") or existing.get("name") or code,
            "first_top50_at": first_seen,
            "last_top50_at": now.isoformat(),
            "current_rank": rank,
            "last_top50_rank": rank,
            "in_current_top50": True,
            "ranking_trading_value": row.get("ranking_trading_value"),
        }

    rows = list(tracked.values())
    rows.sort(
        key=lambda item: (
            0 if item.get("in_current_top50") else 1,
            int(item.get("current_rank") or item.get("last_top50_rank") or 9999),
            str(item.get("ticker") or ""),
        )
    )
    return rows


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


def collect(root: Path, *, now: datetime | None = None, limit: int = 50) -> dict[str, Any]:
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
        current_top50 = fetch_turnover_universe(limit=50)
    except Exception as exc:
        current_top50 = []
        source_status = "ranking_error"
        error = type(exc).__name__

    tracked_universe = build_daily_tracked_universe(
        current_top50,
        previous,
        now,
    )
    codes = [
        str(item.get("ticker") or "")
        for item in tracked_universe
        if item.get("ticker")
    ]

    quotes: dict[str, dict[str, Any]] = {}
    polling_mode = "unavailable"
    if codes:
        try:
            quotes, polling_mode = fetch_quotes(codes)
        except Exception as exc:
            source_status = "polling_error"
            error = type(exc).__name__

    ranking_fresh_today = any(
        _quote_traded_today(quotes.get(str(item.get("ticker") or "")) or {}, now)
        for item in current_top50
    )
    if not ranking_fresh_today:
        # 휴장일·개장 전에는 이전 거래일 순위가 노출될 수 있으므로
        # 오늘 Top50 신규 진입으로 기록하지 않는다. 이미 오늘 추적 중이던 종목만 유지한다.
        current_top50 = []
        tracked_universe = build_daily_tracked_universe([], previous, now)
        codes = [
            str(item.get("ticker") or "")
            for item in tracked_universe
            if item.get("ticker")
        ]
        quotes = {
            code: quote
            for code, quote in quotes.items()
            if code in set(codes)
        }

    universe_by_code = {
        str(item.get("ticker") or ""): item
        for item in tracked_universe
        if item.get("ticker")
    }
    current_top_by_code = {
        str(item.get("ticker") or ""): item
        for item in current_top50
        if item.get("ticker")
    }
    names = {code: item.get("name") for code, item in universe_by_code.items()}
    for code in codes:
        quote = quotes.setdefault(
            code,
            {
                "ticker": code,
                "name": names.get(code),
                "last_price": None,
                "day_return_pct": None,
                "accumulated_trading_value": None,
                "accumulated_trading_volume": None,
                "local_traded_at": None,
                "market_status": None,
            },
        )
        if not quote.get("name"):
            quote["name"] = names.get(code)
        if quote.get("accumulated_trading_value") is None:
            quote["accumulated_trading_value"] = _number(
                current_top_by_code.get(code, {}).get("ranking_trading_value")
            )
            if quote.get("accumulated_trading_value") is not None:
                quote["trading_value_source"] = "ranking"
        else:
            quote["trading_value_source"] = "polling"

    interval_rows, elapsed_minutes = build_interval_rows(quotes, previous, now)
    valid_rows = [item for item in interval_rows if item.get("interval_valid")]

    interval_by_ticker = {
        str(item.get("ticker") or ""): item
        for item in interval_rows
        if item.get("ticker")
    }
    minute_samples_by_ticker: dict[str, list[dict[str, Any]]] = {}
    minute_sample_errors: dict[str, str] = {}
    # 오늘 한 번이라도 Top50에 들어온 모든 종목을 계속 갱신한다.
    # 현재 54위 등 Top50 밖으로 밀려난 종목도 당일 추적에서 제외하지 않는다.
    for code in codes:
        quote = quotes.get(code) or {}
        # 휴장일/장 종료 뒤 과거 값이 섞이는 것을 막기 위해 오늘 체결이 확인된 종목만 조회한다.
        if not _quote_traded_today(quote, now):
            continue
        try:
            raw_samples = fetch_recent_minute_samples(code, now, limit=6)
            interval_total = _number(
                (interval_by_ticker.get(code) or {}).get("interval_trading_value")
            )
            samples = calibrate_minute_samples(raw_samples, interval_total)
            if samples:
                minute_samples_by_ticker[code] = samples
        except Exception as exc:
            minute_sample_errors[code] = type(exc).__name__
        time.sleep(0.12)

    if not current_top50 and not tracked_universe:
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
        "universe_method": "daily_union_of_every_top50_entry",
        "ranking_fresh_today": ranking_fresh_today,
        "current_top50_count": len(current_top50),
        "tracked_universe_count": len(tracked_universe),
        "dropped_from_current_top50_count": sum(
            1 for item in tracked_universe
            if not item.get("in_current_top50")
        ),
        "tracked_universe": tracked_universe,
        "current_top50": [
            {
                **item,
                "current_rank": rank,
            }
            for rank, item in enumerate(current_top50[:50], start=1)
        ],
        "universe_count": len(tracked_universe),
        "quote_count": len(quotes),
        "elapsed_minutes_from_previous": elapsed_minutes,
        "exact_1m_bars": False,
        "one_minute_samples_available": bool(minute_samples_by_ticker),
        "minute_amount_exact": False,
        "amount_method": "cumulative_trading_value_delta",
        "minute_amount_method": "price_x_minute_volume_scaled_to_interval_total",
        "minute_sample_ticker_count": len(minute_samples_by_ticker),
        "tracked_outside_top50_with_samples": sum(
            1
            for item in tracked_universe
            if not item.get("in_current_top50")
            and str(item.get("ticker") or "") in minute_samples_by_ticker
        ),
        "minute_sample_errors": minute_sample_errors,
        "minute_samples_by_ticker": minute_samples_by_ticker,
        "interpretation": (
            "직전 관측과 현재 누적 거래대금의 차이로 최근 약 6분 총 거래대금을 계산한다. "
            "동시에 네이버 시간별 시세에서 최근 6개 분 단위 거래량 표본을 받아 가격×분당 거래량으로 "
            "1분 거래대금을 근사하고, 가능하면 6분 누적 거래대금 차분 합계에 맞춰 보정한다. "
            "따라서 6개의 1분 표본은 사용할 수 있지만 정확한 체결대금 합산값은 아니다."
        ),
        "stocks": interval_rows,
        "interval_leaders": valid_rows[:20],
        "limitations": [
            "네이버 공개 read-only 시세 기반으로 API 계약이 예고 없이 바뀔 수 있음",
            "GitHub Actions 실행 지연에 따라 관측 간격이 정확히 6분이 아닐 수 있음",
            "당일 실제 체결이 확인된 Top50만 신규 편입하며 휴장일·개장 전 이전 거래일 순위는 제외",
            "당일 한 번이라도 거래대금 Top50에 진입한 종목은 순위 밖으로 밀려나도 장 마감까지 계속 추적",
            "최근 6개 1분 표본의 거래대금은 가격×분당 거래량 기반 근사치이며 정확 체결대금 합산값이 아님",
            "6분 누적 거래대금 차분은 분 단위 근사치의 합계 교차검증과 보정에 사용",
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
            "current_top50_count": len(current_top50),
            "tracked_universe_count": len(tracked_universe),
            "dropped_from_current_top50_count": sum(
                1 for item in tracked_universe
                if not item.get("in_current_top50")
            ),
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
        "current_top50_count": len(current_top50),
        "tracked_universe_count": len(tracked_universe),
        "dropped_from_current_top50_count": sum(
            1 for item in tracked_universe
            if not item.get("in_current_top50")
        ),
        "universe_count": len(tracked_universe),
        "quote_count": len(quotes),
        "valid_interval_count": len(valid_rows),
        "elapsed_minutes": elapsed_minutes,
        "latest": str(LATEST),
    }
