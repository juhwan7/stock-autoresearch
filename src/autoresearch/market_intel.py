from __future__ import annotations

import csv
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import load_prompt, load_yaml, render_prompt
from .kiwoom_source import KiwoomAPIError, KiwoomSource
from .llm import ResearchLLM
from .market_stats import (
    MarketStats,
    describe_event_sample,
    normalize_time,
    number,
    percent_change,
)
from .pullback_stats import (
    PULLBACK_EVENT_FIELDS,
    complete_pullback_event,
    cooldown_allows,
    detect_pullback_event,
)


KST = timezone(timedelta(hours=9))

CLOSE_EVENT_FIELDS = [
    "signal_date",
    "ticker",
    "name",
    "entry_price",
    "day_return_pct",
    "total_amount",
    "late_amount_share",
    "burst_count",
    "max_burst_ratio",
    "high_position",
    "group_id",
    "sector",
    "next_date",
    "next_open",
    "next_high",
    "next_low",
    "next_close",
    "next_gap_pct",
    "next_mae_pct",
    "next_mfe_pct",
]


def in_krx_intraday(now: datetime | None = None) -> bool:
    """정규장 데이터 수집 창.

    GitHub Actions 예약 실행이 수분 지연될 수 있어 15:30 마감 데이터를
    회수할 수 있도록 15:40까지 조회 창을 열어 둔다.
    """
    now = now or datetime.now(KST)
    if now.weekday() >= 5:
        return False
    hhmm = now.strftime("%H:%M")
    return "09:00" <= hhmm <= "15:40"


def load_event_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_event_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    temp.replace(path)


