from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
DATA = SITE / "data"
DATA.mkdir(parents=True, exist_ok=True)


def title_of(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    except OSError:
        pass
    return path.name


def report_metadata(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = ""

    generated_at = ""
    quality = None
    industries: list[str] = []
    stocks: list[str] = []
    current = ""

    for line in text.splitlines():
        if line.startswith("> 생성:"):
            generated_at = line.split(":", 1)[1].strip()
        elif line.startswith("> research quality average:"):
            try:
                quality = float(line.rsplit(":", 1)[1].strip())
            except ValueError:
                quality = None
        elif line.startswith("## "):
            current = line[3:].strip()
        elif line.startswith("- **"):
            match = re.match(r"- \*\*(.+?)\*\*", line)
            if not match:
                continue
            value = match.group(1).strip()
            if current == "산업 연결" and value not in industries:
                industries.append(value)
            elif current == "상장사 연결" and value not in stocks:
                stocks.append(value)

    preview = " ".join(
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.startswith("#") and not line.startswith(">")
    )[:900]
    return {
        "generated_at": generated_at,
        "quality": quality,
        "industries": industries[:12],
        "stocks": stocks[:20],
        "preview": preview,
        "content": text[:18000],
    }


def inferred_report_time(path: Path, title: str, generated_at: str) -> str:
    if generated_at:
        return generated_at
    source = f"{path.stem} {title}"
    date_match = re.search(r"(20\d{2}-\d{2}-\d{2})", source)
    if not date_match:
        return ""
    day = date_match.group(1)
    tail = source[date_match.end():]
    time_matches = re.findall(r"(?<!\d)([01]\d|2[0-3])(?::?([0-5]\d))(?!\d)", tail)
    hour, minute = time_matches[-1] if time_matches else ("00", "00")
    return f"{day}T{hour}:{minute}:00+09:00"


def recent_reports(limit: int = 100) -> list[dict]:
    files = list((ROOT / "reports").rglob("*.md"))
    repo = os.getenv("GITHUB_REPOSITORY", "juhwan7/stock-autoresearch")
    result = []
    for path in files:
        title = title_of(path)
        meta = report_metadata(path)
        result.append(
            {
                "title": title,
                "file": str(path.relative_to(ROOT / "reports")),
                "github_url": f"https://github.com/{repo}/blob/main/{path.relative_to(ROOT)}",
                "sort_at": inferred_report_time(path, title, meta.get("generated_at", "")),
                **meta,
            }
        )
    result.sort(key=lambda item: item.get("sort_at") or "", reverse=True)
    result = result[:limit]
    for index, item in enumerate(result):
        if index >= 20:
            item.pop("content", None)
    return result


def idea_board() -> dict[str, list[dict[str, str]]]:
    path = ROOT / "docs" / "아이디어_보드.md"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}

    result: dict[str, list[dict[str, str]]] = {}
    current: dict[str, str] | None = None
    body: list[str] = []

    def flush() -> None:
        nonlocal current, body
        if current is None:
            return
        summary = " ".join(x.strip() for x in body if x.strip())[:500]
        item = dict(current)
        item["summary"] = summary
        result.setdefault(item["status"], []).append(item)
        current = None
        body = []

    for line in lines:
        match = re.match(r"^## (채택|실험중|후보|재검토|보류|폐기) — (.+)$", line)
        if match:
            flush()
            current = {"status": match.group(1), "title": match.group(2).strip()}
            continue
        if current is not None:
            if line.startswith("## "):
                flush()
            else:
                body.append(line)
    flush()
    return result


def recent_change_manifests(limit: int = 30) -> list[dict]:
    folder = ROOT / "data" / "evolution" / "changes"
    result = []
    if not folder.exists():
        return result
    for path in sorted(folder.glob("*.json"), reverse=True)[:limit]:
        data = read_json(path)
        if not data:
            continue
        result.append(
            {
                "change_id": data.get("change_id"),
                "applied_at": data.get("applied_at"),
                "title": data.get("title"),
                "risk": data.get("risk"),
                "status": data.get("status", "active"),
                "paths": data.get("paths", []),
                "rollback_reason": data.get("rollback_reason"),
                "quarantine_reason": data.get("quarantine_reason"),
            }
        )
    return result


def latest_ticks(limit: int = 30) -> list[dict]:
    folder = ROOT / "data" / "evolution" / "ticks"
    result: list[dict] = []
    for path in sorted(folder.glob("*.jsonl"), reverse=True):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            scout = item.get("scout", {})
            result.append(
                {
                    "time": item.get("timestamp_kst"),
                    "title": scout.get("title"),
                    "category": scout.get("category"),
                    "decision": scout.get("decision"),
                    "outcome": item.get("outcome"),
                    "observation": scout.get("observation"),
                    "benefit": scout.get("expected_benefit"),
                }
            )
            if len(result) >= limit:
                return result
    return result


def section_tail(path: Path, chars: int = 12000) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    return text[-chars:]


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def toss_provider_status() -> dict:
    snapshot = read_json(ROOT / "data" / "providers" / "toss" / "latest.json")
    persisted = read_json(ROOT / "data" / "providers" / "toss" / "status.json")
    fetch_runtime = read_json(
        ROOT / "data" / "providers" / "toss" / "fetch_runtime.json"
    )
    if snapshot:
        collector = snapshot.get("collector", {})
        subscriptions = collector.get("subscriptions", [])
        rejected = collector.get("rejected", [])
        result = {
            "available": True,
            "captured_at": snapshot.get("captured_at"),
            "provider": snapshot.get("provider"),
            "source_mode": snapshot.get("source_mode"),
            "minute_amount_method": snapshot.get("minute_amount_method"),
            "ranking_count": len(snapshot.get("ranking", [])),
            "regular_ticker_count": len(snapshot.get("minute_by_ticker", {})),
            "postmarket_ticker_count": len(
                snapshot.get("postmarket_by_ticker", {})
            ),
            "subscription_count": len(subscriptions)
            if isinstance(subscriptions, list)
            else 0,
            "rejected_count": len(rejected)
            if isinstance(rejected, list)
            else 0,
            "last_message_at": collector.get("last_message_at"),
            "last_universe_refresh": collector.get("last_universe_refresh"),
        }
    else:
        result = {
            "available": bool(persisted.get("available")),
            "captured_at": persisted.get("captured_at"),
            "provider": persisted.get("provider"),
            "source_mode": persisted.get("source_mode"),
            "minute_amount_method": persisted.get("minute_amount_method"),
            "ranking_count": persisted.get("ranking_count", 0),
            "regular_ticker_count": persisted.get("regular_ticker_count", 0),
            "postmarket_ticker_count": persisted.get(
                "postmarket_ticker_count", 0
            ),
            "subscription_count": (
                persisted.get("collector", {}).get("subscription_count", 0)
            ),
            "rejected_count": (
                persisted.get("collector", {}).get("rejected_count", 0)
            ),
            "last_message_at": (
                persisted.get("collector", {}).get("last_message_at")
            ),
            "last_universe_refresh": (
                persisted.get("collector", {}).get("last_universe_refresh")
            ),
        }
    result["fetch_runtime"] = {
        "status": fetch_runtime.get("status"),
        "fetched_at": fetch_runtime.get("fetched_at"),
        "captured_at": fetch_runtime.get("captured_at"),
        "error": fetch_runtime.get("error"),
    }
    return result


def macro_matrix(market: dict, risk: dict) -> dict:
    macro = risk.get("macro", {}) if isinstance(risk, dict) else {}
    values = macro.get("values", {}) if isinstance(macro, dict) else {}
    signal_map = {
        str(x.get("field")): str(x.get("risk_level"))
        for x in risk.get("macro_signals", [])
        if isinstance(x, dict) and x.get("field")
    }
    source_map = {}
    for item in macro.get("sources", []) if isinstance(macro, dict) else []:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field") or "")
        if field:
            source_map[field] = {
                "title": item.get("title"),
                "url": item.get("url"),
                "timestamp": item.get("timestamp"),
            }

    overview = (market.get("source") or {}).get("market_overview", {})
    definitions = [
        ("국내", "KOSPI", "kospi_pct", "pct", (overview.get("KOSPI") or {}).get("change_pct")),
        ("국내", "KOSDAQ", "kosdaq_pct", "pct", (overview.get("KOSDAQ") or {}).get("change_pct")),
        ("국내", "KOSPI200 선물", "kospi200_futures_pct", "pct", values.get("kospi200_futures_pct")),
        ("국내", "KOSPI200 야간선물", "kospi200_night_futures_pct", "pct", values.get("kospi200_night_futures_pct")),
        ("환율·금리", "USD/KRW", "usdkrw_pct", "pct", values.get("usdkrw_pct")),
        ("환율·금리", "DXY", "dxy_pct", "pct", values.get("dxy_pct")),
        ("환율·금리", "USD/CNH", "usdcnh_pct", "pct", values.get("usdcnh_pct")),
        ("환율·금리", "미국 2Y", "us2y_yield", "yield", values.get("us2y_yield")),
        ("환율·금리", "미국 2Y Δ", "us2y_change_bp", "bp", values.get("us2y_change_bp")),
        ("환율·금리", "미국 10Y", "us10y_yield", "yield", values.get("us10y_yield")),
        ("환율·금리", "미국 10Y Δ", "us10y_change_bp", "bp", values.get("us10y_change_bp")),
        ("환율·금리", "한국 3Y", "korea3y_yield", "yield", values.get("korea3y_yield")),
        ("환율·금리", "한국 10Y", "korea10y_yield", "yield", values.get("korea10y_yield")),
        ("미국", "Nasdaq 100", "nasdaq100_pct", "pct", values.get("nasdaq100_pct")),
        ("미국", "Nasdaq 선물", "nasdaq_futures_pct", "pct", values.get("nasdaq_futures_pct")),
        ("미국", "S&P 500", "sp500_pct", "pct", values.get("sp500_pct")),
        ("미국", "S&P 선물", "sp500_futures_pct", "pct", values.get("sp500_futures_pct")),
        ("미국", "SOX", "sox_pct", "pct", values.get("sox_pct")),
        ("미국", "VIX", "vix_pct", "pct", values.get("vix_pct")),
        ("아시아", "Nikkei 225", "nikkei225_pct", "pct", values.get("nikkei225_pct")),
        ("아시아", "Hang Seng", "hang_seng_pct", "pct", values.get("hang_seng_pct")),
        ("아시아", "China A50 선물", "china_a50_futures_pct", "pct", values.get("china_a50_futures_pct")),
        ("원자재", "WTI", "wti_pct", "pct", values.get("wti_pct")),
        ("원자재", "구리", "copper_pct", "pct", values.get("copper_pct")),
        ("원자재", "금", "gold_pct", "pct", values.get("gold_pct")),
        ("원자재", "Bitcoin", "bitcoin_pct", "pct", values.get("bitcoin_pct")),
    ]

    items = []
    for group, label, field, kind, value in definitions:
        source = source_map.get(field, {})
        items.append(
            {
                "group": group,
                "label": label,
                "field": field,
                "kind": kind,
                "value": value,
                "risk_level": signal_map.get(field, "LOW"),
                "source": source,
            }
        )

    known = sum(1 for item in items if item.get("value") not in (None, ""))
    evaluation = risk.get("evaluation", {}) if isinstance(risk, dict) else {}
    return {
        "captured_at": macro.get("captured_at") if isinstance(macro, dict) else None,
        "source_mode": macro.get("source_mode") if isinstance(macro, dict) else None,
        "known_count": known,
        "total_count": len(items),
        "risk_level": risk.get("macro_risk_level") if isinstance(risk, dict) else None,
        "macro_regime": evaluation.get("macro_regime"),
        "transmission_paths": evaluation.get("macro_transmission_paths", []),
        "conflicting_signals": evaluation.get("conflicting_signals", []),
        "unknowns": macro.get("unknowns", []) if isinstance(macro, dict) else [],
        "items": items,
    }



def market_with_recent_session_fallback(
    market: dict,
    recent_sessions: dict,
    runtime: dict,
) -> dict:
    """휴장/실시간 공백에도 최근 실제 거래일을 시장 컨텍스트로 유지한다."""
    quantitative = market.get("quantitative", {}) if isinstance(market, dict) else {}
    if market and quantitative.get("status") == "ok":
        return market

    korea = recent_sessions.get("korea", []) if isinstance(recent_sessions, dict) else []
    if not isinstance(korea, list) or not korea:
        return market if isinstance(market, dict) else {}

    rows = [row for row in korea[:3] if isinstance(row, dict)]
    if not rows:
        return market if isinstance(market, dict) else {}

    latest = rows[0]
    flows = latest.get("flows_krw_100m", {}) if isinstance(latest, dict) else {}
    foreign = flows.get("foreign")
    institution = flows.get("institution")

    if isinstance(foreign, (int, float)) and isinstance(institution, (int, float)):
        if foreign > 0 and institution > 0:
            flow_text = "외국인·기관 동반 순매수"
        elif foreign < 0 and institution < 0:
            flow_text = "외국인·기관 동반 순매도"
        else:
            flow_text = "외국인·기관 수급 엇갈림"
    else:
        flow_text = "외국인·기관 수급 미확인"

    overview = {}
    for label, key in (("KOSPI", "kospi"), ("KOSDAQ", "kosdaq")):
        block = latest.get(key, {}) if isinstance(latest.get(key), dict) else {}
        overview[label] = {
            "index": block.get("close"),
            "change_pct": block.get("change_pct"),
            "rising": None,
            "flat": None,
            "falling": None,
            "advance_ratio": None,
        }

    return {
        "generated_at": recent_sessions.get("updated_at"),
        "mode": "historical_fallback",
        "source": {
            "source": "recent_sessions",
            "provider": recent_sessions.get("basis") or "verified_close",
            "status": "historical_fallback",
            "reason": runtime.get("reason")
            or "실시간 시장 데이터가 없어 최근 실제 거래일 3개를 사용",
            "market_overview": overview,
            "flows_krw_100m": flows,
            "session_dates": [row.get("date") for row in rows],
            "historical_session_count": len(rows),
        },
        "quantitative": {
            "status": "historical_fallback",
            "stock_count": 0,
            "historical_session_count": len(rows),
            "historical_sessions": rows,
            "reason": "휴장/장외 실시간 공백: 최근 3거래일 종가·지수·투자자 수급으로 분석 유지",
        },
        "strategy_stats": market.get("strategy_stats", {}) if isinstance(market, dict) else {},
        "event_update": market.get("event_update", {}) if isinstance(market, dict) else {},
        "interpretation": {
            "regime_name": "휴장 · 최근 거래일 기준",
            "confidence": "medium",
            "one_line": (
                f"{latest.get('date', '최근 거래일')} 기준 "
                f"KOSPI {latest.get('kospi', {}).get('change_pct', '-')}%, "
                f"KOSDAQ {latest.get('kosdaq', {}).get('change_pct', '-')}% · {flow_text}. "
                "장중 분봉·Top50은 과거 원본이 보존된 범위에서만 사용합니다."
            ),
            "evidence": [
                {
                    "date": row.get("date"),
                    "kospi_change_pct": (row.get("kospi") or {}).get("change_pct"),
                    "kosdaq_change_pct": (row.get("kosdaq") or {}).get("change_pct"),
                    "flows_krw_100m": row.get("flows_krw_100m", {}),
                }
                for row in rows
            ],
            "unknowns": ["과거 1분 Top50 전체 원본이 저장되지 않은 거래일은 분봉 재구성 불가"],
        },
        "historical_fallback": {
            "active": True,
            "basis": recent_sessions.get("basis"),
            "updated_at": recent_sessions.get("updated_at"),
            "sessions": rows,
        },
        "semantic_state": {},
        "semantic_hash": "",
        "ai_dirty": False,
    }


def main() -> None:
    market = read_json(ROOT / "data" / "market" / "latest.json")
    recent_sessions = read_json(ROOT / "data" / "market" / "recent-sessions.json")
    market_runtime = read_json(ROOT / "data" / "market" / "runtime.json")
    market = market_with_recent_session_fallback(market, recent_sessions, market_runtime)
    risk = read_json(ROOT / "data" / "risk" / "latest.json")
    reports = recent_reports()
    status = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": "Stock AutoResearch",
        "heartbeat": "6분",
        "reports": reports,
        "popular_reports": read_json(ROOT / "data" / "research" / "popular-reports.json"),
        "supervisor_latest": read_json(ROOT / "data" / "supervisor" / "latest-report.json"),
        "supervisor_recent": read_json(ROOT / "data" / "supervisor" / "recent.json"),
        "market_issues": read_json(ROOT / "data" / "supervisor" / "market-issues.json"),
        "discovery": read_json(ROOT / "data" / "discovery" / "latest.json"),
        "news_issue_digest": read_json(ROOT / "data" / "news" / "issue-digest.json"),
        "quality_history": [
            {
                "title": item.get("title"),
                "generated_at": item.get("generated_at"),
                "quality": item.get("quality"),
            }
            for item in reversed(reports)
            if item.get("quality") is not None
        ][-40:],
        "ticks": latest_ticks(),
        "idea_board": idea_board(),
        "recent_changes": recent_change_manifests(),
        "decision_memory": section_tail(ROOT / "docs" / "결정_원장.md"),
        "ideas": section_tail(ROOT / "docs" / "아이디어_보드.md"),
        "help_needed": section_tail(ROOT / "docs" / "사용자_도움_필요.md"),
        "changelog": section_tail(ROOT / "docs" / "AI_변경기록.md"),
        "market": market,
        "market_recent_sessions": recent_sessions,
        "relative_strength": read_json(ROOT / "data" / "market" / "relative-strength.json"),
        "market_runtime": market_runtime,
        "toss_provider": toss_provider_status(),
        "risk": risk,
        "macro_matrix": macro_matrix(market, risk),
        "risk_runtime": read_json(ROOT / "data" / "risk" / "runtime.json"),
        "health": read_json(ROOT / "data" / "health" / "latest.json"),
        "operations": read_json(ROOT / "data" / "operations" / "status.json"),
        "regression": read_json(ROOT / "data" / "regression" / "latest.json"),
        "quarantine": read_json(ROOT / "data" / "regression" / "quarantine.json"),
        "docs_links": [
            {
                "title": "문서 지도",
                "url": "https://github.com/" + os.getenv("GITHUB_REPOSITORY", "juhwan7/stock-autoresearch") + "/blob/main/docs/문서_지도.md",
            },
            {
                "title": "트레이딩 연구 원칙",
                "url": "https://github.com/" + os.getenv("GITHUB_REPOSITORY", "juhwan7/stock-autoresearch") + "/blob/main/docs/매매연구_원칙.md",
            },
            {
                "title": "시장 데이터 명세",
                "url": "https://github.com/" + os.getenv("GITHUB_REPOSITORY", "juhwan7/stock-autoresearch") + "/blob/main/docs/시장데이터_명세.md",
            },
            {
                "title": "회귀 탐지·기능 롤백",
                "url": "https://github.com/" + os.getenv("GITHUB_REPOSITORY", "juhwan7/stock-autoresearch") + "/blob/main/docs/회귀탐지_롤백.md",
            },
            {
                "title": "토스 데이터 계획",
                "url": "https://github.com/" + os.getenv("GITHUB_REPOSITORY", "juhwan7/stock-autoresearch") + "/blob/main/docs/토스데이터_운영계획.md",
            },
            {
                "title": "결정 원장",
                "url": "https://github.com/" + os.getenv("GITHUB_REPOSITORY", "juhwan7/stock-autoresearch") + "/blob/main/docs/결정_원장.md",
            },
        ],
    }
    (DATA / "상태.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (DATA / "상대강도.json").write_text(
        json.dumps(status.get("relative_strength") or {}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
