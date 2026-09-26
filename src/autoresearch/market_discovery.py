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
    ("kr_market_flow", "한국 증시 외국인 기관 수급 거래대금 상승률 상위"),
    ("kr_corporate_events", "한국 기업 공시 수주 계약 투자 실적 신규상장"),
    ("kr_policy_economy", "(한국 경제정책 OR 금융정책 OR 산업정책 OR 세제 OR 규제)"),
    ("kr_diplomacy_summit", "(이재명 OR 한국 대통령) (정상회담 OR 순방 OR 국빈방문 OR 유엔 OR 고위급회담)"),
    ("kr_semiconductor_ai", "한국 반도체 HBM AI 데이터센터 삼성전자 SK하이닉스 수출"),
    ("kr_energy_power", "한국 전력 원전 가스 석유 배터리 전력망 데이터센터 에너지"),
    ("kr_bio_health", "한국 바이오 제약 임상 허가 기술수출 CDMO 의료"),
    ("kr_defense_shipbuilding", "한국 방산 조선 수주 수출 항공 우주 로봇"),
    ("global_market", "(나스닥 OR S&P500 OR 미국채 OR 달러 OR 원유 OR 금)"),
    ("global_diplomacy_summit", "(트럼프 OR 시진핑 OR 정상회담 OR 유엔총회) (관세 OR 무역 OR 제재 OR 휴전 OR 투자 OR 에너지)"),
    ("us_macro_rates", "미국 연준 금리 물가 고용 PCE CPI 국채금리 경기"),
    ("global_energy_middle_east", "이란 호르무즈 사우디 후티 중동 유가 원유 LNG 공급"),
    ("us_china_trade_ai", "미국 중국 트럼프 시진핑 관세 무역 AI 반도체 수출규제 대만"),
    ("japan_boj_fx", "일본 BOJ 금리 엔화 환율 일본증시 캐리트레이드"),
    ("europe_debt_ecb", "유럽 ECB 프랑스 독일 국채 금리 재정 인플레이션 증시"),
    ("global_ai_tech", "Meta Muse Nvidia Microsoft OpenAI AI agent semiconductor data center"),
    ("commodities_shipping_supplychain", "구리 금 원유 LNG 운임 해운 공급망 물류 원자재 가격"),
]


LOW_QUALITY_TITLE_TERMS = {
    "카지노", "토토", "바카라", "슬롯", "도박", "사설토토", "배팅사이트",
}


def is_low_quality_news_item(title: str, publisher: str | None = None) -> bool:
    """시장 뉴스 검색에 섞이는 명백한 도박/SEO 스팸을 센서 단계에서 제거한다."""
    haystack = f"{title} {publisher or ''}".lower()
    return any(term.lower() in haystack for term in LOW_QUALITY_TITLE_TERMS)


