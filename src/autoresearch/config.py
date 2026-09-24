from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def load_settings(root: Path) -> dict[str, Any]:
    research = load_yaml(root / "config" / "research.yaml")
    scoring = load_yaml(root / "config" / "scoring.yaml")
    sources = load_yaml(root / "config" / "sources.yaml")

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
