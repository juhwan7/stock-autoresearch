from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def normalize_title(title: str) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]+", "", title).lower()


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "runs": [], "topics": {}}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"version": 1, "runs": [], "topics": {}}

    def recent_titles(self, limit: int = 20) -> list[str]:
        titles: list[str] = []
        for run in reversed(self.data.get("runs", [])):
            titles.extend(run.get("titles", []))
            if len(titles) >= limit:
                break
        return titles[:limit]

    def previous_for(self, title: str) -> dict[str, Any] | None:
        key = normalize_title(title)
        return self.data.get("topics", {}).get(key)

    def record_run(
        self,
        *,
        run_id: str,
        generated_at: str,
        topic_results: list[dict[str, Any]],
    ) -> None:
        titles = [x.get("topic", {}).get("title", "") for x in topic_results]
        self.data.setdefault("runs", []).append(
            {"run_id": run_id, "generated_at": generated_at, "titles": titles}
        )
        self.data["runs"] = self.data["runs"][-100:]

        topics = self.data.setdefault("topics", {})
        for item in topic_results:
            topic = item.get("topic", {})
            title = topic.get("title", "")
            if not title:
                continue
            topics[normalize_title(title)] = {
                "updated_at": generated_at,
                "topic": topic,
                "final": item.get("final", {}),
            }

        temp = self.path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp.replace(self.path)