TOPIC_RELEVANCE_TERMS: dict[str, tuple[str, ...]] = {
    "kr_market_broad": ("코스피","코스닥","증시","주가","거래대금","공시","수주","계약","상장","상폐","시총"),
    "kr_market_flow": ("외국인","기관","수급","순매수","순매도","거래대금","증시","코스피","코스닥"),
    "kr_corporate_events": ("공시","수주","계약","투자","실적","상장","증자","합병","분할","생산"),
    "kr_policy_economy": ("경제","정책","규제","세제","금융","산업","수입","수출","무역","관세","예산","지원"),
    "kr_diplomacy_summit": ("정상회담","순방","국빈","유엔","회담","대통령","외교","협정","협력"),
    "kr_semiconductor_ai": ("반도체","HBM","DRAM","낸드","AI","데이터센터","삼성전자","SK하이닉스","메모리"),
    "kr_energy_power": ("전력","원전","가스","석유","배터리","전력망","에너지","발전","LNG"),
    "kr_bio_health": ("바이오","제약","임상","허가","기술수출","CDMO","신약","의료"),
    "kr_defense_shipbuilding": ("방산","조선","수주","항공","우주","로봇","군함","미사일"),
    "global_market": ("증시","주가","나스닥","S&P","다우","국채","금리","달러","환율","유가","원유","WTI","브렌트","금값","금가격","채권","선물","비트코인"),
    "global_diplomacy_summit": ("정상회담","회담","관세","무역","제재","휴전","투자","에너지","전쟁","공격","미사일","수출통제"),
    "us_macro_rates": ("연준","Fed","금리","물가","고용","PCE","CPI","국채","인플레이션","실업"),
    "global_energy_middle_east": ("이란","호르무즈","사우디","후티","중동","유가","원유","LNG","공격","휴전"),
    "us_china_trade_ai": ("미중","중국","미국","트럼프","시진핑","관세","무역","AI","반도체","수출규제","수출통제","대만"),
    "japan_boj_fx": ("일본","BOJ","엔화","환율","금리","닛케이","캐리"),
    "europe_debt_ecb": ("유럽","ECB","프랑스","독일","국채","재정","인플레이션","금리"),
    "global_ai_tech": ("AI","Nvidia","엔비디아","Microsoft","마이크로소프트","Meta","OpenAI","반도체","데이터센터","에이전트"),
    "commodities_shipping_supplychain": ("구리","금값","금가격","원유","LNG","운임","해운","공급망","물류","원자재"),
}
GENERAL_MARKET_RELEVANCE_TERMS = (
    "증시","주가","금리","국채","환율","달러","유가","원유","관세","무역","수출","공시","수주","계약",
    "반도체","AI","데이터센터","전력","원전","방산","조선","바이오","제약","정상회담","제재","휴전",
    "전쟁","공격","폭격","미사일","정전","파업","항만","공급망","인플레이션","고용","중앙은행","연준","BOJ","ECB",
    "협정","협상","투자","수입규제","수출통제","국빈","순방",
)
DYNAMIC_QUERY_STOPWORDS = {"대통령","가능성","계획","거부","7일","재개","선거","진전","없이","찾은","관련","오늘","내일"}


def is_market_relevant_news_item(title: str, topic: str) -> bool:
    text = str(title or "").strip()
    if not text:
        return False
    if topic.startswith("dynamic:"):
        term = topic.split(":", 1)[1].strip()
        if not term or term.lower() not in text.lower():
            return False
        return any(context.lower() in text.lower() for context in GENERAL_MARKET_RELEVANCE_TERMS)
    terms = TOPIC_RELEVANCE_TERMS.get(topic, GENERAL_MARKET_RELEVANCE_TERMS)
    return any(term.lower() in text.lower() for term in terms)

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
        if not title or not link or is_low_quality_news_item(title, source) or not is_market_relevant_news_item(title, topic):
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


def extract_naver_index_basic(payload: dict[str, Any]) -> str | None:
    value = payload.get("closePrice")
    if value in (None, ""):
        value = payload.get("close")
    text = _clean_text(str(value or ""))
    return text or None


def fetch_naver_indices_json() -> dict[str, str | None]:
    endpoints = {
        "KOSPI": "https://stock.naver.com/api/securityFe/api/index/KOSPI/basic",
        "KOSDAQ": "https://stock.naver.com/api/securityFe/api/index/KOSDAQ/basic",
        "KOSPI200": "https://stock.naver.com/api/securityFe/api/index/KPI200/basic",
    }
    result: dict[str, str | None] = {}
    for name, url in endpoints.items():
        try:
            result[name] = extract_naver_index_basic(_fetch_json(url))
        except (
            OSError,
            TimeoutError,
            urllib.error.URLError,
            urllib.error.HTTPError,
            json.JSONDecodeError,
            ValueError,
        ):
            result[name] = None
    return result


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


