import json
from datetime import datetime as real_datetime

import autoresearch.market_intel as market_intel
from autoresearch.market_intel import KST, MarketIntelEngine


def make_engine(tmp_path, mode):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "market_intel.yaml").write_text(
        """
minute_analysis:
  baseline_window: 3
  burst_ratio: 2
  min_burst_amount_krw: 100
  close_watch_start: "14:30"
  continuous_end: "15:20"
data:
  snapshot_dir: data/market/snapshots
  stats_dir: data/market/stats
  latest_file: data/market/latest.json
  runtime_file: data/market/runtime.json
  dry_run_file: data/market/dry_run_latest.json
statistics:
  min_sample_size: 20
pullback_research:
  enabled: false
  cohort_version: "v1"
models: {}
""",
        encoding="utf-8",
    )
    return MarketIntelEngine(tmp_path, mode)


class AfterCloseDateTime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 9, 25, 16, 0, 0, tzinfo=KST)
        return value if tz is None else value.astimezone(tz)


def test_live_after_krx_close_without_toss_preserves_last_valid_market(tmp_path, monkeypatch):
    engine = make_engine(tmp_path, "live")
    latest = tmp_path / "data/market/latest.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    original = {"generated_at": "2026-09-25T15:20:00+09:00", "quantitative": {"status": "ok"}}
    latest.write_text(json.dumps(original), encoding="utf-8")

    monkeypatch.setattr(market_intel, "datetime", AfterCloseDateTime)
    monkeypatch.setattr(
        engine,
        "_run_pullback_research",
        lambda now: {"status": "not_due", "created": 0, "completed": 0},
    )

    result = engine.run()

    assert result["status"] == "toss_snapshot_unavailable"
    assert json.loads(latest.read_text(encoding="utf-8")) == original

    runtime = json.loads(
        (tmp_path / "data/market/runtime.json").read_text(encoding="utf-8")
    )
    assert runtime["source_status"] == "toss_snapshot_unavailable"
    assert runtime["last_valid_market_file"] == "data/market/latest.json"


def test_dry_run_never_overwrites_live_latest(tmp_path):
    engine = make_engine(tmp_path, "dry-run")
    latest = tmp_path / "data/market/latest.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    original = {"live": True}
    latest.write_text(json.dumps(original), encoding="utf-8")

    result = engine.run()

    assert json.loads(latest.read_text(encoding="utf-8")) == original
    assert result["latest"] == "data/market/dry_run_latest.json"
    dry = json.loads(
        (tmp_path / "data/market/dry_run_latest.json").read_text(encoding="utf-8")
    )
    assert dry["mode"] == "dry-run"
