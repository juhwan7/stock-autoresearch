from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "site" / "index.html"
GLOBAL = ROOT / "site" / "글로벌리스크.html"
SYSTEM = ROOT / "site" / "시스템.html"
JS = ROOT / "site" / "기능.js"
CSS = ROOT / "site" / "스타일.css"
AGENTS = ROOT / "AGENTS.md"


def test_home_prioritizes_context_before_detail():
    html = INDEX.read_text(encoding="utf-8")
    assert html.index("지금 시장을 움직이는 것") < html.index("지금 시장을 움직이는 핵심 이슈")
    assert html.index("지금 시장을 움직이는 핵심 이슈") < html.index("앞으로 시장을 움직일 트리거")
    assert html.index("앞으로 시장을 움직일 트리거") < html.index("현재 주목해야 할 리서치")
    assert html.index("현재 주목해야 할 리서치") < html.index("시장 핵심 숫자")
    assert 'id="risk-events" data-limit="4"' in html
    assert 'data-persist="home-key-numbers"' in html
    assert 'data-persist="home-reading-guide"' in html


def test_global_risk_prioritizes_overnight_and_collapses_secondary_detail():
    html = GLOBAL.read_text(encoding="utf-8")
    assert html.index("오버나잇 리스크 우선순위") < html.index("미국 최근 3거래일")
    assert html.index("다음 중요 일정") < html.index("미국 최근 3거래일")
    assert 'id="risk-events" data-limit="6"' in html
    assert 'data-persist="global-us-sessions"' in html
    assert 'data-persist="global-macro"' in html


def test_system_keeps_health_visible_and_hides_logs_behind_details():
    html = SYSTEM.read_text(encoding="utf-8")
    assert html.index("현재 시스템 이상") < html.index("데이터 공급자 상태")
    assert 'data-persist="system-provider"' in html
    assert 'data-persist="system-regression"' in html
    assert 'data-persist="system-evolution"' in html
    assert 'data-persist="system-decisions"' in html
    assert 'data-persist="system-changelog"' in html
    assert "<details" in html


def test_disclosure_state_is_resilient_and_persistent():
    js = JS.read_text(encoding="utf-8")
    assert "function initPersistentDetails()" in js
    assert 'localStorage.getItem(key)' in js
    assert 'localStorage.setItem(key' in js
    assert 'details[data-persist]' in js
    assert "riskEventsNode.dataset.limit" in js


def test_disclosure_styles_include_mobile_and_focus_treatment():
    css = CSS.read_text(encoding="utf-8")
    assert ".disclosure-panel>summary" in css
    assert ".inline-disclosure>summary" in css
    assert ":focus-visible" in css
    assert "@media(max-width:680px)" in css


def test_supervisor_rules_make_ui_a_first_class_axis():
    agents = AGENTS.read_text(encoding="utf-8")
    assert "docs/UI_UX_자기진화_규칙.md" in agents
    assert "ui_ux" in agents
    assert "details/summary" in agents


def test_dashboard_javascript_syntax():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    result = subprocess.run(
        [node, "--check", str(JS)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
