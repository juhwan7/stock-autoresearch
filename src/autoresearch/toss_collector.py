from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed


KST = timezone(timedelta(hours=9))
REST_BASE = "https://openapi.tossinvest.com"
WS_URL = "wss://openapi-ws.tossinvest.com/ws/v1"


class TossCollectorError(RuntimeError):
    pass


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _json_number(value: Decimal) -> int | float:
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


def _minute_key(value: datetime) -> str:
    return value.replace(second=0, microsecond=0).isoformat()


def _session_of(value: datetime) -> str | None:
    hhmm = value.strftime("%H:%M")
    if "08:00" <= hhmm <= "08:50":
        return "pre"
    if "09:00" <= hhmm <= "15:30":
        return "regular"
    if "15:40" <= hhmm <= "20:00":
        return "post"
    return None


@dataclass
class MinuteBar:
    timestamp: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal = Decimal("0")
    amount: Decimal = Decimal("0")
    trade_count: int = 0

    def add(self, price: Decimal, volume: Decimal) -> None:
        if self.trade_count == 0:
            self.open = price
            self.high = price
            self.low = price
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += volume
        self.amount += price * volume
        self.trade_count += 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "open": _json_number(self.open),
            "high": _json_number(self.high),
            "low": _json_number(self.low),
            "close": _json_number(self.close),
            "volume": _json_number(self.volume),
            "amount": _json_number(self.amount),
            "trade_count": self.trade_count,
            "amount_estimated": False,
        }


@dataclass
class CollectorState:
    top_n: int
    ranking: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    regular: dict[str, dict[str, MinuteBar]] = field(default_factory=dict)
    premarket: dict[str, dict[str, MinuteBar]] = field(default_factory=dict)
    postmarket: dict[str, dict[str, MinuteBar]] = field(default_factory=dict)
    subscription_id: int = 0
    last_universe_refresh: str | None = None
    subscriptions: list[str] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    last_message_at: str | None = None

    def codes(self) -> list[str]:
        result = []
        for item in self.ranking:
            code = str(item.get("ticker") or "")
            if code and code not in result:
                result.append(code)
            if len(result) >= self.top_n:
                break
        return result[:100]

    def add_trade(
        self,
        *,
        symbol: str,
        price: Any,
        volume: Any,
        timestamp: str,
    ) -> bool:
        p = _decimal(price)
        v = _decimal(volume)
        if p <= 0 or v <= 0:
            return False
        try:
            when = _parse_time(timestamp)
        except ValueError:
            return False
        session = _session_of(when)
        if session is None:
            return False

        storage = {
            "regular": self.regular,
            "pre": self.premarket,
            "post": self.postmarket,
        }[session]
        bars = storage.setdefault(symbol, {})
        key = _minute_key(when)
        bar = bars.get(key)
        if bar is None:
            bar = MinuteBar(
                timestamp=key,
                open=p,
                high=p,
                low=p,
                close=p,
            )
            bars[key] = bar
        bar.add(p, v)
        self.last_message_at = datetime.now(KST).isoformat()
        return True

    @staticmethod
    def _rows(storage: dict[str, dict[str, MinuteBar]]) -> dict[str, list[dict[str, Any]]]:
        return {
            symbol: [
                bars[key].as_dict()
                for key in sorted(bars)
            ]
            for symbol, bars in storage.items()
            if bars
        }

    def snapshot(self) -> dict[str, Any]:
        now = datetime.now(KST)
        metadata = {k: dict(v) for k, v in self.metadata.items()}

        for symbol, bars in self.regular.items():
            if not bars:
                continue
            last_key = max(bars)
            if now.strftime("%H:%M") >= "15:30":
                metadata.setdefault(symbol, {})["krx_close"] = _json_number(
                    bars[last_key].close
                )

        amounts = [
            _decimal(item.get("trading_value"))
            for item in self.ranking
            if _decimal(item.get("trading_value")) > 0
        ]
        denominator = sum(amounts, Decimal("0"))
        top10 = sum(amounts[:10], Decimal("0"))
        top10_share = (
            float(top10 / denominator)
            if denominator > 0
            else None
        )

        return {
            "schema_version": 1,
            "captured_at": now.isoformat(),
            "provider": "toss",
            "source_mode": "websocket_exact",
            "minute_amount_method": "exact_trade_sum",
            "ranking": self.ranking,
            "metadata": metadata,
            "market_overview": {},
            "turnover_rank_top10_share": top10_share,
            "turnover_share_denominator": f"top_{len(amounts)}_ranking",
            "minute_by_ticker": self._rows(self.regular),
            "premarket_by_ticker": self._rows(self.premarket),
            "postmarket_by_ticker": self._rows(self.postmarket),
            "session": {
                "pre_market": {"start": "08:00", "end": "08:50"},
                "krx_regular": {"start": "09:00", "end": "15:30"},
                "nxt_after": {"start": "15:40", "end": "20:00"},
                "note": "국내 WebSocket은 KRX+NXT 통합 체결. 모든 종목이 NXT 지원 종목은 아님.",
            },
            "collector": {
                "subscriptions": self.subscriptions,
                "rejected": self.rejected,
                "last_universe_refresh": self.last_universe_refresh,
                "last_message_at": self.last_message_at,
            },
        }


class TossRestClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        base_url: str = REST_BASE,
        timeout: float = 15.0,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._token: str | None = None
        self._token_expires_at = 0.0

    def invalidate_token(self) -> None:
        self._token = None
        self._token_expires_at = 0.0

    def access_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        body = urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
        ).encode()
        request = Request(
            self.base_url + "/oauth2/token",
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, OSError, json.JSONDecodeError) as exc:
            raise TossCollectorError(f"OAuth 토큰 발급 실패: {exc}") from exc

        token = str(data.get("access_token") or "")
        if not token:
            raise TossCollectorError("OAuth 응답에 access_token이 없음")
        expires = int(data.get("expires_in") or 3600)
        self._token = token
        self._token_expires_at = time.time() + max(60, expires)
        return token

    def get_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        retry_auth: bool = True,
    ) -> dict[str, Any]:
        query = urlencode(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in (params or {}).items()
                if value is not None
            }
        )
        url = self.base_url + path + ("?" + query if query else "")
        request = Request(
            url,
            headers={"Authorization": "Bearer " + self.access_token()},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 401 and retry_auth:
                self.invalidate_token()
                return self.get_json(path, params, retry_auth=False)
            if exc.code == 429:
                retry_after = float(exc.headers.get("Retry-After") or 1)
                time.sleep(min(max(retry_after, 0.2), 10))
                return self.get_json(path, params, retry_auth=retry_auth)
            raise TossCollectorError(f"GET {path} HTTP {exc.code}") from exc
        except (URLError, OSError, json.JSONDecodeError) as exc:
            raise TossCollectorError(f"GET {path} 실패: {exc}") from exc

    def rankings(self, count: int) -> list[dict[str, Any]]:
        data = self.get_json(
            "/api/v1/rankings",
            {
                "type": "MARKET_TRADING_AMOUNT",
                "marketCountry": "KR",
                "duration": "realtime",
                "excludeInvestmentCaution": False,
                "count": min(max(count, 1), 100),
            },
        )
        result = data.get("result") or {}
        rows = []
        for item in result.get("rankings") or []:
            if not isinstance(item, dict):
                continue
            price = item.get("price") or {}
            change_rate = _decimal(price.get("changeRate"))
            rows.append(
                {
                    "rank": int(item.get("rank") or 0),
                    "ticker": str(item.get("symbol") or ""),
                    "last_price": _json_number(_decimal(price.get("lastPrice"))),
                    "base_price": _json_number(_decimal(price.get("basePrice"))),
                    "day_return_pct": float(change_rate * Decimal("100")),
                    "trading_volume": _json_number(_decimal(item.get("tradingVolume"))),
                    "trading_value": _json_number(_decimal(item.get("tradingAmount"))),
                    "currency": item.get("currency"),
                    "ranked_at": result.get("rankedAt"),
                }
            )
        return [x for x in rows if x["ticker"]]

    def stocks(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        if not symbols:
            return {}
        data = self.get_json(
            "/api/v1/stocks",
            {"symbols": ",".join(symbols[:200])},
        )
        result = {}
        for item in data.get("result") or []:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "")
            if not symbol:
                continue
            detail = item.get("koreanMarketDetail") or {}
            result[symbol] = {
                "name": item.get("name") or symbol,
                "market": item.get("market"),
                "listing_date": item.get("listDate"),
                "nxt_supported": detail.get("nxtSupported"),
                "krx_trading_suspended": detail.get("krxTradingSuspended"),
                "nxt_trading_suspended": detail.get("nxtTradingSuspended"),
                "security_type": item.get("securityType"),
            }
        return result


class TossRealtimeCollector:
    def __init__(
        self,
        client: TossRestClient,
        output: Path,
        *,
        top_n: int = 80,
        ranking_refresh_seconds: int = 600,
        snapshot_seconds: int = 20,
        ws_url: str = WS_URL,
    ):
        self.client = client
        self.output = output
        self.top_n = min(max(top_n, 1), 100)
        self.ranking_refresh_seconds = max(60, ranking_refresh_seconds)
        self.snapshot_seconds = max(5, snapshot_seconds)
        self.ws_url = ws_url
        self.state = CollectorState(top_n=self.top_n)

    def refresh_universe(self) -> list[str]:
        ranking = self.client.rankings(self.top_n)
        codes = [x["ticker"] for x in ranking][:100]
        metadata = self.client.stocks(codes)
        self.state.ranking = ranking
        self.state.metadata.update(metadata)
        self.state.last_universe_refresh = datetime.now(KST).isoformat()
        return codes

    async def _declare(self, websocket, codes: list[str]) -> None:
        self.state.subscription_id += 1
        request_id = f"collector-{self.state.subscription_id}"
        payload = [
            {"id": request_id},
            {"type": "trade:kr", "codes": codes[:100]},
        ]
        await websocket.send(json.dumps(payload, ensure_ascii=False))

    async def _universe_loop(self, websocket) -> None:
        while True:
            await asyncio.sleep(self.ranking_refresh_seconds)
            try:
                codes = await asyncio.to_thread(self.refresh_universe)
                if codes:
                    await self._declare(websocket, codes)
            except Exception as exc:
                print(f"[collector] universe refresh failed: {exc}", flush=True)

    async def _snapshot_loop(self) -> None:
        while True:
            await asyncio.sleep(self.snapshot_seconds)
            self.write_snapshot()

    def write_snapshot(self) -> None:
        data = self.state.snapshot()
        self.output.parent.mkdir(parents=True, exist_ok=True)
        temp = self.output.with_suffix(self.output.suffix + ".tmp")
        temp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp.replace(self.output)

    def _handle_frame(self, raw: str) -> None:
        if raw == "PING":
            return
        try:
            frame = json.loads(raw)
        except json.JSONDecodeError:
            return
        frame_type = str(frame.get("type") or "")
        if frame_type == "subscriptions":
            self.state.subscriptions = [
                str(x) for x in frame.get("subscribed") or []
            ]
            self.state.rejected = [
                x for x in frame.get("rejected") or []
                if isinstance(x, dict)
            ]
            return
        if frame_type == "error":
            error = frame.get("error") or {}
            code = str(error.get("code") or "")
            if code == "server-shutdown":
                raise TossCollectorError("Toss WebSocket server-shutdown")
            print(f"[collector] websocket error frame: {error}", flush=True)
            return
        if frame_type != "message":
            return
        topic = str(frame.get("topic") or "")
        if not topic.startswith("trade:kr:"):
            return
        symbol = topic.split(":")[-1]
        data = frame.get("data") or {}
        self.state.add_trade(
            symbol=symbol,
            price=data.get("price"),
            volume=data.get("volume"),
            timestamp=str(data.get("timestamp") or ""),
        )

    async def _connection(self) -> None:
        token = await asyncio.to_thread(self.client.access_token)
        codes = await asyncio.to_thread(self.refresh_universe)
        if not codes:
            raise TossCollectorError("거래대금 랭킹에서 구독 종목을 찾지 못함")

        async with connect(
            self.ws_url,
            additional_headers={"Authorization": "Bearer " + token},
            ping_interval=60,
            ping_timeout=20,
            open_timeout=15,
            close_timeout=10,
            proxy=None,
        ) as websocket:
            await self._declare(websocket, codes)
            self.write_snapshot()

            universe_task = asyncio.create_task(self._universe_loop(websocket))
            snapshot_task = asyncio.create_task(self._snapshot_loop())
            try:
                async for raw in websocket:
                    self._handle_frame(raw)
            finally:
                universe_task.cancel()
                snapshot_task.cancel()
                await asyncio.gather(
                    universe_task,
                    snapshot_task,
                    return_exceptions=True,
                )
                self.write_snapshot()

    async def run_forever(self) -> None:
        backoff = 1.0
        while True:
            try:
                await self._connection()
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except (ConnectionClosed, TossCollectorError, OSError) as exc:
                self.client.invalidate_token()
                delay = min(backoff, 60.0) + random.random()
                print(
                    f"[collector] disconnected: {exc}; retry in {delay:.1f}s",
                    flush=True,
                )
                await asyncio.sleep(delay)
                backoff = min(backoff * 2, 60.0)
            except Exception as exc:
                delay = min(backoff, 60.0) + random.random()
                print(
                    f"[collector] unexpected error: {exc}; retry in {delay:.1f}s",
                    flush=True,
                )
                await asyncio.sleep(delay)
                backoff = min(backoff * 2, 60.0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="고정 IP 환경용 토스증권 실시간 체결 Collector"
    )
    parser.add_argument(
        "--output",
        default=os.getenv(
            "TOSS_COLLECTOR_OUTPUT",
            "data/providers/toss/latest.json",
        ),
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=int(os.getenv("TOSS_COLLECTOR_TOP_N", "80")),
    )
    parser.add_argument(
        "--ranking-refresh",
        type=int,
        default=int(os.getenv("TOSS_COLLECTOR_RANKING_REFRESH", "600")),
        help="거래대금 상위 Universe 재선정 주기(초)",
    )
    parser.add_argument(
        "--snapshot-seconds",
        type=int,
        default=int(os.getenv("TOSS_COLLECTOR_SNAPSHOT_SECONDS", "20")),
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    client_id = os.getenv("TOSS_CLIENT_ID", "").strip()
    client_secret = os.getenv("TOSS_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise SystemExit(
            "TOSS_CLIENT_ID와 TOSS_CLIENT_SECRET을 고정 IP 서버의 환경변수/Secret에 설정하세요."
        )

    collector = TossRealtimeCollector(
        TossRestClient(client_id, client_secret),
        Path(args.output).resolve(),
        top_n=args.top_n,
        ranking_refresh_seconds=args.ranking_refresh,
        snapshot_seconds=args.snapshot_seconds,
    )
    try:
        asyncio.run(collector.run_forever())
    except KeyboardInterrupt:
        collector.write_snapshot()


if __name__ == "__main__":
    main()
