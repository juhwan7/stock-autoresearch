from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI


class JSONResponseError(RuntimeError):
    pass


def extract_json(text: str) -> dict[str, Any]:
    value = text.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        value = "\n".join(lines).strip()
        if value.startswith("json"):
            value = value[4:].lstrip()

    try:
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = value.find("{")
    end = value.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(value[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as exc:
            raise JSONResponseError(str(exc)) from exc

    raise JSONResponseError("Model did not return a JSON object")


class ResearchLLM:
    def __init__(self, model_cfg: dict[str, Any] | None = None):
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError(
                "OPENAI_API_KEY is required for live mode. Use --mode dry-run to test without a key."
            )
        self.client = OpenAI()
        self.default_cfg = model_cfg or {}

    def request_json(
        self,
        prompt: str,
        *,
        web: bool,
        model_cfg: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cfg = dict(self.default_cfg)
        if model_cfg:
            cfg.update(model_cfg)

        model = cfg.get("name", "gpt-5.6-terra")
        effort = cfg.get("reasoning_effort", "high")
        search_context = cfg.get("web_search_context", "medium")

        last_raw = ""
        last_error: Exception | None = None

        for attempt in range(2):
            current_prompt = prompt
            if attempt == 1:
                current_prompt += (
                    "\n\n이전 출력이 JSON 파싱에 실패했다. 설명이나 Markdown 없이 "
                    "유효한 JSON 객체 하나만 다시 출력하라. 이전 출력:\n" + last_raw
                )

            kwargs: dict[str, Any] = {
                "model": model,
                "input": current_prompt,
            }
            if effort:
                kwargs["reasoning"] = {"effort": effort}
            if web:
                kwargs["tools"] = [
                    {
                        "type": "web_search",
                        "search_context_size": search_context,
                    }
                ]

            response = self.client.responses.create(**kwargs)
            last_raw = response.output_text
            try:
                return extract_json(last_raw)
            except JSONResponseError as exc:
                last_error = exc

        raise JSONResponseError(
            "Could not parse model output after retry: " + str(last_error)
        )
