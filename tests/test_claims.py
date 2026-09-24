import json

from autoresearch.claims import append_claim_records, build_claim_records, claim_id


def sample_result():
    return {
        "topic": {"title": "테스트 주제"},
        "research": {
            "claims": [
                {
                    "claim": "공식 계약 금액은 100억원이다.",
                    "status": "verified_fact",
                    "confidence": "high",
                    "source_ids": ["S1", "MISSING"],
                }
            ],
            "sources": [
                {
                    "id": "S1",
                    "title": "공식 공시",
                    "publisher": "DART",
                    "url": "https://dart.fss.or.kr/example",
                    "published_at": "2026-09-25",
                    "tier": 1,
                    "primary": True,
                }
            ],
        },
        "critic": {
            "verdict": "pass",
            "claims_supported": ["공식 계약 금액은 100억원이다."],
            "claims_to_downgrade": [],
        },
    }


def test_claim_record_keeps_source_links_and_missing_ids():
    item = sample_result()
    records = build_claim_records(
        run_id="run-1",
        generated_at="2026-09-25T00:00:00+00:00",
        mode="live",
        topic=item["topic"],
        research=item["research"],
        critic=item["critic"],
    )

    assert len(records) == 1
    row = records[0]
    assert row["claim_id"] == claim_id("공식 계약 금액은 100억원이다.")
    assert row["status"] == "verified_fact"
    assert row["critic_disposition"] == "supported"
    assert row["sources"][0]["id"] == "S1"
    assert row["missing_source_ids"] == ["MISSING"]


def test_claim_ledger_is_append_only_and_idempotent_per_run(tmp_path):
    result = sample_result()
    first = append_claim_records(
        tmp_path,
        run_id="run-1",
        generated_at="2026-09-25T00:00:00+00:00",
        mode="live",
        topic_results=[result],
    )
    second = append_claim_records(
        tmp_path,
        run_id="run-1",
        generated_at="2026-09-25T00:00:00+00:00",
        mode="live",
        topic_results=[result],
    )

    assert first["appended"] == 1
    assert second["appended"] == 0
    path = tmp_path / first["path"]
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["run_id"] == "run-1"
