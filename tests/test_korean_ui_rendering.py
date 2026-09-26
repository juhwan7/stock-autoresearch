from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
JS = SITE / "기능.js"
LATEST = ROOT / "data" / "supervisor" / "latest-report.json"

ALLOWED_ACRONYMS = {
    "AI", "DART", "NXT", "KOSPI", "KOSDAQ", "NASDAQ", "S&P", "CPI", "FOMC", "USTR",
}


def _strip_allowed_acronyms(text: str) -> str:
    result = text
    for token in ALLOWED_ACRONYMS:
        result = result.replace(token, "")
    return result


def test_user_facing_headings_are_korean_first():
    pattern = re.compile(r'<p class="(?:eyebrow|kicker)">([^<]+)</p>')
    offenders: list[tuple[str, str]] = []
    for path in SITE.glob("*.html"):
        html = path.read_text(encoding="utf-8")
        for heading in pattern.findall(html):
            check = _strip_allowed_acronyms(heading)
            if re.search(r"[A-Za-z]{3,}", check) and not re.search(r"[가-힣]", check):
                offenders.append((path.name, heading))
    assert not offenders, f"영문 UI 소제목이 남아 있음: {offenders}"


def test_no_raw_object_fallback_in_user_renderer():
    js = JS.read_text(encoding="utf-8")
    assert "[object Object]" not in js
    assert "JSON.stringify(item)" not in js
    assert "JSON.stringify(v)" not in js
    assert "function displayStatusLabel" in js
    assert "function displayText" in js
    assert "function humanizeObject" in js
    assert "세부 내용을 구조화해 표시할 수 없습니다." in js


def test_known_raw_statuses_are_not_directly_exposed():
    js = JS.read_text(encoding="utf-8")
    forbidden = [
        'setText("supervisor-status", supervisor.status',
        "TOSS LIVE",
        "KIWOOM FALLBACK",
        '"STALE · "',
        '["Toss Snapshot"',
        "빈 값을 LOW로 해석하지 않습니다.",
    ]
    for token in forbidden:
        assert token not in js, f"사용자 화면에 원시 상태/영문 문구가 남아 있음: {token}"


def test_all_static_pages_do_not_embed_object_artifacts():
    for path in SITE.glob("*.html"):
        html = path.read_text(encoding="utf-8")
        assert "[object Object]" not in html
        assert '{"status":' not in html
        assert '{"type":' not in html


def test_actual_supervisor_objects_render_without_json_or_internal_tokens():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    script = r"""
const fs = require("fs");
const path = process.argv[1];
const latestPath = process.argv[2];
const code = fs.readFileSync(path, "utf8");
const prefix = code.split("function sessionCard")[0];
eval(prefix);
const data = JSON.parse(fs.readFileSync(latestPath, "utf8"));
const fields = [
  "actions", "market_focus", "project_improvement_signals", "work_axes_reviewed",
  "feedback_received", "feedback_resolved", "feedback_disagreed", "feedback_deferred",
  "supervisor_disagreements", "feedback_to_other_supervisor", "next_checks"
];
const values = [];
for (const field of fields) {
  for (const item of asArray(data[field])) values.push(readableItem(item));
}
values.push(readableItem({type:"sensor_root_cause", status:"investigating", detail:"센서 저장 충돌 가능성"}));
values.push(readableItem({axis:"ui_ux", status:"no_change", finding:"화면 추가 불필요"}));
values.push(readableItem({id:"internal-id", status:"verification_pending", signal:"다음 관측에서 확인"}));
console.log(JSON.stringify(values));
"""
    result = subprocess.run(
        [node, "-e", script, str(JS), str(LATEST)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    values = json.loads(result.stdout.strip())
    joined = "\n".join(values)
    assert "[object Object]" not in joined
    assert '{"' not in joined
    assert "sensor_root_cause" not in joined
    assert "verification_pending" not in joined
    assert "no_change" not in joined
    assert "investigating" not in joined
    assert "조사 중" in joined
    assert "검증 대기" in joined
    assert "변화 없음" in joined


def test_issue_detail_does_not_stringify_unknown_fact_objects():
    js = JS.read_text(encoding="utf-8")
    assert "v.text||v.claim||JSON.stringify(v)" not in js
    assert "v.text||JSON.stringify(v)" not in js
    assert "readableItem(v)" in js
