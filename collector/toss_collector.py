from __future__ import annotations

import json
import os
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any

import websocket


KST = timezone(timedelta(hours=9))
API = "https://openapi.tossinvest.com"
WS = "wss://openapi-ws.tossinvest.com/ws/v1"


def number(value: Any) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temp, path)


def now_kst() -> datetime:
    return datetime.now(KST)


def collection_window(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    current = now.time()
    return dt_time(7, 55) <= current <= dt_time(20, 10)


def session_name(stamp: datetime) -> str:
    value = stamp.astimezone(KST).time()
    if dt_time(8, 0) <= value <= dt_time(8, 50):
        return "pre"
    if dt_time(9, 0) <= value <= dt_time(15, 30):
        return "regular"
    if dt_time(15, 40) <= value <= dt_time(20, 0):
        return "post"
    return "other"


def parse_stamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


@dataclass
class MinuteBar:
    minute: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    amount: float = 0.0
    trades: int = 0

    def add(self, price: float, volume: float) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += volume
        self.amount += price * volume
        self.trades += 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.minute,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "amount": self.amount,
            "amount_estimated": False,
            "trade_count": self.trades,
        }


@dataclass
class CollectorState:
    bars: dict[str, dict[str, dict[str, MinuteBar]]] = field(
        default_factory=lambda: {"pre": {}, "regular": {}, "post": {}}
    )
    ranking: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    subscribed: list[str] = field(default_factory=list)
    rejected: list[Any] = field(default_factory=list)
    messages: int = 0
    parsed_trades: int = 0
    parse_errors: int = 0
    reconnects: int = 0
    last_message_at: str | None = None
    last_subscription_at: str | None = None
    last_error: str | None = None
    unknown_trade_keys: list[str] = field(default_factory=list)


