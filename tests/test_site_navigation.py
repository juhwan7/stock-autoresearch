from __future__ import annotations

from html.parser import HTMLParser
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


def test_issue_tracker_defaults_to_market_priority_sort():
    html = (SITE / "이슈추적.html").read_text(encoding="utf-8")
    js = (SITE / "기능.js").read_text(encoding="utf-8")
    assert '<option value="priority" selected>' in html
    assert 'let activeSort="priority";' in js
