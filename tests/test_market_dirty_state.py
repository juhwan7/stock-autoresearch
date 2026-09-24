from datetime import datetime, timedelta

from autoresearch.market_intel import KST, MarketIntelEngine


def make_engine(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "market_intel.yaml").write_text(
        """
minute_analysis:
  baseline_window: 3
  burst_ratio: 2
  min_burst_amount_krw: 100
data:
  latest_file: data/market/latest.json
  stats_dir: data/market/stats
ai_dirty_state:
  enabled: true
  state_file: data/market/semantic_state.json
  force_minutes: 60
  rounding:
    index_pct: 0.2
    breadth_ratio: 0.05
    turnover_share: 0.05
    nxt_premium_pct: 0.5
""",
        encoding="utf-8",
    )
    return MarketIntelEngine(tmp_path, "live")


def state(kospi=0.31, turnover=0.51, coflow_members=3, premium=0.6):
    quantitative = {
        "status": "ok",
        "turnover": {"top10_share": turnover},
        "recent_listings": {
            "count": 4,
            "positive_burst_count": 2,
            "threshold_event_counts": {"1000000000": 7},
        },
        "coflow_groups": [
            {
                "group": "한화",
                "synchronized_burst_members": coflow_members,
                "synchronized_center": "13:42",
            }
        ],
        "burst_leaders": [
            {
                "ticker": "A",
                "return_pct": 3.1,
                "burst_count": 4,
                "amount_threshold_counts": {"1000000000": 3},
            }
        ],
    }
    source = {
        "provider": "toss",
        "market_overview": {
            "KOSPI": {"change_pct": kospi, "advance_ratio": 0.56},
            "KOSDAQ": {"change_pct": 0.12, "advance_ratio": 0.51},
        },
        "turnover_rank_top10_share": turnover,
        "postmarket": {
            "stocks": [
                {
                    "ticker": "A",
                    "krx_close_premium_pct": premium,
                    "minute_ge_10eok_count": 2,
                }
            ]
        },
    }
    return quantitative, source


def test_small_market_noise_does_not_recall_ai(tmp_path):
    engine = make_engine(tmp_path)
    now = datetime(2026, 9, 25, 14, 0, tzinfo=KST)
    q1, s1 = state()
    semantic1, hash1, dirty1, previous1 = engine._market_semantic_state(
        now, q1, s1
    )
    assert dirty1 is True
    engine._save_market_semantic_state(now, hash1, True, previous1)

    q2, s2 = state(kospi=0.32, turnover=0.52, premium=0.7)
    semantic2, hash2, dirty2, _ = engine._market_semantic_state(
        now + timedelta(minutes=10), q2, s2
    )

    assert semantic1 == semantic2
    assert hash1 == hash2
    assert dirty2 is False


def test_meaningful_coflow_change_marks_market_dirty(tmp_path):
    engine = make_engine(tmp_path)
    now = datetime(2026, 9, 25, 14, 0, tzinfo=KST)
    q1, s1 = state(coflow_members=3)
    _, hash1, _, previous1 = engine._market_semantic_state(now, q1, s1)
    engine._save_market_semantic_state(now, hash1, True, previous1)

    q2, s2 = state(coflow_members=5)
    _, hash2, dirty2, _ = engine._market_semantic_state(
        now + timedelta(minutes=10), q2, s2
    )

    assert hash2 != hash1
    assert dirty2 is True


def test_market_ai_forces_periodic_recheck(tmp_path):
    engine = make_engine(tmp_path)
    now = datetime(2026, 9, 25, 14, 0, tzinfo=KST)
    q, source = state()
    _, hash1, _, previous = engine._market_semantic_state(now, q, source)
    engine._save_market_semantic_state(now, hash1, True, previous)

    _, hash2, dirty2, _ = engine._market_semantic_state(
        now + timedelta(minutes=61), q, source
    )

    assert hash2 == hash1
    assert dirty2 is True
