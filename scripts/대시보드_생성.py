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
    }


def recent_reports(limit: int = 100) -> list[dict]:
    files = sorted((ROOT / "reports").rglob("*.md"), reverse=True)[:limit]
    repo = os.getenv("GITHUB_REPOSITORY", "juhwan7/stock-autoresearch")
    result = []
    for path in files:
        meta = report_metadata(path)
        result.append(
            {
                "title": title_of(path),
                "file": str(path.relative_to(ROOT / "reports")),
                "github_url": f"https://github.com/{repo}/blob/main/{path.relative_to(ROOT)}",
                **meta,
            }
        )
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


def main() -> None:
    market = read_json(ROOT / "data" / "market" / "latest.json")
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
        "market_recent_sessions": read_json(ROOT / "data" / "market" / "recent-sessions.json"),
        "market_runtime": read_json(ROOT / "data" / "market" / "runtime.json"),
        "toss_provider": toss_provider_status(),
        "risk": risk,
        "macro_matrix": macro_matrix(market, risk),
        "risk_runtime": read_json(ROOT / "data" / "risk" / "runtime.json"),
        "health": read_json(ROOT / "data" / "health" / "latest.json"),
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


if __name__ == "__main__":
    main()
