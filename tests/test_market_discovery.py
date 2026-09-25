from autoresearch.market_discovery import (
    build_dynamic_handoff_queries,
    extract_naver_indices,
    extract_trending_terms,
    parse_google_news_rss,
)


def test_parse_google_news_rss():
    xml = """<?xml version="1.0"?>
    <rss><channel>
      <item>
        <title>반도체 뉴스 - 매체A</title>
        <link>https://example.com/a</link>
        <pubDate>Fri, 25 Sep 2026 00:00:00 GMT</pubDate>
        <source>매체A</source>
      </item>
    </channel></rss>
    """
    rows = parse_google_news_rss(xml, "semiconductor_ai")
    assert len(rows) == 1
    assert rows[0]["topic"] == "semiconductor_ai"
    assert rows[0]["title"] == "반도체 뉴스 - 매체A"
    assert rows[0]["publisher"] == "매체A"


def test_extract_naver_indices():
    html = """
    <span id="KOSPI_now">7,123.45</span>
    <span id="KOSDAQ_now">845.67</span>
    <span id="KOSPI200_now">999.01</span>
    """
    result = extract_naver_indices(html)
    assert result["KOSPI"] == "7,123.45"
    assert result["KOSDAQ"] == "845.67"
    assert result["KOSPI200"] == "999.01"


def test_dynamic_trends_are_derived_from_headlines():
    items = [
        {"title": "조선 수주 확대 기대", "publisher": "매체A"},
        {"title": "조선 대형 수주 잇따라", "publisher": "매체B"},
        {"title": "원전 해외 수주 기대", "publisher": "매체C"},
    ]
    trends = extract_trending_terms(items, {})
    assert trends[0]["term"] == "수주" or any(item["term"] == "조선" for item in trends)
    queries = build_dynamic_handoff_queries(trends)
    assert any("조선" in query or "수주" in query for query in queries)
