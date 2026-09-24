from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import load_yaml


KST = timezone(timedelta(hours=9))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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


def _age_minutes(value: Any, now: datetime) -> float | None:
    stamp = _parse_time(value)
    if stamp is None:
        return None
    return max(0.0, (now - stamp).total_seconds() / 60.0)


def _kr_market_monitor_window(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    return "08:00" <= now.strftime("%H:%M") <= "20:10"


class HealthWatchdog:
    def __init__(self, root: Path):
        self.root = root
        self.cfg = load_yaml(root / "config" / "health.yaml")
        data = self.cfg.get("data", {})
        self.state_path = root / data.get("state_file", "data/health/state.json")
        self.latest_path = root / data.get("latest_file", "data/health/latest.json")

    def _issue(
        self,
        component: str,
        code: str,
        severity: str,
        message: str,
        recovery: str,
    ) -> dict[str, str]:
        return {
            "component": component,
            "code": code,
            "severity": severity,
            "message": message,
            "recovery": recovery,
        }

    def _check_market(self, now: datetime) -> list[dict[str, str]]:
        path = self.root / self.cfg.get("components", {}).get("market", {}).get(
            "runtime_file", "data/market/runtime.json"
        )
        data = _read_json(path)
        issues = []
        status = str(data.get("source_status") or "")
        age = _age_minutes(data.get("generated_at"), now)

        if not data:
            issues.append(
                self._issue(
                    "market",
                    "runtime-missing",
                    "WARN",
                    "Market runtime 상태 파일이 없음",
                    "market-intel 실행과 데이터 공급자 설정을 확인",
                )
            )
            return issues

        if status == "needs_credentials":
            issues.append(
                self._issue(
                    "market",
                    "credentials",
                    "WARN",
                    "국내시장 데이터 인증정보가 준비되지 않음",
                    "HELP_NEEDED의 시장 데이터 Secret/Collector 항목 확인",
                )
            )
        elif status in {"no_rows", "error"}:
            issues.append(
                self._issue(
                    "market",
                    "source-error",
                    "WARN",
                    f"시장 데이터 상태: {status}",
                    "데이터 공급자 응답과 API 제한을 확인하고 마지막 유효 장세는 유지",
                )
            )

        limit = float(
            self.cfg.get("thresholds", {}).get(
                "market_stale_minutes_during_session", 25
            )
        )
        if _kr_market_monitor_window(now) and age is not None and age > limit:
            issues.append(
                self._issue(
                    "market",
                    "stale",
                    "WARN",
                    f"시장 runtime이 {age:.0f}분째 갱신되지 않음",
                    "10분 Continuous workflow와 데이터 공급자 상태 확인",
                )
            )
        return issues

    def _check_risk(self, now: datetime) -> list[dict[str, str]]:
        comp = self.cfg.get("components", {}).get("risk", {})
        runtime = _read_json(
            self.root / comp.get("runtime_file", "data/risk/runtime.json")
        )
        latest = _read_json(
            self.root / comp.get("latest_file", "data/risk/latest.json")
        )
        issues = []
        if not runtime:
            issues.append(
                self._issue(
                    "risk",
                    "runtime-missing",
                    "WARN",
                    "Risk runtime 상태가 없음",
                    "risk-intel dry-run/live 실행 여부 확인",
                )
            )
            return issues

        age = _age_minutes(runtime.get("generated_at"), now)
        limit = float(
            self.cfg.get("thresholds", {}).get("risk_stale_minutes", 25)
        )
        if age is not None and age > limit:
            issues.append(
                self._issue(
                    "risk",
                    "stale",
                    "WARN",
                    f"Risk 상태가 {age:.0f}분째 갱신되지 않음",
                    "risk-intel 단계와 OPENAI_API_KEY 상태 확인",
                )
            )

        macro = latest.get("macro", {})
        if macro.get("refresh_error"):
            issues.append(
                self._issue(
                    "risk",
                    "macro-refresh-error",
                    "WARN",
                    "매크로 갱신 중 오류가 기록됨",
                    "기존 값은 유지하고 source freshness와 웹 검색/API 상태 확인",
                )
            )

        calendar = latest.get("upcoming_events", [])
        if not calendar:
            issues.append(
                self._issue(
                    "risk",
                    "calendar-empty",
                    "INFO",
                    "가까운 주요 일정이 없거나 일정 데이터가 비어 있음",
                    "공식 일정 갱신 상태를 확인하되 실제로 일정이 없으면 조치 불필요",
                )
            )
        return issues

    def _check_macro(self, now: datetime) -> list[dict[str, str]]:
        path = self.root / self.cfg.get("components", {}).get("macro", {}).get(
            "file", "data/macro/current.json"
        )
        data = _read_json(path)
        if not data:
            return [
                self._issue(
                    "macro",
                    "missing",
                    "WARN",
                    "매크로 스냅샷이 없음",
                    "Risk source refresh 또는 Toss/외부 Collector 연결 확인",
                )
            ]
        age = _age_minutes(data.get("captured_at"), now)
        limit = float(
            self.cfg.get("thresholds", {}).get("macro_stale_minutes", 25)
        )
        if age is not None and age > limit:
            return [
                self._issue(
                    "macro",
                    "stale",
                    "WARN",
                    f"매크로 데이터가 {age:.0f}분째 갱신되지 않음",
                    "provider_current.json 또는 web fallback 갱신 상태 확인",
                )
            ]
        return []

    def _update_consecutive(
        self,
        previous: dict[str, Any],
        issues: list[dict[str, str]],
    ) -> dict[str, int]:
        active = {f"{x['component']}:{x['code']}" for x in issues if x["severity"] != "INFO"}
        old = previous.get("consecutive", {})
        keys = set(old) | active
        return {
            key: (int(old.get(key, 0)) + 1 if key in active else 0)
            for key in keys
            if key in active
        }

    def run(self) -> dict[str, Any]:
        now = datetime.now(KST)
        previous = _read_json(self.state_path)
        issues = []
        issues.extend(self._check_market(now))
        issues.extend(self._check_risk(now))
        issues.extend(self._check_macro(now))

        consecutive = self._update_consecutive(previous, issues)
        warn_n = int(self.cfg.get("thresholds", {}).get("warn_consecutive", 2))
        critical_n = int(
            self.cfg.get("thresholds", {}).get("critical_consecutive", 4)
        )

        for issue in issues:
            key = f"{issue['component']}:{issue['code']}"
            count = consecutive.get(key, 0)
            issue["consecutive"] = str(count)
            if issue["severity"] == "WARN" and count >= critical_n:
                issue["severity"] = "CRITICAL"
            elif issue["severity"] == "WARN" and count < warn_n:
                issue["severity"] = "NOTICE"

        order = {"OK": 0, "INFO": 1, "NOTICE": 2, "WARN": 3, "CRITICAL": 4}
        overall = "OK"
        for issue in issues:
            if order.get(issue["severity"], 0) > order.get(overall, 0):
                overall = issue["severity"]

        latest = {
            "generated_at": now.isoformat(),
            "status": overall,
            "issue_count": len(issues),
            "issues": issues,
            "consecutive": consecutive,
        }
        _write_json(self.latest_path, latest)
        _write_json(
            self.state_path,
            {
                "last_checked_at": now.isoformat(),
                "status": overall,
                "consecutive": consecutive,
            },
        )
        return latest
