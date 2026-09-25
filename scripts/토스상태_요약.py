from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_INPUT = Path("data/providers/toss/latest.json")
DEFAULT_OUTPUT = Path("data/providers/toss/status.json")


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(path)


def summarize(snapshot: dict[str, Any]) -> dict[str, Any]:
    collector = snapshot.get("collector", {})
    subscriptions = collector.get("subscriptions", [])
    rejected = collector.get("rejected", [])
    regular = snapshot.get("minute_by_ticker", {})
    postmarket = snapshot.get("postmarket_by_ticker", {})
    premarket = snapshot.get("premarket_by_ticker", {})
    return {
        "summarized_at": datetime.now(timezone.utc).isoformat(),
        "available": bool(snapshot),
        "captured_at": snapshot.get("captured_at"),
        "provider": snapshot.get("provider"),
        "source_mode": snapshot.get("source_mode"),
        "minute_amount_method": snapshot.get("minute_amount_method"),
        "ranking_count": len(snapshot.get("ranking", [])),
        "ranking_fresh_today": snapshot.get("ranking_fresh_today"),
        "current_top50_count": snapshot.get("current_top50_count"),
        "tracked_universe_count": snapshot.get("tracked_universe_count"),
        "dropped_from_current_top50_count": snapshot.get("dropped_from_current_top50_count"),
        "regular_ticker_count": len(regular) if isinstance(regular, dict) else 0,
        "premarket_ticker_count": len(premarket) if isinstance(premarket, dict) else 0,
        "postmarket_ticker_count": len(postmarket)
        if isinstance(postmarket, dict)
        else 0,
        "collector": {
            "subscription_count": len(subscriptions)
            if isinstance(subscriptions, list)
            else 0,
            "rejected_count": len(rejected)
            if isinstance(rejected, list)
            else 0,
            "last_message_at": collector.get("last_message_at"),
            "last_universe_refresh": collector.get("last_universe_refresh"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Toss raw snapshot에서 Git 보관용 작은 상태 요약 생성"
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    source = Path(args.input)
    snapshot = read_json(source)
    if not snapshot:
        raise SystemExit(f"유효한 Toss snapshot을 읽을 수 없음: {source}")

    target = Path(args.output)
    write_json(target, summarize(snapshot))
    print("Toss provider status written:", target)


if __name__ == "__main__":
    main()
