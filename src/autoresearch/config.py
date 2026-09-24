from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


LEGACY_CONFIG_NAMES = {
    "리서치.yaml": "research.yaml",
    "점수기준.yaml": "scoring.yaml",
    "출처.yaml": "sources.yaml",
    "자기진화.yaml": "evolution.yaml",
    "상태감시.yaml": "health.yaml",
    "시장분석.yaml": "market_intel.yaml",
    "회귀탐지.yaml": "regression.yaml",
    "리스크.yaml": "risk.yaml",
    "주요일정_2026.yaml": "events_2026.yaml",
}


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists() and path.parent.name == "config":
        legacy_name = LEGACY_CONFIG_NAMES.get(path.name)
        legacy_path = path.parent / legacy_name if legacy_name else None
        if legacy_path is not None and legacy_path.exists():
            path = legacy_path
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def load_settings(root: Path) -> dict[str, Any]:
    research = load_yaml(root / "config" / "리서치.yaml")
    scoring = load_yaml(root / "config" / "점수기준.yaml")
    sources = load_yaml(root / "config" / "출처.yaml")

    research.setdefault("model", {})
    research["model"]["name"] = os.getenv(
        "OPENAI_MODEL", research["model"].get("name", "gpt-5.6-terra")
    )
    research["model"]["reasoning_effort"] = os.getenv(
        "AUTORESEARCH_REASONING",
        research["model"].get("reasoning_effort", "high"),
    )

    return {
        "research": research,
        "scoring": scoring,
        "sources": sources,
    }


def render_prompt(template: str, values: dict[str, str]) -> str:
    out = template
    for key, value in values.items():
        out = out.replace("<<" + key + ">>", value)
    return out


def load_prompt(root: Path, name: str) -> str:
    return (root / "prompts" / name).read_text(encoding="utf-8")
