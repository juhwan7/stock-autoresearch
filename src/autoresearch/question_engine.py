from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _qid(kind: str, subject: str, question: str) -> str:
    raw = "|".join((kind, subject, question))
    return "q-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _question(kind: str, subject: str, text: str, *, priority: int, evidence: list[str], parent: str | None = None) -> dict[str, Any]:
    return {
        "question_id": _qid(kind, subject, text),
        "kind": kind,
        "subject": subject,
        "question": text,
        "priority": max(1, min(5, priority)),
        "evidence": evidence[:8],
        "parent_question_id": parent,
        "status": "open",
    }


def infer_questions(observation: dict[str, Any]) -> list[dict[str, Any]]:
    """6분 관측만으로 다음 1시간 AI가 조사할 질문 후보를 만든다.

    이 단계는 답을 만들거나 원인을 확정하지 않는다. 관측된 변화에서 검증 가능한
    질문과 반증 질문을 생성하는 no-AI 추론 계층이다.
    """
    out: list[dict[str, Any]] = []
    discovery = observation.get("market_discovery") or {}
    market = observation.get("public_batch_market") or {}

    filings = discovery.get("new_dart_filings") or []
    for item in filings[:8]:
        if not isinstance(item, dict):
            continue
        subject = str(item.get("corp_name") or item.get("company") or item.get("title") or "DART 공시")
        evidence = [str(item.get("title") or item.get("report_nm") or "신규 DART 공시")]
        q = _question("new_fact", subject, f"{subject}의 새 공시는 기존 시장 기대와 비교해 무엇이 실제로 달라졌고 실적·수주·생산·정책 영향으로 연결되는가?", priority=5, evidence=evidence)
        out.append(q)
        out.append(_question("falsification", subject, f"{subject} 공시가 주가 재료로 해석되지 않을 수 있는 반대 근거·조건은 무엇인가?", priority=4, evidence=evidence, parent=q["question_id"]))

    leaders = market.get("interval_leaders") or []
    for row in leaders[:12]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("stock_name") or row.get("ticker") or row.get("code") or "종목")
        amount = row.get("interval_trading_value")
        evidence = [f"최근 6분 거래대금 상위: {name}"]
        if amount is not None:
            evidence.append(f"6분 거래대금={amount}")
        q = _question("flow", name, f"{name}의 최근 6분 자금 유입은 단독 종목 움직임인가, 같은 사업·테마·공급망 종목으로 동시에 확산되는가?", priority=4, evidence=evidence)
        out.append(q)
        out.append(_question("causality", name, f"{name}의 수급 변화가 뉴스·공시보다 먼저 시작됐는가, 뒤따라 반응했는가? 시간 순서를 재구성하라.", priority=4, evidence=evidence, parent=q["question_id"]))

    new_items = discovery.get("top_new_items") or []
    for item in new_items[:8]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        subject = str(item.get("topic") or title[:50])
        evidence = [title, str(item.get("publisher") or "")]
        q = _question("news", subject, f"'{title}'은 새로운 사실인가, 기존 기사·발언의 재인용인가? 최초 출처와 1차 자료는 무엇인가?", priority=3, evidence=evidence)
        out.append(q)

    terms = discovery.get("trending_terms") or []
    for item in terms[:8]:
        if not isinstance(item, dict):
            continue
        term = str(item.get("term") or "").strip()
        if len(term) < 2:
            continue
        count = int(item.get("count") or 0)
        publishers = int(item.get("publisher_count") or 0)
        if count < 2:
            continue
        evidence = [f"반복 키워드={term}", f"기사={count}, 매체={publishers}"]
        out.append(_question("emerging_topic", term, f"'{term}' 언급 증가는 실제 새 정보의 확산인가 단순 기사 복제인가, 그리고 실제 거래대금 반응이 동반되는가?", priority=3 if publishers >= 2 else 2, evidence=evidence))

    health = observation.get("health") or {}
    for issue in (health.get("issues") or [])[:6]:
        if not isinstance(issue, dict):
            continue
        severity = str(issue.get("severity") or "")
        if severity not in {"WARN", "CRITICAL"}:
            continue
        subject = str(issue.get("component") or "system")
        msg = str(issue.get("message") or issue.get("code") or "")
        out.append(_question("system", subject, f"{subject}의 '{msg}' 문제가 반복되는 구조적 원인인가 일시적 센서 공백인가? 다음 관측에서 무엇으로 구분할 수 있는가?", priority=5 if severity == "CRITICAL" else 3, evidence=[msg]))

    # 같은 관측에서 동일 질문은 한 번만 보존한다.
    dedup: dict[str, dict[str, Any]] = {}
    for item in out:
        dedup[item["question_id"]] = item
    return sorted(dedup.values(), key=lambda x: (-int(x["priority"]), x["question_id"]))


def merge_question_queue(root: Path, observation: dict[str, Any], questions: list[dict[str, Any]]) -> dict[str, Any]:
    path = root / "data" / "supervisor" / "question_queue.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {"schema_version": 1, "questions": []}

    existing = {str(x.get("question_id")): x for x in payload.get("questions", []) if isinstance(x, dict)}
    observed_at = str(observation.get("observed_at") or datetime.now().isoformat())
    obs_id = observation.get("observation_id")

    for item in questions:
        qid = item["question_id"]
        if qid in existing:
            row = existing[qid]
            row["last_seen_at"] = observed_at
            row["seen_count"] = int(row.get("seen_count") or 1) + 1
            ids = list(row.get("observation_ids") or [])
            if obs_id and obs_id not in ids:
                ids.append(obs_id)
            row["observation_ids"] = ids[-20:]
            row["priority"] = max(int(row.get("priority") or 1), int(item["priority"]))
        else:
            row = dict(item)
            row["first_seen_at"] = observed_at
            row["last_seen_at"] = observed_at
            row["seen_count"] = 1
            row["observation_ids"] = [obs_id] if obs_id else []
            existing[qid] = row

    rows = sorted(existing.values(), key=lambda x: (-int(x.get("priority") or 1), -int(x.get("seen_count") or 1), str(x.get("last_seen_at") or "")))
    # 열린 질문은 충분히 보존하되 저장소가 무한히 커지지 않게 상한을 둔다.
    rows = rows[:500]
    output = {"schema_version": 1, "updated_at": observed_at, "open_count": sum(1 for x in rows if x.get("status") == "open"), "questions": rows}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output
