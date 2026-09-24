from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
DATA = SITE / "data"
DATA.mkdir(parents=True, exist_ok=True)


def title_of(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    except OSError:
        pass
    return path.name


def recent_reports(limit: int = 20) -> list[dict]:
    files = sorted((ROOT / "reports").glob("*.md"), reverse=True)[:limit]
    repo = os.getenv("GITHUB_REPOSITORY", "juhwan7/stock-autoresearch")
    return [
        {
            "title": title_of(path),
            "file": path.name,
            "github_url": f"https://github.com/{repo}/blob/main/reports/{path.name}",
        }
        for path in files
    ]


def latest_ticks(limit: int = 30) -> list[dict]:
    folder = ROOT / "data" / "evolution" / "ticks"
    result: list[dict] = []
    for path in sorted(folder.glob("*.jsonl"), reverse=True):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            scout = item.get("scout", {})
            result.append(
                {
                    "time": item.get("timestamp_kst"),
                    "title": scout.get("title"),
                    "category": scout.get("category"),
                    "decision": scout.get("decision"),
                    "outcome": item.get("outcome"),
                    "observation": scout.get("observation"),
                    "benefit": scout.get("expected_benefit"),
                }
            )
            if len(result) >= limit:
                return result
    return result


def section_tail(path: Path, chars: int = 12000) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    return text[-chars:]


def main() -> None:
    status = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": "Stock AutoResearch",
        "heartbeat": "10분",
        "reports": recent_reports(),
        "ticks": latest_ticks(),
        "decision_memory": section_tail(ROOT / "docs" / "DECISIONS.md"),
        "ideas": section_tail(ROOT / "docs" / "IDEAS.md"),
        "help_needed": section_tail(ROOT / "docs" / "HELP_NEEDED.md"),
        "changelog": section_tail(ROOT / "docs" / "CHANGELOG_AI.md"),
    }
    (DATA / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
