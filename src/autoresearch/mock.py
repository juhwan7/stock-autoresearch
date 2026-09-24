from __future__ import annotations

from typing import Any


def scan() -> dict[str, Any]:
    return {
        "candidates": [
            {
                "title": "[DRY-RUN] 반도체 공급망의 새로운 공식 공시 변화",
                "why_now": "전체 파이프라인 검증용 합성 이벤트이며 실제 시장 사실이 아니다.",
                "event_date": None,
                "markets": ["KRX", "NASDAQ"],
                "sectors": ["반도체"],
                "companies": [],
                "scores": {
                    "novelty": 80,
                    "market_impact": 75,
                    "evidence_strength": 90,
                    "followup_value": 80,
                    "official_source_signal": 90,
                    "price_action_signal": 50,
                },
                "source_urls": [],
            }
        ]
    }


def research(topic: dict[str, Any]) -> dict[str, Any]:
    return {
        "topic": topic["title"],
        "thesis": "DRY-RUN용 합성 연구 결과. 실제 투자 판단에 사용하면 안 된다.",
        "questions": ["공식 근거가 있는가?", "산업 연결이 실제 사업과 연결되는가?"],
        "claims": [
            {
                "claim": "이 문장은 파이프라인 검증을 위한 합성 데이터다.",
                "status": "verified_fact",
                "confidence": "high",
                "source_ids": ["M1"],
            }
        ],
        "numbers": [],
        "sources": [
            {
                "id": "M1",
                "title": "Synthetic dry-run source",
                "publisher": "stock-autoresearch",
                "url": None,
                "published_at": None,
                "tier": 0,
                "primary": True,
            }
        ],
        "counterevidence": ["실제 시장 데이터가 아니므로 시장 결론을 낼 수 없다."],
        "unknowns": ["모든 실제 시장 사실"],
        "industry_map": [],
        "stock_map": [],
    }


def critic() -> dict[str, Any]:
    return {
        "verdict": "pass",
        "material_problems": [],
        "counterevidence": [],
        "additional_questions": [],
        "claims_to_downgrade": [],
        "claims_supported": ["합성 데이터임이 명시되어 있다."],
    }


def final(topic: dict[str, Any], research_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": topic["title"],
        "three_line_summary": [
            "이 보고서는 DRY-RUN 파이프라인 검증용이다.",
            "실제 시장 사실을 포함하지 않는다.",
            "live 모드에서는 웹 검색과 검증 루프가 실행된다.",
        ],
        "why_it_matters": "코드와 저장 구조가 API 키 없이 끝까지 작동하는지 확인한다.",
        "timeline": [],
        "verified_facts": ["현재 결과는 합성 dry-run 데이터다."],
        "analysis": ["실전 연구 결과가 아니다."],
        "counter_case": ["실제 데이터가 없으므로 시장 해석은 불가능하다."],
        "unknowns": ["실제 시장 정보 전체"],
        "industry_map": [],
        "stock_map": [],
        "watch_next": ["OPENAI_API_KEY를 등록한 뒤 live 모드를 실행한다."],
        "sources": research_data.get("sources", []),
        "quality_score": {
            "source_quality": 100,
            "cross_checking": 100,
            "uncertainty_handling": 100,
            "counterevidence": 100,
            "numerical_verification": 100,
            "stock_link_evidence": 100,
        },
    }
