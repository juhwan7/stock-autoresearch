from autoresearch.market_discovery import (
    build_dynamic_handoff_queries,
    extract_naver_index_basic,
    extract_naver_indices,
    extract_trending_terms,
    is_low_quality_news_item,
    parse_google_news_rss,
    recent_items,
    summarize_toss_market,
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
    assert rows[0]["title"] == "반도체 뉴스"
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


def test_summarize_toss_market_exposes_turnover_and_burst(tmp_path):
    path = tmp_path / "data/providers/toss/latest.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        """{
          "captured_at": "2026-09-25T10:00:00+09:00",
          "ranking": [
            {"rank": 1, "ticker": "000001", "trading_value": 10000000000, "day_return_pct": 8.0, "last_price": 10000}
          ],
          "metadata": {"000001": {"name": "테스트조선"}},
          "minute_by_ticker": {
            "000001": [
              {"amount": 100000000},
              {"amount": 120000000},
              {"amount": 500000000}
            ]
          },
          "turnover_rank_top10_share": 0.42
        }""",
        encoding="utf-8",
    )
    result = summarize_toss_market(tmp_path)
    assert result["available"] is True
    assert result["top_turnover"][0]["name"] == "테스트조선"
    assert result["minute_burst_leaders"][0]["burst_ratio"] > 1


def test_google_news_parser_strips_publisher_suffix():
    xml = """<?xml version="1.0"?>
    <rss><channel>
      <item>
        <title>조선 수주 확대 - 연합뉴스</title>
        <link>https://example.com/a</link>
        <pubDate>Fri, 25 Sep 2026 00:30:00 GMT</pubDate>
        <source>연합뉴스</source>
      </item>
    </channel></rss>
    """
    rows = parse_google_news_rss(xml, "kr_market_broad")
    assert rows[0]["title"] == "조선 수주 확대"


def test_recent_items_drops_stale_articles():
    from datetime import datetime, timezone

    items = [
        {"title": "최신", "published_at": "Fri, 25 Sep 2026 00:30:00 GMT"},
        {"title": "오래됨", "published_at": "Mon, 10 Aug 2026 00:00:00 GMT"},
    ]
    now = datetime(2026, 9, 25, 1, 0, tzinfo=timezone.utc)
    result = recent_items(items, now, hours=36)
    assert [item["title"] for item in result] == ["최신"]


def test_extract_naver_index_basic_from_new_json_shape():
    assert extract_naver_index_basic({"closePrice": "3,421.55"}) == "3,421.55"
    assert extract_naver_index_basic({"close": 842.1}) == "842.1"
    assert extract_naver_index_basic({}) is None


def test_google_news_parser_filters_obvious_gambling_spam():
    xml = """<?xml version="1.0"?>
    <rss><channel>
      <item>
        <title>처음 읽는 게임 정보에서 찾을 카지노 핵심 내용 - 스팸매체</title>
        <link>https://example.com/spam</link>
        <pubDate>Fri, 25 Sep 2026 00:30:00 GMT</pubDate>
        <source>스팸매체</source>
      </item>
      <item>
        <title>한미 정상회담에서 전략투자 논의 - 연합뉴스</title>
        <link>https://example.com/real</link>
        <pubDate>Fri, 25 Sep 2026 00:31:00 GMT</pubDate>
        <source>연합뉴스</source>
      </item>
    </channel></rss>
    """
    rows = parse_google_news_rss(xml, "kr_diplomacy_summit")
    assert [row["title"] for row in rows] == ["한미 정상회담에서 전략투자 논의"]


def test_low_quality_title_filter_covers_common_gambling_spam():
    assert is_low_quality_news_item("바카라 유출 정보", "낯선매체") is True
    assert is_low_quality_news_item("미중 정상회담 무역휴전 연장", "연합뉴스") is False