def summarize_public_batch_market(root: Path) -> dict[str, Any]:
    snapshot = _read_json(root / "data" / "providers" / "naver_batch" / "latest.json")
    if not snapshot:
        return {"available": False}
    return {
        "available": snapshot.get("status") in {"ok", "warming_or_gap"},
        "generated_at": snapshot.get("generated_at"),
        "status": snapshot.get("status"),
        "provider": snapshot.get("provider"),
        "exact_1m_bars": snapshot.get("exact_1m_bars"),
        "amount_method": snapshot.get("amount_method"),
        "elapsed_minutes_from_previous": snapshot.get("elapsed_minutes_from_previous"),
        "interval_leaders": (snapshot.get("interval_leaders") or [])[:20],
        "one_minute_samples_available": snapshot.get("one_minute_samples_available"),
        "minute_amount_exact": snapshot.get("minute_amount_exact"),
        "minute_amount_method": snapshot.get("minute_amount_method"),
        "minute_sample_ticker_count": snapshot.get("minute_sample_ticker_count"),
        "current_top50_count": snapshot.get("current_top50_count"),
        "tracked_universe_count": snapshot.get("tracked_universe_count"),
        "dropped_from_current_top50_count": snapshot.get("dropped_from_current_top50_count"),
        "tracked_outside_top50_with_samples": snapshot.get("tracked_outside_top50_with_samples"),
        "minute_samples_by_ticker": {
            str(ticker): rows[-6:]
            for ticker, rows in (snapshot.get("minute_samples_by_ticker") or {}).items()
            if isinstance(rows, list)
        },
        "limitations": snapshot.get("limitations") or [],
    }


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


