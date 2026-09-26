from __future__ import annotations

import json
import math
import re
import statistics
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

KST = timezone(timedelta(hours=9))
OUTPUT = Path("data/market/relative-strength.json")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0 Safari/537.36"
)
CACHE_MINUTES = 30
UNIVERSE_LIMIT = 500


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _fetch_json(url: str, *, referer: str, timeout: int = 20) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
            "Referer": referer,
            "Origin": referer.rstrip("/"),
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_text(url: str, timeout: int = 20) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
            "Referer": "https://finance.naver.com/",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset()
    for encoding in (charset, "euc-kr", "cp949", "utf-8"):
        if not encoding:
            continue
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            pass
    return raw.decode("utf-8", errors="replace")


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    replacements = {
        "&nbsp;": " ",
        "&amp;": "&",
        "&#39;": "'",
        "&quot;": '"',
        "▲": "+",
        "▼": "-",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return re.sub(r"\s+", " ", text).strip()


def _number(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", "").replace("$", "").replace("%", "")
    text = text.replace("+", "")
    if text in {"", "-", "--", "N/A", "n/a"}:
        return None
    multiplier = 1.0
    suffix = text[-1:].upper()
    if suffix in {"K", "M", "B", "T"}:
        multiplier = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}[suffix]
        text = text[:-1]
    try:
        number = float(text) * multiplier
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if row.get(key) not in (None, ""):
            return row.get(key)
    return None


def _generated_recently(previous: dict[str, Any], now: datetime) -> bool:
    value = previous.get("generated_at")
    if not value:
        return False
    try:
        stamp = datetime.fromisoformat(str(value))
    except ValueError:
        return False
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=KST)
    return now - stamp.astimezone(KST) < timedelta(minutes=CACHE_MINUTES)


def parse_nasdaq_screener(payload: Any, limit: int = UNIVERSE_LIMIT) -> list[dict[str, Any]]:
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    rows = data.get("rows", []) if isinstance(data, dict) else []
    parsed: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        ticker = str(_first(row, "symbol", "Symbol") or "").strip().upper()
        name = str(_first(row, "name", "companyName", "Name") or ticker).strip()
        change_pct = _number(_first(row, "pctchange", "percentageChange", "changePercent"))
        market_cap = _number(_first(row, "marketCap", "marketcap"))
        if not ticker or change_pct is None or not market_cap or market_cap <= 0:
            continue
        parsed.append(
            {
                "ticker": ticker,
                "name": name,
                "change_pct": change_pct,
                "price": _number(_first(row, "lastsale", "lastSalePrice", "lastPrice")),
                "volume": _number(_first(row, "volume", "Volume")),
                "market_cap": market_cap,
                "source": "Nasdaq Stock Screener",
            }
        )
    parsed.sort(key=lambda x: float(x.get("market_cap") or 0), reverse=True)
    return parsed[: max(1, limit)]


def parse_nasdaq_benchmark(payload: Any) -> dict[str, Any]:
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    primary = data.get("primaryData", {}) if isinstance(data, dict) else {}
    if not isinstance(primary, dict):
        primary = {}
    change_pct = _number(
        _first(primary, "percentageChange", "percentChange")
        or _first(data if isinstance(data, dict) else {}, "percentageChange")
    )
    return {
        "name": "Nasdaq Composite",
        "symbol": "COMP",
        "change_pct": change_pct,
        "close": _number(_first(primary, "lastSalePrice", "lastPrice")),
        "session": _first(primary, "lastTradeTimestamp", "lastTradeTime"),
        "market_status": data.get("marketStatus") if isinstance(data, dict) else None,
        "source": "Nasdaq",
        "source_url": "https://www.nasdaq.com/market-activity/index/comp",
    }


