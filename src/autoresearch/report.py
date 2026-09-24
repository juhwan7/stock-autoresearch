from __future__ import annotations

from typing import Any

from .scoring import quality_average


def _bullets(items: list[Any]) -> str:
    if not items:
        return "- 없음\n"
    return "".join("- " + str(x) + "\n" for x in items)


def render_report(
    final: dict[str, Any],
    *,
    run_id: str,
    generated_at: str,
    priority_score: float,
    mode: str,
) -> str:
    lines: list[str] = []
    lines.append("# " + str(final.get("title", "Untitled research")))
    lines.append("")
    lines.append("> 생성: " + generated_at)
    lines.append("> run_id: " + run_id)
    lines.append("> mode: " + mode)
    lines.append("> research priority: " + str(priority_score))
    lines.append("> research quality average: " + str(quality_average(final)))
    if mode == "dry-run":
        lines.append("> **DRY-RUN: 아래 내용은 합성 테스트 데이터이며 실제 시장 정보가 아닙니다.**")

    lines.extend(["", "## 3줄 요약", ""])
    lines.append(_bullets(final.get("three_line_summary", [])))

    sections = [
        ("왜 중요한가", [final.get("why_it_matters")] if final.get("why_it_matters") else []),
        ("확인된 사실", final.get("verified_facts", [])),
        ("분석", final.get("analysis", [])),
        ("반론·다른 가능성", final.get("counter_case", [])),
        ("아직 모르는 것", final.get("unknowns", [])),
        ("다음 확인사항", final.get("watch_next", [])),
    ]
    for title, items in sections:
        lines.extend(["", "## " + title, "", _bullets(items)])

    lines.extend(["", "## 타임라인", ""])
    timeline = final.get("timeline", [])
    if timeline:
        for item in timeline:
            lines.append("- " + str(item.get("date") or "날짜 미확인") + " — " + str(item.get("event", "")))
    else:
        lines.append("- 없음")

    lines.extend(["", "## 산업 연결", ""])
    industry = final.get("industry_map", [])
    if industry:
        for item in industry:
            lines.append("- **" + str(item.get("node", "")) + "**: " + str(item.get("impact_path", "")))
    else:
        lines.append("- 없음")

    lines.extend(["", "## 상장사 연결", ""])
    stocks = final.get("stock_map", [])
    if stocks:
        for item in stocks:
            name = str(item.get("company", ""))
            ticker = item.get("ticker")
            if ticker:
                name += " (" + str(ticker) + ")"
            lines.append("- **" + name + "** · " + str(item.get("link_type", "")) + ": " + str(item.get("evidence", "")))
            for caveat in item.get("caveats", []):
                lines.append("  - 주의: " + str(caveat))
    else:
        lines.append("- 근거가 충분한 종목 연결 없음")

    lines.extend(["", "## 품질 점검", ""])
    for key, value in final.get("quality_score", {}).items():
        lines.append("- " + str(key) + ": " + str(value))

    lines.extend(["", "## 출처", ""])
    sources = final.get("sources", [])
    if sources:
        for source in sources:
            label = str(source.get("title") or source.get("publisher") or source.get("id") or "source")
            url = source.get("url")
            tier = source.get("tier")
            suffix = " (Tier " + str(tier) + ")" if tier is not None else ""
            if url:
                lines.append("- [" + label + "](" + str(url) + ")" + suffix)
            else:
                lines.append("- " + label + suffix)
    else:
        lines.append("- 없음")

    lines.extend([
        "",
        "---",
        "이 문서는 자동 리서치 결과이며 매수·매도 추천이 아닙니다. 중요한 사실은 원문을 다시 확인해야 합니다.",
        "",
    ])
    return "\n".join(lines)