def _append_discovery_archive(root: Path, snapshot: dict[str, Any]) -> None:
    """6분 센서의 커버리지/핫키워드 통계를 일별 JSONL로 장기 보존한다."""
    generated = _published_datetime(str(snapshot.get("generated_at") or ""))
    if generated is None:
        try:
            generated = datetime.fromisoformat(str(snapshot.get("generated_at") or "").replace("Z", "+00:00")).astimezone(KST)
        except (TypeError, ValueError):
            generated = datetime.now(KST)
    folder = root / "data" / "discovery" / "archive"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (generated.strftime("%Y-%m-%d") + ".jsonl")
    compact = {
        "generated_at": snapshot.get("generated_at"),
        "item_count": snapshot.get("item_count"),
        "new_item_count": snapshot.get("new_item_count"),
        "query_group_count": snapshot.get("query_group_count"),
        "source_summary": snapshot.get("source_summary"),
        "topic_counts": snapshot.get("topic_counts"),
        "dynamic_query_terms": snapshot.get("dynamic_query_terms"),
        "hot_topic_candidates": (snapshot.get("hot_topic_candidates") or [])[:12],
    }
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(compact, ensure_ascii=False, separators=(",", ":")) + "\n")

    index_path = folder / "index.json"
    index = _read_json(index_path)
    days = [x for x in (index.get("days") or []) if isinstance(x, dict) and x.get("date") != generated.strftime("%Y-%m-%d")]
    days.insert(0, {"date": generated.strftime("%Y-%m-%d"), "file": str(path.relative_to(root)), "last_generated_at": snapshot.get("generated_at")})
    _write_json(index_path, {"updated_at": snapshot.get("generated_at"), "days": days[:60]})


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
        key = "google_news:" + topic
        try:
            params = urllib.parse.urlencode(
                {
                    "q": query + " when:1d",
                    "hl": "ko",
                    "gl": "KR",
                    "ceid": "KR:ko",
                }
            )
            xml_text = fetcher("https://news.google.com/rss/search?" + params)
            rows = recent_items(
                parse_google_news_rss(xml_text, topic, limit=30),
                now,
                hours=48,
            )
            retried_without_when = False
            if not rows:
                retried_without_when = True
                fallback_params = urllib.parse.urlencode(
                    {
                        "q": query,
                        "hl": "ko",
                        "gl": "KR",
                        "ceid": "KR:ko",
                    }
                )
                fallback_xml = fetcher(
                    "https://news.google.com/rss/search?" + fallback_params
                )
                rows = recent_items(
                    parse_google_news_rss(fallback_xml, topic, limit=40),
                    now,
                    hours=72,
                )
            items.extend(rows)
            source_status[key] = {
                "status": "ok" if rows else "empty",
                "count": len(rows),
                "auto_repair": (
                    "retry_without_when_filter"
                    if retried_without_when
                    else None
                ),
            }
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


    # 직전 센서에서 새로 부상한 키워드는 다음 6분 주기의 독립 검색축으로 자동 승격한다.
    # 고정 키워드만 장기간 보는 문제를 막고, 생소한 기업·국가·인물도 반복 등장하면 따라간다.
    dynamic_terms = [
        str(item.get("term") or "").strip()
        for item in (previous.get("trending_terms") or [])
        if isinstance(item, dict)
        and str(item.get("term") or "").strip()
        and int(item.get("publisher_count") or 0) >= 2
        and str(item.get("term") or "").strip() not in DYNAMIC_QUERY_STOPWORDS
        and not re.fullmatch(r"\d+(?:일|월|년)?", str(item.get("term") or "").strip())
    ][:8]
    for term in dynamic_terms:
        key = "google_news:dynamic:" + re.sub(r"[^0-9A-Za-z가-힣_-]", "_", term)[:40]
        try:
            params = urllib.parse.urlencode(
                {"q": term + " when:1d", "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
            )
            xml_text = fetcher("https://news.google.com/rss/search?" + params)
            rows = recent_items(parse_google_news_rss(xml_text, "dynamic:" + term, limit=20), now, hours=36)
            items.extend(rows)
            source_status[key] = {"status": "ok" if rows else "empty", "count": len(rows), "term": term}
        except (OSError, TimeoutError, urllib.error.URLError, urllib.error.HTTPError, ValueError) as exc:
            source_status[key] = {"status": "error", "error": type(exc).__name__, "term": term}

    google_ok_groups = sum(
        1
        for key, value in source_status.items()
        if key.startswith("google_news:")
        and isinstance(value, dict)
        and int(value.get("count") or 0) > 0
    )
    if google_ok_groups < 3:
        broad_key = "google_news:broad_fallback"
        try:
            broad_params = urllib.parse.urlencode(
                {
                    "q": "코스피 OR 코스닥 OR 한국증시 OR 나스닥 OR 미국채 OR 환율 OR 유가",
                    "hl": "ko",
                    "gl": "KR",
                    "ceid": "KR:ko",
                }
            )
            broad_xml = fetcher(
                "https://news.google.com/rss/search?" + broad_params
            )
            broad_rows = recent_items(
                parse_google_news_rss(
                    broad_xml,
                    "broad_fallback",
                    limit=30,
                ),
                now,
                hours=72,
            )
            items.extend(broad_rows)
            source_status[broad_key] = {
                "status": "ok" if broad_rows else "empty",
                "count": len(broad_rows),
                "auto_repair": "broad_market_fallback",
            }
        except (
            OSError,
            TimeoutError,
            urllib.error.URLError,
            urllib.error.HTTPError,
            ValueError,
        ) as exc:
            source_status[broad_key] = {
                "status": "error",
                "error": type(exc).__name__,
                "auto_repair": "broad_market_fallback",
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
            "반도체 HBM AI 데이터센터",
            "원전 전력망 배터리 에너지",
            "방산 조선 로봇 우주",
            "바이오 제약 임상 기술수출",
            "미국 증시 유가 금리 환율 한국 영향",
        ]:
            try:
                naver_news_rows.extend(fetch_naver_news(query, display=50))
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

    indices = fetch_naver_indices_json()
    if any(indices.values()):
        source_status["naver_finance"] = {
            "status": "ok",
            "mode": "stock_naver_json",
            "indices": indices,
        }
    else:
        naver_url = "https://finance.naver.com/sise/"
        try:
            html_text = fetcher(naver_url)
            indices = extract_naver_indices(html_text)
            source_status["naver_finance"] = {
                "status": "ok" if any(indices.values()) else "degraded",
                "mode": "legacy_html_fallback",
                "auto_repair": "json_endpoint_failed_then_html_fallback",
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
                "mode": "all_fallbacks_failed",
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
    # 개별 source가 fallback에서 72시간 창을 사용했다면 마지막 병합 단계에서
    # 다시 36시간으로 잘라 수집 건수를 0으로 만드는 모순을 피한다.
    deduped = recent_items(deduped, now, hours=72)[:500]

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

    public_batch_market = summarize_public_batch_market(root)
    toss_market = summarize_toss_market(root)
    handoff_queries = build_dynamic_handoff_queries(trending_terms)
    hot_topic_candidates = [
        {
            **item,
            "article_velocity": max(int(item.get("delta") or 0), 0),
            "hot_score": (
                int(item.get("count") or 0) * 2
                + int(item.get("publisher_count") or 0) * 3
                + max(int(item.get("delta") or 0), 0) * 4
            ),
        }
        for item in trending_terms
        if str(item.get("term") or "").strip() not in DYNAMIC_QUERY_STOPWORDS
        and not re.fullmatch(r"\d+(?:일|월|년|건)?", str(item.get("term") or "").strip())
    ][:12]

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
    degraded_sources = sum(
        1
        for value in source_status.values()
        if str(value.get("status")) in {"empty", "degraded"}
    )

    snapshot = {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "purpose": "6분 비AI 시장·뉴스 단서 센서. 1시간 ChatGPT 심층리서치의 탐색 힌트이며 사실 확정 엔진이 아님.",
        "source_status": source_status,
        "source_summary": {
            "ok_or_partial": ok_sources,
            "failed": failed_sources,
            "degraded": degraded_sources,
        },
        "naver_indices": (
            source_status.get("naver_finance", {}).get("indices") or {}
        ),
        "topic_counts": topic_counts,
        "trending_terms": trending_terms,
        "dart_filings": dart_rows[:100],
        "new_dart_filings": new_dart_filings[:40],
        "official_web_candidates": official_candidates[:30],
        "public_batch_market": public_batch_market,
        "toss_market": toss_market,
        "item_count": len(deduped),
        "news_scan_target": 500,
        "query_group_count": len(QUERY_GROUPS),
        "new_item_count": len(new_items),
        "new_items": new_items[:20],
        "items": deduped,
        "handoff_queries": handoff_queries,
        "dynamic_query_terms": dynamic_terms,
        "hot_topic_candidates": hot_topic_candidates,
        "sector_selection": {
            "mode": "dynamic",
            "fixed_sector_whitelist": False,
            "rule": "현재 뉴스 반복도·출처 다양성·정량 시장 반응을 조합해 1시간 AI가 주도 섹터를 선택",
        },
        "rules": {
            "discovery_only": True,
            "confirm_material_claims_with_primary_sources": True,
            "canonical_trade_data": "정확 1분봉은 Toss/KRX/broker 우선. 기본 no-Pi 모드는 네이버 공개 6분 누적 거래대금 차분",
            "portal_news_role": "discovery_and_cross_check",
            "dart_role": "official_filing_primary_source",
            "official_web_candidates_role": "candidate_only_verify_domain_before_claim",
            "public_batch_role": "기본 no-Pi 센서. 6분마다 최근 6개 분 단위 표본을 받아 1분 거래대금을 근사하고, 누적 거래대금 차분으로 합계를 교차검증. minute_amount_exact=false이므로 정확 체결합계로 표현하지 않음",
            "toss_role": "선택 연결 시 정확한 체결·1분 거래대금 보강",
        },
    }
    _write_json(output, snapshot)
    _append_discovery_archive(root, snapshot)
    return {
        "status": "ok" if ok_sources else "unavailable",
        "output": str(OUTPUT),
        "item_count": len(deduped),
        "new_item_count": len(new_items),
        "source_summary": snapshot["source_summary"],
    }
