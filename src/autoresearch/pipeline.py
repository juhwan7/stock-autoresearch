from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import mock
from .config import load_prompt, load_settings, render_prompt
from .llm import ResearchLLM
from .memory import StateStore
from .report import render_report
from .scoring import rank_candidates


class Pipeline:
    def __init__(self, root: Path, mode: str):
        if mode not in {"dry-run", "live"}:
            raise ValueError("mode must be dry-run or live")
        self.root = root
        self.mode = mode
        self.settings = load_settings(root)
        self.research_cfg = self.settings["research"]
        self.limits = self.research_cfg.get("limits", {})
        self.output_cfg = self.research_cfg.get("output", {})
        self.state = StateStore(
            root / self.output_cfg.get("state_dir", "data/state") / "research_state.json"
        )
        self.llm = None if mode == "dry-run" else ResearchLLM(self.research_cfg["model"])

    def _prompt(self, name: str, values: dict[str, Any]) -> str:
        rendered = {
            key: value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
            for key, value in values.items()
        }
        return render_prompt(load_prompt(self.root, name), rendered)

    def _scan(self, now_utc: str) -> dict[str, Any]:
        if self.mode == "dry-run":
            return mock.scan()
        prompt = self._prompt(
            "market_scanner.md",
            {
                "NOW_UTC": now_utc,
                "ROOT_TOPIC": self.research_cfg.get("root_topic", "stocks"),
                "MARKETS": self.research_cfg.get("markets", []),
                "WINDOW_HOURS": self.research_cfg.get("window_hours", 30),
                "RECENT_TITLES": self.state.recent_titles(),
            },
        )
        return self.llm.request_json(prompt, web=True)

    def _research(
        self,
        topic: dict[str, Any],
        previous: dict[str, Any] | None,
        critic_gaps: list[str] | None = None,
    ) -> dict[str, Any]:
        if self.mode == "dry-run":
            return mock.research(topic)
        prompt = self._prompt(
            "researcher.md",
            {
                "TOPIC_JSON": topic,
                "PREVIOUS_RESEARCH": previous or {},
                "CRITIC_GAPS": critic_gaps or [],
            },
        )
        return self.llm.request_json(prompt, web=True)

    def _critic(self, research_data: dict[str, Any]) -> dict[str, Any]:
        if self.mode == "dry-run":
            return mock.critic()
        prompt = self._prompt("critic.md", {"RESEARCH_JSON": research_data})
        return self.llm.request_json(prompt, web=True)

    def _finalize(
        self,
        topic: dict[str, Any],
        research_data: dict[str, Any],
        critic_data: dict[str, Any],
    ) -> dict[str, Any]:
        if self.mode == "dry-run":
            return mock.final(topic, research_data)
        prompt = self._prompt(
            "chief_researcher.md",
            {
                "TOPIC_JSON": topic,
                "RESEARCH_JSON": research_data,
                "CRITIC_JSON": critic_data,
            },
        )
        return self.llm.request_json(prompt, web=False)

    def run(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        generated_at = now.isoformat()
        run_id = now.strftime("%Y%m%dT%H%M%SZ")

        scan = self._scan(generated_at)
        candidates = scan.get("candidates", [])[: int(self.limits.get("max_candidates", 8))]
        ranked = rank_candidates(
            candidates,
            self.settings["scoring"].get("weights", {}),
        )

        minimum = float(self.limits.get("minimum_candidate_score", 55))
        max_topics = int(self.limits.get("max_topics", 1))
        selected = [x for x in ranked if x.get("priority_score", 0) >= minimum][:max_topics]

        topic_results: list[dict[str, Any]] = []
        reports_dir = self.root / self.output_cfg.get("reports_dir", "reports")
        reports_dir.mkdir(parents=True, exist_ok=True)

        for index, topic in enumerate(selected, start=1):
            previous = self.state.previous_for(str(topic.get("title", "")))
            research_data = self._research(topic, previous)
            critic_data = self._critic(research_data)

            max_loops = int(self.limits.get("max_research_loops", 1))
            loop = 0
            while critic_data.get("verdict") == "needs_more_research" and loop < max_loops:
                gaps = critic_data.get("additional_questions", [])
                research_data = self._research(topic, previous, gaps)
                critic_data = self._critic(research_data)
                loop += 1

            final = self._finalize(topic, research_data, critic_data)
            report_name = run_id + "-" + str(index).zfill(2) + ".md"
            report_path = reports_dir / report_name
            report_path.write_text(
                render_report(
                    final,
                    run_id=run_id,
                    generated_at=generated_at,
                    priority_score=float(topic.get("priority_score", 0)),
                    mode=self.mode,
                ),
                encoding="utf-8",
            )
            topic_results.append(
                {
                    "topic": topic,
                    "research": research_data,
                    "critic": critic_data,
                    "final": final,
                    "report": str(report_path.relative_to(self.root)),
                    "research_loops": loop,
                }
            )

        run_data = {
            "run_id": run_id,
            "generated_at": generated_at,
            "mode": self.mode,
            "scan": scan,
            "ranked_candidates": ranked,
            "selected_count": len(selected),
            "topics": topic_results,
        }

        runs_dir = self.root / self.output_cfg.get("runs_dir", "data/runs")
        runs_dir.mkdir(parents=True, exist_ok=True)
        run_path = runs_dir / (run_id + ".json")
        run_path.write_text(
            json.dumps(run_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self.state.record_run(
            run_id=run_id,
            generated_at=generated_at,
            topic_results=topic_results,
        )

        return {
            "run_id": run_id,
            "mode": self.mode,
            "candidates": len(ranked),
            "selected": len(selected),
            "reports": [x["report"] for x in topic_results],
            "run_file": str(run_path.relative_to(self.root)),
        }
