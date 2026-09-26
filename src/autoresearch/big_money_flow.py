from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

KOFIA_MAIN_URL = "https://freesis.kofia.or.kr/stat/main.do"

METRIC_SPECS = {
    "investor_deposit": {
        "label": "투자자예탁금",
        "unit": "백만원",
        "group": "liquidity",
        "description": "증권계좌에 대기 중인 투자자 예탁금",
    },
    "credit_financing": {
        "label": "신용융자",
        "unit": "백만원",
        "group": "leverage",
        "description": "주식 매수를 위해 사용된 신용융자 잔고",
    },
    "cma_balance": {
        "label": "CMA잔고",
        "unit": "백만원",
        "group": "liquidity",
        "description": "CMA 계좌 잔고",
    },
    "equity_fund_nav": {
        "label": "주식형펀드 순자산",
        "unit": "억원",
        "group": "fund",
        "description": "주식형펀드 순자산",
    },
    "total_fund_nav": {
        "label": "펀드 순자산",
        "unit": "억원",
        "group": "fund",
        "description": "전체 펀드 순자산",
    },
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            value = data.strip()
            if value:
                self.parts.append(value)


def _plain_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return re.sub(r"\s+", " ", " ".join(parser.parts))


def _number(value: str) -> float:
    return float(value.replace(",", ""))


def _reported_date(mmdd: str, today: date) -> str:
    month, day = [int(part) for part in mmdd.split("/")]
    candidate = date(today.year, month, day)
    if candidate > today + timedelta(days=7):
        candidate = date(today.year - 1, month, day)
    return candidate.isoformat()


def _to_eok(value: float, unit: str) -> float:
    if unit == "백만원":
        return value / 100.0
    if unit == "억원":
        return value
    raise ValueError(f"unsupported unit: {unit}")


def parse_kofia_main(html: str, *, today: date | None = None) -> dict[str, dict[str, Any]]:
    today = today or datetime.now(timezone.utc).date()
    text = _plain_text(html)
    parsed: dict[str, dict[str, Any]] = {}

    for key, spec in METRIC_SPECS.items():
        label = re.escape(spec["label"])
        unit = re.escape(spec["unit"])
        pattern = re.compile(
            rf"{label}.{{0,140}}?{unit}\s*\|\s*(\d{{2}}/\d{{2}})\s*"
            rf"([-+]?\d[\d,]*(?:\.\d+)?)\s+"
            rf"([-+]?\d[\d,]*(?:\.\d+)?)\s+"
            rf"([-+]?\d+(?:\.\d+)?)%"
        )
        match = pattern.search(text)
        if not match:
            raise ValueError(f"KOFIA metric not found: {spec['label']}")

        mmdd, raw_value, raw_change, raw_pct = match.groups()
        value = _number(raw_value)
        change = _number(raw_change)
        value_eok = _to_eok(value, spec["unit"])
        change_eok = _to_eok(change, spec["unit"])
        parsed[key] = {
            "label": spec["label"],
            "group": spec["group"],
            "description": spec["description"],
            "reported_date": _reported_date(mmdd, today),
            "reported_unit": spec["unit"],
            "reported_value": value,
            "reported_change": change,
            "change_pct": float(raw_pct),
            "value_krw_100m": round(value_eok, 4),
            "change_krw_100m": round(change_eok, 4),
            "quality": "official_public_summary",
        }

    return parsed


def fetch_kofia_main(timeout: int = 20) -> str:
    request = Request(
        KOFIA_MAIN_URL,
        headers={
            "User-Agent": "Mozilla/5.0 StockAutoResearch/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        body = response.read()
        charset = response.headers.get_content_charset()

    encodings = [charset, "utf-8", "euc-kr", "cp949"]
    for encoding in encodings:
        if not encoding:
            continue
        try:
            return body.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    raise UnicodeDecodeError("utf-8", body, 0, 1, "unable to decode KOFIA page")


def _metric_fingerprint(metrics: dict[str, dict[str, Any]]) -> tuple[tuple[str, str, float], ...]:
    return tuple(
        sorted(
            (
                key,
                str(value.get("reported_date", "")),
                float(value.get("reported_value", 0)),
            )
            for key, value in metrics.items()
        )
    )


def build_payload(
    metrics: dict[str, dict[str, Any]],
    *,
    previous: dict[str, Any] | None = None,
    collected_at: str | None = None,
) -> dict[str, Any]:
    previous = previous or {}
    history = list(previous.get("history") or [])
    current_fingerprint = _metric_fingerprint(metrics)
    previous_metrics = previous.get("metrics") or {}

    if not previous_metrics or _metric_fingerprint(previous_metrics) != current_fingerprint:
        history.append(
            {
                "observed_at": collected_at or datetime.now(timezone.utc).isoformat(),
                "metrics": {
                    key: {
                        "reported_date": item["reported_date"],
                        "value_krw_100m": item["value_krw_100m"],
                        "change_krw_100m": item["change_krw_100m"],
                        "change_pct": item["change_pct"],
                    }
                    for key, item in metrics.items()
                },
            }
        )
    history = history[-365:]

    return {
        "schema_version": 1,
        "updated_at": collected_at or datetime.now(timezone.utc).isoformat(),
        "source": {
            "name": "금융투자협회 자본시장통계 FreeSIS",
            "url": KOFIA_MAIN_URL,
            "status": "official_primary",
            "note": "공개 메인 통계의 최신 발표값을 사용합니다. 지표별 기준일은 서로 다를 수 있습니다.",
        },
        "metrics": metrics,
        "derived": {
            "credit_to_deposit_pct": round(
                metrics["credit_financing"]["value_krw_100m"]
                / metrics["investor_deposit"]["value_krw_100m"]
                * 100,
                2,
            ),
            "equity_fund_share_pct": round(
                metrics["equity_fund_nav"]["value_krw_100m"]
                / metrics["total_fund_nav"]["value_krw_100m"]
                * 100,
                2,
            ),
        },
        "history": history,
        "extensions": [
            {
                "key": "mmf",
                "label": "MMF 규모",
                "status": "adapter_pending",
                "official_path": "펀드 > 주제 > MMF현황 > 기간MMF규모",
                "reason": "공식 통계 항목은 확인했지만 안정적인 자동수집 어댑터를 아직 연결하지 않았습니다.",
            },
            {
                "key": "equity_fund_flow",
                "label": "주식형펀드 자금유출입",
                "status": "adapter_pending",
                "official_path": "펀드 > 설정통계 > 기간자금유출입",
                "reason": "순자산 증감과 실제 자금유입을 분리하기 위해 별도 연결이 필요합니다.",
            },
            {
                "key": "etf",
                "label": "ETF 규모·자금흐름",
                "status": "adapter_pending",
                "official_path": "펀드 > 주제 > ETF현황 > 회사별ETF규모",
                "reason": "ETF 잔고와 순유입을 구분할 수 있는 자동수집 경로를 추가 검증 중입니다.",
            },
            {
                "key": "rp",
                "label": "RP 대고객 잔고",
                "status": "adapter_pending",
                "official_path": "단기자금 > RP > 대고객 종류별 매매잔고",
                "reason": "대기성 단기자금 보조지표로 추가할 예정이며 현재 숫자는 표시하지 않습니다.",
            },
        ],
    }


def collect_to_file(path: str | Path) -> bool:
    output = Path(path)
    previous: dict[str, Any] = {}
    if output.exists():
        try:
            previous = json.loads(output.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            previous = {}

    html = fetch_kofia_main()
    metrics = parse_kofia_main(html)
    fingerprint_before = _metric_fingerprint(previous.get("metrics") or {}) if previous.get("metrics") else None
    fingerprint_after = _metric_fingerprint(metrics)
    if fingerprint_before == fingerprint_after:
        print("KOFIA 거대자금 통계 변화 없음")
        return False

    payload = build_payload(metrics, previous=previous)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"KOFIA 거대자금 통계 갱신: {output}")
    return True
