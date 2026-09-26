from __future__ import annotations

from html.parser import HTMLParser
import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"

EXPECTED_PRIMARY_ORDER = [
    "index.html",
    "이슈추적.html",
    "리서치.html",
    "국내시장.html",
    "글로벌리스크.html",
    "상대강도.html",
    "거대자금.html",
    "시스템.html",
    "AI대화.html",
]

PAGES = {
    "index.html",
    "국내시장.html",
    "거대자금.html",
    "글로벌리스크.html",
    "이슈추적.html",
    "리서치.html",
    "시스템.html",
    "상대강도.html",
    "AI대화.html",
}


class NavigationParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.nav_depth = 0
        self.nav_links: list[tuple[str, set[str]]] = []
        self.all_hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        classes = set(values.get("class", "").split())
        if tag == "nav" and ({"page-tabs", "topbar"} & classes):
            self.nav_depth += 1
        elif tag == "nav" and self.nav_depth:
            self.nav_depth += 1

        if tag == "a":
            href = values.get("href", "")
            if href:
                self.all_hrefs.append(href)
            if self.nav_depth:
                self.nav_links.append((href, set(values.get("class", "").split())))

    def handle_endtag(self, tag: str) -> None:
        if tag == "nav" and self.nav_depth:
            self.nav_depth -= 1


def parse(path: Path) -> NavigationParser:
    parser = NavigationParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


def test_primary_navigation_is_complete_unique_and_active():
    for page_name in PAGES:
        parser = parse(SITE / page_name)
        nav_hrefs = [href for href, _classes in parser.nav_links]

        for target in PAGES:
            assert nav_hrefs.count(target) == 1, (
                f"{page_name}: 상단 메뉴의 {target} 링크가 없거나 중복됨: {nav_hrefs}"
            )

        primary_order = [href for href in nav_hrefs if href in PAGES]
        assert primary_order == EXPECTED_PRIMARY_ORDER, (
            f"{page_name}: 시장 중요도 기준 메뉴 순서가 다름: {primary_order}"
        )

        active = [href for href, classes in parser.nav_links if "active" in classes]
        assert active == [page_name], (
            f"{page_name}: 활성 메뉴가 현재 페이지와 다름: {active}"
        )


def test_all_internal_html_links_point_to_existing_pages():
    for path in SITE.glob("*.html"):
        parser = parse(path)
        for href in parser.all_hrefs:
            parts = urlsplit(href)
            if parts.scheme or parts.netloc or not parts.path.endswith(".html"):
                continue
            target = (path.parent / parts.path).resolve()
            assert target.exists(), f"{path.name}: 존재하지 않는 페이지 링크 {href}"


def test_html_does_not_contain_literal_newline_escape_artifacts():
    for path in SITE.glob("*.html"):
        text = path.read_text(encoding="utf-8")
        assert "\\n" not in text, f"{path.name}: HTML에 문자 그대로 \\n이 남아 있음"


def test_home_market_first_sections_precede_supporting_numbers():
    html = (SITE / "index.html").read_text(encoding="utf-8")
    headings = [
        "지금 시장을 움직이는 핵심 이슈",
        "앞으로 시장을 움직일 트리거",
        "현재 주목해야 할 리서치",
        "시장 핵심 숫자",
    ]
    positions = [html.index(title) for title in headings]
    assert positions == sorted(positions)


def test_issue_tracker_defaults_to_latest_activity_sort():
    html = (SITE / "이슈추적.html").read_text(encoding="utf-8")
    js = (SITE / "기능.js").read_text(encoding="utf-8")
    assert '<option value="updated" selected>최근 변화순</option>' in html
    assert 'let activeSort="updated";' in js
    assert "function issueLatestActivity(issue)" in js
    assert "function compareIssueRecency(a,b)" in js
    assert 'add(x.status_changed_at, "status_changed_at")' in js
    assert 'add(x.last_updated, "last_updated")' in js
    assert 'add(x.first_detected, "first_detected")' in js
    assert 'add(x.event_time, "event_time")' in js
    assert 'asArray(x.history).forEach' in js
    assert 'const activityMs=issueLatestActivityTime(x);' in js
    assert 'if(activeSort==="updated") return compareIssueRecency(a,b);' in js


def test_issue_recency_helpers_cover_recent_status_change_and_bad_timestamps():
    node = shutil.which("node")
    if not node:
        return
    js = (SITE / "기능.js").read_text(encoding="utf-8")
    start = js.index("// ISSUE_RECENCY_HELPERS_START")
    end = js.index("// ISSUE_RECENCY_HELPERS_END")
    helpers = js[start:end]
    script = f"""
function asArray(value) {{
  if (Array.isArray(value)) return value;
  if (value == null || value === "") return [];
  return [value];
}}
{helpers}
const rows = [
  {{issue_id:"old-but-changed", status:"EASING", event_time:"2026-09-21", status_changed_at:"2026-09-27T00:30:00+09:00"}},
  {{issue_id:"new-event", status:"NEW", event_time:"2026-09-26", first_detected:"2026-09-26T20:00:00+09:00"}},
  {{issue_id:"history-newest", status:"ACTIVE", event_time:"2026-09-20", last_updated:"2026-09-26T21:00:00+09:00", history:[{{at:"2026-09-27T00:40:00+09:00"}}]}},
  {{issue_id:"bad-time", status:"RESOLVED", event_time:"not-a-date", last_updated:"also-bad"}},
  {{issue_id:"same-a", status:"ACTIVE", last_updated:"2026-09-26T22:00:00+09:00"}},
  {{issue_id:"same-z", status:"ACTIVE", last_updated:"2026-09-26T22:00:00+09:00"}}
];
const sorted = [...rows].sort(compareIssueRecency).map(x => x.issue_id);
process.stdout.write(JSON.stringify({{
  sorted,
  invalid: issueLatestActivityTime(rows[3]),
  changed: issueLatestActivity(rows[0]).source,
  history: issueLatestActivity(rows[2]).source
}}));
"""
    result = subprocess.run([node, "-e", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["sorted"][:2] == ["history-newest", "old-but-changed"]
    assert payload["sorted"][-1] == "bad-time"
    assert payload["sorted"].index("same-a") < payload["sorted"].index("same-z")
    assert payload["invalid"] == 0
    assert payload["changed"] == "status_changed_at"
    assert payload["history"] == "history.at"
