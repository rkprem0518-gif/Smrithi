"""Builds the POST /v2/agent payload from config/agent.json + prompts/smriti_agent.md."""

from __future__ import annotations

import copy
from typing import Any

from app.scoring.types import ScoringConfig
from app.settings import Settings

# Placeholders the prompt expects in user_data ({{name}} in the prompt, per Bolna docs).
PROMPT_VARIABLES = ("language", "word_list")


def build_agent_payload(
    settings: Settings,
    template: dict[str, Any],
    prompt: str,
    cfg: ScoringConfig | None = None,
    with_keywords: bool = False,
) -> dict[str, Any]:
    agent_config = copy.deepcopy(template["agent_config"])
    task = agent_config["tasks"][0]
    task["task_config"]["call_terminate"] = int(settings.max_call_minutes) * 60
    agent_config["webhook_url"] = settings.webhook_url if settings.webhook_reachable else None
    if with_keywords and cfg is not None:
        # TODO(bolna): the docs list `transcriber.keywords` but not its format for Sarvam.
        # Off by default; enable with --with-keywords once the format is confirmed.
        words = sorted({w.hi for form in cfg.forms.values() for w in form})
        task["tools_config"]["transcriber"]["keywords"] = ",".join(words)
    missing = [v for v in PROMPT_VARIABLES if "{{" + v + "}}" not in prompt]
    if missing:
        raise ValueError(f"prompt is missing placeholders: {missing}")
    return {"agent_config": agent_config, "agent_prompts": {"task_1": {"system_prompt": prompt}}}
