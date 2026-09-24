from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import load_prompt, load_yaml, render_prompt
from .llm import ResearchLLM
from .market_stats import number


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


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


def _age_minutes(path: Path, now: datetime) -> float | None:
    data = _read_json(path)
    stamp = _parse_iso(
        str(data.get("captured_at") or data.get("generated_at") or "")
    )
    if stamp is None:
        return None
    return max(0.0, (now - stamp).total_seconds() / 60.0)


def _severity_rank(level: str) -> int:
    return {"LOW": 0, "WATCH": 1, "HIGH": 2, "VETO": 3}.get(level, 0)


def _max_level(*levels: str) -> str:
    return max(levels, key=_severity_rank) if levels else "LOW"


def _round_value(value: Any, unit: float) -> float | None:
    if value in (None, ""):
        return None
    n = number(value)
    if unit <= 0:
        return n
    return round(n / unit) * unit


class RiskEngine:
    def __init__(self, root: Path, mode: str = "live"):
        if mode not in {"dry-run", "live"}:
            raise ValueError("mode must be dry-run or live")
        self.root = root
        self.mode = mode
        self.cfg = load_yaml(root / "config" / "risk.yaml")
        self.data_cfg = self.cfg.get("data", {})
        self.state_path = root / self.data_cfg.get(
            "state_file", "data/risk/state.json"
        )
        self.latest_path = root / self.data_cfg.get(
            "latest_file", "data/risk/latest.json"
        )
        self.runtime_path = root / self.data_cfg.get(
            "runtime_file", "data/risk/runtime.json"
        )
        self.calendar_path = root / self.data_cfg.get(
            "calendar_file", "data/risk/calendar_live.json"
        )
        self.macro_path = root / self.data_cfg.get(
            "macro_file", "data/macro/current.json"
        )
        self.provider_macro_path = root / self.data_cfg.get(
            "provider_macro_file", "data/macro/provider_current.json"
        )

    def _fallback_calendar(self) -> list[dict[str, Any]]:
        data = load_yaml(self.root / "config" / "events_2026.yaml")
        rows = data.get("events", [])
        return [x for x in rows if isinstance(x, dict)]

    def _calendar_due(self, now: datetime) -> bool:
        hours = float(self.cfg.get("refresh", {}).get("calendar_hours", 12))
        age = _age_minutes(self.calendar_path, now)
        return age is None or age >= hours * 60

    def _macro_due(self, now: datetime) -> bool:
        minutes = float(self.cfg.get("refresh", {}).get("macro_minutes", 10))
        age = _age_minutes(self.macro_path, now)
        return age is None or age >= minutes

    def _valid_calendar_event(self, event: dict[str, Any]) -> bool:
        url = str(event.get("official_url") or "")
        host = (urlparse(url).hostname or "").lower()
        allowed = [
            str(x).lower()
            for x in self.cfg.get("refresh", {}).get(
                "calendar_allowed_domains", []
            )
        ]
        if not host or not any(
            host == domain or host.endswith("." + domain)
            for domain in allowed
        ):
            return False
        if not event.get("id") or not event.get("title"):
            return False
        if not event.get("datetime_kst") and not event.get("date_kst"):
            return False
        severity = int(number(event.get("severity")) or 0)
        return 1 <= severity <= 5

    def _merge_calendar_events(
        self,
        live_events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for event in self._fallback_calendar():
            if self._valid_calendar_event(event):
                merged[str(event["id"])] = dict(event)
        for event in live_events:
            if isinstance(event, dict) and self._valid_calendar_event(event):
                merged[str(event["id"])] = dict(event)
        return list(merged.values())

    def _refresh_calendar(self, now: datetime) -> dict[str, Any]:
        existing = _read_json(self.calendar_path)
        if self.mode == "dry-run":
            result = {
                "generated_at": now.isoformat(),
                "events": self._merge_calendar_events([]),
                "mode": "dry-run",
            }
            _write_json(self.calendar_path, result)
            return result

        if not self._calendar_due(now) and existing.get("events"):
            return existing

        cfg = self.cfg.get("models", {}).get("source", {})
        llm = ResearchLLM(cfg)
        prompt = render_prompt(
            load_prompt(self.root, "리스크일정_갱신.md"),
            {
                "NOW": now.isoformat(),
                "EXISTING": json.dumps(
                    existing or {"events": self._fallback_calendar()},
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        )
        try:
            result = llm.request_json(prompt, web=True, model_cfg=cfg)
            if not isinstance(result.get("events"), list):
                raise ValueError("events가 배열이 아님")
            result["events"] = self._merge_calendar_events(result["events"])
            result["generated_at"] = str(
                result.get("generated_at") or now.isoformat()
            )
            _write_json(self.calendar_path, result)
            return result
        except Exception as exc:
            fallback = existing if existing.get("events") else {
                "generated_at": now.isoformat(),
                "events": self._fallback_calendar(),
            }
            fallback["refresh_error"] = str(exc)
            return fallback

    def _provider_macro_is_fresh(self, now: datetime) -> bool:
        max_age = float(self.cfg.get("refresh", {}).get("provider_max_age_minutes", 15))
        age = _age_minutes(self.provider_macro_path, now)
        return age is not None and age <= max_age

    def _refresh_macro(self, now: datetime) -> dict[str, Any]:
        if self.mode == "dry-run":
            result = {
                "captured_at": now.isoformat(),
                "values": {
                    "nasdaq100_pct": -0.25,
                    "nasdaq_futures_pct": -0.35,
                    "sp500_pct": -0.15,
                    "sp500_futures_pct": -0.2,
                    "us2y_yield": 3.8,
                    "us2y_change_bp": 3,
                    "us10y_yield": 4.15,
                    "us10y_change_bp": 5,
                    "korea3y_yield": 2.9,
                    "korea3y_change_bp": 1,
                    "korea10y_yield": 3.2,
                    "korea10y_change_bp": 2,
                    "dxy_pct": 0.2,
                    "usdkrw_pct": 0.25,
                    "usdcnh_pct": 0.1,
                    "vix_pct": 4,
                    "kospi200_futures_pct": 0.1,
                    "kospi200_night_futures_pct": None,
                    "sox_pct": 0.3,
                    "nikkei225_pct": 0.2,
                    "hang_seng_pct": -0.1,
                    "china_a50_futures_pct": -0.2,
                    "wti_pct": 0.4,
                    "copper_pct": 0.3,
                    "gold_pct": 0.1,
                    "bitcoin_pct": 0.8,
                },
                "sources": [],
                "unknowns": ["dry-run 합성값"],
                "source_mode": "synthetic",
            }
            _write_json(self.macro_path, result)
            return result

        if self._provider_macro_is_fresh(now):
            provider = _read_json(self.provider_macro_path)
            provider["source_mode"] = str(
                provider.get("source_mode") or "provider"
            )
            _write_json(self.macro_path, provider)
            return provider

        existing = _read_json(self.macro_path)
        if not self._macro_due(now) and existing.get("values"):
            return existing

        cfg = self.cfg.get("models", {}).get("source", {})
        llm = ResearchLLM(cfg)
        prompt = render_prompt(
            load_prompt(self.root, "매크로_갱신.md"),
            {"NOW": now.isoformat()},
        )
        try:
            result = llm.request_json(prompt, web=True, model_cfg=cfg)
            result["captured_at"] = str(
                result.get("captured_at") or now.isoformat()
            )
            result["source_mode"] = "web_fallback"
            _write_json(self.macro_path, result)
            return result
        except Exception as exc:
            if existing.get("values"):
                existing["refresh_error"] = str(exc)
                return existing
            return {
                "captured_at": now.isoformat(),
                "values": {},
                "sources": [],
                "unknowns": ["매크로 갱신 실패"],
                "refresh_error": str(exc),
                "source_mode": "unavailable",
            }

    def _event_datetime(self, event: dict[str, Any]) -> tuple[datetime | None, bool]:
        confirmed = _parse_iso(str(event.get("datetime_kst") or ""))
        if confirmed is not None:
            return confirmed, False
        date_value = str(event.get("date_kst") or "")
        if not date_value:
            return None, True
        try:
            day = datetime.strptime(date_value, "%Y-%m-%d")
        except ValueError:
            return None, True
        # 시간이 미확정인 고충격 일정은 장 시작 시점 기준으로 보수적 근사한다.
        return day.replace(hour=9, minute=0, tzinfo=KST), True

    def _event_state(
        self,
        now: datetime,
        calendar: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], str, dict[str, Any] | None]:
        risk_cfg = self.cfg.get("risk", {})
        veto_hours = float(risk_cfg.get("veto_event_hours", 12))
        high_hours = float(risk_cfg.get("high_event_hours", 24))
        watch_hours = float(risk_cfg.get("watch_event_hours", 72))
        veto_severity = int(risk_cfg.get("veto_single_event_severity", 5))

        upcoming: list[dict[str, Any]] = []
        level = "LOW"
        biggest: dict[str, Any] | None = None

        for raw in calendar.get("events", []):
            if not isinstance(raw, dict):
                continue
            event_dt, time_unknown = self._event_datetime(raw)
            if event_dt is None:
                continue
            hours = (event_dt - now).total_seconds() / 3600.0
            if hours < -6 or hours > 24 * 45:
                continue

            severity = int(number(raw.get("severity")) or 1)
            phase = "FUTURE"
            event_level = "LOW"
            if hours < 0:
                phase = "POST_EVENT"
                event_level = "WATCH" if severity >= 4 else "LOW"
            elif hours <= veto_hours and severity >= veto_severity:
                phase = "VETO_WINDOW"
                event_level = "VETO"
            elif hours <= high_hours and severity >= 4:
                phase = "HIGH_WINDOW"
                event_level = "HIGH"
            elif hours <= watch_hours and severity >= 3:
                phase = "WATCH_WINDOW"
                event_level = "WATCH"

            if time_unknown and 0 <= hours <= high_hours and severity >= 5:
                event_level = _max_level(event_level, "HIGH")

            nxt_close = str(risk_cfg.get("nxt_close", "20:00"))
            krx_close = str(risk_cfg.get("krx_close", "15:30"))
            event_hhmm = event_dt.strftime("%H:%M")
            if time_unknown:
                trade_window = "UNKNOWN_TIME"
            elif event_hhmm > nxt_close:
                trade_window = "AFTER_NXT_CLOSE"
            elif event_hhmm > krx_close:
                trade_window = "AFTER_KRX_BEFORE_NXT_CLOSE"
            else:
                trade_window = "KOREA_TRADING_HOURS"

            item = dict(raw)
            item.update(
                {
                    "resolved_datetime_kst": event_dt.isoformat(),
                    "time_unknown": time_unknown,
                    "hours_to_event": round(hours, 2),
                    "phase": phase,
                    "risk_level": event_level,
                    "trade_window": trade_window,
                }
            )
            upcoming.append(item)
            level = _max_level(level, event_level)

            if biggest is None or (
                _severity_rank(event_level),
                severity,
                -abs(hours),
            ) > (
                _severity_rank(str(biggest.get("risk_level") or "LOW")),
                int(number(biggest.get("severity")) or 0),
                -abs(float(biggest.get("hours_to_event") or 99999)),
            ):
                biggest = item

        upcoming.sort(key=lambda x: float(x.get("hours_to_event") or 999999))
        return upcoming, level, biggest

    def _macro_state(
        self,
        macro: dict[str, Any],
    ) -> tuple[str, list[dict[str, Any]]]:
        values = macro.get("values", {})
        thresholds = self.cfg.get("macro_thresholds", {})
        signals: list[dict[str, Any]] = []
        level = "LOW"

        negative_fields = {
            "nasdaq_futures_pct",
            "sp500_futures_pct",
            "kospi200_futures_pct",
            "kospi200_night_futures_pct",
            "sox_pct",
        }

        for field, rule in thresholds.items():
            value = values.get(field)
            if value in (None, ""):
                continue
            n = number(value)
            field_level = "LOW"
            if field in negative_fields:
                if n <= float(rule.get("veto", -999)):
                    field_level = "VETO"
                elif n <= float(rule.get("high", -999)):
                    field_level = "HIGH"
                elif n <= float(rule.get("watch", -999)):
                    field_level = "WATCH"
            else:
                if n >= float(rule.get("veto", 999)):
                    field_level = "VETO"
                elif n >= float(rule.get("high", 999)):
                    field_level = "HIGH"
                elif n >= float(rule.get("watch", 999)):
                    field_level = "WATCH"

            if field_level != "LOW":
                signals.append(
                    {
                        "field": field,
                        "value": n,
                        "risk_level": field_level,
                    }
                )
                level = _max_level(level, field_level)

        return level, signals

    def _market_state(self) -> dict[str, Any]:
        market = _read_json(self.root / "data" / "market" / "latest.json")
        source = market.get("source", {})
        quantitative = market.get("quantitative", {})
        overview = source.get("market_overview", {})
        return {
            "generated_at": market.get("generated_at"),
            "regime": (market.get("interpretation") or {}).get("regime_name"),
            "one_line": (market.get("interpretation") or {}).get("one_line"),
            "kospi": overview.get("KOSPI"),
            "kosdaq": overview.get("KOSDAQ"),
            "turnover_rank_top10_share": source.get("turnover_rank_top10_share"),
            "recent_listings": quantitative.get("recent_listings"),
            "coflow_groups": quantitative.get("coflow_groups", [])[:5],
        }

    def _logic_hashes(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for rel in self.cfg.get("dirty_state", {}).get("logic_files", []):
            path = self.root / str(rel)
            try:
                content = path.read_bytes()
            except OSError:
                result[str(rel)] = "missing"
                continue
            result[str(rel)] = hashlib.sha256(content).hexdigest()
        return result

    def _semantic_payload(
        self,
        event_level: str,
        biggest: dict[str, Any] | None,
        events: list[dict[str, Any]],
        macro: dict[str, Any],
        macro_level: str,
        macro_signals: list[dict[str, Any]],
        market: dict[str, Any],
    ) -> dict[str, Any]:
        rounding = self.cfg.get("dirty_state", {}).get("semantic_rounding", {})
        pct_unit = float(rounding.get("percent", 0.1))
        bp_unit = float(rounding.get("yield_bp", 2.0))
        values = macro.get("values", {})
        rounded_macro = {}
        for key, value in values.items():
            unit = bp_unit if key.endswith("_change_bp") else pct_unit
            rounded_macro[key] = _round_value(value, unit)

        return {
            "logic_hashes": self._logic_hashes(),
            "event_level": event_level,
            "next_event": {
                "id": biggest.get("id") if biggest else None,
                "phase": biggest.get("phase") if biggest else None,
                "trade_window": biggest.get("trade_window") if biggest else None,
            },
            "event_phases": [
                {
                    "id": x.get("id"),
                    "phase": x.get("phase"),
                    "risk_level": x.get("risk_level"),
                }
                for x in events[:8]
            ],
            "macro_level": macro_level,
            "macro": rounded_macro,
            "macro_signals": macro_signals,
            "market": {
                "regime": market.get("regime"),
                "kospi_change": (market.get("kospi") or {}).get("change_pct"),
                "kosdaq_change": (market.get("kosdaq") or {}).get("change_pct"),
                "top10_share": market.get("turnover_rank_top10_share"),
                "coflow_groups": [
                    x.get("group") for x in market.get("coflow_groups", [])
                ],
            },
        }

    @staticmethod
    def _hash(payload: dict[str, Any]) -> str:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _force_due(self, now: datetime, state: dict[str, Any]) -> bool:
        last = _parse_iso(str(state.get("last_evaluated_at") or ""))
        if last is None:
            return True
        hours = float(self.cfg.get("refresh", {}).get("force_evaluation_hours", 6))
        return (now - last).total_seconds() >= hours * 3600

    def _deterministic_summary(
        self,
        risk_level: str,
        biggest: dict[str, Any] | None,
        macro_signals: list[dict[str, Any]],
    ) -> dict[str, Any]:
        reasons = []
        if biggest and biggest.get("risk_level") in {"HIGH", "VETO"}:
            reasons.append(
                f"{biggest.get('title')} · {biggest.get('phase')} · "
                f"{biggest.get('trade_window')}"
            )
        reasons.extend(
            f"{x.get('field')}={x.get('value')} ({x.get('risk_level')})"
            for x in macro_signals
            if x.get("risk_level") in {"HIGH", "VETO"}
        )
        return {
            "risk_level": risk_level,
            "single_biggest_risk": {
                "title": biggest.get("title") if biggest else "확인된 단일 이벤트 없음",
                "why": (
                    f"{biggest.get('hours_to_event')}시간 후 · "
                    f"{biggest.get('trade_window')}"
                    if biggest
                    else "고충격 일정 없음"
                ),
                "severity": biggest.get("severity") if biggest else 0,
            },
            "summary": (
                "고충격 일정 또는 매크로 스트레스가 확인됨."
                if risk_level in {"HIGH", "VETO"}
                else "현재 확인 가능한 입력 기준 대형 Overnight Risk는 제한적."
            ),
            "veto_reasons": reasons if risk_level == "VETO" else [],
            "supportive_factors": [],
            "conflicting_signals": [],
            "unknowns": [],
            "next_check": (
                biggest.get("resolved_datetime_kst") if biggest else "다음 10분 Tick"
            ),
        }

    def _evaluate(
        self,
        now: datetime,
        state: dict[str, Any],
        dirty: bool,
    ) -> dict[str, Any]:
        cfg = self.cfg.get("models", {}).get("evaluator", {})
        if self.mode == "dry-run":
            return self._deterministic_summary(
                state["risk_level"],
                state.get("single_biggest_event"),
                state.get("macro_signals", []),
            )

        if not dirty:
            previous = _read_json(self.latest_path)
            previous_eval = previous.get("evaluation")
            if isinstance(previous_eval, dict):
                return previous_eval

        llm = ResearchLLM(cfg)
        prompt = render_prompt(
            load_prompt(self.root, "리스크_평가.md"),
            {
                "NOW": now.isoformat(),
                "RISK_STATE": json.dumps(state, ensure_ascii=False, indent=2),
                "MARKET": json.dumps(state.get("market"), ensure_ascii=False, indent=2),
                "MACRO": json.dumps(state.get("macro"), ensure_ascii=False, indent=2),
                "EVENTS": json.dumps(
                    state.get("upcoming_events"),
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        )
        try:
            result = llm.request_json(prompt, web=False, model_cfg=cfg)
            result["risk_level"] = _max_level(
                str(result.get("risk_level") or "LOW"),
                str(state.get("risk_level") or "LOW"),
            )
            return result
        except Exception:
            return self._deterministic_summary(
                state["risk_level"],
                state.get("single_biggest_event"),
                state.get("macro_signals", []),
            )

    def _render_report(self, result: dict[str, Any]) -> str:
        evaluation = result.get("evaluation", {})
        lines = [
            "# 종가베팅 Overnight Risk",
            "",
            f"> 생성: {result.get('generated_at')}",
            f"> 의미 상태 변경: {'예' if result.get('dirty') else '아니오'}",
            f"> Risk Level: **{evaluation.get('risk_level', result.get('risk_level', 'LOW'))}**",
            "",
            "## 핵심 판단",
            "",
            str(evaluation.get("summary") or ""),
            "",
            "## 가장 큰 단일 리스크",
            "",
        ]
        biggest = evaluation.get("single_biggest_risk") or {}
        lines.append(
            f"- **{biggest.get('title', '없음')}** · severity {biggest.get('severity', 0)}"
        )
        lines.append(f"- {biggest.get('why', '')}")

        lines.extend(["", "## 예정 이벤트", ""])
        events = result.get("upcoming_events", [])
        if events:
            lines.extend(
                [
                    "| 일정 | 남은 시간 | 중요도 | 위험 단계 | 거래 가능성 관점 |",
                    "|---|---:|---:|---|---|",
                ]
            )
            for event in events[:10]:
                lines.append(
                    f"| {event.get('title')} | {event.get('hours_to_event')}h | "
                    f"{event.get('severity')} | {event.get('risk_level')} | "
                    f"{event.get('trade_window')} |"
                )
        else:
            lines.append("- 45일 내 확인된 주요 일정 없음")

        lines.extend(["", "## 매크로 경고", ""])
        signals = result.get("macro_signals", [])
        if signals:
            for item in signals:
                lines.append(
                    f"- {item.get('field')}: {item.get('value')} · {item.get('risk_level')}"
                )
        else:
            lines.append("- 현재 임계값을 넘은 매크로 경고 없음")

        unknowns = evaluation.get("unknowns") or []
        lines.extend(["", "## 미확인", ""])
        if unknowns:
            lines.extend(f"- {x}" for x in unknowns)
        else:
            lines.append("- 별도 미확인 항목 없음")

        lines.extend(
            [
                "",
                "## 다음 확인",
                "",
                f"- {evaluation.get('next_check') or '다음 10분 Tick'}",
                "",
                "---",
                "Risk Veto는 매수·매도 추천이 아니라 다음날 갭 리스크 연구용 상태입니다.",
                "",
            ]
        )
        return "\n".join(lines)

    def _enrich_close_events(
        self,
        now: datetime,
        result: dict[str, Any],
    ) -> int:
        path = self.root / "data" / "market" / "stats" / "close_bet_events.csv"
        if not path.exists():
            return 0
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                fieldnames = list(reader.fieldnames or [])
                rows = list(reader)
        except OSError:
            return 0

        extra = [
            "risk_level_latest",
            "overnight_max_risk_level",
            "overnight_risk_hash",
            "overnight_biggest_risk",
            "overnight_event_level",
            "overnight_macro_level",
            "risk_last_updated_at",
        ]
        for field in extra:
            if field not in fieldnames:
                fieldnames.append(field)

        today = now.strftime("%Y-%m-%d")
        current = str(
            (result.get("evaluation") or {}).get("risk_level")
            or result.get("risk_level")
            or "LOW"
        )
        biggest = (
            (result.get("evaluation") or {})
            .get("single_biggest_risk", {})
            .get("title", "")
        )
        changed = 0

        for row in rows:
            if str(row.get("signal_date") or "") != today:
                continue
            old_max = str(row.get("overnight_max_risk_level") or "LOW")
            max_level = _max_level(old_max, current)
            row["risk_level_latest"] = current
            row["overnight_max_risk_level"] = max_level
            row["overnight_risk_hash"] = result.get("semantic_hash", "")
            row["overnight_biggest_risk"] = biggest
            row["overnight_event_level"] = result.get("event_risk_level", "")
            row["overnight_macro_level"] = result.get("macro_risk_level", "")
            row["risk_last_updated_at"] = now.isoformat()
            changed += 1

        if not changed:
            return 0

        temp = path.with_suffix(path.suffix + ".risk.tmp")
        with temp.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=fieldnames,
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(rows)
        temp.replace(path)
        return changed

    def run(self) -> dict[str, Any]:
        now = datetime.now(KST)
        calendar = self._refresh_calendar(now)
        macro = self._refresh_macro(now)
        market = self._market_state()

        upcoming, event_level, biggest = self._event_state(now, calendar)
        macro_level, macro_signals = self._macro_state(macro)
        risk_level = _max_level(event_level, macro_level)

        semantic = self._semantic_payload(
            event_level,
            biggest,
            upcoming,
            macro,
            macro_level,
            macro_signals,
            market,
        )
        semantic_hash = self._hash(semantic)
        previous_state = _read_json(self.state_path)
        dirty = (
            semantic_hash != previous_state.get("semantic_hash")
            or self._force_due(now, previous_state)
        )

        state = {
            "generated_at": now.isoformat(),
            "risk_level": risk_level,
            "event_risk_level": event_level,
            "macro_risk_level": macro_level,
            "single_biggest_event": biggest,
            "upcoming_events": upcoming,
            "macro": macro,
            "macro_signals": macro_signals,
            "market": market,
            "semantic": semantic,
            "semantic_hash": semantic_hash,
        }
        evaluation = self._evaluate(now, state, dirty)
        result = dict(state)
        result["dirty"] = dirty
        result["evaluation"] = evaluation

        _write_json(self.latest_path, result)
        _write_json(
            self.runtime_path,
            {
                "generated_at": now.isoformat(),
                "dirty": dirty,
                "semantic_hash": semantic_hash,
                "previous_hash": previous_state.get("semantic_hash"),
                "evaluation_called": dirty,
                "calendar_source": (
                    "live" if self.calendar_path.exists() else "fallback"
                ),
                "macro_source": macro.get("source_mode"),
            },
        )
        enriched_close_events = self._enrich_close_events(now, result)

        _write_json(
            self.state_path,
            {
                "semantic_hash": semantic_hash,
                "last_seen_at": now.isoformat(),
                "last_evaluated_at": (
                    now.isoformat()
                    if dirty
                    else previous_state.get("last_evaluated_at")
                ),
                "risk_level": evaluation.get("risk_level", risk_level),
            },
        )

        if dirty:
            report_dir = self.root / self.data_cfg.get(
                "report_dir", "reports/risk"
            )
            report_dir.mkdir(parents=True, exist_ok=True)
            report = report_dir / (now.strftime("%Y%m%d-%H%M") + ".md")
            report.write_text(self._render_report(result), encoding="utf-8")
            result["report"] = str(report.relative_to(self.root))

        return {
            "risk_level": evaluation.get("risk_level", risk_level),
            "dirty": dirty,
            "semantic_hash": semantic_hash,
            "report": result.get("report"),
            "next_event": biggest.get("title") if biggest else None,
            "macro_source": macro.get("source_mode"),
            "enriched_close_events": enriched_close_events,
        }
