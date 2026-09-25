from datetime import datetime, timedelta, timezone
from pathlib import Path

from autoresearch.risk_engine import KST, RiskEngine


def make_engine(tmp_path: Path) -> RiskEngine:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "risk.yaml").write_text(
        """
refresh:
  macro_minutes: 10
  provider_max_age_minutes: 15
  calendar_hours: 12
  force_evaluation_hours: 6
risk:
  veto_single_event_severity: 5
  veto_event_hours: 12
  high_event_hours: 24
  watch_event_hours: 72
  nxt_close: "20:00"
  krx_close: "15:30"
macro_thresholds:
  nasdaq_futures_pct:
    watch: -0.6
    high: -1.0
    veto: -1.8
  us10y_change_bp:
    watch: 8
    high: 15
    veto: 25
data:
  state_file: data/risk/state.json
  latest_file: data/risk/latest.json
  runtime_file: data/risk/runtime.json
  calendar_file: data/risk/calendar_live.json
  macro_file: data/macro/current.json
  provider_macro_file: data/macro/provider_current.json
  report_dir: reports/risk
""",
        encoding="utf-8",
    )
    (tmp_path / "config" / "events_2026.yaml").write_text(
        "events: []\n", encoding="utf-8"
    )
    (tmp_path / "prompts").mkdir()
    for name in (
        "risk_calendar_refresh.md",
        "macro_refresh.md",
        "risk_evaluator.md",
    ):
        (tmp_path / "prompts" / name).write_text("{}", encoding="utf-8")
    return RiskEngine(tmp_path, "dry-run")


def test_single_severity_five_event_can_veto(tmp_path):
    engine = make_engine(tmp_path)
    now = datetime(2026, 10, 14, 12, 0, tzinfo=KST)
    calendar = {
        "events": [
            {
                "id": "cpi",
                "title": "미국 CPI",
                "datetime_kst": "2026-10-14T21:30:00+09:00",
                "severity": 5,
            }
        ]
    }
    events, level, biggest = engine._event_state(now, calendar)
    assert level == "VETO"
    assert biggest["title"] == "미국 CPI"
    assert events[0]["trade_window"] == "AFTER_NXT_CLOSE"


def test_event_inside_24h_but_outside_veto_window_is_high(tmp_path):
    engine = make_engine(tmp_path)
    now = datetime(2026, 10, 14, 0, 0, tzinfo=KST)
    calendar = {
        "events": [
            {
                "id": "cpi",
                "title": "미국 CPI",
                "datetime_kst": "2026-10-14T21:30:00+09:00",
                "severity": 5,
            }
        ]
    }
    _, level, _ = engine._event_state(now, calendar)
    assert level == "HIGH"


def test_macro_stress_can_veto_without_event(tmp_path):
    engine = make_engine(tmp_path)
    level, signals = engine._macro_state(
        {
            "values": {
                "nasdaq_futures_pct": -2.0,
                "us10y_change_bp": 5,
            }
        }
    )
    assert level == "VETO"
    assert any(x["field"] == "nasdaq_futures_pct" for x in signals)


def test_semantic_hash_ignores_tiny_macro_noise_after_rounding(tmp_path):
    engine = make_engine(tmp_path)
    market = {"regime": "테스트", "coflow_groups": []}

    def payload(value):
        macro = {"values": {"nasdaq_futures_pct": value}}
        return engine._semantic_payload(
            "LOW",
            None,
            [],
            macro,
            "LOW",
            [],
            market,
        )

    assert engine._hash(payload(0.21)) == engine._hash(payload(0.24))
    assert engine._hash(payload(0.21)) != engine._hash(payload(0.36))


def test_force_evaluation_after_six_hours(tmp_path):
    engine = make_engine(tmp_path)
    now = datetime(2026, 9, 25, 18, 0, tzinfo=KST)
    recent = {"last_evaluated_at": (now - timedelta(hours=1)).isoformat()}
    old = {"last_evaluated_at": (now - timedelta(hours=7)).isoformat()}
    assert engine._force_due(now, recent) is False
    assert engine._force_due(now, old) is True


