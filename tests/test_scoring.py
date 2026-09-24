from autoresearch.scoring import rank_candidates, score_candidate


def test_weighted_score():
    candidate = {
        "scores": {
            "novelty": 100,
            "market_impact": 50,
            "evidence_strength": 100,
            "followup_value": 50,
            "official_source_signal": 100,
            "price_action_signal": 50,
        }
    }
    weights = {
        "novelty": 0.20,
        "market_impact": 0.20,
        "evidence_strength": 0.15,
        "followup_value": 0.15,
        "official_source_signal": 0.15,
        "price_action_signal": 0.15,
    }
    assert score_candidate(candidate, weights) == 75.0


def test_rank_candidates_descending():
    weights = {"novelty": 1.0}
    ranked = rank_candidates(
        [
            {"title": "low", "scores": {"novelty": 10}},
            {"title": "high", "scores": {"novelty": 90}},
        ],
        weights,
    )
    assert [x["title"] for x in ranked] == ["high", "low"]
