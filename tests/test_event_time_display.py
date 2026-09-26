from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "site" / "기능.js"
INDEX = ROOT / "site" / "index.html"
GLOBAL = ROOT / "site" / "글로벌리스크.html"


def _event_helpers_source() -> str:
    text = JS.read_text(encoding="utf-8")
    match = re.search(
        r"(function kstDateParts\(value\) \{[\s\S]+?function eventCard\(event\) \{[\s\S]+?\n\})\nfunction issueTemporalLabel",
        text,
    )
    assert match, "일정 시간 helper를 찾지 못함"
    return match.group(1)


def _run_event_timing(event: dict, now: str) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    source = _event_helpers_source()
    script = (
        "function esc(v=''){return String(v);}\n"
        + source
        + "\nconst out=eventTiming("
        + json.dumps(event, ensure_ascii=False)
        + ", new Date("
        + json.dumps(now)
        + ").getTime());\nconsole.log(JSON.stringify(out));"
    )
    result = subprocess.run(
        [node, "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("2026-10-15T21:06:00+09:00", "D-19 · 19일 5시간 남음"),
        ("2026-09-27T17:00:00+09:00", "D-1 · 1일 1시간 남음"),
        ("2026-09-27T15:00:00+09:00", "D-DAY · 23시간 남음"),
        ("2026-09-26T16:30:00+09:00", "D-DAY · 30분 남음"),
    ],
)
def test_event_countdown_is_human_readable(target: str, expected: str):
    out = _run_event_timing(
        {"datetime_kst": target, "time_unknown": False},
        "2026-09-26T16:00:00+09:00",
    )
    assert out["countdown"] == expected


def test_past_event_never_shows_negative_hours():
    out = _run_event_timing(
        {"datetime_kst": "2026-09-26T14:00:00+09:00", "time_unknown": False},
        "2026-09-26T16:00:00+09:00",
    )
    assert out["countdown"] == "종료 · 2시간 전"
    assert "-" not in out["countdown"].replace("종료", "")


def test_unknown_time_keeps_date_without_inventing_clock_time():
    out = _run_event_timing(
        {"date_kst": "2026-10-22", "time_unknown": True, "time_status": "unknown"},
        "2026-09-26T16:00:00+09:00",
    )
    assert "10월 22일" in out["dateLabel"]
    assert "시간 미확정" in out["dateLabel"]
    assert "D-26" in out["countdown"]


def test_missing_date_is_safe():
    out = _run_event_timing({}, "2026-09-26T16:00:00+09:00")
    assert out["valid"] is False
    assert out["dateLabel"] == "일정 시각 확인 중"
    assert out["countdown"] == "일정 시각 확인 중"


def test_both_dashboard_pages_use_same_risk_event_renderer():
    for path in (INDEX, GLOBAL):
        html = path.read_text(encoding="utf-8")
        assert 'id="risk-events"' in html
        assert '<script src="기능.js"></script>' in html


def test_raw_decimal_hour_after_text_is_removed():
    js = JS.read_text(encoding="utf-8")
    assert 'toFixed(1)+"시간 후"' not in js
    assert '"시간 후"' not in js