def test_risk_enrichment_preserves_max_level(tmp_path):
    engine = make_engine(tmp_path)
    path = tmp_path / "data/market/stats/종가베팅_이벤트.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "signal_date,ticker,next_date\n"
        "2026-09-25,A,\n",
        encoding="utf-8",
    )
    now = datetime(2026, 9, 25, 18, 0, tzinfo=KST)

    first = {
        "risk_level": "VETO",
        "event_risk_level": "VETO",
        "macro_risk_level": "WATCH",
        "semantic_hash": "hash-veto",
        "evaluation": {
            "risk_level": "VETO",
            "single_biggest_risk": {"title": "미국 CPI"},
        },
    }
    assert engine._enrich_close_events(now, first) == 1

    second = {
        "risk_level": "WATCH",
        "event_risk_level": "WATCH",
        "macro_risk_level": "LOW",
        "semantic_hash": "hash-watch",
        "evaluation": {
            "risk_level": "WATCH",
            "single_biggest_risk": {"title": "이벤트 해소 후"},
        },
    }
    engine._enrich_close_events(now + timedelta(hours=4), second)

    import csv
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle))

    assert row["risk_level_latest"] == "WATCH"
    assert row["overnight_max_risk_level"] == "VETO"
    assert row["overnight_risk_hash"] == "hash-watch"


def test_logic_document_change_changes_semantic_hash(tmp_path):
    engine = make_engine(tmp_path)
    engine.cfg.setdefault("dirty_state", {})["logic_files"] = [
        "prompts/risk_evaluator.md"
    ]
    market = {"regime": "테스트", "coflow_groups": []}
    macro = {"values": {}}

    before = engine._semantic_payload(
        "LOW", None, [], macro, "LOW", [], market
    )
    before_hash = engine._hash(before)

    (tmp_path / "prompts" / "risk_evaluator.md").write_text(
        "changed rule",
        encoding="utf-8",
    )
    after = engine._semantic_payload(
        "LOW", None, [], macro, "LOW", [], market
    )
    after_hash = engine._hash(after)

    assert before_hash != after_hash


def test_calendar_rejects_non_official_domain(tmp_path):
    engine = make_engine(tmp_path)
    engine.cfg.setdefault("refresh", {})["calendar_allowed_domains"] = [
        "bls.gov",
        "federalreserve.gov",
    ]
    assert engine._valid_calendar_event(
        {
            "id": "cpi",
            "title": "CPI",
            "datetime_kst": "2026-10-14T21:30:00+09:00",
            "severity": 5,
            "official_url": "https://www.bls.gov/schedule/news_release/cpi.htm",
        }
    )
    assert not engine._valid_calendar_event(
        {
            "id": "rumor",
            "title": "루머 일정",
            "datetime_kst": "2026-10-14T21:30:00+09:00",
            "severity": 5,
            "official_url": "https://example.com/calendar",
        }
    )


def test_active_veto_beats_far_future_same_severity(tmp_path):
    engine = make_engine(tmp_path)
    now = datetime(2026, 10, 14, 12, 0, tzinfo=KST)
    calendar = {
        "events": [
            {
                "id": "far",
                "title": "먼 FOMC",
                "datetime_kst": "2026-10-29T03:00:00+09:00",
                "severity": 5,
            },
            {
                "id": "near",
                "title": "오늘 CPI",
                "datetime_kst": "2026-10-14T21:30:00+09:00",
                "severity": 5,
            },
        ]
    }
    _, level, biggest = engine._event_state(now, calendar)
    assert level == "VETO"
    assert biggest["id"] == "near"


def test_sensor_evaluation_never_needs_llm(tmp_path):
    engine = make_engine(tmp_path)
    engine.mode = "sensor"
    result = engine._evaluate(
        datetime(2026, 9, 25, 10, 0, tzinfo=KST),
        {
            "risk_level": "WATCH",
            "single_biggest_event": None,
            "macro_signals": [
                {"field": "us10y_change_bp", "value": 10, "risk_level": "WATCH"}
            ],
        },
        True,
    )
    assert result["risk_level"] == "WATCH"
    assert "summary" in result
