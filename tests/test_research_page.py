from __future__ import annotations

import runpy
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RESEARCH_HTML = ROOT / "site" / "리서치.html"
DASHBOARD_JS = ROOT / "site" / "기능.js"
DASHBOARD_SCRIPT = ROOT / "scripts" / "대시보드_생성.py"


def test_research_sections_are_in_requested_order():
    html = RESEARCH_HTML.read_text(encoding="utf-8")
    headings = [
        "최근 인기 증권 리포트 30개",
        "최신 AI 심층 리서치",
        "시장 이슈 관련 리서치",
        "새 공시",
        "프로젝트 최근 리포트",
        "리서치 입력 소스 상태",
    ]
    positions = [html.index(title) for title in headings]
    assert positions == sorted(positions)


def test_research_page_uses_expandable_cards():
    html = RESEARCH_HTML.read_text(encoding="utf-8")
    js = DASHBOARD_JS.read_text(encoding="utf-8")
    assert 'id="popular-report-list"' in html
    assert 'id="supervisor-research"' in html
    assert 'id="recent-reports"' in html
    assert "research-detail" in js
    assert "<details" in js
    assert "상세 데이터 미수집" in js


def test_research_rendering_guards_variable_data_shapes():
    js = DASHBOARD_JS.read_text(encoding="utf-8")
    assert "function asArray(value)" in js
    assert "function asObject(value)" in js
    for expression in (
        "asArray(popular.items)",
        "asArray(data.reports)",
        "asArray(supervisor.summary)",
        "asArray(supervisor.market_focus)",
        "asArray(discovery.new_dart_filings)",
    ):
        assert expression in js


def test_recent_project_reports_are_sorted_latest_first_and_embed_recent_content():
    namespace = runpy.run_path(str(DASHBOARD_SCRIPT))
    reports = namespace["recent_reports"](limit=15)
    keys = [item.get("sort_at") or "" for item in reports]
    assert keys == sorted(keys, reverse=True)
    if reports:
        assert isinstance(reports[0].get("content"), str)
        assert reports[0]["content"].strip()


def test_dashboard_javascript_syntax():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    result = subprocess.run(
        [node, "--check", str(DASHBOARD_JS)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