def load_metadata(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    out: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            ticker = str(row.get("ticker") or "").strip()
            if ticker:
                item = dict(row)
                if item.get("listing_age_days"):
                    try:
                        item["listing_age_days"] = int(item["listing_age_days"])
                    except ValueError:
                        item["listing_age_days"] = None
                out[ticker] = item
    return out


def session_ohlc(
    rows: list[dict[str, Any]],
    *,
    start: str = "09:00",
    cutoff: str = "15:30",
) -> dict[str, float] | None:
    clean: list[dict[str, float | str]] = []
    for row in rows:
        tm = normalize_time(str(row.get("time") or row.get("cntr_tm") or ""))
        if not (start <= tm <= cutoff):
            continue
        close = abs(number(row.get("close") or row.get("cur_prc")))
        if close <= 0:
            continue
        open_ = abs(number(row.get("open") or row.get("open_pric"))) or close
        high = abs(number(row.get("high") or row.get("high_pric"))) or close
        low = abs(number(row.get("low") or row.get("low_pric"))) or close
        clean.append(
            {
                "time": tm,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
            }
        )
    if not clean:
        return None
    clean.sort(key=lambda x: str(x["time"]))
    return {
        "open": float(clean[0]["open"]),
        "high": max(float(x["high"]) for x in clean),
        "low": min(float(x["low"]) for x in clean),
        "close": float(clean[-1]["close"]),
    }


def synthetic_market() -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    minute: dict[str, list[dict[str, Any]]] = {}
    meta: dict[str, dict[str, Any]] = {}
    for idx, ticker in enumerate(("000001", "000002", "000003")):
        rows = []
        price = 10000 + idx * 1000
        for i in range(65):
            total_minutes = 25 + i
            hour = 14 + total_minutes // 60
            minute_value = total_minutes % 60
            amount = 120_000_000 + i * 2_000_000
            if i in (10, 11, 28, 50):
                amount *= 6
            close = price * (1 + i * 0.0015)
            rows.append(
                {
                    "time": f"{hour:02d}:{minute_value:02d}",
                    "open": close * 0.999,
                    "high": close * 1.002,
                    "low": close * 0.998,
                    "close": close,
                    "volume": amount / close,
                    "amount": amount,
                }
            )
        minute[ticker] = rows
        meta[ticker] = {
            "name": f"합성종목{idx + 1}",
            "group_id": "합성그룹",
            "sector": "테스트",
            "listing_age_days": 20 + idx,
        }
    return minute, meta


def render_market_markdown(result: dict[str, Any]) -> str:
    q = result.get("quantitative", {})
    interpretation = result.get("interpretation") or {}
    lines = [
        "# 국내시장 트렌드 리포트",
        "",
        f"> 생성: {result.get('generated_at', '')}",
        f"> 데이터 상태: {result.get('source', {}).get('status', '')}",
        "",
    ]

    if q.get("status") != "ok":
        lines.extend(
            [
                "## 현재 상태",
                "",
                "- 장세를 정량 판독할 수 있는 분봉 데이터가 부족합니다.",
                "- "
                + str(
                    result.get("source", {}).get("reason")
                    or q.get("reason")
                    or "원인 미상"
                ),
                "",
            ]
        )
        return "\n".join(lines)

    lines.extend(
        [
            "## 현재 장세",
            "",
            str(
                interpretation.get("one_line")
                or "정량 데이터는 수집됐지만 AI 장세 해석은 아직 없습니다."
            ),
            "",
            "## 분석 Universe 폭",
            "",
            f"- 분석 종목 수: {q.get('stock_count', 0)} (현재 거래대금 상위 상세조회 Universe)",
            f"- 상승 종목: {q.get('breadth', {}).get('advancers', 0)}",
            f"- 하락 종목: {q.get('breadth', {}).get('decliners', 0)}",
            f"- 상위 10개 거래대금 집중도: {q.get('turnover', {}).get('top10_share', 0):.1%}",
            "",
            "## 분봉 거래대금 Burst 상위",
            "",
        ]
    )

    for item in q.get("burst_leaders", [])[:10]:
        lines.append(
            f"- **{item.get('name')} ({item.get('ticker')})** "
            f"수익률 {item.get('return_pct')}% · burst {item.get('burst_count')}회 · "
            f"최대 {item.get('max_burst_ratio')}배 · "
            f"장후반 거래대금 비중 {float(item.get('close_watch_share') or 0):.1%}"
        )

    lines.extend(["", "## 동조 수급 그룹", ""])
    groups = q.get("coflow_groups", [])
    if groups:
        for group in groups[:8]:
            names = ", ".join(x.get("name", "") for x in group.get("members", []))
            lines.append(
                f"- **{group.get('group')}**: 거래대금 burst를 동반한 상승 종목 "
                f"{group.get('positive_burst_members')}개 — {names}"
            )
    else:
        lines.append("- 현재 데이터에서 조건을 충족한 동조 그룹 없음")

    new_flow = q.get("recent_listings", {})
    lines.extend(
        [
            "",
            "## 신규주 흐름",
            "",
            f"- 추적 신규주: {new_flow.get('count', 0)}개",
            f"- 상승 + 거래대금 burst: {new_flow.get('positive_burst_count', 0)}개",
            "",
            "## 종가베팅 관점",
            "",
        ]
    )
    close_view = interpretation.get("close_bet_view", {})
    items = close_view.get("warning_patterns", [])
    if items:
        for item in items:
            lines.append("- 주의: " + str(item))
    else:
        lines.append("- 통계가 충분히 쌓이기 전에는 고정된 패턴 결론을 내리지 않습니다.")

    lines.extend(["", "## 단기스윙 눌림 관점", ""])
    swing_view = interpretation.get("pullback_swing_view", {})
    items = swing_view.get("warning_patterns", [])
    if items:
        for item in items:
            lines.append("- 주의: " + str(item))
    else:
        lines.append("- 눌림 이벤트 표본을 누적 중입니다.")

    strategy = result.get("strategy_stats", {})
    lines.extend(["", "## 누적 통계 상태", ""])
    for key, label in (("close_bet", "종가베팅"), ("pullback", "눌림")):
        block = strategy.get(key, {})
        sample = block.get("summary", {}).get("sample_size", 0)
        lines.append(
            f"- {label}: 표본 {sample}개 · "
            f"{'통계 사용 가능' if block.get('ready') else '표본 축적 중'}"
        )

    lines.extend(
        [
            "",
            "---",
            "이 리포트는 통계 연구용이며 매수·매도 추천이 아닙니다.",
            "",
        ]
    )
    return "\n".join(lines)


class MarketIntelEngine:
    def __init__(self, root: Path, mode: str):
        self.root = root
        self.mode = mode
        self.cfg = load_yaml(root / "config" / "market_intel.yaml")
        self.stats = MarketStats(self.cfg)

    @property
    def stats_dir(self) -> Path:
        return self.root / self.cfg.get("data", {}).get(
            "stats_dir", "data/market/stats"
        )

    def _pending_close_tickers(self, today: str) -> list[str]:
        rows = load_event_csv(self.stats_dir / "close_bet_events.csv")
        seen = []
        for row in rows:
            if (
                row.get("signal_date")
                and row.get("signal_date") < today
                and not row.get("next_date")
                and row.get("ticker")
                and row.get("ticker") not in seen
            ):
                seen.append(str(row["ticker"]))
        return seen

    def _reference_metadata(
        self,
        source: KiwoomSource,
        now: datetime,
    ) -> dict[str, dict[str, Any]]:
        cache = self.root / "data" / "market" / "reference" / "kiwoom_stock_list.json"
        today = now.strftime("%Y-%m-%d")
        cached: dict[str, Any] = {}
        if cache.exists():
            try:
                cached = json.loads(cache.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                cached = {}

        items = cached.get("items") if cached.get("date") == today else None
        if not isinstance(items, list):
            items = []
            for market_type in ("0", "10"):
                try:
                    items.extend(source.stock_list(market_type))
                except KiwoomAPIError:
                    continue
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(
                json.dumps({"date": today, "items": items}, ensure_ascii=False),
                encoding="utf-8",
            )

        out: dict[str, dict[str, Any]] = {}
        for row in items:
            ticker = str(row.get("code") or "").split("_")[0]
            if not ticker:
                continue
            reg = str(row.get("regDay") or "").replace("-", "")
            listing_age = None
            if len(reg) == 8 and reg.isdigit():
                try:
                    listing_dt = datetime.strptime(reg, "%Y%m%d").date()
                    listing_age = (now.date() - listing_dt).days
                except ValueError:
                    listing_age = None
            out[ticker] = {
                "name": row.get("name") or ticker,
                "market": row.get("marketName") or "",
                "listing_date": reg,
                "listing_age_days": listing_age,
                "sector": row.get("upName") or "",
                "industry": row.get("upName") or "",
                "group_id": "",
            }

        # 사람이 검증한 기업집단/테마 메타데이터는 API 기본정보 위에 덮어쓴다.
        manual = load_metadata(self.root / "data" / "market" / "metadata.csv")
        for ticker, item in manual.items():
            base = out.setdefault(ticker, {"name": item.get("name") or ticker})
            for key, value in item.items():
                if value not in (None, ""):
                    base[key] = value
        return out

    def _collect_live(
        self,
    ) -> tuple[
        dict[str, list[dict[str, Any]]],
        dict[str, dict[str, Any]],
        dict[str, Any],
    ]:
        if not os.getenv("KIWOOM_APP_KEY") or not os.getenv("KIWOOM_SECRET_KEY"):
            return {}, {}, {
                "source": "kiwoom",
                "status": "needs_credentials",
                "reason": "KIWOOM_APP_KEY / KIWOOM_SECRET_KEY가 등록되지 않음",
            }

        source = KiwoomSource()
        rank_limit = int(
            self.cfg.get("universe", {}).get("turnover_rank_limit", 30)
        )
        detail_limit = int(
            self.cfg.get("universe", {}).get("detail_minute_limit", 20)
        )
        ranking = source.trading_value_top(limit=rank_limit)
        now = datetime.now(KST)
        metadata = self._reference_metadata(source, now)

        today = now.strftime("%Y-%m-%d")
        detail_tickers: list[str] = []
        ranking_by_ticker: dict[str, dict[str, Any]] = {}
        for row in ranking:
            ticker = str(row.get("stk_cd") or "").split("_")[0]
            if not ticker:
                continue
            ranking_by_ticker[ticker] = row
            if len(detail_tickers) < detail_limit:
                detail_tickers.append(ticker)

        # 전일 종가베팅 표본은 다음 날 결과를 완결하기 위해 순위에서 빠져도 조회한다.
        for ticker in self._pending_close_tickers(today):
            if ticker not in detail_tickers:
                detail_tickers.append(ticker)

        minute_by_ticker: dict[str, list[dict[str, Any]]] = {}
        base_date = datetime.now(KST).strftime("%Y%m%d")
        for ticker in detail_tickers:
            row = ranking_by_ticker.get(ticker, {})
            if ticker not in metadata:
                metadata[ticker] = {
                    "name": row.get("stk_nm") or ticker,
                    "sector": "",
                    "group_id": "",
                    "listing_age_days": None,
                }
            try:
                raw = source.minute_chart(ticker, base_date=base_date, max_pages=2)
                minute_by_ticker[ticker] = source.normalize_minute_rows(raw)
            except KiwoomAPIError as exc:
                metadata[ticker]["data_error"] = str(exc)
            time.sleep(0.2)

        return minute_by_ticker, metadata, {
            "source": "kiwoom",
            "status": "ok" if minute_by_ticker else "no_rows",
            "ranking_count": len(ranking),
            "detail_count": len(minute_by_ticker),
            "minute_amount_method": "close_x_volume_estimate",
        }

    def _update_close_bet_events(
        self,
        now: datetime,
        minute: dict[str, list[dict[str, Any]]],
        quantitative: dict[str, Any],
    ) -> dict[str, int]:
        path = self.stats_dir / "close_bet_events.csv"
        rows = load_event_csv(path)
        today = now.strftime("%Y-%m-%d")
        changed = False
        completed = 0
        created = 0

        # 과거 미완료 표본의 다음 거래일 결과를 채운다.
        for row in rows:
            if (
                not row.get("signal_date")
                or row.get("signal_date") >= today
                or row.get("next_date")
            ):
                continue
            ticker = str(row.get("ticker") or "")
            ohlc = session_ohlc(minute.get(ticker, []), cutoff="15:30")
            entry = number(row.get("entry_price"))
            if not ohlc or entry <= 0:
                continue
            row["next_date"] = today
            row["next_open"] = round(ohlc["open"], 4)
            row["next_high"] = round(ohlc["high"], 4)
            row["next_low"] = round(ohlc["low"], 4)
            row["next_close"] = round(ohlc["close"], 4)
            row["next_gap_pct"] = round(percent_change(entry, ohlc["open"]), 4)
            row["next_mae_pct"] = round(percent_change(entry, ohlc["low"]), 4)
            row["next_mfe_pct"] = round(percent_change(entry, ohlc["high"]), 4)
            completed += 1
            changed = True

        # 15:30 이후 현재 분석 Universe 전체를 편향 없는 종가베팅 연구 표본으로 저장한다.
        if (
            now.strftime("%H:%M") >= "15:30"
            and quantitative.get("status") == "ok"
        ):
            existing = {
                (str(x.get("signal_date")), str(x.get("ticker"))) for x in rows
            }
            for item in quantitative.get("stocks", []):
                ticker = str(item.get("ticker") or "")
                if not ticker or (today, ticker) in existing:
                    continue
                ohlc = session_ohlc(minute.get(ticker, []), cutoff="15:30")
                if not ohlc:
                    continue
                rows.append(
                    {
                        "signal_date": today,
                        "ticker": ticker,
                        "name": item.get("name") or ticker,
                        "entry_price": round(ohlc["close"], 4),
                        "day_return_pct": item.get("return_pct"),
                        "total_amount": item.get("total_amount"),
                        "late_amount_share": item.get("close_watch_share"),
                        "burst_count": item.get("burst_count"),
                        "max_burst_ratio": item.get("max_burst_ratio"),
                        "high_position": item.get("high_position"),
                        "group_id": item.get("group_id"),
                        "sector": item.get("sector"),
                    }
                )
                existing.add((today, ticker))
                created += 1
                changed = True

        if changed:
            write_event_csv(path, rows, CLOSE_EVENT_FIELDS)

        return {"created": created, "completed": completed}

    def _pullback_research_due(self, now: datetime) -> bool:
        cfg = self.cfg.get("pullback_research", {})
        if not cfg.get("enabled", True) or now.weekday() >= 5:
            return False
        hhmm = now.strftime("%H:%M")
        if not (
            str(cfg.get("run_after", "15:30"))
            <= hhmm
            <= str(cfg.get("run_before", "18:00"))
        ):
            return False

        state_path = self.root / "data" / "market" / "state" / "pullback_research.json"
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                state = {}
            if state.get("last_success_date") == now.strftime("%Y-%m-%d"):
                return False
        return True

    def _pending_pullback_tickers(self) -> list[str]:
        rows = load_event_csv(self.stats_dir / "pullback_events.csv")
        tickers: list[str] = []
        for row in rows:
            if (
                row.get("ticker")
                and not row.get("forward_5d_date")
                and row.get("ticker") not in tickers
            ):
                tickers.append(str(row["ticker"]))
        return tickers

    def _run_pullback_research(self, now: datetime) -> dict[str, Any]:
        if self.mode != "live":
            return {"status": "dry_run_skip", "created": 0, "completed": 0}
        if not self._pullback_research_due(now):
            return {"status": "not_due", "created": 0, "completed": 0}
        if not os.getenv("KIWOOM_APP_KEY") or not os.getenv("KIWOOM_SECRET_KEY"):
            return {"status": "needs_credentials", "created": 0, "completed": 0}

        cfg = self.cfg.get("pullback_research", {})
        source = KiwoomSource()
        limit = int(cfg.get("universe_limit", 20))
        ranking = source.trading_value_top(limit=limit)
        ranked_tickers = [
            str(row.get("stk_cd") or "").split("_")[0]
            for row in ranking
            if row.get("stk_cd")
        ]
        tickers = list(ranked_tickers)
        for ticker in self._pending_pullback_tickers():
            if ticker not in tickers:
                tickers.append(ticker)

        metadata = self._reference_metadata(source, now)
        path = self.stats_dir / "pullback_events.csv"
        events = load_event_csv(path)
        changed = False
        created = 0
        completed = 0
        fetched = 0
        base_date = now.strftime("%Y%m%d")

        daily_by_ticker: dict[str, list[dict[str, Any]]] = {}
        for ticker in tickers:
            try:
                raw = source.daily_chart(ticker, base_date=base_date, max_pages=1)
                daily = source.normalize_daily_rows(raw)
                if daily:
                    daily_by_ticker[ticker] = daily
                    fetched += 1
            except KiwoomAPIError:
                continue
            time.sleep(0.2)

        # 기존 눌림 표본의 1/3/5거래일 MFE·MAE를 먼저 완결한다.
        for event in events:
            ticker = str(event.get("ticker") or "")
            daily = daily_by_ticker.get(ticker)
            if not daily:
                continue
            before = str(event.get("forward_5d_date") or "")
            if complete_pullback_event(event, daily):
                changed = True
                if not before and event.get("forward_5d_date"):
                    completed += 1

        # 오늘 거래대금 상위 연구 Universe에서 조건을 만족한 모든 종목을 저장한다.
        for ticker in ranked_tickers:
            daily = daily_by_ticker.get(ticker)
            if not daily:
                continue
            event = detect_pullback_event(
                ticker,
                daily,
                metadata.get(ticker),
                min_impulse_return_pct=float(cfg.get("min_impulse_return_pct", 5.0)),
                min_impulse_amount_krw=float(
                    cfg.get("min_impulse_amount_krw", 100_000_000_000)
                ),
                min_impulse_amount_ratio=float(
                    cfg.get("min_impulse_amount_ratio", 2.0)
                ),
                impulse_lookback_days=int(cfg.get("impulse_lookback_days", 25)),
                min_drawdown_pct=float(cfg.get("min_drawdown_pct", 5.0)),
                max_drawdown_pct=float(cfg.get("max_drawdown_pct", 35.0)),
                min_amount_decay_pct=float(cfg.get("min_amount_decay_pct", 30.0)),
                max_pullback_days=int(cfg.get("max_pullback_days", 20)),
            )
            if not event:
                continue
            if not cooldown_allows(
                events,
                ticker,
                str(event.get("signal_date") or ""),
                calendar_days=int(cfg.get("event_cooldown_calendar_days", 7)),
            ):
                continue
            events.append(event)
            created += 1
            changed = True

        if changed:
            write_event_csv(path, events, PULLBACK_EVENT_FIELDS)

        if fetched:
            state_path = self.root / "data" / "market" / "state" / "pullback_research.json"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(
                json.dumps(
                    {
                        "last_success_date": now.strftime("%Y-%m-%d"),
                        "fetched": fetched,
                        "universe_count": len(ranked_tickers),
                        "created": created,
                        "completed": completed,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

        return {
            "status": "ok" if fetched else "no_daily_rows",
            "fetched": fetched,
            "created": created,
            "completed": completed,
            "universe_count": len(ranked_tickers),
        }

    def _strategy_stats(self) -> dict[str, Any]:
        close_events = load_event_csv(self.stats_dir / "close_bet_events.csv")
        pullback_events = load_event_csv(self.stats_dir / "pullback_events.csv")
        minimum = int(self.cfg.get("statistics", {}).get("min_sample_size", 20))

        close_completed = [x for x in close_events if x.get("next_date")]
        pullback_completed = [
            x for x in pullback_events if x.get("forward_5d_mfe_pct") not in (None, "")
        ]
        return {
            "close_bet": {
                "pending": len(close_events) - len(close_completed),
                "ready": len(close_completed) >= minimum,
                "summary": describe_event_sample(
                    close_completed,
                    [
                        "next_gap_pct",
                        "next_mae_pct",
                        "next_mfe_pct",
                        "late_amount_share",
                        "high_position",
                    ],
                ),
            },
            "pullback": {
                "pending": len(pullback_events) - len(pullback_completed),
                "ready": len(pullback_completed) >= minimum,
                "summary": describe_event_sample(
                    pullback_completed,
                    [
                        "drawdown_pct",
                        "pullback_days",
                        "amount_decay_pct",
                        "forward_5d_mae_pct",
                        "forward_5d_mfe_pct",
                    ],
                ),
            },
        }

    def _recent_market_history(self, limit: int = 12) -> list[dict[str, Any]]:
        folder = self.root / self.cfg.get("data", {}).get(
            "snapshot_dir", "data/market/snapshots"
        )
        if not folder.exists():
            return []
        history: list[dict[str, Any]] = []
        for path in sorted(folder.glob("*.json"), reverse=True)[:limit]:
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            q = item.get("quantitative", {})
            if q.get("status") != "ok":
                continue
            history.append(
                {
                    "generated_at": item.get("generated_at"),
                    "analyzed_stock_count": q.get("stock_count"),
                    "advance_ratio": q.get("breadth", {}).get("advance_ratio"),
                    "top10_turnover_share": q.get("turnover", {}).get("top10_share"),
                    "recent_listing_count": q.get("recent_listings", {}).get("count"),
                    "recent_listing_positive_burst_count": q.get(
                        "recent_listings", {}
                    ).get("positive_burst_count"),
                    "coflow_groups": [
                        {
                            "group": group.get("group"),
                            "positive_burst_members": group.get(
                                "positive_burst_members"
                            ),
                        }
                        for group in q.get("coflow_groups", [])[:5]
                    ],
                    "burst_leaders": [
                        {
                            "name": stock.get("name"),
                            "return_pct": stock.get("return_pct"),
                            "burst_count": stock.get("burst_count"),
                            "max_burst_ratio": stock.get("max_burst_ratio"),
                        }
                        for stock in q.get("burst_leaders", [])[:5]
                    ],
                }
            )
        history.reverse()
        return history

    def _interpret(
        self,
        quantitative: dict[str, Any],
        strategy_stats: dict[str, Any],
    ) -> dict[str, Any] | None:
        if self.mode != "live" or quantitative.get("status") != "ok":
            return None
        model_cfg = self.cfg.get("models", {}).get("regime", {})
        llm = ResearchLLM(model_cfg)
        prompt = render_prompt(
            load_prompt(self.root, "market_regime.md"),
            {
                "SNAPSHOT": json.dumps(
                    {
                        "quantitative": quantitative,
                        "strategy_stats": strategy_stats,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                "HISTORY": json.dumps(
                    self._recent_market_history(),
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        )
        return llm.request_json(prompt, web=False, model_cfg=model_cfg)

    def run(self) -> dict[str, Any]:
        now = datetime.now(KST)
        if self.mode == "dry-run":
            minute, metadata = synthetic_market()
            source_state = {"source": "synthetic", "status": "ok"}
        else:
            if not in_krx_intraday(now):
                minute, metadata = {}, {}
                source_state = {
                    "source": "kiwoom",
                    "status": "outside_regular_session",
                    "reason": "현재 국내시장 분봉 수집 시간(09:00~15:40)이 아님",
                }
            else:
                minute, metadata, source_state = self._collect_live()

        quantitative = self.stats.summarize_market(minute, metadata)
        event_update = {"created": 0, "completed": 0}
        if minute and self.mode == "live":
            event_update = self._update_close_bet_events(now, minute, quantitative)

        pullback_update = self._run_pullback_research(now)
        strategy_stats = self._strategy_stats()
        interpretation = (
            self._interpret(quantitative, strategy_stats)
            if quantitative.get("status") == "ok"
            else None
        )

        result = {
            "generated_at": now.isoformat(),
            "mode": self.mode,
            "source": source_state,
            "quantitative": quantitative,
            "strategy_stats": strategy_stats,
            "event_update": {
                "close_bet": event_update,
                "pullback": pullback_update,
            },
            "interpretation": interpretation,
        }

        # 읽기 쉬운 Markdown 보고서는 실제 분석 데이터가 있을 때만 만든다.
        if quantitative.get("status") == "ok":
            report_dir = self.root / "reports" / "market"
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = report_dir / (now.strftime("%Y%m%d-%H%M") + ".md")
            report_path.write_text(
                render_market_markdown(result),
                encoding="utf-8",
            )
            result["report"] = str(report_path.relative_to(self.root))

        latest = self.root / self.cfg.get("data", {}).get(
            "latest_file", "data/market/latest.json"
        )
        latest.parent.mkdir(parents=True, exist_ok=True)
        latest.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 10분 스냅샷도 유효한 시장 데이터가 있을 때만 보존해 저장소 팽창을 줄인다.
        if quantitative.get("status") == "ok":
            snap_dir = self.root / self.cfg.get("data", {}).get(
                "snapshot_dir", "data/market/snapshots"
            )
            snap_dir.mkdir(parents=True, exist_ok=True)
            snap = snap_dir / (now.strftime("%Y%m%d-%H%M") + ".json")
            snap.write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        return {
            "status": source_state.get("status"),
            "market_status": quantitative.get("status"),
            "stocks": quantitative.get("stock_count", 0),
            "latest": str(latest.relative_to(self.root)),
            "report": result.get("report"),
            "events": {
                "close_bet": event_update,
                "pullback": pullback_update,
            },
        }
