from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any, Callable


KST = timezone(timedelta(hours=9))
OUTPUT = Path("data/discovery/latest.json")
USER_AGENT = "Mozilla/5.0 (compatible; StockAutoResearch/1.0; +https://github.com/juhwan7/stock-autoresearch)"

QUERY_GROUPS: list[tuple[str, str]] = [
    ("kr_market_broad", "한국 증시 코스피 코스닥 주도주 거래대금 급등 공시"),
    ("kr_market_flow", "한국 증시 외국인 기관 거래대금 상승률 상위"),
    ("kr_corporate_events", "한국 기업 공시 수주 계약 투자 실적 신규상장"),
    ("global_market", "미국 증시 나스닥 S&P500 미국채 금리 환율 원자재 한국 증시"),
    ("policy_geopolitics", "한국 미국 중국 일본 정책 관세 규제 공급망 지정학 증시"),
    ("emerging_trends", "한국 주식 산업 신기술 공급망 수주 테마 시장 트렌드"),
]

STOPWORDS = {
    "한국", "증시", "주식", "시장", "코스피", "코스닥", "관련", "전망", "급등", "급락",
    "상승", "하락", "오늘", "내일", "뉴스", "단독", "속보", "종목", "기업", "투자",
    "외국인", "기관", "개인", "거래", "거래대금", "주가", "정부", "미국", "중국",
    "일본", "글로벌", "국내", "올해", "내년", "확대", "감소", "증가", "발표", "공개",
}


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
        if source and title.endswith(" - " + source):
            title = title[: -(len(source) + 3)].strip()
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


def _fetch_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 10,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    value = json.loads(raw)
    return value if isinstance(value, dict) else {}