def _walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def parse_kospi_market_payload(payload: Any) -> list[dict[str, Any]]:
    """네이버증권 KOSPI 시총순 JSON 목록을 상대강도 입력으로 정규화한다."""
    parsed: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in _walk_dicts(payload):
        code = str(
            _first(row, "itemCode", "itemcode", "stockCode", "code", "cd") or ""
        ).strip().upper()
        if not re.fullmatch(r"\d{6}", code) or code in seen:
            continue

        price_block = row.get("price") if isinstance(row.get("price"), dict) else row
        change_pct = _number(
            _first(
                price_block,
                "fluctuationsRatio",
                "prevChangeRate",
                "changeRate",
                "percentageChange",
                "changePercent",
                "rate",
                "cr",
            )
        )
        if change_pct is None:
            continue

        name = str(
            _first(row, "stockName", "itemName", "itemname", "name", "nm") or code
        ).strip()
        market_cap = _number(
            _first(
                row,
                "marketValue",
                "marketSum",
                "marketCap",
                "marketCapitalization",
                "marketValueAmount",
            )
        )
        parsed.append(
            {
                "ticker": code,
                "name": name,
                "change_pct": change_pct,
                "price": _number(
                    _first(
                        price_block,
                        "closePrice",
                        "currentPrice",
                        "nowPrice",
                        "lastPrice",
                        "lastSalePrice",
                        "nv",
                    )
                ),
                "market_cap": market_cap,
                "volume": _number(
                    _first(
                        price_block,
                        "accumulatedTradingVolume",
                        "tradingVolume",
                        "volume",
                        "accQuant",
                        "aq",
                    )
                ),
                "source": "Naver Stock",
            }
        )
        seen.add(code)
    return parsed


def parse_kospi_benchmark(payload: Any) -> dict[str, Any]:
    """네이버증권 통합 지표/폴링 응답에서 KOSPI 값을 보수적으로 추출한다."""
    candidates: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        domestic = payload.get("domesticIndex")
        if isinstance(domestic, dict):
            direct = domestic.get("KOSPI")
            if isinstance(direct, dict):
                candidates.append(direct)

    for row in _walk_dicts(payload):
        code = str(
            _first(row, "itemCode", "reutersCode", "symbol", "code") or ""
        ).strip().upper()
        if code == "KOSPI":
            candidates.append(row)

    rate = None
    close = None
    session = None
    for row in candidates:
        price_block = row.get("price") if isinstance(row.get("price"), dict) else row
        rate = _number(
            _first(
                price_block,
                "fluctuationsRatio",
                "changeRate",
                "percentageChange",
                "changePercent",
                "percentChange",
                "rate",
                "cr",
            )
        )
        close = _number(
            _first(
                price_block,
                "currentPrice",
                "closePrice",
                "lastPrice",
                "lastSalePrice",
                "nv",
            )
        )
        session = _first(
            price_block,
            "localTradedAt",
            "lastTradeTimestamp",
            "lastTradeTime",
            "tradeTime",
            "baseDateTime",
        ) or _first(row, "localTradedAt", "baseDateTime")
        if rate is not None:
            break

    return {
        "name": "KOSPI",
        "symbol": "KOSPI",
        "change_pct": rate,
        "close": close,
        "session": session,
        "source": "Naver Stock",
        "source_url": "https://stock.naver.com/market/index/KOSPI",
    }


