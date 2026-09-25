from __future__ import annotations

from datetime import datetime, time
from typing import Any


def audit_toss_snapshot(toss: dict[str, Any], fallback: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Toss 장중 스냅샷의 누락을 보조 공급자와 비교해 진단한다."""
    hhmm = now.time()
    regular = time(9, 0) <= hhmm <= time(15, 30)
    ranking = [x for x in (toss.get("ranking") or []) if isinstance(x, dict)]
    fallback_ranking = [x for x in (fallback.get("ranking") or fallback.get("leaders") or []) if isinstance(x, dict)]
    minute = toss.get("minute_by_ticker") or {}
    errors = toss.get("fetch_errors") or {}

    toss_codes = {str(x.get("ticker") or x.get("code") or "") for x in ranking}
    fallback_codes = {str(x.get("ticker") or x.get("code") or "") for x in fallback_ranking}
    toss_codes.discard("")
    fallback_codes.discard("")

    missing_vs_fallback = sorted(fallback_codes - toss_codes)
    missing_minute = sorted(code for code in toss_codes if code not in minute or not minute.get(code))
    issues: list[dict[str, Any]] = []

    if regular and fallback_codes and len(ranking) < min(45, len(fallback_codes)):
        issues.append({"code": "ranking-incomplete", "severity": "CRITICAL", "count": len(ranking)})
    if regular and missing_vs_fallback:
        issues.append({"code": "ranking-cross-source-gap", "severity": "WARN", "tickers": missing_vs_fallback[:30]})
    if regular and toss_codes and len(missing_minute) >= max(3, len(toss_codes) // 10):
        issues.append({"code": "minute-bars-missing", "severity": "WARN", "tickers": missing_minute[:30]})
    if errors:
        issues.append({"code": "ticker-fetch-errors", "severity": "WARN", "count": len(errors)})

    return {
        "status": "degraded" if issues else "ok",
        "regular_session": regular,
        "toss_ranking_count": len(ranking),
        "fallback_ranking_count": len(fallback_ranking),
        "missing_vs_fallback": missing_vs_fallback,
        "missing_minute_tickers": missing_minute,
        "fetch_error_count": len(errors),
        "issues": issues,
        "recommended_action": (
            "fallback_provider_and_backfill"
            if issues and fallback_codes
            else "retry_toss"
            if issues
            else "none"
        ),
    }
