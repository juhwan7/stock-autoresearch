from pathlib import Path

from autoresearch.question_engine import infer_questions, merge_question_queue


def observation():
    return {
        "observation_id": "obs-1",
        "observed_at": "2026-09-25T10:06:00+09:00",
        "market_discovery": {
            "new_dart_filings": [{"corp_name": "테스트기업", "title": "공급계약"}],
            "top_new_items": [{"topic": "robot", "title": "로봇 신규 공급 뉴스", "publisher": "테스트뉴스"}],
            "trending_terms": [{"term": "로봇", "count": 4, "publisher_count": 3}],
        },
        "public_batch_market": {
            "interval_leaders": [{"name": "테스트로봇", "interval_trading_value": 123}],
        },
        "health": {"issues": []},
    }


def test_questions_include_fact_flow_causality_and_falsification():
    rows = infer_questions(observation())
    kinds = {x["kind"] for x in rows}
    assert {"new_fact", "falsification", "flow", "causality", "news", "emerging_topic"} <= kinds


def test_question_queue_accumulates_seen_count_without_duplicates(tmp_path: Path):
    obs = observation()
    rows = infer_questions(obs)
    first = merge_question_queue(tmp_path, obs, rows)
    second_obs = dict(obs)
    second_obs["observation_id"] = "obs-2"
    second_obs["observed_at"] = "2026-09-25T10:12:00+09:00"
    second = merge_question_queue(tmp_path, second_obs, rows)

    assert len(second["questions"]) == len(first["questions"])
    assert max(x["seen_count"] for x in second["questions"]) == 2
    assert all(len(x["observation_ids"]) == 2 for x in second["questions"])