def _distribution(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bands = [
        ("+3%p 이상", 3.0, None),
        ("+1~+3%p", 1.0, 3.0),
        ("0~+1%p", 0.0, 1.0),
        ("-1~0%p", -1.0, 0.0),
        ("-3~-1%p", -3.0, -1.0),
        ("-3%p 이하", None, -3.0),
    ]
    result = []
    for label, low, high in bands:
        count = 0
        for row in rows:
            value = row.get("relative_strength_pct")
            if value is None:
                continue
            if low is None and value <= high:
                count += 1
            elif high is None and value >= low:
                count += 1
            elif low is not None and high is not None and low <= value < high:
                count += 1
        result.append({"label": label, "count": count})
    return result


def summarize_market(
    benchmark: dict[str, Any],
    stocks: list[dict[str, Any]],
    *,
    market: str,
    universe_label: str,
    source_urls: list[str],
) -> dict[str, Any]:
    benchmark_change = _number(benchmark.get("change_pct"))
    if benchmark_change is None:
        return {
            "status": "unavailable",
            "market": market,
            "universe_label": universe_label,
            "benchmark": benchmark,
            "universe_count": len(stocks),
            "reason": "지수 등락률을 확인하지 못해 상대강도를 계산하지 않음",
            "sources": source_urls,
            "stocks": [],
        }

    if not stocks:
        return {
            "status": "unavailable",
            "market": market,
            "universe_label": universe_label,
            "benchmark": benchmark,
            "universe_count": 0,
            "reason": "비교 종목 목록을 확인하지 못해 상대강도를 계산하지 않음",
            "sources": source_urls,
            "strongest": [],
            "weakest": [],
            "distribution": [],
        }

    rows: list[dict[str, Any]] = []
    for stock in stocks:
        change_pct = _number(stock.get("change_pct"))
        if change_pct is None:
            continue
        item = dict(stock)
        item["relative_strength_pct"] = round(change_pct - benchmark_change, 4)
        rows.append(item)

    rows.sort(key=lambda x: float(x["relative_strength_pct"]), reverse=True)
    relative_values = [float(x["relative_strength_pct"]) for x in rows]
    above = sum(value > 0 for value in relative_values)
    below = sum(value < 0 for value in relative_values)
    equal = len(relative_values) - above - below
    top_n = min(50, len(rows))

    return {
        "status": "ok",
        "market": market,
        "universe_label": universe_label,
        "benchmark": benchmark,
        "universe_count": len(rows),
        "above_benchmark_count": above,
        "below_benchmark_count": below,
        "equal_benchmark_count": equal,
        "above_benchmark_ratio": round(above / len(rows), 4) if rows else None,
        "median_relative_strength_pct": round(statistics.median(relative_values), 4)
        if relative_values
        else None,
        "strongest": rows[:top_n],
        "weakest": list(reversed(rows[-top_n:])),
        "distribution": _distribution(rows),
        "sources": source_urls,
        "_universe": rows,
    }



def parse_yahoo_spark(payload: Any) -> dict[str, list[dict[str, Any]]]:
    """Yahoo spark 다종목 일봉 응답을 symbol -> 날짜/종가 배열로 정규화한다."""
    spark = payload.get("spark", {}) if isinstance(payload, dict) else {}
    results = spark.get("result", []) if isinstance(spark, dict) else []
    parsed: dict[str, list[dict[str, Any]]] = {}
    for item in results if isinstance(results, list) else []:
        if not isinstance(item, dict):
            continue
        responses = item.get("response", [])
        if not isinstance(responses, list) or not responses:
            continue
        response = responses[0] if isinstance(responses[0], dict) else {}
        meta = response.get("meta", {}) if isinstance(response.get("meta"), dict) else {}
        symbol = str(item.get("symbol") or meta.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        timestamps = response.get("timestamp", [])
        indicators = response.get("indicators", {})
        quotes = indicators.get("quote", []) if isinstance(indicators, dict) else []
        quote = quotes[0] if isinstance(quotes, list) and quotes and isinstance(quotes[0], dict) else {}
        closes = quote.get("close", [])
        if not isinstance(timestamps, list) or not isinstance(closes, list):
            continue
        rows: list[dict[str, Any]] = []
        for stamp, close in zip(timestamps, closes):
            close_number = _number(close)
            stamp_number = _number(stamp)
            if close_number is None or close_number <= 0 or stamp_number is None:
                continue
            rows.append(
                {
                    "timestamp": int(stamp_number),
                    "date": datetime.fromtimestamp(int(stamp_number), tz=timezone.utc).date().isoformat(),
                    "close": close_number,
                }
            )
        rows.sort(key=lambda x: int(x["timestamp"]))
        if rows:
            parsed[symbol] = rows
    return parsed


def _period_return(rows: list[dict[str, Any]], sessions: int) -> tuple[float | None, str | None]:
    valid = [row for row in rows if _number(row.get("close")) not in (None, 0)]
    if len(valid) < sessions + 1:
        return None, valid[-1].get("date") if valid else None
    latest = float(valid[-1]["close"])
    base = float(valid[-(sessions + 1)]["close"])
    if base <= 0:
        return None, valid[-1].get("date")
    return round((latest / base - 1.0) * 100.0, 6), valid[-1].get("date")


def fetch_yahoo_daily_history(
    symbols: list[str],
    *,
    batch_size: int = 20,
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """다종목 spark를 묶어서 받아 5D/20D 계산용 일봉을 만든다."""
    clean = []
    seen: set[str] = set()
    for symbol in symbols:
        value = str(symbol or "").strip().upper()
        if value and value not in seen:
            clean.append(value)
            seen.add(value)

    collected: dict[str, list[dict[str, Any]]] = {}
    errors: list[str] = []
    for start in range(0, len(clean), max(1, batch_size)):
        chunk = clean[start : start + max(1, batch_size)]
        params = urllib.parse.urlencode(
            {
                "symbols": ",".join(chunk),
                "range": "3mo",
                "interval": "1d",
                "indicators": "close",
                "includeTimestamps": "true",
                "includePrePost": "false",
                "formatted": "false",
            }
        )
        url = "https://query1.finance.yahoo.com/v7/finance/spark?" + params
        try:
            payload = _fetch_json(url, referer="https://finance.yahoo.com/")
            collected.update(parse_yahoo_spark(payload))
        except (
            OSError,
            TimeoutError,
            urllib.error.URLError,
            urllib.error.HTTPError,
            json.JSONDecodeError,
            ValueError,
            KeyError,
        ) as exc:
            errors.append(f"{chunk[0]}..{chunk[-1]}: {exc}")
    return collected, errors


def _history_symbol(market: str, ticker: str) -> str:
    if market == "KOSPI":
        return f"{ticker}.KS"
    return ticker


def _period_source_url(symbol: str) -> str:
    return "https://finance.yahoo.com/quote/" + urllib.parse.quote(symbol, safe="^.")


def build_period_summary(
    base_market: dict[str, Any],
    histories: dict[str, list[dict[str, Any]]],
    *,
    market: str,
    benchmark_symbol: str,
    sessions: int,
) -> dict[str, Any]:
    benchmark_rows = histories.get(benchmark_symbol.upper(), [])
    benchmark_return, benchmark_date = _period_return(benchmark_rows, sessions)
    benchmark_base = base_market.get("benchmark", {}) if isinstance(base_market, dict) else {}
    benchmark = {
        "name": benchmark_base.get("name") or benchmark_symbol,
        "symbol": benchmark_symbol,
        "change_pct": benchmark_return,
        "close": _number(benchmark_rows[-1].get("close")) if benchmark_rows else None,
        "session": benchmark_date,
        "source": "Yahoo Finance",
        "source_url": _period_source_url(benchmark_symbol),
    }

    base_universe = base_market.get("_universe", []) if isinstance(base_market, dict) else []
    stocks: list[dict[str, Any]] = []
    for row in base_universe if isinstance(base_universe, list) else []:
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        symbol = _history_symbol(market, ticker)
        change_pct, latest_date = _period_return(histories.get(symbol.upper(), []), sessions)
        if change_pct is None:
            continue
        stocks.append(
            {
                "ticker": ticker,
                "name": row.get("name") or ticker,
                "change_pct": change_pct,
                "price": row.get("price"),
                "volume": row.get("volume"),
                "market_cap": row.get("market_cap"),
                "history_session": latest_date,
                "source": "Yahoo Finance",
            }
        )

    summary = summarize_market(
        benchmark,
        stocks,
        market=market,
        universe_label=base_market.get("universe_label") or market,
        source_urls=[_period_source_url(benchmark_symbol)],
    )
    requested = len(base_universe) if isinstance(base_universe, list) else 0
    coverage = len(stocks) / requested if requested else 0.0
    summary["period"] = f"{sessions}D"
    summary["requested_universe_count"] = requested
    summary["history_coverage_ratio"] = round(coverage, 4)
    if summary.get("status") == "ok" and coverage < 0.95:
        summary["status"] = "partial"
        summary["reason"] = f"일봉 확보율 {coverage * 100:.1f}%"
    return summary


def build_consistency(base_market: dict[str, Any]) -> dict[str, Any]:
    one_day = {
        str(row.get("ticker")): row
        for row in base_market.get("_universe", [])
        if isinstance(row, dict) and row.get("ticker")
    }
    five_block = (base_market.get("periods") or {}).get("5D") or {}
    twenty_block = (base_market.get("periods") or {}).get("20D") or {}
    five = {
        str(row.get("ticker")): row
        for row in five_block.get("_universe", [])
        if isinstance(row, dict) and row.get("ticker")
    }
    twenty = {
        str(row.get("ticker")): row
        for row in twenty_block.get("_universe", [])
        if isinstance(row, dict) and row.get("ticker")
    }

    common = sorted(set(one_day) & set(five) & set(twenty))
    if not common:
        return {
            "status": "unavailable",
            "coverage_count": 0,
            "persistent_strong": [],
            "persistent_weak": [],
            "turning_strong": [],
            "turning_weak": [],
        }

    rows: list[dict[str, Any]] = []
    for ticker in common:
        r1 = _number(one_day[ticker].get("relative_strength_pct"))
        r5 = _number(five[ticker].get("relative_strength_pct"))
        r20 = _number(twenty[ticker].get("relative_strength_pct"))
        if r1 is None or r5 is None or r20 is None:
            continue
        rows.append(
            {
                "ticker": ticker,
                "name": one_day[ticker].get("name") or ticker,
                "market_cap": one_day[ticker].get("market_cap"),
                "rs_1d": round(r1, 4),
                "rs_5d": round(r5, 4),
                "rs_20d": round(r20, 4),
            }
        )

    persistent_strong = [row for row in rows if row["rs_1d"] > 0 and row["rs_5d"] > 0 and row["rs_20d"] > 0]
    persistent_weak = [row for row in rows if row["rs_1d"] < 0 and row["rs_5d"] < 0 and row["rs_20d"] < 0]
    turning_strong = [
        row for row in rows
        if row["rs_1d"] > 0 and (row["rs_5d"] <= 0 or row["rs_20d"] <= 0)
    ]
    turning_weak = [
        row for row in rows
        if row["rs_1d"] < 0 and (row["rs_5d"] >= 0 or row["rs_20d"] >= 0)
    ]

    persistent_strong.sort(key=lambda x: (x["rs_20d"], x["rs_5d"], x["rs_1d"]), reverse=True)
    persistent_weak.sort(key=lambda x: (x["rs_20d"], x["rs_5d"], x["rs_1d"]))
    turning_strong.sort(key=lambda x: (x["rs_1d"], x["rs_5d"]), reverse=True)
    turning_weak.sort(key=lambda x: (x["rs_1d"], x["rs_5d"]))

    requested = len(one_day)
    coverage = len(rows) / requested if requested else 0.0
    return {
        "status": "ok" if coverage >= 0.95 else "partial",
        "coverage_count": len(rows),
        "coverage_ratio": round(coverage, 4),
        "counts": {
            "persistent_strong": len(persistent_strong),
            "persistent_weak": len(persistent_weak),
            "turning_strong": len(turning_strong),
            "turning_weak": len(turning_weak),
        },
        "persistent_strong": persistent_strong[:30],
        "persistent_weak": persistent_weak[:30],
        "turning_strong": turning_strong[:30],
        "turning_weak": turning_weak[:30],
        "definition": {
            "persistent_strong": "1D·5D·20D 모두 지수 대비 플러스",
            "persistent_weak": "1D·5D·20D 모두 지수 대비 마이너스",
            "turning_strong": "1D는 플러스지만 5D 또는 20D는 0 이하",
            "turning_weak": "1D는 마이너스지만 5D 또는 20D는 0 이상",
        },
    }


def _period_session_key(market_block: dict[str, Any]) -> str:
    benchmark = market_block.get("benchmark", {}) if isinstance(market_block, dict) else {}
    return "|".join(
        [
            str(benchmark.get("session") or ""),
            str(benchmark.get("close") or ""),
            str(market_block.get("universe_count") or ""),
        ]
    )


def enrich_periods(
    market_block: dict[str, Any],
    previous_market: Any,
    *,
    market: str,
    benchmark_symbol: str,
    force: bool,
    now: datetime,
) -> dict[str, Any]:
    if market_block.get("status") != "ok":
        return market_block

    session_key = _period_session_key(market_block)
    previous_market = previous_market if isinstance(previous_market, dict) else {}
    if (
        not force
        and previous_market.get("period_session_key") == session_key
        and isinstance(previous_market.get("periods"), dict)
    ):
        market_block["periods"] = previous_market.get("periods")
        market_block["consistency"] = previous_market.get("consistency")
        market_block["period_session_key"] = session_key
        market_block["periods_generated_at"] = previous_market.get("periods_generated_at")
        market_block["period_history_cache_used"] = True
        market_block["period_history_errors"] = previous_market.get("period_history_errors", [])
        return market_block

    universe = market_block.get("_universe", [])
    symbols = [_history_symbol(market, str(row.get("ticker") or "")) for row in universe if row.get("ticker")]
    symbols.append(benchmark_symbol)
    histories, history_errors = fetch_yahoo_daily_history(symbols)
    periods = {
        "5D": build_period_summary(
            market_block,
            histories,
            market=market,
            benchmark_symbol=benchmark_symbol,
            sessions=5,
        ),
        "20D": build_period_summary(
            market_block,
            histories,
            market=market,
            benchmark_symbol=benchmark_symbol,
            sessions=20,
        ),
    }

    if all(block.get("status") == "unavailable" for block in periods.values()) and previous_market.get("periods"):
        periods = previous_market.get("periods")
        consistency = previous_market.get("consistency")
        history_errors.append("새 기간 데이터 확보 실패로 이전 기간 데이터 유지")
        cache_used = True
    else:
        market_block["periods"] = periods
        consistency = build_consistency(market_block)
        cache_used = False

    market_block["periods"] = periods
    market_block["consistency"] = consistency
    market_block["period_session_key"] = session_key
    market_block["periods_generated_at"] = now.isoformat()
    market_block["period_history_cache_used"] = cache_used
    market_block["period_history_errors"] = history_errors[:20]
    return market_block


def _strip_internal_universe(market_block: dict[str, Any]) -> dict[str, Any]:
    market_block.pop("_universe", None)
    periods = market_block.get("periods")
    if isinstance(periods, dict):
        for block in periods.values():
            if isinstance(block, dict):
                block.pop("_universe", None)
    return market_block


def fetch_nasdaq(limit: int = UNIVERSE_LIMIT) -> dict[str, Any]:
    screener_url = (
        "https://api.nasdaq.com/api/screener/stocks?"
        + urllib.parse.urlencode(
            {
                "tableonly": "true",
                "limit": 5000,
                "exchange": "nasdaq",
                "download": "true",
            }
        )
    )
    benchmark_url = "https://api.nasdaq.com/api/quote/COMP/info?assetclass=index"
    stocks = parse_nasdaq_screener(
        _fetch_json(screener_url, referer="https://www.nasdaq.com/"),
        limit=limit,
    )
    benchmark = parse_nasdaq_benchmark(
        _fetch_json(benchmark_url, referer="https://www.nasdaq.com/")
    )
    return summarize_market(
        benchmark,
        stocks,
        market="NASDAQ",
        universe_label=f"NASDAQ 상장 시가총액 상위 {limit}개",
        source_urls=[
            "https://www.nasdaq.com/market-activity/stocks/screener",
            benchmark["source_url"],
        ],
    )


def fetch_kospi(limit: int = UNIVERSE_LIMIT) -> dict[str, Any]:
    per_page = 100
    pages = max(1, math.ceil(limit / per_page))
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    list_source = "https://stock.naver.com/market/stock/kr/stocklist/capitalization"

    for page in range(pages):
        params = urllib.parse.urlencode(
            {
                "tradeType": "KRX",
                "marketType": "KOSPI",
                "orderType": "marketSum",
                "startIdx": page,
                "pageSize": per_page,
            }
        )
        payload = _fetch_json(
            "https://stock.naver.com/api/domestic/market/stock/default?" + params,
            referer=list_source,
        )
        page_rows = parse_kospi_market_payload(payload)
        if not page_rows:
            break
        for item in page_rows:
            ticker = str(item.get("ticker") or "")
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            rows.append(item)
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break

    indicator_url = (
        "https://stock.naver.com/api/securityService/integration/v1/indicators?"
        + urllib.parse.urlencode({"domesticIndexCodes": "KOSPI"})
    )
    benchmark = parse_kospi_benchmark(
        _fetch_json(
            indicator_url,
            referer="https://stock.naver.com/market",
        )
    )

    if benchmark.get("change_pct") is None:
        benchmark = parse_kospi_benchmark(
            _fetch_json(
                "https://stock.naver.com/api/polling/domestic/index?itemCodes=KOSPI",
                referer="https://stock.naver.com/market",
            )
        )

    return summarize_market(
        benchmark,
        rows[:limit],
        market="KOSPI",
        universe_label=f"KOSPI 시가총액 상위 {limit}개",
        source_urls=[
            list_source,
            benchmark["source_url"],
        ],
    )


def _stale_copy(previous_market: Any, error: Exception, market: str) -> dict[str, Any]:
    if isinstance(previous_market, dict) and previous_market:
        value = dict(previous_market)
        value["status"] = "stale"
        value["stale_reason"] = str(error)
        value["market"] = value.get("market") or market
        return value
    return {
        "status": "unavailable",
        "market": market,
        "reason": str(error),
        "universe_count": 0,
        "strongest": [],
        "weakest": [],
        "distribution": [],
    }


def collect(
    root: Path,
    *,
    force: bool = False,
    limit: int = UNIVERSE_LIMIT,
) -> dict[str, Any]:
    root = root.resolve()
    output = root / OUTPUT
    previous = _read_json(output)
    now = datetime.now(KST)

    if not force and previous and _generated_recently(previous, now):
        cached = dict(previous)
        cached["cache_used"] = True
        return cached

    errors: list[dict[str, str]] = []
    try:
        nasdaq = fetch_nasdaq(limit=limit)
    except (
        OSError,
        TimeoutError,
        urllib.error.URLError,
        urllib.error.HTTPError,
        json.JSONDecodeError,
        ValueError,
        KeyError,
    ) as exc:
        errors.append({"market": "NASDAQ", "error": str(exc)})
        nasdaq = _stale_copy(previous.get("nasdaq"), exc, "NASDAQ")

    try:
        kospi = fetch_kospi(limit=limit)
    except (
        OSError,
        TimeoutError,
        urllib.error.URLError,
        urllib.error.HTTPError,
        json.JSONDecodeError,
        ValueError,
        KeyError,
    ) as exc:
        errors.append({"market": "KOSPI", "error": str(exc)})
        kospi = _stale_copy(previous.get("kospi"), exc, "KOSPI")

    try:
        nasdaq = enrich_periods(
            nasdaq,
            previous.get("nasdaq"),
            market="NASDAQ",
            benchmark_symbol="^IXIC",
            force=force,
            now=now,
        )
    except Exception as exc:
        errors.append({"market": "NASDAQ_PERIODS", "error": str(exc)})

    try:
        kospi = enrich_periods(
            kospi,
            previous.get("kospi"),
            market="KOSPI",
            benchmark_symbol="^KS11",
            force=force,
            now=now,
        )
    except Exception as exc:
        errors.append({"market": "KOSPI_PERIODS", "error": str(exc)})

    nasdaq = _strip_internal_universe(nasdaq)
    kospi = _strip_internal_universe(kospi)

    result = {
        "schema_version": 2,
        "generated_at": now.isoformat(),
        "cache_used": False,
        "methodology": {
            "formula": "상대강도(%p) = 종목 등락률(%) - 기준지수 등락률(%)",
            "interpretation": "0보다 크면 같은 세션에서 지수보다 강했고, 0보다 작으면 지수보다 약했음을 뜻함",
            "periods": ["1D", "5D", "20D"],
            "historical_formula": "N거래일 수익률 = 최신 종가 / N거래일 전 종가 - 1",
            "universe_limit": limit,
            "ranking": "시가총액 상위 유니버스 내 상대강도 순",
            "not_investment_advice": True,
        },
        "nasdaq": nasdaq,
        "kospi": kospi,
        "errors": errors,
    }
    _write_json(output, result)
    return result
