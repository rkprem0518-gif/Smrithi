"""Builds the POST /v2/agent payload from config/agent.json + the prompt for each kind of agent.

kind="memory"  (default) the memory check: prompts/smriti_agent.md, one or more languages
kind="checkin" the weekly check-in: prompts/checkin_agent.md, always multilingual
kind="family"  the call to the son/daughter: prompts/family_agent.md, always multilingual
"""

from __future__ import annotations

import copy
from typing import Any

from app.scoring.types import ScoringConfig
from app.settings import Settings

# Placeholders the memory-check prompt expects in user_data ({{name}} in the prompt, per Bolna docs).
PROMPT_VARIABLES = ("language", "word_list_hi", "word_list_kn", "word_list_en")
LANGUAGES = ("hi", "kn", "en")
KINDS = ("memory", "checkin", "family")


def _multilingual_config(
    welcome_messages: dict[str, str], default_language: str, switch_trigger: str, base_synth: dict[str, Any]
) -> dict[str, Any]:
    """tools_config.multilingual_config: one agent speaking Hindi, Kannada and English.

    Shape per bolna.ai/docs/customizations/multilingual-config-reference: each language overrides
    the base transcriber language and synthesizer, and has its own welcome message.
    """
    languages = {}
    for lang in LANGUAGES:
        synth = copy.deepcopy(base_synth)
        synth["provider_config"]["language"] = lang
        languages[lang] = {
            "transcriber": {"language": lang},
            "synthesizer": {"provider": synth["provider"], "provider_config": synth["provider_config"]},
            "welcome_message": welcome_messages[lang],
        }
    return {
        "enabled": True,
        "active_language": default_language,
        "language_switch_trigger": switch_trigger,
        "languages": languages,
    }


def build_agent_payload(
    settings: Settings,
    template: dict[str, Any],
    prompt: str,
    cfg: ScoringConfig | None = None,
    with_keywords: bool = False,
    language: str = "hi",
    multilingual: bool = False,
    kind: str = "memory",
) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"unknown agent kind {kind!r}")
    if kind != "memory":
        return _build_kind_payload(settings, template, prompt, kind)
    agent_config = copy.deepcopy(template["agent_config"])
    task = agent_config["tasks"][0]
    variant = None if multilingual else template.get("language_variants", {}).get(language)
    if multilingual:
        tools = task["tools_config"]
        ml = template["multilingual"]
        tools["multilingual_config"] = _multilingual_config(
            ml["welcome_messages"], ml["default_language"], ml["language_switch_trigger"], tools["synthesizer"]
        )
        agent_config["agent_welcome_message"] = ml["welcome_messages"][ml["default_language"]]
        # The call starts in English, so the "can you hear me" check is a plain "Hello?".
        task["task_config"]["check_user_online_message"] = ml["check_user_online_message"]
    if variant:
        # TODO(bolna): confirm Sarvam saaras:v4 + bulbul:v3 voice "suhani" with language "kn".
        agent_config["agent_name"] += variant["agent_name_suffix"]
        agent_config["agent_welcome_message"] = variant["agent_welcome_message"]
        task["tools_config"]["transcriber"]["language"] = variant["transcriber_language"]
        task["tools_config"]["synthesizer"]["provider_config"]["language"] = variant["synthesizer_language"]
        task["task_config"]["call_hangup_message"] = variant["call_hangup_message"]
        # Bolna's default "are you still there" prompt is English; say it in the call's language.
        task["task_config"]["check_user_online_message"] = variant["check_user_online_message"]
    task["task_config"]["call_terminate"] = int(settings.max_call_minutes) * 60
    _webhook(agent_config, settings)
    if with_keywords and cfg is not None:
        # TODO(bolna): the docs list `transcriber.keywords` but not its format for Sarvam.
        # Off by default; enable with --with-keywords once the format is confirmed.
        words = sorted({w.hi for form in cfg.forms.values() for w in form})
        task["tools_config"]["transcriber"]["keywords"] = ",".join(words)
    _check_placeholders(prompt, PROMPT_VARIABLES)
    return {"agent_config": agent_config, "agent_prompts": {"task_1": {"system_prompt": prompt}}}


def _build_kind_payload(settings: Settings, template: dict[str, Any], prompt: str, kind: str) -> dict[str, Any]:
    spec = template["kinds"][kind]
    agent_config = copy.deepcopy(template["agent_config"])
    task = agent_config["tasks"][0]
    tools = task["tools_config"]
    switch = template["multilingual"]["language_switch_trigger"]
    tools["multilingual_config"] = _multilingual_config(
        spec["welcome_messages"], spec["default_language"], switch, tools["synthesizer"]
    )
    agent_config["agent_name"] = spec["agent_name"]
    agent_config["agent_welcome_message"] = spec["welcome_messages"][spec["default_language"]]
    tc = task["task_config"]
    tc["check_user_online_message"] = spec["check_user_online_message"]
    tc["call_cancellation_prompt"] = spec["call_cancellation_prompt"]
    tc["hangup_after_silence"] = spec["hangup_after_silence"]
    tc["call_terminate"] = int(spec["call_terminate_seconds"])
    tc["call_hangup_message"] = "Take care. Goodbye."
    _webhook(agent_config, settings)
    _check_placeholders(prompt, tuple(spec["variables"]))
    return {"agent_config": agent_config, "agent_prompts": {"task_1": {"system_prompt": prompt}}}


def _webhook(agent_config: dict[str, Any], settings: Settings) -> None:
    if settings.webhook_reachable:
        agent_config["webhook_url"] = settings.webhook_url
    else:
        # The docs type webhook_url as a string; omit it rather than sending null (poller is used).
        agent_config.pop("webhook_url", None)


def _check_placeholders(prompt: str, variables: tuple[str, ...]) -> None:
    missing = [v for v in variables if "{{" + v + "}}" not in prompt]
    if missing:
        raise ValueError(f"prompt is missing placeholders: {missing}")
