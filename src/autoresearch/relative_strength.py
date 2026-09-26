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


def parse_kospi_market_sum(html_text: str) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    blocks = re.findall(r"<tr[^>]*>(.*?)</tr>", html_text, flags=re.IGNORECASE | re.DOTALL)
    for block in blocks:
        code_match = re.search(r"/item/main\.naver\?code=(\d{6})", block)
        name_match = re.search(
            r"<a[^>]*href=[\"'][^\"]*?/item/main\.naver\?code=\d{6}[^\"']*[\"'][^>]*>(.*?)</a>",
            block,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not code_match or not name_match:
            continue
        cells = [
            _strip_html(cell)
            for cell in re.findall(r"<td[^>]*>(.*?)</td>", block, flags=re.IGNORECASE | re.DOTALL)
        ]
        if len(cells) < 10:
            continue
        change_pct = _number(cells[4])
        market_cap_eok = _number(cells[6])
        if change_pct is None or market_cap_eok is None:
            continue
        parsed.append(
            {
                "ticker": code_match.group(1),
                "name": _strip_html(name_match.group(1)),
                "change_pct": change_pct,
                "price": _number(cells[2]),
                "market_cap": market_cap_eok * 100_000_000,
                "volume": _number(cells[9]),
                "source": "Naver Finance",
            }
        )
    return parsed


def parse_kospi_benchmark(html_text: str) -> dict[str, Any]:
    rate = None
    match = re.search(
        r'id=[\"\']change_value_and_rate[\"\'][^>]*>(.*?)</span>',
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        text = _strip_html(match.group(1))
        rate_match = re.search(r"([+-]?\d+(?:\.\d+)?)\s*%", text)
        if rate_match:
            rate = _number(rate_match.group(1))
    if rate is None:
        for candidate in re.findall(r"([+-]?\d+(?:\.\d+)?)\s*%", _strip_html(html_text)):
            value = _number(candidate)
            if value is not None and -30 <= value <= 30:
                rate = value
                break

    close = None
    close_match = re.search(
        r'id=[\"\']now_value[\"\'][^>]*>(.*?)</span>',
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if close_match:
        close = _number(_strip_html(close_match.group(1)))

    session = None
    time_match = re.search(
        r'<span[^>]*id=[\"\']time[\"\'][^>]*>(.*?)</span>',
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if time_match:
        session = _strip_html(time_match.group(1))

    return {
        "name": "KOSPI",
        "symbol": "KOSPI",
        "change_pct": rate,
        "close": close,
        "session": session,
        "source": "Naver Finance",
        "source_url": "https://finance.naver.com/sise/sise_index.naver?code=KOSPI",
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
    }


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
    per_page = 50
    pages = max(1, math.ceil(limit / per_page))
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in range(1, pages + 1):
        url = (
            "https://finance.naver.com/sise/sise_market_sum.naver?"
            + urllib.parse.urlencode({"sosok": 0, "page": page})
        )
        for item in parse_kospi_market_sum(_fetch_text(url)):
            ticker = str(item.get("ticker") or "")
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            rows.append(item)
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break

    benchmark_url = "https://finance.naver.com/sise/sise_index.naver?code=KOSPI"
    benchmark = parse_kospi_benchmark(_fetch_text(benchmark_url))
    rows.sort(key=lambda x: float(x.get("market_cap") or 0), reverse=True)
    return summarize_market(
        benchmark,
        rows[:limit],
        market="KOSPI",
        universe_label=f"KOSPI 시가총액 상위 {limit}개",
        source_urls=[
            "https://finance.naver.com/sise/sise_market_sum.naver?sosok=0",
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

    result = {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "cache_used": False,
        "methodology": {
            "formula": "상대강도(%p) = 종목 등락률(%) - 기준지수 등락률(%)",
            "interpretation": "0보다 크면 같은 세션에서 지수보다 강했고, 0보다 작으면 지수보다 약했음을 뜻함",
            "period": "latest_session",
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