class TossCollector:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.client_id = os.getenv("TOSS_CLIENT_ID")
        self.client_secret = os.getenv("TOSS_CLIENT_SECRET")
        if not self.client_id or not self.client_secret:
            raise RuntimeError(
                "TOSS_CLIENT_ID / TOSS_CLIENT_SECRET이 필요합니다."
            )

        self.output = Path(
            os.getenv(
                "TOSS_SNAPSHOT_PATH",
                str(
                    config.get(
                        "output_path",
                        "/var/lib/stock-autoresearch/toss/latest.json",
                    )
                ),
            )
        )
        self.diagnostics = Path(
            str(
                config.get(
                    "diagnostics_path",
                    "/var/lib/stock-autoresearch/toss/diagnostics.json",
                )
            )
        )
        self.ranking_count = min(
            95,
            max(1, int(config.get("ranking_count", 80))),
        )
        self.extra_symbols = [
            str(x)
            for x in config.get("extra_symbols", [])
            if str(x).strip()
        ]
        self.ranking_refresh = int(
            config.get("ranking_refresh_seconds", 600)
        )
        self.flush_seconds = int(
            config.get("snapshot_flush_seconds", 10)
        )
        self.ping_seconds = int(config.get("ping_seconds", 60))
        self.state = CollectorState()
        self.stop = False
        self.ws = None

    def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        query: dict[str, Any] | None = None,
        form: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = API + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {"Accept": "application/json"}
        body = None
        if token:
            headers["Authorization"] = "Bearer " + token
        if form is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            body = urllib.parse.urlencode(form).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Toss HTTP {exc.code}: {payload[:500]}"
            ) from exc

    def token(self) -> str:
        payload = self._request(
            "POST",
            "/oauth2/token",
            form={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        token = payload.get("access_token")
        if not token:
            raise RuntimeError("토스 토큰 응답에 access_token이 없습니다.")
        return str(token)

    def rankings(self, token: str) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            "/api/v1/rankings",
            token=token,
            query={
                "type": "MARKET_TRADING_AMOUNT",
                "marketCountry": "KR",
                "duration": "realtime",
                "excludeInvestmentCaution": "false",
                "count": self.ranking_count,
            },
        )
        raw = payload.get("result", payload)
        rows = raw.get("rankings", []) if isinstance(raw, dict) else []
        result = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "")
            if not symbol:
                continue
            price = row.get("price") or {}
            result.append(
                {
                    "rank": row.get("rank"),
                    "ticker": symbol,
                    "symbol": symbol,
                    "name": (
                        self.state.metadata.get(symbol, {}).get("name")
                        or symbol
                    ),
                    "last_price": number(
                        price.get("lastPrice")
                        if isinstance(price, dict)
                        else None
                    ),
                    "day_return_pct": number(
                        price.get("changeRate")
                        if isinstance(price, dict)
                        else None
                    ),
                    "trading_value": number(row.get("tradingAmount")),
                    "trading_volume": number(row.get("tradingVolume")),
                }
            )
        return result

    def stock_metadata(
        self,
        token: str,
        symbols: list[str],
    ) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for start in range(0, len(symbols), 100):
            chunk = symbols[start:start + 100]
            if not chunk:
                continue
            payload = self._request(
                "GET",
                "/api/v1/stocks",
                token=token,
                query={"symbols": ",".join(chunk)},
            )
            raw = payload.get("result", [])
            rows = raw if isinstance(raw, list) else []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                symbol = str(row.get("symbol") or "")
                if not symbol:
                    continue
                result[symbol] = {
                    "name": row.get("name") or row.get("stockName") or symbol,
                    "market": row.get("market") or row.get("exchange") or "",
                    "currency": row.get("currency") or "KRW",
                    "listing_status": row.get("listingStatus") or "",
                }
        return result

    def refresh_universe(self, token: str) -> list[str]:
        ranking = self.rankings(token)
        symbols = [x["ticker"] for x in ranking]
        for symbol in self.extra_symbols:
            if symbol not in symbols:
                symbols.append(symbol)
        symbols = symbols[:100]

        metadata = self.stock_metadata(token, symbols)
        for row in ranking:
            symbol = row["ticker"]
            if symbol in metadata:
                row["name"] = metadata[symbol].get("name") or symbol

        amounts = [
            float(x.get("trading_value") or 0)
            for x in ranking
            if float(x.get("trading_value") or 0) > 0
        ]
        total = sum(amounts)
        top10_share = sum(amounts[:10]) / total if total else None

        self.state.ranking = ranking
        self.state.metadata.update(metadata)
        self.state.subscribed = symbols
        self.state.last_subscription_at = now_kst().isoformat()
        self._top10_share = top10_share
        return symbols

    @staticmethod
    def _trade_fields(data: dict[str, Any]) -> tuple[float, float, datetime | None]:
        price = number(
            data.get("price")
            or data.get("tradePrice")
            or data.get("executedPrice")
            or data.get("lastPrice")
        )
        volume = number(
            data.get("volume")
            or data.get("tradeVolume")
            or data.get("executedVolume")
            or data.get("quantity")
        )
        stamp = parse_stamp(
            data.get("timestamp")
            or data.get("tradeTime")
            or data.get("executedAt")
        )
        return price, volume, stamp

    def on_trade(
        self,
        symbol: str,
        data: dict[str, Any],
    ) -> None:
        price, volume, stamp = self._trade_fields(data)
        if price <= 0 or volume <= 0 or stamp is None:
            self.state.parse_errors += 1
            keys = sorted(str(x) for x in data.keys())
            key_sig = ",".join(keys)
            if key_sig not in self.state.unknown_trade_keys:
                self.state.unknown_trade_keys.append(key_sig)
                self.state.unknown_trade_keys = (
                    self.state.unknown_trade_keys[-20:]
                )
            return

        session = session_name(stamp)
        if session not in {"pre", "regular", "post"}:
            return
        minute = stamp.replace(second=0, microsecond=0).isoformat()
        symbol_bars = self.state.bars[session].setdefault(symbol, {})
        bar = symbol_bars.get(minute)
        if bar is None:
            bar = MinuteBar(
                minute=minute,
                open=price,
                high=price,
                low=price,
                close=price,
            )
            symbol_bars[minute] = bar
        bar.add(price, volume)
        self.state.parsed_trades += 1
        self.state.last_message_at = stamp.isoformat()

    def snapshot(self) -> dict[str, Any]:
        def serialize(session: str) -> dict[str, list[dict[str, Any]]]:
            return {
                symbol: [
                    bars[key].as_dict()
                    for key in sorted(bars)
                ]
                for symbol, bars in self.state.bars[session].items()
            }

        return {
            "captured_at": now_kst().isoformat(),
            "provider": "toss",
            "source_mode": "websocket_trade_kr",
            "minute_amount_method": "exact_trade_sum",
            "session": {
                "integrated_krx_nxt": True,
                "monitor_start": "08:00",
                "krx_close": "15:30",
                "nxt_after_start": "15:40",
                "nxt_close": "20:00",
            },
            "ranking": self.state.ranking,
            "metadata": self.state.metadata,
            "turnover_rank_top10_share": getattr(
                self, "_top10_share", None
            ),
            "minute_by_ticker": serialize("regular"),
            "premarket_by_ticker": serialize("pre"),
            "postmarket_by_ticker": serialize("post"),
            "collector": {
                "subscribed_count": len(self.state.subscribed),
                "messages": self.state.messages,
                "parsed_trades": self.state.parsed_trades,
                "parse_errors": self.state.parse_errors,
                "reconnects": self.state.reconnects,
                "last_message_at": self.state.last_message_at,
                "last_subscription_at": self.state.last_subscription_at,
                "rejected": self.state.rejected,
                "last_error": self.state.last_error,
            },
        }

    def flush(self) -> None:
        atomic_json(self.output, self.snapshot())
        atomic_json(
            self.diagnostics,
            {
                "captured_at": now_kst().isoformat(),
                "subscribed": self.state.subscribed,
                "rejected": self.state.rejected,
                "messages": self.state.messages,
                "parsed_trades": self.state.parsed_trades,
                "parse_errors": self.state.parse_errors,
                "reconnects": self.state.reconnects,
                "last_error": self.state.last_error,
                "unknown_trade_keys": self.state.unknown_trade_keys,
            },
        )

    def subscribe(self, symbols: list[str]) -> None:
        request_id = "market-" + str(int(time.time()))
        declaration = [
            {"id": request_id},
            {"type": "trade:kr", "codes": symbols},
        ]
        self.ws.send(json.dumps(declaration))

    def connect(self, token: str) -> None:
        self.ws = websocket.create_connection(
            WS,
            header=[f"Authorization: Bearer {token}"],
            timeout=5,
        )
        self.ws.settimeout(1)

    def loop_connection(self) -> None:
        token = self.token()
        symbols = self.refresh_universe(token)
        self.connect(token)
        self.subscribe(symbols)

        last_ping = 0.0
        last_flush = 0.0
        last_ranking = time.monotonic()

        while not self.stop:
            now_mono = time.monotonic()

            if now_mono - last_ping >= self.ping_seconds:
                self.ws.send("PING")
                last_ping = now_mono

            if now_mono - last_flush >= self.flush_seconds:
                self.flush()
                last_flush = now_mono

            if now_mono - last_ranking >= self.ranking_refresh:
                new_symbols = self.refresh_universe(token)
                self.subscribe(new_symbols)
                last_ranking = now_mono

            try:
                raw = self.ws.recv()
            except websocket.WebSocketTimeoutException:
                continue

            if not raw:
                continue
            self.state.messages += 1
            try:
                frame = json.loads(raw)
            except json.JSONDecodeError:
                continue

            frame_type = frame.get("type")
            if frame_type == "subscriptions":
                self.state.rejected = frame.get("rejected", [])
            elif frame_type == "error":
                error = frame.get("error", {})
                self.state.last_error = (
                    str(error.get("code")) + ": " + str(error.get("message"))
                )
                if error.get("code") == "server-shutdown":
                    raise RuntimeError("Toss WebSocket server-shutdown")
            elif frame_type == "message":
                topic = str(frame.get("topic") or "")
                if not topic.startswith("trade:kr:"):
                    continue
                symbol = topic.rsplit(":", 1)[-1]
                data = frame.get("data")
                if isinstance(data, dict):
                    self.on_trade(symbol, data)

    def run(self) -> None:
        backoff = 1
        while not self.stop:
            if not collection_window(now_kst()):
                self.flush()
                time.sleep(30)
                continue

            try:
                self.loop_connection()
                backoff = 1
            except KeyboardInterrupt:
                self.stop = True
            except Exception as exc:
                self.state.reconnects += 1
                self.state.last_error = str(exc)
                self.flush()
                if self.ws is not None:
                    try:
                        self.ws.close()
                    except Exception:
                        pass
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)

        self.flush()


def load_config(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"잘못된 collector config: {exc}") from exc


def main() -> None:
    config_path = Path(
        os.getenv("TOSS_COLLECTOR_CONFIG", "collector/config.json")
    )
    collector = TossCollector(load_config(config_path))

    def stop_handler(signum, frame):
        collector.stop = True

    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    collector.run()


if __name__ == "__main__":
    main()