def _naver_headers() -> dict[str, str] | None:
    client_id = os.getenv("NAVER_CLIENT_ID", "").strip()
    client_secret = os.getenv("NAVER_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return None
    return {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }


def fetch_naver_news(query: str, *, display: int = 20) -> list[dict[str, Any]]:
    headers = _naver_headers()
    if headers is None:
        return []
    params = urllib.parse.urlencode(
        {"query": query, "display": min(max(display, 1), 100), "start": 1, "sort": "date"}
    )
    payload = _fetch_json(
        "https://openapi.naver.com/v1/search/news.json?" + params,
        headers=headers,
    )
    rows: list[dict[str, Any]] = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        title = _clean_text(item.get("title"))
        url = str(item.get("originallink") or item.get("link") or "").strip()
        if not title or not url:
            continue
        rows.append(
            {
                "topic": "naver_news",
                "title": title,
                "url": url,
                "published_at": _clean_text(item.get("pubDate")) or None,
                "publisher": None,
                "discovery_source": "naver_news_api",
            }
        )
    return rows


def fetch_naver_official_web_candidates(
    query: str,
    *,
    display: int = 10,
) -> list[dict[str, Any]]:
    headers = _naver_headers()
    if headers is None:
        return []
    params = urllib.parse.urlencode(
        {"query": query + " 공식 IR 뉴스룸", "display": min(max(display, 1), 100), "start": 1}
    )
    payload = _fetch_json(
        "https://openapi.naver.com/v1/search/webkr.json?" + params,
        headers=headers,
    )
    rows: list[dict[str, Any]] = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        title = _clean_text(item.get("title"))
        url = str(item.get("link") or "").strip()
        description = _clean_text(item.get("description"))
        if not title or not url:
            continue
        rows.append(
            {
                "topic": "official_web_candidate",
                "title": title,
                "url": url,
                "description": description,
                "published_at": None,
                "publisher": None,
                "discovery_source": "naver_web_api",
                "verification_required": True,
            }
        )
    return rows


def fetch_dart_filings(now: datetime, *, limit: int = 100) -> tuple[list[dict[str, Any]], str]:
    api_key = os.getenv("DART_API_KEY", "").strip()
    if not api_key:
        return [], "needs_credentials"
    day = now.astimezone(KST).strftime("%Y%m%d")
    params = urllib.parse.urlencode(
        {
            "crtfc_key": api_key,
            "bgn_de": day,
            "end_de": day,
            "page_no": 1,
            "page_count": min(max(limit, 1), 100),
        }
    )
    payload = _fetch_json("https://opendart.fss.or.kr/api/list.json?" + params)
    status = str(payload.get("status") or "")
    if status == "013":
        return [], "ok"
    if status and status != "000":
        return [], "error:" + status

    rows: list[dict[str, Any]] = []
    for item in payload.get("list") or []:
        if not isinstance(item, dict):
            continue
        rcept_no = str(item.get("rcept_no") or "").strip()
        corp_name = str(item.get("corp_name") or "").strip()
        report_nm = str(item.get("report_nm") or "").strip()
        if not rcept_no or not report_nm:
            continue
        rows.append(
            {
                "rcept_no": rcept_no,
                "corp_name": corp_name,
                "report_nm": report_nm,
                "rcept_dt": item.get("rcept_dt"),
                "corp_cls": item.get("corp_cls"),
                "flr_nm": item.get("flr_nm"),
                "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + rcept_no,
            }
        )
    return rows, "ok"


def summarize_toss_market(root: Path) -> dict[str, Any]:
    snapshot = _read_json(root / "data" / "providers" / "toss" / "latest.json")
    if not snapshot:
        return {"available": False}

    ranking = [
        item for item in snapshot.get("ranking", [])
        if isinstance(item, dict)
    ][:30]
    metadata = snapshot.get("metadata") or {}
    minute_by_ticker = snapshot.get("minute_by_ticker") or {}

    burst_rows: list[dict[str, Any]] = []
    for ticker, bars in minute_by_ticker.items():
        if not isinstance(bars, list) or not bars:
            continue
        numeric = [
            float(bar.get("amount") or 0)
            for bar in bars[-20:]
            if isinstance(bar, dict)
        ]
        if not numeric:
            continue
        baseline_values = numeric[:-1] or numeric
        ordered = sorted(baseline_values)
        baseline = ordered[len(ordered) // 2] if ordered else 0.0
        latest = numeric[-1]
        ratio = (latest / baseline) if baseline > 0 else None
        info = metadata.get(ticker) if isinstance(metadata, dict) else {}
        burst_rows.append(
            {
                "ticker": ticker,
                "name": (info or {}).get("name") if isinstance(info, dict) else None,
                "latest_minute_amount": latest,
                "median_recent_amount": baseline,
                "burst_ratio": ratio,
            }
        )
    burst_rows.sort(
        key=lambda item: (
            float(item.get("burst_ratio") or 0),
            float(item.get("latest_minute_amount") or 0),
        ),
        reverse=True,
    )

    top_ranking = []
    for item in ranking:
        ticker = str(item.get("ticker") or "")
        info = metadata.get(ticker) if isinstance(metadata, dict) else {}
        top_ranking.append(
            {
                "rank": item.get("rank"),
                "ticker": ticker,
                "name": (info or {}).get("name") if isinstance(info, dict) else None,
                "trading_value": item.get("trading_value"),
                "day_return_pct": item.get("day_return_pct"),
                "last_price": item.get("last_price"),
            }
        )

    return {
        "available": True,
        "captured_at": snapshot.get("captured_at"),
        "top_turnover": top_ranking[:20],
        "minute_burst_leaders": burst_rows[:20],
        "top10_share": snapshot.get("turnover_rank_top10_share"),
    }


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


def _title_tokens(title: str) -> list[str]:
    cleaned = re.sub(r"[^0-9A-Za-z가-힣+\-]", " ", title)
    tokens: list[str] = []
    for token in cleaned.split():
        token = token.strip("+-")
        if len(token) < 2:
            continue
        if token in STOPWORDS:
            continue
        lower = token.lower()
        if lower in {"kr", "co", "com", "net", "org", "www", "html", "http", "https"}:
            continue
        if token.isdigit() or re.fullmatch(r"20\d{2}년", token):
            continue
        tokens.append(token)
    return tokens


def _published_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(KST)


def recent_items(
    items: list[dict[str, Any]],
    now: datetime,
    *,
    hours: int = 36,
) -> list[dict[str, Any]]:
    cutoff = now.astimezone(KST) - timedelta(hours=hours)
    result: list[dict[str, Any]] = []
    for item in items:
        stamp = _published_datetime(str(item.get("published_at") or ""))
        if stamp is None or stamp >= cutoff:
            result.append(item)
    return result


def extract_trending_terms(
    items: list[dict[str, Any]],
    previous: dict[str, Any] | None = None,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    previous = previous or {}
    previous_counts = {
        str(item.get("term")): int(item.get("count") or 0)
        for item in previous.get("trending_terms", [])
        if isinstance(item, dict) and item.get("term")
    }

    counts: dict[str, int] = {}
    publishers: dict[str, set[str]] = {}
    examples: dict[str, list[str]] = {}
    for item in items:
        title = str(item.get("title") or "")
        publisher = str(item.get("publisher") or "")
        unique_tokens = set(_title_tokens(title))
        for token in unique_tokens:
            counts[token] = counts.get(token, 0) + 1
            if publisher:
                publishers.setdefault(token, set()).add(publisher)
            bucket = examples.setdefault(token, [])
            if title and title not in bucket and len(bucket) < 3:
                bucket.append(title)

    ranked: list[dict[str, Any]] = []
    for term, count in counts.items():
        if count < 2:
            continue
        publisher_count = len(publishers.get(term, set()))
        previous_count = previous_counts.get(term, 0)
        delta = count - previous_count
        score = (count * 2) + publisher_count + max(delta, 0)
        ranked.append(
            {
                "term": term,
                "count": count,
                "publisher_count": publisher_count,
                "previous_count": previous_count,
                "delta": delta,
                "score": score,
                "examples": examples.get(term, []),
            }
        )

    ranked.sort(
        key=lambda item: (
            int(item.get("score") or 0),
            int(item.get("publisher_count") or 0),
            int(item.get("count") or 0),
            str(item.get("term") or ""),
        ),
        reverse=True,
    )
    return ranked[:limit]


def build_dynamic_handoff_queries(
    trending_terms: list[dict[str, Any]],
    *,
    limit: int = 8,
) -> list[str]:
    queries = [
        "한국 증시 오늘 주도 섹터 거래대금 상위 이유",
        "코스피 코스닥 거래대금 상위 상승률 상위 공시 뉴스",
        "한국 증시 오늘 새 공시 수주 계약 정책 변화",
        "미국 증시 금리 환율 원자재 변화 한국 증시 영향",
    ]
    for item in trending_terms[:limit]:
        term = str(item.get("term") or "").strip()
        if term:
            queries.append(
                f"{term} 한국 증시 관련 기업 공시 수주 실적 거래대금 시장 반응"
            )
    return queries


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
                "q": query + " when:1d",
                "hl": "ko",
                "gl": "KR",
                "ceid": "KR:ko",
            }
        )
        url = "https://news.google.com/rss/search?" + params
        key = "google_news:" + topic
        try:
            xml_text = fetcher(url)
            rows = parse_google_news_rss(xml_text, topic, limit=12)
            rows = recent_items(rows, now, hours=36)
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

    naver_headers = _naver_headers()
    if naver_headers is None:
        source_status["naver_news_api"] = {"status": "needs_credentials"}
        source_status["naver_web_api"] = {"status": "needs_credentials"}
    else:
        naver_news_rows: list[dict[str, Any]] = []
        for query in [
            "한국 증시 주도주 거래대금",
            "한국 기업 공시 수주 계약",
            "코스피 코스닥 정책 산업",
        ]:
            try:
                naver_news_rows.extend(fetch_naver_news(query, display=20))
            except (
                OSError,
                TimeoutError,
                urllib.error.URLError,
                urllib.error.HTTPError,
                json.JSONDecodeError,
                ValueError,
            ) as exc:
                source_status["naver_news_api"] = {
                    "status": "error",
                    "error": type(exc).__name__,
                }
                break
        else:
            items.extend(naver_news_rows)
            source_status["naver_news_api"] = {
                "status": "ok",
                "count": len(naver_news_rows),
            }

    try:
        dart_rows, dart_status = fetch_dart_filings(now)
        source_status["dart"] = {"status": dart_status, "count": len(dart_rows)}
    except (
        OSError,
        TimeoutError,
        urllib.error.URLError,
        urllib.error.HTTPError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        dart_rows = []
        source_status["dart"] = {
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
    deduped = recent_items(deduped, now, hours=36)[:80]

    new_items = [item for item in deduped if _item_key(item) not in previous_keys]
    topic_counts: dict[str, int] = {}
    for item in deduped:
        topic = str(item.get("topic") or "unknown")
        topic_counts[topic] = topic_counts.get(topic, 0) + 1

    trending_terms = extract_trending_terms(deduped, previous)

    official_candidates: list[dict[str, Any]] = []
    if naver_headers is not None:
        for trend in trending_terms[:5]:
            term = str(trend.get("term") or "").strip()
            if not term:
                continue
            try:
                official_candidates.extend(
                    fetch_naver_official_web_candidates(term, display=5)
                )
            except (
                OSError,
                TimeoutError,
                urllib.error.URLError,
                urllib.error.HTTPError,
                json.JSONDecodeError,
                ValueError,
            ):
                continue
        if source_status.get("naver_web_api", {}).get("status") != "error":
            source_status["naver_web_api"] = {
                "status": "ok",
                "count": len(official_candidates),
            }

    previous_filing_ids = {
        str(item.get("rcept_no") or "")
        for item in previous.get("dart_filings", [])
        if isinstance(item, dict)
    }
    new_dart_filings = [
        item for item in dart_rows
        if str(item.get("rcept_no") or "") not in previous_filing_ids
    ]

    toss_market = summarize_toss_market(root)
    handoff_queries = build_dynamic_handoff_queries(trending_terms)

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
        "trending_terms": trending_terms,
        "dart_filings": dart_rows[:100],
        "new_dart_filings": new_dart_filings[:40],
        "official_web_candidates": official_candidates[:30],
        "toss_market": toss_market,
        "item_count": len(deduped),
        "new_item_count": len(new_items),
        "new_items": new_items[:20],
        "items": deduped,
        "handoff_queries": handoff_queries,
        "sector_selection": {
            "mode": "dynamic",
            "fixed_sector_whitelist": False,
            "rule": "현재 뉴스 반복도·출처 다양성·정량 시장 반응을 조합해 1시간 AI가 주도 섹터를 선택",
        },
        "rules": {
            "discovery_only": True,
            "confirm_material_claims_with_primary_sources": True,
            "canonical_trade_data": "Toss/KRX/broker API",
            "portal_news_role": "discovery_and_cross_check",
            "dart_role": "official_filing_primary_source",
            "official_web_candidates_role": "candidate_only_verify_domain_before_claim",
            "toss_role": "canonical_turnover_and_minute_trade_signal_when_available",
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
