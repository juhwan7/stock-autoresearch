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
from .market_stats import MarketStats, describe_event_sample


KST = timezone(timedelta(hours=9))


def in_krx_intraday(now: datetime | None = None) -> bool:
    now = now or datetime.now(KST)
    if now.weekday() >= 5:
        return False
    hhmm = now.strftime("%H:%M")
    return "09:00" <= hhmm <= "15:30"


def load_event_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


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


def synthetic_market() -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    minute: dict[str, list[dict[str, Any]]] = {}
    meta: dict[str, dict[str, Any]] = {}
    for idx, ticker in enumerate(("000001", "000002", "000003")):
        rows = []
        price = 10000 + idx * 1000
        for i in range(35):
            hour = 14 + (25 + i) // 60
            minute_value = (25 + i) % 60
            amount = 120_000_000 + i * 2_000_000
            if i in (10, 11, 28):
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
        lines.extend([
            "## 현재 상태",
            "",
            "- 장세를 정량 판독할 수 있는 분봉 데이터가 부족합니다.",
            "- " + str(result.get("source", {}).get("reason") or q.get("reason") or "원인 미상"),
            "",
        ])
        return "\n".join(lines)

    lines.extend([
        "## 현재 장세",
        "",
        str(interpretation.get("one_line") or "정량 데이터는 수집됐지만 AI 장세 해석은 아직 없습니다."),
        "",
        "## 시장 폭",
        "",
        f"- 분석 종목 수: {q.get('stock_count', 0)}",
        f"- 상승 종목: {q.get('breadth', {}).get('advancers', 0)}",
        f"- 하락 종목: {q.get('breadth', {}).get('decliners', 0)}",
        f"- 상위 10개 거래대금 집중도: {q.get('turnover', {}).get('top10_share', 0):.1%}",
        "",
        "## 분봉 거래대금 Burst 상위",
        "",
    ])

    for item in q.get("burst_leaders", [])[:10]:
        lines.append(
            f"- **{item.get('name')} ({item.get('ticker')})** "
            f"수익률 {item.get('return_pct')}% · burst {item.get('burst_count')}회 · "
            f"최대 {item.get('max_burst_ratio')}배 · 장후반 거래대금 비중 {float(item.get('close_watch_share') or 0):.1%}"
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
    lines.extend([
        "",
        "## 신규주 흐름",
        "",
        f"- 추적 신규주: {new_flow.get('count', 0)}개",
        f"- 상승 + 거래대금 burst: {new_flow.get('positive_burst_count', 0)}개",
        "",
        "## 종가베팅 관점",
        "",
    ])
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
        lines.append(f"- {label}: 표본 {sample}개 · {'통계 사용 가능' if block.get('ready') else '표본 축적 중'}")

    lines.extend([
        "",
        "---",
        "이 리포트는 통계 연구용이며 매수·매도 추천이 아닙니다.",
        "",
    ])
    return "\n".join(lines)


class MarketIntelEngine:
    def __init__(self, root: Path, mode: str):
        self.root = root
        self.mode = mode
        self.cfg = load_yaml(root / "config" / "market_intel.yaml")
        self.stats = MarketStats(self.cfg)

    def _collect_live(self) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]], dict[str, Any]]:
        if not os.getenv("KIWOOM_APP_KEY") or not os.getenv("KIWOOM_SECRET_KEY"):
            return {}, {}, {
                "source": "kiwoom",
                "status": "needs_credentials",
                "reason": "KIWOOM_APP_KEY / KIWOOM_SECRET_KEY가 등록되지 않음",
            }

        source = KiwoomSource()
        rank_limit = int(self.cfg.get("universe", {}).get("turnover_rank_limit", 30))
        detail_limit = int(self.cfg.get("universe", {}).get("detail_minute_limit", 20))
        ranking = source.trading_value_top(limit=rank_limit)
        metadata = load_metadata(self.root / "data" / "market" / "metadata.csv")

        minute_by_ticker: dict[str, list[dict[str, Any]]] = {}
        today = datetime.now(KST).strftime("%Y%m%d")
        for row in ranking[:detail_limit]:
            ticker = str(row.get("stk_cd") or "").split("_")[0]
            if not ticker:
                continue
            if ticker not in metadata:
                metadata[ticker] = {
                    "name": row.get("stk_nm") or ticker,
                    "sector": "",
                    "group_id": "",
                    "listing_age_days": None,
                }
            try:
                raw = source.minute_chart(ticker, base_date=today, max_pages=2)
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

    def _strategy_stats(self) -> dict[str, Any]:
        stats_dir = self.root / self.cfg.get("data", {}).get("stats_dir", "data/market/stats")
        close_events = load_event_csv(stats_dir / "close_bet_events.csv")
        pullback_events = load_event_csv(stats_dir / "pullback_events.csv")
        minimum = int(self.cfg.get("statistics", {}).get("min_sample_size", 20))
        return {
            "close_bet": {
                "ready": len(close_events) >= minimum,
                "summary": describe_event_sample(
                    close_events,
                    ["next_gap_pct", "next_mae_pct", "next_mfe_pct", "late_amount_share", "high_position"],
                ),
            },
            "pullback": {
                "ready": len(pullback_events) >= minimum,
                "summary": describe_event_sample(
                    pullback_events,
                    ["drawdown_pct", "pullback_days", "amount_decay_pct", "forward_5d_mae_pct", "forward_5d_mfe_pct"],
                ),
            },
        }

    def _interpret(self, snapshot: dict[str, Any]) -> dict[str, Any] | None:
        if self.mode != "live" or snapshot.get("status") != "ok":
            return None
        model_cfg = self.cfg.get("models", {}).get("regime", {})
        llm = ResearchLLM(model_cfg)
        prompt = render_prompt(
            load_prompt(self.root, "market_regime.md"),
            {
                "SNAPSHOT": json.dumps(snapshot, ensure_ascii=False, indent=2),
                "HISTORY": "현재 V1에서는 정량 스냅샷 히스토리 비교를 준비 중",
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
                    "reason": "현재 KRX 정규장 시간이 아님",
                }
            else:
                minute, metadata, source_state = self._collect_live()

        quantitative = self.stats.summarize_market(minute, metadata)
        strategy_stats = self._strategy_stats()
        interpretation = self._interpret(quantitative) if quantitative.get("status") == "ok" else None

        result = {
            "generated_at": now.isoformat(),
            "mode": self.mode,
            "source": source_state,
            "quantitative": quantitative,
            "strategy_stats": strategy_stats,
            "interpretation": interpretation,
        }

        report_dir = self.root / "reports" / "market"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / (now.strftime("%Y%m%d-%H%M") + ".md")
        report_path.write_text(render_market_markdown(result), encoding="utf-8")
        result["report"] = str(report_path.relative_to(self.root))

        latest = self.root / self.cfg.get("data", {}).get("latest_file", "data/market/latest.json")
        latest.parent.mkdir(parents=True, exist_ok=True)
        latest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        snap_dir = self.root / self.cfg.get("data", {}).get("snapshot_dir", "data/market/snapshots")
        snap_dir.mkdir(parents=True, exist_ok=True)
        snap = snap_dir / (now.strftime("%Y%m%d-%H%M") + ".json")
        snap.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        return {
            "status": source_state.get("status"),
            "market_status": quantitative.get("status"),
            "stocks": quantitative.get("stock_count", 0),
            "latest": str(latest.relative_to(self.root)),
            "report": result.get("report"),
        }
