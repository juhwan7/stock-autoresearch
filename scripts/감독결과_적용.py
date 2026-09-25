from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "data/supervisor/latest-report.json"
STATE = ROOT / "data/supervisor/state.json"

def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/supervisor_result_apply.py <result.json>")
    src = Path(sys.argv[1])
    result = json.loads(src.read_text(encoding="utf-8"))
    required = ("batch_id", "processed_at", "notify", "summary", "actions", "changed_paths", "next_checks")
    missing = [k for k in required if k not in result]
    if missing:
        raise SystemExit("missing fields: " + ", ".join(missing))
    if result.get("notify") is not True:
        raise SystemExit("Supervisor result must have notify=true")
    observation_ids = result.get("observation_ids") or []
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["last_batch_id"] = result["batch_id"]
    state["last_processed_at"] = result["processed_at"]
    if observation_ids:
        state["last_processed_observation_id"] = observation_ids[-1]
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("applied", result["batch_id"])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
