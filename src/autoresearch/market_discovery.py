from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Any, Callable


KST = timezone(timedelta(hours=9))
OUTPUT = Path("data/discovery/latest.json")
USER_AGENT = "Mozilla/5.0 (compatible; StockAutoResearch/1.0; +https://github.com/juhwan7/stock-autoresearch)"

QUERY_GROUPS: list[tuple[str, str]] = [
    ("market", "코스피 코스닥 증시 외국인 기관"),
    ("semiconductor_ai", "반도체 HBM AI 데이터센터 삼성전자 SK하이닉스"),
    ("robot_power_defense", "로봇 전력 원전 방산 한국 주식"),
    ("bio_battery_auto", "바이오 2차전지 자동차 한국 주식"),
    ("macro", "나스닥 미국채 금리 원달러 환율 유가"),
    ("policy_supply_chain", "관세 희토류 수출통제 공급망 반도체"),
]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _clean_text(value: str | None) -> str:
    text = unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_google_news_rss(xml_text: str, topic: str, limit: int = 10) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    rows: list[dict[str, Any]] = []
    for item in root.findall(".//item")[:limit]:
        title = _clean_text(item.findtext("title"))
        link = _clean_text(item.findtext("link"))
        published_at = _clean_text(item.findtext("pubDate"))
        source = _clean_text(item.findtext("source"))
        if not title or not link:
            continue
        rows.append(
            {
                "topic": topic,
                "title": title,
                "url": link,
                "published_at": published_at or None,
                "publisher": source or None,
                "discovery_source": "google_news_rss",
            }
        )
    return rows


def extract_naver_indices(html_text: str) -> dict[str, str | None]:
    result: dict[str, str | None] = {
        "KOSPI": None,
        "KOSDAQ": None,
        "KOSPI200": None,
    }
    for name in result:
        match = re.search(
            rf'id=["\']{name}_now["\'][^>]*>\s*([^<]+)',
            html_text,
            flags=re.IGNORECASE,
        )
        if match:
            result[name] = _clean_text(match.group(1))
    return result


def _default_fetch(url: str, timeout: int = 10) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset()
    for encoding in [charset, "utf-8", "euc-kr", "cp949"]:
        if not encoding:
            continue
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def _item_key(item: dict[str, Any]) -> str:
    return (
        str(item.get("title") or "").strip().lower()
        + "|"
        + str(item.get("url") or "").strip()
    )


def collect(
    root: Path,
    *,
    now: datetime | None = None,
    fetcher: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(KST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=KST)
    now = now.astimezone(KST)
    fetcher = fetcher or _default_fetch

    output = root / OUTPUT
    previous = _read_json(output)
    previous_keys = {
        _item_key(item)
        for item in previous.get("items", [])
        if isinstance(item, dict)
    }

    items: list[dict[str, Any]] = []
    source_status: dict[str, dict[str, Any]] = {}

    for topic, query in QUERY_GROUPS:
        params = urllib.parse.urlencode(
            {
                "q": query,
                "hl": "ko",
                "gl": "KR",
                "ceid": "KR:ko",
            }
        )
        url = "https://news.google.com/rss/search?" + params
        key = "google_news:" + topic
        try:
            xml_text = fetcher(url)
            rows = parse_google_news_rss(xml_text, topic, limit=8)
            items.extend(rows)
            source_status[key] = {"status": "ok", "count": len(rows)}
        except (
            OSError,
            TimeoutError,
            urllib.error.URLError,
            urllib.error.HTTPError,
            ValueError,
        ) as exc:
            source_status[key] = {
                "status": "error",
                "error": type(exc).__name__,
            }

    naver_url = "https://finance.naver.com/sise/"
    try:
        html_text = fetcher(naver_url)
        indices = extract_naver_indices(html_text)
        source_status["naver_finance"] = {
            "status": "ok" if any(indices.values()) else "partial",
            "indices": indices,
        }
    except (
        OSError,
        TimeoutError,
        urllib.error.URLError,
        urllib.error.HTTPError,
        ValueError,
    ) as exc:
        source_status["naver_finance"] = {
            "status": "error",
            "error": type(exc).__name__,
            "indices": {},
        }

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = _item_key(item)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    deduped = deduped[:60]

    new_items = [item for item in deduped if _item_key(item) not in previous_keys]
    topic_counts: dict[str, int] = {}
    for item in deduped:
        topic = str(item.get("topic") or "unknown")
        topic_counts[topic] = topic_counts.get(topic, 0) + 1

    ok_sources = sum(
        1
        for value in source_status.values()
        if str(value.get("status")) in {"ok", "partial"}
    )
    failed_sources = sum(
        1
        for value in source_status.values()
        if str(value.get("status")) == "error"
    )

    snapshot = {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "purpose": "6분 비AI 시장·뉴스 단서 센서. 1시간 ChatGPT 심층리서치의 탐색 힌트이며 사실 확정 엔진이 아님.",
        "source_status": source_status,
        "source_summary": {
            "ok_or_partial": ok_sources,
            "failed": failed_sources,
        },
        "naver_indices": (
            source_status.get("naver_finance", {}).get("indices") or {}
        ),
        "topic_counts": topic_counts,
        "item_count": len(deduped),
        "new_item_count": len(new_items),
        "new_items": new_items[:20],
        "items": deduped,
        "handoff_queries": [
            query for _, query in QUERY_GROUPS
        ],
        "rules": {
            "discovery_only": True,
            "confirm_material_claims_with_primary_sources": True,
            "canonical_trade_data": "Toss/KRX/broker API",
            "portal_news_role": "discovery_and_cross_check",
        },
    }
    _write_json(output, snapshot)
    return {
        "status": "ok" if ok_sources else "unavailable",
        "output": str(OUTPUT),
        "item_count": len(deduped),
        "new_item_count": len(new_items),
        "source_summary": snapshot["source_summary"],
    }
